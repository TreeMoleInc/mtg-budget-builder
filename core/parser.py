# core/parser.py — Parses raw input list into (quantity, card_name) tuples

import re


def parse_decklist(text: str) -> tuple[list[tuple[int, str]], list[str]]:
    """
    Parse a raw deck list string into a list of (quantity, card_name) tuples.

    Handles formats:
        4 Lightning Bolt
        4x Lightning Bolt
        x4 Lightning Bolt
        Lightning Bolt          -> qty defaults to 1
        // comment              -> skipped
        # comment               -> skipped
        (empty lines)           -> skipped

    Returns:
        (cards, errors)
        cards:  list of (qty: int, name: str) tuples
        errors: list of raw lines that could not be parsed
    """
    cards: list[tuple[int, str]] = []
    errors: list[str] = []

    # Strips set code + collector number from names like:
    #   "Lightning Bolt (LEA) 161"
    #   "Counterspell (3ED) *F* 268"
    #   "Argothian Elder (plst) USG-233"   <- The List format
    # Matches an opening paren followed by 1-6 alphanumeric chars (the set code)
    # and strips everything from that point onwards.
    set_code_suffix = re.compile(r'\s*\([A-Za-z0-9]{1,6}\).*$')

    # Regex patterns for quantity prefixes/suffixes
    # "4 Card Name", "4x Card Name", "x4 Card Name"
    pattern_leading = re.compile(r'^x?(\d+)x?\s+(.+)$', re.IGNORECASE)
    # Catch "Card Namex4" style — unlikely but handle anyway
    pattern_trailing = re.compile(r'^(.+?)\s+x(\d+)$', re.IGNORECASE)

    for raw_line in text.splitlines():
        line = raw_line.strip()

        # Skip empty lines
        if not line:
            continue

        # Skip comment lines
        if line.startswith('//') or line.startswith('#'):
            continue

        # Try leading quantity: "4 Name", "4x Name", "x4 Name"
        m = pattern_leading.match(line)
        if m:
            qty = int(m.group(1))
            name = set_code_suffix.sub("", m.group(2)).strip()
            if name:
                cards.append((qty, name))
                continue
            # name was empty after stripping — fall through to error

        # Try trailing quantity: "Name x4"
        m2 = pattern_trailing.match(line)
        if m2:
            name = set_code_suffix.sub("", m2.group(1)).strip()
            qty = int(m2.group(2))
            if name:
                cards.append((qty, name))
                continue

        # No quantity — treat entire line as card name (qty=1)
        # but only if the line looks like a plausible card name
        # (letters, spaces, commas, apostrophes, hyphens, colons, quotes)
        if re.match(r"^[A-Za-z][\w ',\-:\"!.&/]*$", line):
            name = set_code_suffix.sub("", line).strip()
            cards.append((1, name))
            continue

        # Could not parse
        errors.append(raw_line)

    return cards, errors


if __name__ == "__main__":
    test_input = """4 Lightning Bolt
2x Counterspell
1 Sheoldred, the Apocalypse
x1 Sol Ring
Force of Will
// a comment
# another comment

badline!!!@@@
"""
    cards, errors = parse_decklist(test_input)
    print("=== Parsed Cards ===")
    for qty, name in cards:
        print(f"  qty={qty}  name={name!r}")
    print("\n=== Errors ===")
    for err in errors:
        print(f"  {err!r}")
