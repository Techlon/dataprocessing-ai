"""Column lookup with a suggestion when the name is close but not right.

`clean` standardises column names — "Customer ID" becomes "customer_id" — so
the most common mistake in a pipeline is asking for a name that was correct one
step earlier. A bare "column not found" is true but unhelpful there: the caller
has the right column in mind and the wrong spelling of it, and an agent has no
cheap way to discover that short of re-listing the columns.
"""
import difflib


def suggest(name, available, limit=3):
    """Return column names close to `name`, best first, or an empty list."""
    text = str(name)
    matches = difflib.get_close_matches(text, [str(c) for c in available], n=limit, cutoff=0.6)

    # Catch the standardisation case explicitly. "Customer ID" and "customer_id"
    # score below the cutoff on raw similarity, yet it is the single most likely
    # mistake this library produces, so compare the normalised forms too.
    normalised = text.strip().lower().replace(" ", "_")
    for column in available:
        if str(column) not in matches and str(column).strip().lower().replace(" ", "_") == normalised:
            matches.insert(0, str(column))
    return matches[:limit]


def not_found_message(name, available):
    message = f"Column '{name}' does not exist."
    matches = suggest(name, available)
    if matches:
        message += " Did you mean " + " or ".join(repr(m) for m in matches) + "?"
    elif len(available) <= 12:
        message += f" Available: {[str(c) for c in available]}"
    return message


def require_column(df, column):
    if column not in df.columns:
        raise ValueError(not_found_message(column, df.columns))


def require_columns(df, columns, label="Column(s)"):
    missing = [c for c in columns if c not in df.columns]
    if not missing:
        return
    if len(missing) == 1:
        raise ValueError(not_found_message(missing[0], df.columns))
    hints = []
    for name in missing:
        matches = suggest(name, df.columns)
        if matches:
            hints.append(f"{name!r} -> {matches[0]!r}?")
    message = f"{label} not found: {missing}."
    if hints:
        message += " Did you mean: " + ", ".join(hints)
    return_error = ValueError(message)
    raise return_error
