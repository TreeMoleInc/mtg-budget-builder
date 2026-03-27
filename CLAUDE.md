# MTG Budget Builder — CLAUDE.md

## TODO

---

## Releasing a New Version

When the user says **"release vX.Y.Z"**, perform these steps in order:

1. Bump `CURRENT_VERSION = "vX.Y.Z"` in `ui/app.py`
2. Update `self.title("MTG Budget Builder vX.Y.Z")` in `ui/app.py`
3. Update `name="MTG Budget Builder (vX.Y.Z)"` in `build_windows.spec`
4. Rebuild the exe: `.venv/Scripts/pyinstaller build_windows.spec --noconfirm`
5. Commit and push: `git add -A && git commit -m "Release vX.Y.Z" && git push`
6. Create GitHub release: `gh release create vX.Y.Z "dist/MTG Budget Builder (vX.Y.Z).exe" --title "vX.Y.Z" --notes "..."`

Use the user's provided release notes if given, otherwise use a generic "Bug fixes and improvements."

---

## Project Overview

A desktop Python application that finds the cheapest available version of each card in a user-supplied Magic: The Gathering card list, using the Scryfall API for pricing data.

The user pastes a card list, clicks search, and receives a reformatted list using the cheapest printing of each card, ready to be copied into Moxfield.

---

## Environment

- **Python:** 3.13
- **Virtual environment:** `.venv/` in project root — always install packages here
  - Activate: `.venv/Scripts/activate` (Windows)
  - Install: `.venv/Scripts/pip install <package>`
- **Run app:** `.venv/Scripts/python main.py`

---

## Project Structure

```
budget builder/
├── main.py              # Entry point — creates and runs the CTk app
├── ui/
│   ├── __init__.py
│   ├── app.py           # Main CTkFrame — overall layout
│   └── widgets.py       # Custom reusable widget components
├── core/
│   ├── __init__.py
│   ├── parser.py        # Parses raw input list → list of (qty, card_name)
│   ├── scryfall.py      # All Scryfall API calls with rate limiting
│   └── finder.py        # Cheapest-version logic + background thread orchestration
├── requirements.txt
└── CLAUDE.md
```

---

## UI Design

- **Framework:** customtkinter (modern Tkinter wrapper)
- **Theme:** Dark grays (`#1e1e1e` bg, `#2b2b2b` panels, `#3a3a3a` borders) with light green accents (`#4caf50` buttons, `#81c784` highlights)
- **Text:** White (`#ffffff`) for content, light gray (`#888888`) for placeholder text

### Layout
Two side-by-side panels:

**Left — Input panel:**
- Large text area with placeholder text guiding the user on format
- "Find Cheapest Versions" button (green) below

**Right — Output panel:**
- Card list text area (selectable/copyable) — left portion
- Price column (read-only, non-selectable, visually distinct) — right portion
- "Copy List" button — copies card list text only, never the price column
- Total price label at the bottom

**Shared:**
- Progress bar (hidden at rest, visible during search): shows `X / Y cards processed`
- Status label for live feedback and error messages

---

## Core Logic

### Input Parsing (`core/parser.py`)

Accepts common deck list formats:
```
4 Lightning Bolt
4x Lightning Bolt
1 Sheoldred, the Apocalypse
Lightning Bolt          (assumes qty = 1)
```
Returns a list of `(quantity: int, card_name: str)` tuples.
Flags lines that look malformed — these are shown as warnings in the output after the search.

### Scryfall Integration (`core/scryfall.py`)

