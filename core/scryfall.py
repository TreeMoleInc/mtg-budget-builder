# core/scryfall.py — All Scryfall API calls with rate limiting

import time
import threading
import requests
from requests.exceptions import RequestException

# ---------------------------------------------------------------------------
# Rate limiting — 150ms minimum between ALL requests (conservative, avoids 429)
# ---------------------------------------------------------------------------
_last_request_time: float = 0.0
_MIN_DELAY = 0.15  # seconds

# _backoff_until: set when a 429 is received so the UI can show a countdown.
# Does not affect request scheduling — the sleep in _get_with_retry handles that.
_backoff_until: float = 0.0

# ---------------------------------------------------------------------------
# Session cache — avoids re-fetching printings for the same card within a session
# ---------------------------------------------------------------------------
_printing_cache: dict[str, list[dict]] = {}
_cache_lock = threading.Lock()


def get_backoff_remaining() -> float:
    """Return seconds remaining in the current 429 backoff, or 0.0 if not backing off."""
    return max(0.0, _backoff_until - time.monotonic())


def _rate_limited_get(url: str, params: dict | None = None) -> requests.Response | None:
    """Perform a GET request, enforcing the minimum delay between all requests."""
    global _last_request_time
    elapsed = time.monotonic() - _last_request_time
    if elapsed < _MIN_DELAY:
        time.sleep(_MIN_DELAY - elapsed)
    try:
        return requests.get(url, params=params, timeout=10)
    except RequestException:
        return None
    finally:
        _last_request_time = time.monotonic()


def _rate_limited_post(url: str, json_body: dict) -> requests.Response | None:
    """Perform a POST request with the same rate limiting as GET."""
    global _last_request_time
    elapsed = time.monotonic() - _last_request_time
    if elapsed < _MIN_DELAY:
        time.sleep(_MIN_DELAY - elapsed)
    try:
        return requests.post(url, json=json_body, timeout=10)
    except RequestException:
        return None
    finally:
        _last_request_time = time.monotonic()


def _get_with_retry(url: str, params: dict | None = None, max_retries: int = 4) -> requests.Response | None:
    """Rate-limited GET with automatic 429 backoff and transient-error retry."""
    global _backoff_until
    for attempt in range(max_retries):
        resp = _rate_limited_get(url, params)
        if resp is None:
            if attempt < max_retries - 1:
                time.sleep(0.5 * (attempt + 1))
            continue
        if resp.status_code == 429:
            try:
                wait = float(resp.headers.get("Retry-After", 2)) + 0.5
            except (ValueError, TypeError):
                wait = 2.5
            _backoff_until = time.monotonic() + wait
            time.sleep(wait)
            continue
        if resp.status_code >= 500:
            if attempt < max_retries - 1:
                time.sleep(1.0)
            continue
        return resp
    return None


def _post_with_retry(url: str, json_body: dict, max_retries: int = 3) -> requests.Response | None:
    """Rate-limited POST with the same 429 backoff and retry logic as GET."""
    global _backoff_until
    for attempt in range(max_retries):
        resp = _rate_limited_post(url, json_body)
        if resp is None:
            if attempt < max_retries - 1:
                time.sleep(0.5 * (attempt + 1))
            continue
        if resp.status_code == 429:
            try:
                wait = float(resp.headers.get("Retry-After", 2)) + 0.5
            except (ValueError, TypeError):
                wait = 2.5
            _backoff_until = time.monotonic() + wait
            time.sleep(wait)
            continue
        if resp.status_code >= 500:
            if attempt < max_retries - 1:
                time.sleep(1.0)
            continue
        return resp
    return None


# ---------------------------------------------------------------------------
# Public API functions
# ---------------------------------------------------------------------------

def resolve_card(card_name: str) -> tuple[dict | None, str | None]:
    """
    Resolve a card name via Scryfall fuzzy search.

    Returns:
        (card_dict, None)          — found
        (None, "not_found")        — Scryfall doesn't recognise the name
        (None, "network_error")    — request failed after retries
    """
    resp = _get_with_retry("https://api.scryfall.com/cards/named", {"fuzzy": card_name})
    if resp is None:
        return None, "network_error"
    if resp.status_code == 200:
        return resp.json(), None
    return None, "not_found"


