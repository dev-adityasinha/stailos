"""Search helpers."""


def like_pattern(term: str) -> str:
    """Escape LIKE wildcards in user search input and wrap with %…%."""
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped.strip()}%"
