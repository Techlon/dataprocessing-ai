import pandas as pd
import numpy as np

def histogram(df, column, bins=10):
    if column not in df.columns:
        raise ValueError(f"Column '{column}' does not exist.")
    if not pd.api.types.is_numeric_dtype(df[column]):
        raise ValueError(f"'{column}' is not a numeric column.")
    
    hist, bin_edges = np.histogram(df[column], bins=bins)
    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "description": "Histogram of <column>",
        "data": {"values": [{"bin_start": float(bin_edges[i]), "bin_end": float(bin_edges[i+1]), "count": int(hist[i])} for i in range(len(bin_edges) - 1)]},
        "mark": "bar",
        "encoding": {
            "x": {"field": "bin_start", "type": "quantitative"},
            "x2": {"field": "bin_end", "type": "quantitative"},
            "y": {"field": "count", "type": "quantitative"},
        },
    }

def bar_chart(df, column):
    if column not in df.columns:
        raise ValueError(f"Column '{column}' does not exist.")
    
    value_counts = df[column].value_counts()
    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "description": f"Bar Chart of {column}",
        "data": {"values": [{"category": str(cat), "count": count} for cat, count in zip(value_counts.index, value_counts)]},
        "mark": "bar",
        "encoding": {
            "x": {"field": "category", "type": "nominal"},
            "y": {"field": "count", "type": "quantitative"},
        },
    }

def scatter(df, x, y):
    if x not in df.columns:
        raise ValueError(f"Column '{x}' does not exist.")
    if y not in df.columns:
        raise ValueError(f"Column '{y}' does not exist.")
    if not pd.api.types.is_numeric_dtype(df[x]):
        raise ValueError(f"'{x}' is not a numeric column.")
    if not pd.api.types.is_numeric_dtype(df[y]):
        raise ValueError(f"'{y}' is not a numeric column.")
    
    filtered = df[[x, y]].dropna()
    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "description": f"Scatter Plot of {x} vs {y}",
        "data": {"values": [{"x": float(filtered[x].iloc[i]), "y": float(filtered[y].iloc[i])} for i in range(len(filtered))]},
        "mark": "point",
    }

def line_chart(df, x, y):
    if x not in df.columns:
        raise ValueError(f"Column '{x}' does not exist.")
    if y not in df.columns:
        raise ValueError(f"Column '{y}' does not exist.")
    if not pd.api.types.is_numeric_dtype(df[y]):
        raise ValueError(f"'{y}' is not a numeric column.")

    # x may be non-numeric (dates, categories); its Vega-Lite type is inferred.
    x_is_numeric = pd.api.types.is_numeric_dtype(df[x])
    x_type = "quantitative" if x_is_numeric else "nominal"
    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "description": f"Line Chart of {x} vs {y}",
        "data": {"values": [
            {"x": (float(df[x].iloc[i]) if x_is_numeric else str(df[x].iloc[i])),
             "y": float(df[y].iloc[i])}
            for i in range(len(df))
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
    
    corr_matrix = df[columns].corr()
    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "description": "Correlation Heatmap",
        "data": {"values": [{"x": col1, "y": col2, "correlation": float(corr_matrix.iloc[i, j])} for i, col1 in enumerate(columns) for j, col2 in enumerate(columns)]},
        "mark": "rect",
        "encoding": {
            "x": {"field": "x", "type": "nominal"},
            "y": {"field": "y", "type": "nominal"},
            "color": {"field": "correlation", "type": "quantitative"},
        },
    }
