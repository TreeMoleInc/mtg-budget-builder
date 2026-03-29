# core/scryfall.py — All Scryfall API calls with rate limiting

import time
import threading
import requests
from requests.exceptions import RequestException

# ---------------------------------------------------------------------------
# Rate limiting — 150ms minimum between ALL requests (conservative, avoids 429)
# Thread-safe via lock so parallel workers don't race on _last_request_time
# ---------------------------------------------------------------------------
_last_request_time: float = 0.0
_MIN_DELAY = 0.15  # seconds
_rate_lock = threading.Lock()


def _rate_limited_get(url: str, params: dict | None = None) -> requests.Response | None:
    """Perform a GET request, enforcing the minimum delay between all requests.
    Thread-safe. The lock is released before the HTTP call so parallel workers
    can overlap their network wait time while still respecting the rate limit."""
    global _last_request_time
    with _rate_lock:
        elapsed = time.monotonic() - _last_request_time
        if elapsed < _MIN_DELAY:
            time.sleep(_MIN_DELAY - elapsed)
        _last_request_time = time.monotonic()
    # Lock released — HTTP request runs in parallel with other workers' rate-limit waits
    try:
        return requests.get(url, params=params, timeout=10)
    except RequestException:
        return None


def _rate_limited_post(url: str, json_body: dict) -> requests.Response | None:
    """Perform a POST request with the same rate limiting as GET requests."""
    global _last_request_time
    with _rate_lock:
        elapsed = time.monotonic() - _last_request_time
        if elapsed < _MIN_DELAY:
            time.sleep(_MIN_DELAY - elapsed)
        _last_request_time = time.monotonic()
    try:
        return requests.post(url, json=json_body, timeout=10)
    except RequestException:
        return None


def _get_with_retry(url: str, params: dict | None = None, max_retries: int = 4) -> requests.Response | None:
    """Rate-limited GET with automatic 429 backoff and transient-error retry."""
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
    Resolve a single card name via Scryfall fuzzy search.

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
    Uses exact name matching; fuzzy fallback must be handled by the caller.

    Returns:
        (found_dict, not_found_names)
        found_dict:      maps each input name (lowercased) -> card_data dict
        not_found_names: list of input names Scryfall could not match exactly
    """
    if not names:
        return {}, []

    body = {"identifiers": [{"name": n} for n in names[:75]]}
    resp = _rate_limited_post("https://api.scryfall.com/cards/collection", body)

    if resp is None or resp.status_code != 200:
        # Treat entire chunk as not found — caller falls back to fuzzy
        return {}, list(names[:75])

    data = resp.json()
    found_cards = data.get("data", [])
    not_found_raw = data.get("not_found", [])

    # Build a lookup: lowercase input name -> card_data
    # Scryfall returns cards in an arbitrary order; match by name field
    name_lower_set = {n.lower() for n in names[:75]}
    found_dict: dict[str, dict] = {}
    for card in found_cards:
        canonical = card.get("name", "")
        # Try to match back to one of our input names
        for n in names[:75]:
            if n.lower() == canonical.lower() or canonical.lower().startswith(n.lower()):
                found_dict[n.lower()] = card
                break
        else:
            # Fallback: store by canonical name
            found_dict[canonical.lower()] = card

    not_found_names = [item.get("name", "") for item in not_found_raw]
    return found_dict, not_found_names


def get_all_printings(prints_search_uri: str) -> list[dict]:
    """
    Fetch ALL printings by following prints_search_uri and paginating
    via has_more / next_page until done.
    Returns a flat list of all card dicts across all pages.
    """
    cards: list[dict] = []
    url: str | None = prints_search_uri

    while url:
        resp = _get_with_retry(url)
        if resp is None or resp.status_code != 200:
            break
        data = resp.json()
        cards.extend(data.get("data", []))
        url = data.get("next_page") if data.get("has_more") else None

    return cards


def _pick_cheapest(printings: list[dict], canonical_name: str) -> tuple[dict | None, str | None]:
    """Given a list of printing dicts, return the cheapest (result, None) or (None, reason)."""
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


def find_cheapest_from_card(card_data: dict, card_name: str) -> tuple[dict | None, str | None]:
    """
    Find the cheapest printing given a pre-resolved card dict (has prints_search_uri).
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
    Resolves the name then fetches all printings sequentially.
    """
    card, error = resolve_card(card_name)
    if card is None:
        return None, error

    return find_cheapest_from_card(card, card_name)