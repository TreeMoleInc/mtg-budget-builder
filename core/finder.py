# core/finder.py — Cheapest-version logic and background thread orchestration
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from core import scryfall
except ModuleNotFoundError:
    import scryfall  # type: ignore[no-redef]

# ---------------------------------------------------------------------------
# Basic land names
# ---------------------------------------------------------------------------
_BASICS_LOWER = frozenset({
    "plains", "island", "swamp", "mountain", "forest",
    "snow-covered plains", "snow-covered island", "snow-covered swamp",
    "snow-covered mountain", "snow-covered forest",
    "wastes",
})

# Max parallel workers for printing fetches — conservative to respect rate limits
_MAX_WORKERS = 4


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


def run_search(
    card_list: list[tuple[int, str]],
    on_progress: callable,
    on_complete: callable,
    on_error: callable,
    discount_basics: bool = False,
    cancel_event: threading.Event | None = None,
    on_status: callable | None = None,
) -> None:
    """
    Search for the cheapest version of each card in card_list.

    Speed strategy:
      Phase 1 — Batch resolve all card names via /cards/collection (chunks of 75).
                 Any not found by exact match fall back to individual fuzzy resolve.
      Phase 2 — Fetch printings for all cards in parallel (up to _MAX_WORKERS threads).
                 on_status(completed, total) is called as each fetch completes.
      Phase 3 — Results are emitted in original card order via on_progress.

    Callbacks:
      on_progress(current, total, card_name, result_line, price_str, is_basic)
      on_complete(result_lines, error_lines, total_price, total_cards, unique_cards)
      on_error(message)
      on_status(completed, total)  — optional, progress bar updates during parallel phase
    """
    try:
        total = len(card_list)
        names = [name for _, name in card_list]

        # ------------------------------------------------------------------
        # Phase 1: Batch resolve names
        # ------------------------------------------------------------------
        resolved: dict[str, dict | None] = {}  # lowercase name -> card_data or None

        # Chunk into groups of 75
        chunks = [names[i:i + 75] for i in range(0, len(names), 75)]
        fuzzy_fallback: list[str] = []

        for chunk in chunks:
            if cancel_event and cancel_event.is_set():
                break
            found_dict, not_found = scryfall.batch_resolve_cards(chunk)
            # Map results back by original (lowercase) name
            for name in chunk:
                key = name.lower()
                if key in found_dict:
                    resolved[key] = found_dict[key]
                else:
                    fuzzy_fallback.append(name)

        # Fuzzy fallback for names not matched by batch
        for name in fuzzy_fallback:
            if cancel_event and cancel_event.is_set():
                break
            card, _ = scryfall.resolve_card(name)
            resolved[name.lower()] = card  # None if still not found

        # ------------------------------------------------------------------
        # Phase 2: Parallel printing fetches
        # ------------------------------------------------------------------
        fetch_results: dict[int, tuple] = {}  # index -> (qty, name, result, reason)
        completed_count = [0]

        def fetch_one(idx: int, qty: int, name: str):
            card_data = resolved.get(name.lower())
            if card_data is None:
                return idx, qty, name, None, "not_found"
            result, reason = scryfall.find_cheapest_from_card(card_data, name)
            return idx, qty, name, result, reason

        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
            futures = {
                executor.submit(fetch_one, i, qty, name): i
                for i, (qty, name) in enumerate(card_list)
            }

            for future in as_completed(futures):
                if cancel_event and cancel_event.is_set():
                    # Cancel remaining futures
                    for f in futures:
                        f.cancel()
                    break
                idx, qty, name, result, reason = future.result()
                fetch_results[idx] = (qty, name, result, reason)
                completed_count[0] += 1
                if on_status:
                    on_status(completed_count[0], total)

        # ------------------------------------------------------------------
        # Phase 3: Emit results in original order
        # ------------------------------------------------------------------
        result_lines: list[str] = []
        error_lines: list[str] = []
        total_price: float = 0.0
        successful_cards: list[tuple[int, str]] = []

        for i in range(total):
            if i not in fetch_results:
                continue  # was cancelled before fetching

            qty, name, result, reason = fetch_results[i]
            basic = discount_basics and _is_basic(name)

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
    on_status: callable | None = None,
) -> tuple[threading.Thread, threading.Event]:
    """Create, start, and return a background thread and cancel event for run_search."""
    cancel_event = threading.Event()
    thread = threading.Thread(
        target=run_search,
        args=(card_list, on_progress, on_complete, on_error, discount_basics, cancel_event, on_status),
        daemon=True,
    )
    thread.start()
    return thread, cancel_event
