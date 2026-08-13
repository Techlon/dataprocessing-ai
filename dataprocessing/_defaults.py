"""Default values that govern judgement calls, and their validators.

These live in one place because the same number is used from more than one
module — the IQR fence is applied by both `clean.remove_outliers` and
`analyse.detect_outliers` — and this release has already been bitten twice by a
value written down twice and then drifting apart.

Each of these is a policy, not a fact. The defaults are the conventional
choices; every one is overridable at the call site.
"""

DEFAULT_NULL_THRESHOLD = 0.5
"""Share of a column that may be null before the column itself is dropped."""

DEFAULT_ROW_NULL_THRESHOLD = 0.0
"""Share of a row that may be null before the row is dropped. 0.0 means a single
null anywhere drops the row, which is what `dropna()` does and is far lossier
than it sounds — 5% of cells missing costs roughly a quarter of the rows."""

DEFAULT_TYPE_THRESHOLD = 0.9
"""Share of a column's non-null values that must convert for a type change to
be accepted. See `clean.fix_types`."""

DEFAULT_IQR_FACTOR = 1.5
"""Multiplier on the interquartile range that sets the outlier fence. 1.5 is
Tukey's convention: roughly 0.7% of normally-distributed data falls outside it.
Raise it (3.0 marks only 'far out' points) to flag less, lower it to flag more."""


def check_share(value, name="threshold"):
    """Validate a proportion. Rejects the percentage-vs-share slip."""
    if not 0 <= value <= 1:
        raise ValueError(
            f"{name} must be between 0 and 1, got {value!r}. "
            "It is a share of non-null values, not a percentage."
        )


def check_positive(value, name="factor"):
    if not value > 0:
        raise ValueError(f"{name} must be greater than 0, got {value!r}.")
