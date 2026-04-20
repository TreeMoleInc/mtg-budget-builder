# core/finder.py — Cheapest-version logic and background thread orchestration
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED

try:
    from core import scryfall
except ModuleNotFoundError:
    import scryfall  # type: ignore[no-redef]

# ---------------------------------------------------------------------------
# Basic land names — always skipped (zero API calls), still shown in output
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
    finish = result["finish"]
    if finish == "foil":
        finish_tag = " *F*"
    elif finish == "etched":
        finish_tag = " *E*"
    else:
        finish_tag = ""
    return f"{qty} {result['name']} ({result['set']}){finish_tag} {result['collector_number']}"


def _poll(future, cancel_event, on_rate_limit=None):
    """Poll a future every 100ms. Returns True if cancelled, False if completed normally."""
    while True:
        if cancel_event and cancel_event.is_set():
            return True
        done_set, _ = wait({future}, timeout=0.1, return_when=FIRST_COMPLETED)
        if done_set:
            return False
        remaining = scryfall.get_backoff_remaining()
        if remaining > 0 and on_rate_limit:
            on_rate_limit(remaining)


def run_search(
    card_list: list[tuple[int, str]],
    on_progress: callable,
    on_complete: callable,
    on_error: callable,
    cancel_event: threading.Event | None = None,
    on_cancel: callable | None = None,
    on_rate_limit: callable | None = None,
) -> None:
    """
    Search for the cheapest version of each card in card_list.
    Basic lands are always skipped — no API calls made for them.

    Phase 1 — Batch resolve non-basic names via POST /cards/collection (1 request
               for up to 75 cards). Unmatched names fall back to individual fuzzy resolve.
    Phase 2 — Fetch printings sequentially, one card at a time. Results emitted live
               via on_progress as each card finishes.

    Cancel is checked every 100ms via polling — near-instant regardless of network state.
    Rate limit countdowns are surfaced via on_rate_limit(remaining_seconds).

    Callbacks:
      on_progress(current, total, card_name, result_line, price_str, is_basic)
      on_complete(result_lines, error_lines, total_price, total_cards, unique_cards, basic_cards, unique_basics)
      on_error(message)
      on_cancel()
      on_rate_limit(remaining_seconds: float)
    """
    try:
        total = len(card_list)
        result_lines: list[str] = []
        error_lines: list[str] = []
        total_price: float = 0.0
        successful_cards: list[tuple[int, str]] = []
        basic_entries: list[tuple[int, str]] = []

        executor = ThreadPoolExecutor(max_workers=1)
        cancelled = False

        # ------------------------------------------------------------------
        # Phase 1: Batch resolve non-basic names
        # ------------------------------------------------------------------
        non_basic_names = [name for _, name in card_list if not _is_basic(name)]
        resolved: dict[str, dict | None] = {}  # lowercase name -> card_data or None

        chunks = [non_basic_names[i:i + 75] for i in range(0, len(non_basic_names), 75)]
        fuzzy_fallback: list[str] = []

        for chunk in chunks:
            future = executor.submit(scryfall.batch_resolve_cards, chunk)
            cancelled = _poll(future, cancel_event, on_rate_limit)
            if cancelled:
                break
            found_dict, not_found = future.result()
            for name in chunk:
                if name.lower() in found_dict:
                    resolved[name.lower()] = found_dict[name.lower()]
                else:
                    fuzzy_fallback.append(name)

        # Fuzzy fallback for names not matched by batch
        for name in fuzzy_fallback:
            if cancelled:
                break
            future = executor.submit(scryfall.resolve_card, name)
            cancelled = _poll(future, cancel_event, on_rate_limit)
            if cancelled:
                break
            card, _ = future.result()
            resolved[name.lower()] = card

        if cancelled:
            executor.shutdown(wait=False, cancel_futures=True)
            if on_cancel:
                on_cancel()
            return

        # ------------------------------------------------------------------
        # Phase 2: Fetch printings sequentially, emit results live
        # ------------------------------------------------------------------
        for i, (qty, name) in enumerate(card_list):
            if cancel_event and cancel_event.is_set():
                executor.shutdown(wait=False, cancel_futures=True)
                cancelled = True
                break

            # Basics: emit immediately, zero API calls
            if _is_basic(name):
                line = f"{qty} {name}"
                basic_entries.append((qty, name))
                result_lines.append(line)
                on_progress(i + 1, total, name, line, "", True)
                continue

            card_data = resolved.get(name.lower())
            if card_data is None:
                # Was not found in Phase 1 at all
                line = f'# ERROR: "{name}" \u2014 not found on Scryfall'
                error_lines.append(line)
                result_lines.append(line)
                on_progress(i + 1, total, name, line, "", False)
                continue

            future = executor.submit(scryfall.find_cheapest_from_card, card_data, name)
            cancelled = _poll(future, cancel_event, on_rate_limit)
            if cancelled:
                executor.shutdown(wait=False, cancel_futures=True)
                break

            result, reason = future.result()

            if result:
                line = _format_result_line(qty, result)
                successful_cards.append((qty, name))
                price = result["price"]
                total_price += qty * price
                price_str = f"${price:.2f} ea." if qty > 1 else f"${price:.2f}"
            elif reason == "no_price":
                line = f'# WARNING: "{name}" \u2014 no USD price available'
                error_lines.append(line)
                price_str = ""
            elif reason == "network_error":
                line = f'# ERROR: "{name}" \u2014 network error, try again'
                error_lines.append(line)
                price_str = ""
            else:
                line = f'# ERROR: "{name}" \u2014 not found on Scryfall'
                error_lines.append(line)
                price_str = ""

            result_lines.append(line)
            on_progress(i + 1, total, name, line, price_str, False)

        if cancelled:
            if on_cancel:
                on_cancel()
            return

        executor.shutdown(wait=False)

        total_cards = sum(qty for qty, _ in successful_cards) + sum(qty for qty, _ in basic_entries)
        unique_cards = len({n.strip().lower() for _, n in successful_cards}) + len({n.strip().lower() for _, n in basic_entries})
        basic_cards = sum(qty for qty, _ in basic_entries)
        unique_basics = len({n.strip().lower() for _, n in basic_entries})
        on_complete(result_lines, error_lines, total_price, total_cards, unique_cards, basic_cards, unique_basics)

    except Exception as exc:
        on_error(f"Unexpected error during search: {exc}")


def start_search(
    card_list: list[tuple[int, str]],
    on_progress: callable,
    on_complete: callable,
    on_error: callable,
    on_cancel: callable | None = None,
    on_rate_limit: callable | None = None,
) -> tuple[threading.Thread, threading.Event]:
    """Create, start, and return a background thread and cancel event for run_search."""
    cancel_event = threading.Event()
    thread = threading.Thread(
        target=run_search,
        args=(card_list, on_progress, on_complete, on_error, cancel_event, on_cancel, on_rate_limit),
        daemon=True,
    )
    thread.start()
    return thread, cancel_event
