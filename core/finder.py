# core/finder.py — Cheapest-version logic and background thread orchestration

import threading

try:
    from core import scryfall
except ModuleNotFoundError:
    import scryfall  # type: ignore[no-redef]  # when run directly from core/

# ---------------------------------------------------------------------------
# Basic land names — checked case-insensitively against input card names
# ---------------------------------------------------------------------------
_BASICS_LOWER = frozenset({
    "plains", "island", "swamp", "mountain", "forest",
    "snow-covered plains", "snow-covered island", "snow-covered swamp",
    "snow-covered mountain", "snow-covered forest",
    "wastes",
})


def _is_basic(name: str) -> bool:
    return name.strip().lower() in _BASICS_LOWER


def _format_result_line(qty: int, result: dict) -> str:
    """Format a result dict into a Moxfield-style output line."""
    finish = result["finish"]
    if finish == "foil":
        finish_tag = " *F*"
    elif finish == "etched":
        finish_tag = " *E*"
    else:
        finish_tag = ""
    return f"{qty} {result['name']} ({result['set']}){finish_tag} {result['collector_number']}"


def run_search(
    card_list: list[tuple[int, str]],
    on_progress: callable,
    on_complete: callable,
    on_error: callable,
    discount_basics: bool = False,
    cancel_event: threading.Event | None = None,
) -> None:
    """
    Search for the cheapest version of each card in card_list.

    Calls on_progress(current, total, card_name, result_line, price_str, is_basic) after each card.
    Calls on_complete(result_lines, error_lines, total_price, total_cards, unique_cards) when done.
    Calls on_error(message) on unexpected fatal error.

    If cancel_event is set mid-search, stops early and calls on_complete with partial results.

    Intended to be run in a background thread.
    """
    try:
        total = len(card_list)
        result_lines: list[str] = []
        error_lines: list[str] = []
        total_price: float = 0.0
        successful_cards: list[tuple[int, str]] = []  # (qty, name) for found cards only

        for i, (qty, name) in enumerate(card_list):
            if cancel_event and cancel_event.is_set():
                break
            basic = discount_basics and _is_basic(name)
            result, reason = scryfall.find_cheapest_version(name)

            if result:
                line = _format_result_line(qty, result)
                successful_cards.append((qty, name))
                if basic:
                    price_str = "ignored"
                else:
                    price = result["price"]
                    total_price += qty * price
                    price_str = f"${price:.2f} ea." if qty > 1 else f"${price:.2f}"
            elif reason == "no_price":
                line = f'# WARNING: "{name}" \u2014 no USD price available'
                error_lines.append(line)
                price_str = ""
                basic = False
            elif reason == "network_error":
                line = f'# ERROR: "{name}" \u2014 network error, try again'
                error_lines.append(line)
                price_str = ""
                basic = False
            else:
                line = f'# ERROR: "{name}" \u2014 not found on Scryfall'
                error_lines.append(line)
                price_str = ""
                basic = False

            result_lines.append(line)
            on_progress(i + 1, total, name, line, price_str, basic)

        total_cards = sum(qty for qty, _ in successful_cards)
        unique_cards = len({name.strip().lower() for _, name in successful_cards})
        on_complete(result_lines, error_lines, total_price, total_cards, unique_cards)

    except Exception as exc:
        on_error(f"Unexpected error during search: {exc}")


def start_search(
    card_list: list[tuple[int, str]],
    on_progress: callable,
    on_complete: callable,
    on_error: callable,
    discount_basics: bool = False,
) -> tuple[threading.Thread, threading.Event]:
    """Create, start, and return a background thread and cancel event for run_search."""
    cancel_event = threading.Event()
    thread = threading.Thread(
        target=run_search,
        args=(card_list, on_progress, on_complete, on_error, discount_basics, cancel_event),
        daemon=True,
    )
    thread.start()
    return thread, cancel_event


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    test_cards = [
        (4, "Lightning Bolt"),
        (1, "Sol Ring"),
        (4, "Forest"),
        (1, "Fakecardname Xyz"),
    ]

    def on_progress(current, total, name, line, price_str, is_basic):
        tag = f"  [{price_str}]" if price_str else "  [no price]"
        basic_tag = "  [BASIC]" if is_basic else ""
        print(f"  {current}/{total}: {line}{tag}{basic_tag}")

    def on_complete(result_lines, error_lines, total_price, total_cards, unique_cards):
        print(f"\n=== Complete ===")
        print(f"Total price: ${total_price:.2f}")
        print(f"Total cards: {total_cards}  |  Unique: {unique_cards}")
        print(f"Errors: {len(error_lines)}")

    def on_error(message):
        print(f"FATAL: {message}")

    print("Starting search (discount_basics=True)...")
    thread = start_search(test_cards, on_progress, on_complete, on_error, discount_basics=True)
    thread.join()
    print("Done.")