def batch_resolve_cards(names: list[str]) -> tuple[dict[str, dict], list[str]]:
    """
    Resolve up to 75 card names in a single POST to /cards/collection.
    Uses exact name matching; unmatched names must be handled by the caller (fuzzy fallback).

    Returns:
        (found_dict, not_found_names)
        found_dict:      maps each input name (lowercased) -> card_data dict
        not_found_names: list of input names Scryfall could not match exactly
    """
    if not names:
        return {}, []

    body = {"identifiers": [{"name": n} for n in names[:75]]}
    resp = _post_with_retry("https://api.scryfall.com/cards/collection", body)

    if resp is None or resp.status_code != 200:
        return {}, list(names[:75])

    data = resp.json()
    found_cards = data.get("data", [])
    not_found_raw = data.get("not_found", [])

    found_dict: dict[str, dict] = {}
    for card in found_cards:
        canonical = card.get("name", "")
        for n in names[:75]:
            if n.lower() == canonical.lower() or canonical.lower().startswith(n.lower()):
                found_dict[n.lower()] = card
                break
        else:
            found_dict[canonical.lower()] = card

    not_found_names = [item.get("name", "") for item in not_found_raw]
    return found_dict, not_found_names


def get_all_printings(prints_search_uri: str) -> list[dict]:
    """
    Fetch ALL printings by following prints_search_uri and paginating
    via has_more / next_page until done.
    Results are cached for the session so repeat searches are instant.
    """
    with _cache_lock:
        if prints_search_uri in _printing_cache:
            return _printing_cache[prints_search_uri]

    cards: list[dict] = []
    url: str | None = prints_search_uri

    while url:
        resp = _get_with_retry(url)
        if resp is None or resp.status_code != 200:
            break
        data = resp.json()
        cards.extend(data.get("data", []))
        url = data.get("next_page") if data.get("has_more") else None

    with _cache_lock:
        _printing_cache[prints_search_uri] = cards

    return cards


def find_cheapest_from_card(card_data: dict, card_name: str) -> tuple[dict | None, str | None]:
    """
    Find the cheapest printing given a pre-resolved card dict.
    Skips the name-resolution step — use when card_data came from batch_resolve_cards.
    """
    prints_search_uri = card_data.get("prints_search_uri")
    if not prints_search_uri:
        return None, "not_found"

    canonical_name = card_data.get("name", card_name)
    printings = get_all_printings(prints_search_uri)
    if not printings:
        return None, "network_error"

    return _pick_cheapest(printings, canonical_name)


def find_cheapest_version(card_name: str) -> tuple[dict | None, str | None]:
    """
    High-level function to find the cheapest physical printing of a card.
    Resolves the name then fetches all printings.
    """
    card, error = resolve_card(card_name)
    if card is None:
        return None, error
    return find_cheapest_from_card(card, card_name)


def _pick_cheapest(printings: list[dict], canonical_name: str) -> tuple[dict | None, str | None]:
    best_price: float | None = None
    best_result: dict | None = None

    for printing in printings:
        if printing.get("digital", False):
            continue
        if printing.get("lang", "en") != "en":
            continue
        if printing.get("border_color") == "gold":
            continue

        prices = printing.get("prices", {}) or {}
        finishes = printing.get("finishes", [])

        for finish in finishes:
            if finish in ("nonfoil", "glossy"):
                price_key = "usd"
                finish_label = "nonfoil"
            elif finish == "foil":
                price_key = "usd_foil"
                finish_label = "foil"
            elif finish == "etched":
                price_key = "usd_etched"
                finish_label = "etched"
            else:
                continue

            price_str = prices.get(price_key)
            if price_str is None:
                continue
            try:
                price = float(price_str)
            except (ValueError, TypeError):
                continue
            if price <= 0:
                continue

            if best_price is None or price < best_price:
                best_price = price
                best_result = {
                    "name": canonical_name,
                    "set": printing.get("set", "").upper(),
                    "collector_number": printing.get("collector_number", ""),
                    "finish": finish_label,
                    "price": price,
                }

    if best_result is not None:
        return best_result, None
    return None, "no_price"
