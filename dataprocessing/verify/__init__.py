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


# Operations whose whole purpose is to change the row count. Warning that a
# group-by "removed 96% of rows" is not a finding, it is a description of
# grouping — and a warning that fires on correct behaviour is worse than no
# warning at all, because it teaches the reader to skip all of them.
RESHAPING_OPERATIONS = frozenset({"group_and_aggregate", "pivot"})

# A filter is meant to remove rows, so partial loss is not news. Matching
# almost nothing usually is: it is the signature of a wrong value or a type
# mismatch, e.g. filtering a text column of digits with a numeric comparison.
FILTER_ALARM_SHARE = 0.90


def transform_result(operation, rows_in, rows_out):
    """Warn about a transform whose outcome the caller probably did not intend.

    Deliberately quieter than a plain row-loss check. Found by using the tools
    on real data: a group-by legitimately collapsing 120 rows to 5 was being
    reported as a 96% loss, which is exactly the noise that makes an agent stop
    reading warnings.
    """
    if rows_in <= 0 or operation in RESHAPING_OPERATIONS:
        return None
    if rows_out == 0:
        return (
            f"{operation} returned no rows at all from {rows_in}. Check the "
            f"value and the column's type — comparing a numeric value against "
            f"a column of text digits matches nothing."
        )
    if operation == "filter_rows" and (rows_in - rows_out) / rows_in >= FILTER_ALARM_SHARE:
        lost = rows_in - rows_out
        return (
            f"filter_rows kept only {rows_out} of {rows_in} rows "
            f"({_percent(lost, rows_in):.0f}% removed). Intended, or is the "
            f"comparison value wrong for this column?"
        )
    return None


def dropped_columns(columns_in, columns_out, cause, remedy=None):
    """Warn that columns disappeared. Always reported — a column vanishing is
    never routine, and the caller may be about to ask for one that is gone."""
    lost = [c for c in columns_in if c not in set(columns_out)]
    if not lost:
        return None
    names = ", ".join(repr(c) for c in lost)
    message = f"Dropped {len(lost)} column(s) [{names}]: {cause}"
    return f"{message} {remedy}" if remedy else message


def merge_result(left_rows, right_rows, result_rows, how="inner", unmatched=None):
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

    if how in {"left", "outer"} and unmatched:
        # A left join keeps unmatched rows and fills their right-hand columns
        # with nulls. The row count is unchanged, so nothing about the response
        # reveals that a chunk of the result is empty on one side.
        warnings.append(
            f"{unmatched} of {left_rows} left rows found no match, so their "
            f"columns from the right frame are null. Counts and averages over "
            f"those columns will be computed from {left_rows - unmatched} rows, "
            f"not {left_rows}."
        )
    return warnings


def extreme_values(df, factor=None, columns=None):
    """Warn about outliers left in place, without removing them.

    Cleaning does not drop outliers by default, and said nothing about them, so
    a single mistyped 999999 in an order-value column moved the mean from 196
    to 9453 with no indication anything was wrong. Removing the row is a
    judgement only the caller can make; mentioning it is not.
    """
    from dataprocessing._defaults import DEFAULT_IQR_FACTOR
    from dataprocessing.analyse import detect_outliers

    factor = DEFAULT_IQR_FACTOR if factor is None else factor
    warnings = []
    for column, positions in detect_outliers(df, columns=columns, factor=factor).items():
        if not positions:
            continue
        series = df[column].dropna()
        extreme = series.loc[[p for p in positions if p in series.index]]
        if extreme.empty:
            continue

        # Being beyond the fence is not itself worth reporting: in any normal
        # sample a few points always are, so warning on that fires constantly on
        # healthy data. What matters is whether they actually distort the
        # answer, so the test is how far the mean moves without them.
        without = series.drop(extreme.index)
        if without.empty or series.mean() == 0:
            continue
        shift = abs(series.mean() - without.mean()) / abs(series.mean())
        if shift < MEAN_DISTORTION_SHARE:
            continue

        worst = extreme.max() if abs(extreme.max()) > abs(extreme.min()) else extreme.min()
        warnings.append(
            f"Column {column!r} holds {len(positions)} value(s) beyond {factor} x "
            f"the interquartile range — the most extreme is {worst:g} against a "
            f"median of {series.median():g}. They were left in place, and they "
            f"move the mean of this column by {shift:.0%} "
            f"({series.mean():.2f} with them, {without.mean():.2f} without). "
            f"Set remove_outliers to drop those rows, or check them for "
            f"data-entry errors."
        )
    return warnings


def unmatched_rows(left, right, left_keys, right_keys):
    """Count left rows whose key has no match on the right."""
    def keyed(frame, keys):
        if len(keys) == 1:
            return frame[keys[0]]
        return frame[list(keys)].apply(tuple, axis=1)

    try:
        return int((~keyed(left, left_keys).isin(set(keyed(right, right_keys)))).sum())
    except Exception:
        return 0


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


# A statistic computed from a handful of values is not wrong, but it carries far
# less weight than its precision suggests, and nothing in "mean: 7.5" says so.
SPARSE_COLUMN_SHARE = 0.50

# Correlations this close to +/-1 are almost never a discovery. They are one
# column derived from another — revenue = signups * price — and reporting them
# as findings invites an agent to announce a tautology as an insight.
DERIVED_CORRELATION = 0.999

