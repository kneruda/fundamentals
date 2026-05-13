"""Shared ticker-input parser used by bulk universe upload and watchlist creation."""


def parse_ticker_input(raw_text: str) -> list[str]:
    """Return clean ticker list from a newline-delimited string.

    Blank lines and lines starting with '#' are ignored.
    Each remaining line is stripped and uppercased.
    """
    result = []
    for line in raw_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        result.append(stripped.upper())
    return result
