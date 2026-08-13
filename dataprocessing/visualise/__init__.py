import pandas as pd
import numpy as np

SCHEMA = "https://vega.github.io/schema/vega-lite/v5.json"


def _require_column(df, column):
    if column not in df.columns:
        raise ValueError(f"Column '{column}' does not exist.")


def _require_numeric(df, column):
    _require_column(df, column)
    if not pd.api.types.is_numeric_dtype(df[column]):
        raise ValueError(f"'{column}' is not a numeric column.")


def histogram(df, column, bins=10):
    _require_numeric(df, column)

    # np.histogram raises "autodetected range of [nan, nan] is not finite" if a
    # single null is present, so nulls are excluded rather than crashing.
    col_data = df[column].dropna()
    if col_data.empty:
        return {
            "$schema": SCHEMA,
            "description": f"Histogram of {column}",
            "data": {"values": []},
            "mark": "bar",
            "encoding": {
                "x": {"field": "bin_start", "type": "quantitative"},
                "x2": {"field": "bin_end", "type": "quantitative"},
                "y": {"field": "count", "type": "quantitative"},
            },
        }

    hist, bin_edges = np.histogram(col_data, bins=bins)
    return {
        "$schema": SCHEMA,
        "description": f"Histogram of {column}",
        "data": {"values": [{"bin_start": float(bin_edges[i]), "bin_end": float(bin_edges[i + 1]), "count": int(hist[i])} for i in range(len(bin_edges) - 1)]},
        "mark": "bar",
        "encoding": {
            "x": {"field": "bin_start", "type": "quantitative"},
            "x2": {"field": "bin_end", "type": "quantitative"},
            "y": {"field": "count", "type": "quantitative"},
        },
    }


def bar_chart(df, column):
    _require_column(df, column)

    value_counts = df[column].value_counts()
    return {
        "$schema": SCHEMA,
        "description": f"Bar Chart of {column}",
        "data": {"values": [{"category": str(cat), "count": int(count)} for cat, count in zip(value_counts.index, value_counts)]},
        "mark": "bar",
        "encoding": {
            "x": {"field": "category", "type": "nominal"},
            "y": {"field": "count", "type": "quantitative"},
        },
    }


def scatter(df, x, y):
    _require_numeric(df, x)
    _require_numeric(df, y)

    filtered = df[[x, y]].dropna()
    return {
        "$schema": SCHEMA,
        "description": f"Scatter Plot of {x} vs {y}",
        "data": {"values": [{"x": float(row[0]), "y": float(row[1])} for row in filtered.itertuples(index=False)]},
        "mark": "point",
        "encoding": {
            "x": {"field": "x", "type": "quantitative"},
            "y": {"field": "y", "type": "quantitative"},
        },
    }


def line_chart(df, x, y):
    _require_column(df, x)
    _require_numeric(df, y)

    # Rows with a null in either axis are dropped: float(NaN) would otherwise
    # put a bare NaN token in the spec, which is not valid JSON.
    filtered = df[[x, y]].dropna()

    # x may be non-numeric (dates, categories); its Vega-Lite type is inferred.
    x_is_numeric = pd.api.types.is_numeric_dtype(df[x])
    x_type = "quantitative" if x_is_numeric else "nominal"
    return {
        "$schema": SCHEMA,
        "description": f"Line Chart of {x} vs {y}",
        "data": {"values": [
            {"x": (float(row[0]) if x_is_numeric else str(row[0])), "y": float(row[1])}
            for row in filtered.itertuples(index=False)
        ]},
        "mark": "line",
        "encoding": {
            "x": {"field": "x", "type": x_type},
            "y": {"field": "y", "type": "quantitative"},
        },
    }


def correlation_heatmap(df, columns=None):
    if columns is None:
        columns = [col for col in df.columns if pd.api.types.is_numeric_dtype(df[col])]
    else:
        # Explicitly requested columns are validated. Passing a text column
        # previously surfaced as "could not convert string to float", which
        # names neither the column nor the actual problem.
        for col in columns:
            _require_numeric(df, col)
    columns = list(columns)

    if not columns:
        raise ValueError("No numeric columns available for a correlation heatmap.")

    corr_matrix = df[columns].corr()
    values = []
    for col1 in columns:
        for col2 in columns:
            corr = corr_matrix.loc[col1, col2]
            corr = float(corr)
            values.append({"x": col1, "y": col2, "correlation": None if corr != corr else corr})

    return {
        "$schema": SCHEMA,
        "description": "Correlation Heatmap",
        "data": {"values": values},
        "mark": "rect",
        "encoding": {
            "x": {"field": "x", "type": "nominal"},
            "y": {"field": "y", "type": "nominal"},
            "color": {"field": "correlation", "type": "quantitative"},
        },
    }
