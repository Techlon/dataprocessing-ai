"""Observations about what an operation actually did.

Every serious defect this library has had shared one property: it returned a
confident, plausible, wrong answer. Cleaning emptied text columns, outlier
detection reported none when there were some, a rename silently did nothing, a
join quietly multiplied rows. None of them raised. An agent calling these
operations unattended has no other way to notice.

Reporting `rows` and `rows_in` was the first answer to that, but it is passive:
it only helps a caller who thinks to compare the two, and mostly they do not.
These functions produce the active version — a short list of plain statements
about anything surprising, carried in the response alongside the data.

Each warning says three things, because a warning missing any of them cannot be
acted on: what happened, how large it was, and what to do instead. They describe
outcomes, never faults — an operation that removed 90% of the rows may be
exactly right, and the caller is the one who can tell.
"""
from dataprocessing._defaults import WARN_ROW_LOSS_SHARE


def _percent(part, whole):
    return 0.0 if not whole else (part / whole) * 100


def row_loss(rows_in, rows_out, cause, remedy=None, threshold=WARN_ROW_LOSS_SHARE):
    """Warn that an operation removed rows, or return None if unremarkable.

    Total loss is always reported, however the threshold is set: a caller handed
    an empty dataset needs to know why, and "0 rows" is the single most
    misleading thing this library can return without explanation.
    """
    if rows_in <= 0 or rows_out >= rows_in:
        return None

    lost = rows_in - rows_out
    share = lost / rows_in

    if rows_out == 0:
        message = f"All {rows_in} rows were removed: {cause}"
    elif share >= threshold:
        message = (
            f"Removed {lost} of {rows_in} rows ({_percent(lost, rows_in):.0f}%): {cause}"
        )
    else:
        return None

    return f"{message} {remedy}" if remedy else message


def dropped_columns(columns_in, columns_out, cause, remedy=None):
    """Warn that columns disappeared. Always reported — a column vanishing is
    never routine, and the caller may be about to ask for one that is gone."""
    lost = [c for c in columns_in if c not in set(columns_out)]
    if not lost:
        return None
    names = ", ".join(repr(c) for c in lost)
    message = f"Dropped {len(lost)} column(s) [{names}]: {cause}"
    return f"{message} {remedy}" if remedy else message


def merge_result(left_rows, right_rows, result_rows, how="inner"):
    """Warn about a join whose shape is not what the caller probably expected.

    A join fails by multiplying rather than by erroring, which is why this
    exists: nothing else in a successful response distinguishes a correct
    3-row join from one that silently became 9.
    """
    warnings = []
    if how == "cross":
        return warnings

    if result_rows > max(left_rows, right_rows):
        warnings.append(
            f"Join returned {result_rows} rows from {left_rows} left and "
            f"{right_rows} right: the key matched more than once, so rows were "
            f"multiplied rather than paired. Pass validate='one_to_one' or "
            f"'many_to_one' to make an unexpected fan-out an error."
        )
    elif result_rows == 0 and left_rows and right_rows:
        warnings.append(
            "Join returned no rows: the key values do not overlap at all. Check "
            "the join column, and check its type — 1 and '1' do not match."
        )
    elif how == "inner" and result_rows < left_rows:
        warnings.append(
            f"Inner join returned {result_rows} rows from {left_rows} on the "
            f"left: rows without a match in the right frame are dropped. Use "
            f"how='left' to keep them."
        )
    return warnings


def type_changes(before, after):
    """Warn where a type conversion blanked values that used to be present.

    `fix_types` converts a column only when most of it converts, so a minority
    can still be lost — and the loss is silent, because the column is still
    there and still the right length.
    """
    warnings = []
    for column in after.columns:
        if column not in before.columns:
            continue
        if before[column].dtype == after[column].dtype:
            continue
        gained_nulls = int(after[column].isna().sum() - before[column].isna().sum())
        if gained_nulls > 0:
            warnings.append(
                f"Column {column!r} was converted to {after[column].dtype}, and "
                f"{gained_nulls} value(s) did not convert and are now null. "
                f"Raise the type threshold toward 1.0 to leave such a column as text."
            )
    return warnings