# How far outliers must move a column's mean before they are worth reporting.
# Points beyond the IQR fence are ordinary in any real sample; distortion is not.
MEAN_DISTORTION_SHARE = 0.10

# Below this many points a chart implies a pattern it cannot support.
THIN_CHART_POINTS = 5


def _text_columns_that_are_really_numbers(df, threshold=0.5):
    """Text columns holding mostly numbers, with the share that would convert.

    The common cause of an all-text frame is JSON: numbers arriving quoted from
    another tool or an API. Naming those columns turns "nothing to report" into
    an instruction.

    The threshold here is lower than the one `fix_types` converts at, and
    deliberately so: this is a hint about where to look, not a conversion. A
    column that is 60% numeric will not be converted automatically, and that is
    exactly the case where the caller most needs to be told it exists.
    """
    import pandas as pd

    found = []
    for column in df.columns:
        series = df[column]
        if pd.api.types.is_numeric_dtype(series):
            continue
        non_null = int(series.count())
        if non_null == 0:
            continue
        share = int(pd.to_numeric(series, errors="coerce").count()) / non_null
        if share >= threshold:
            found.append((column, share))
    return found


def analysis(df):
    """Warn about columns whose statistics are likely to mislead.

    `analyse` is where an agent forms conclusions, so a misleading number here
    propagates further than anywhere else in the library.
    """
    import pandas as pd

    warnings = []
    total = len(df)
    if total == 0:
        return ["The dataset is empty, so every statistic below is undefined."]

    # An empty report is the most misleading thing analyse can return: it is
    # well-formed, confident, and says nothing about why it is empty. This is
    # the failure class the whole module exists to catch, and it was sitting
    # inside the module itself.
    numeric_columns = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    if not numeric_columns:
        looks_numeric = _text_columns_that_are_really_numbers(df)
        message = (
            "No column is numeric, so summary_stats, correlations and outliers "
            "are all empty — this report contains nothing."
        )
        if looks_numeric:
            names = ", ".join(f"{c!r} ({share:.0%} numeric)" for c, share in looks_numeric)
            message += (
                f" Column(s) [{names}] hold values that look like numbers but "
                f"are stored as text. Clean the data with fix_types enabled — "
                f"and if a column is only partly numeric, lower type_threshold "
                f"to that share or repair the offending values first."
            )
        else:
            message += " Every column holds text or dates."
        warnings.append(message)

    for column in df.columns:
        series = df[column]
        non_null = int(series.count())
        null_share = 1 - (non_null / total)

        if non_null == 0:
            warnings.append(
                f"Column {column!r} is entirely null; its statistics are all undefined."
            )
            continue

        if null_share >= SPARSE_COLUMN_SHARE and pd.api.types.is_numeric_dtype(series):
            warnings.append(
                f"Column {column!r}: statistics are computed from {non_null} of "
                f"{total} values ({null_share:.0%} null). Treat the mean and "
                f"quartiles as indicative rather than representative."
            )

        if non_null > 1 and series.nunique(dropna=True) == 1:
            warnings.append(
                f"Column {column!r} holds a single distinct value, so its "
                f"variance is zero and its correlations are undefined."
            )
        elif (
            pd.api.types.is_integer_dtype(series)
            and non_null > 20
            and series.nunique(dropna=True) == non_null
        ):
            warnings.append(
                f"Column {column!r} is an integer with a distinct value in every "
                f"row, which usually means an identifier rather than a "
                f"measurement. Its mean and correlations are unlikely to mean "
                f"anything; exclude it with the columns argument."
            )

    numeric = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    seen = set()
    for i, left in enumerate(numeric):
        for right in numeric[i + 1:]:
            if df[left].count() < 2 or df[right].count() < 2:
                continue
            value = df[left].corr(df[right])
            if value == value and abs(value) >= DERIVED_CORRELATION:
                pair = tuple(sorted((str(left), str(right))))
                if pair in seen:
                    continue
                seen.add(pair)
                warnings.append(
                    f"Columns {left!r} and {right!r} correlate at {value:.3f}. A "
                    f"correlation this perfect almost always means one is "
                    f"derived from the other, not that a relationship was found."
                )
    return warnings


def chart(name, df, params, point_count):
    """Warn where a chart will imply more than the data supports."""
    import pandas as pd

    warnings = []
    column = params.get("column") or params.get("y")
    if column is not None and column in df.columns:
        series = df[column]
        total = len(series)
        non_null = int(series.count())
        if total and non_null / total <= 1 - SPARSE_COLUMN_SHARE:
            warnings.append(
                f"Column {column!r} is {1 - non_null / total:.0%} null, so this "
                f"chart is drawn from {non_null} of {total} rows."
            )

    if name == "bar_chart" and point_count == 1:
        warnings.append(
            "Only one category is present, so this bar chart shows a single bar."
        )
    if name in {"histogram", "scatter", "line_chart"} and 0 < point_count < THIN_CHART_POINTS:
        warnings.append(
            f"Only {point_count} point(s) are plotted, which is too few to read "
            f"a trend or a distribution from."
        )
    if point_count == 0:
        warnings.append("No data points were plotted; the chart will be empty.")
    return warnings
