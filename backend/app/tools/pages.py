"""Page-range parsing shared by tools. Ranges are 1-based, like every PDF viewer."""

from app.domain.errors import ValidationFailed


def parse_page_list(spec: str | None, total: int) -> list[int]:
    """Parse ``"1-3, 5, 8-"`` into 0-based page indexes, in the order given.

    Supports ``all``, ``odd``, ``even``, ``last``, ``N``, ``N-M``, ``N-`` and ``-M``.
    Ranges may run backwards (``5-1``).
    """
    spec = (spec or "all").strip().lower()
    if total <= 0:
        return []
    out: list[int] = []
    for raw in spec.split(","):
        part = raw.strip()
        if not part:
            continue
        if part == "all":
            out.extend(range(total))
        elif part == "odd":
            out.extend(range(0, total, 2))
        elif part == "even":
            out.extend(range(1, total, 2))
        elif "-" in part:
            a, b = (s.strip() for s in part.split("-", 1))
            start = _page(a, total) if a else 1
            end = _page(b, total) if b else total
            step = 1 if end >= start else -1
            out.extend(i - 1 for i in range(start, end + step, step))
        else:
            out.append(_page(part, total) - 1)
    if not out:
        raise ValidationFailed("The page selection is empty.")
    return out


def parse_page_set(spec: str | None, total: int) -> set[int]:
    return set(parse_page_list(spec, total))


def parse_range_groups(spec: str, total: int) -> list[list[int]]:
    """``"1-3, 4-6, 9"`` becomes one group per comma-separated part."""
    groups = [parse_page_list(part, total) for part in spec.split(",") if part.strip()]
    if not groups:
        raise ValidationFailed("Enter at least one page range, for example 1-3, 4-6.")
    return groups


def _page(token: str, total: int) -> int:
    if token == "last":
        return total
    try:
        value = int(token)
    except ValueError:
        raise ValidationFailed(f"'{token}' is not a page number.") from None
    if value < 1 or value > total:
        raise ValidationFailed(f"Page {value} is out of range (the document has {total} pages).")
    return value
