# core/scryfall.py — All Scryfall API calls with rate limiting

import time
import requests
from requests.exceptions import RequestException

# ---------------------------------------------------------------------------
# Rate limiting — 150ms minimum between ALL requests (conservative, avoids 429)
# ---------------------------------------------------------------------------
_last_request_time: float = 0.0
_MIN_DELAY = 0.15  # seconds


def _rate_limited_get(url: str, params: dict | None = None) -> requests.Response | None:
    """Perform a GET request, enforcing the minimum delay between all requests.
    Returns the Response object (any status code) or None on network failure."""
    global _last_request_time
    elapsed = time.monotonic() - _last_request_time
    if elapsed < _MIN_DELAY:
        time.sleep(_MIN_DELAY - elapsed)
    try:
        response = requests.get(url, params=params, timeout=10)
        return response
    except RequestException:
        return None
    finally:
        _last_request_time = time.monotonic()


def _get_with_retry(url: str, params: dict | None = None, max_retries: int = 4) -> requests.Response | None:
    """Rate-limited GET with automatic 429 backoff and transient-error retry.

    Returns the Response on success/404, None only if all retries exhausted.
    """
    for attempt in range(max_retries):
        resp = _rate_limited_get(url, params)

        if resp is None:
            # Network / timeout failure — short wait then retry
            if attempt < max_retries - 1:
                time.sleep(0.5 * (attempt + 1))
            continue

        if resp.status_code == 429:
            # Scryfall rate-limited us — honour their Retry-After header if present
            try:
                wait = float(resp.headers.get("Retry-After", 2)) + 0.5
            except (ValueError, TypeError):
                wait = 2.5
            time.sleep(wait)
            continue

        if resp.status_code >= 500:
            # Scryfall server error — brief wait then retry
            if attempt < max_retries - 1:
                time.sleep(1.0)
            continue

        # Any other status code (200, 404, etc.) — return as-is
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
        (None, "not_found")        — Scryfall doesn't recognise the name (404)
        (None, "network_error")    — request failed after retries
    """
    resp = _get_with_retry("https://api.scryfall.com/cards/named", {"fuzzy": card_name})
    if resp is None:
        return None, "network_error"
    if resp.status_code == 200:
        return resp.json(), None
    return None, "not_found"


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


def find_cheapest_version(card_name: str) -> tuple[dict | None, str | None]:
    """
    High-level function to find the cheapest physical printing of a card.

    Returns:
        (result, None)              — success; result has keys: name, set, collector_number, finish, price
        (None, "not_found")         — card name not recognised by Scryfall
        (None, "no_price")          — card found but no USD pricing on any eligible printing
        (None, "network_error")     — network failure after retries

    finish values: "nonfoil", "foil", "etched"
    """
    # Step 1: Resolve card
    card, error = resolve_card(card_name)
    if card is None:
        return None, error  # "not_found" or "network_error"

    prints_search_uri = card.get("prints_search_uri")
    if not prints_search_uri:
        return None, "not_found"

    canonical_name = card.get("name", card_name)

    # Step 2: Get all printings
    printings = get_all_printings(prints_search_uri)
    if not printings:
        return None, "network_error"

    # Step 3 + 4: Filter and find cheapest
    best_price: float | None = None
    best_result: dict | None = None

    for printing in printings:
        # Skip digital-only (MTGO/Arena)
        if printing.get("digital", False):
            continue

        # Skip non-English
        if printing.get("lang", "en") != "en":
            continue

        # Skip gold-bordered (World Championship decks, 30th Anniversary)
        # Silver-bordered (Unsets) and acorn cards are kept
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


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    test_cards = [
        "Lightning Bolt",
        "Arcane Signet",
        "Sol Ring",
        "Black Lotus",
        "Fakecardname Xyz",
    ]

    for name in test_cards:
        print(f"\nSearching: {name!r}")
        result, reason = find_cheapest_version(name)
        if result:
            finish_tag = {"foil": " *F*", "etched": " *E*"}.get(result["finish"], "")
            print(f"  -> {result['name']} ({result['set']}){finish_tag} #{result['collector_number']}  ${result['price']:.2f}")
        else:
            print(f"  -> None ({reason})")