**Rate limiting:** Enforce a minimum 100ms gap between all requests (Scryfall's stated limit: max 10 req/s). Exceeding this risks a temporary or permanent IP ban.

**Step 1 — Resolve card name:**
```
GET https://api.scryfall.com/cards/named?fuzzy={card_name}
```
On success, extract the card's `prints_search_uri` for the next step.
On failure (404), mark card as not found.

**Step 2 — Fetch ALL printings:**
Follow `prints_search_uri` (uses `unique=prints` — one result per physical printing).
This URL already handles deduplication and is more reliable than constructing a search manually.
**Paginate** via `has_more` / `next_page` until all pages are fetched. This is critical — the Scryfall website shows a truncated table with a "View all prints" button, but the API always returns the full list via pagination, so we must follow all pages.

**Step 3 — Filter candidates:**
Exclude the following from price consideration:
- `"digital": true` — MTGO/Arena digital-only cards (no paper price)
- `"lang" != "en"` — Non-English printings
- Cards where ALL of `prices.usd`, `prices.usd_foil`, `prices.usd_etched` are null (unpriced)

**Step 4 — Find cheapest version:**
For each printing, check every finish listed in the `finishes` array:
| Finish | Price field |
|--------|-------------|
| `nonfoil` | `prices.usd` |
| `foil` | `prices.usd_foil` |
| `etched` | `prices.usd_etched` |

All finish types are considered (nonfoil, foil, etched, glossy where applicable).
Prices are strings in the API — convert to `float` for comparison. Null prices are skipped.
Select the (printing, finish) pair with the lowest price.

**Pricing note:** Scryfall's `usd` prices are sourced from **TCGPlayer Market Price**, which is a weighted average of recent actual sales. This reflects Near Mint (NM) condition as the default/most-traded condition, so no condition filtering is needed beyond using Scryfall's prices directly.

### Output Formatting

Uses **Moxfield format** (widely supported by Moxfield, Archidekt, and others):
```
4 Lightning Bolt (LEA) 161         # nonfoil
2 Counterspell (3ED) *F* 268       # foil
1 Jeweled Lotus (CMM) *E* 611      # etched foil
```
- Set codes are **UPPERCASE** in output (e.g. `LEA`, not `lea`)
- Collector number is the string as returned by Scryfall (can include letters: `141a`, `★`)
- Foil indicator: `*F*` for foil, `*E*` for etched foil, nothing for nonfoil

### Finder / Orchestration (`core/finder.py`)

- Runs the entire search in a **background thread** (so the UI never freezes)
- Emits progress callbacks to the UI: `(current_index, total, card_name, result_line, price)`
- The UI receives these and updates the progress bar and output in real-time

---

## Error Handling

| Situation | Output |
|-----------|--------|
| Card name not found on Scryfall | `# ERROR: "Carrd Naem" — not found on Scryfall` |
| Card found but all prints unpriced | `# WARNING: "Card Name" — no USD price available` |
| Network timeout / API failure | `# ERROR: "Card Name" — network error, try again` |
| Malformed input line | `# WARNING: could not parse line: "raw line here"` |

Errors are included inline in the output list so the user can see exactly which cards failed without losing the rest of the results.

---

## API Reference

| Endpoint | Use |
|----------|-----|
| `GET /cards/named?fuzzy={name}` | Resolve card name, get `prints_search_uri` |
| Follow `prints_search_uri` + paginate | Get all printings |
| `GET /cards/search?q=...&unique=prints` | Alternative all-prints search |

Key fields used from card objects:
- `prices.usd`, `prices.usd_foil`, `prices.usd_etched`
- `finishes` (array — use this, NOT deprecated `foil`/`nonfoil` booleans)
- `set` (lowercase set code)
- `collector_number` (string — may contain letters/symbols)
- `digital` (bool — exclude if true)
- `lang` (string — exclude if not `"en"`)
- `prints_search_uri` (URL for all printings of same oracle identity)
- `has_more`, `next_page` (pagination)

**Important:** `foil` and `nonfoil` boolean fields on card objects are **deprecated** — always use the `finishes` array instead.

---

## Development Notes

- Always run and test with `.venv/Scripts/python main.py`
- The price column in the output must be non-selectable — use a disabled/overlay widget, not a regular text box
- The "Copy List" button must copy only the card list column (without prices)
- Scryfall prices update once daily — no need to cache aggressively within a session
- Never exceed Scryfall's rate limit — this is an external service and bans are hard to reverse
