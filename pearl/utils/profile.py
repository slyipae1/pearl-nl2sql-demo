from __future__ import annotations

from typing import Optional

import pandas as pd


def _is_numeric(series: pd.Series) -> bool:
    """Check if series is numeric (int, float, or bool)."""
    return pd.api.types.is_numeric_dtype(series)


def _is_temporal(series: pd.Series) -> bool:
    """Check if series is datetime/timedelta."""
    return pd.api.types.is_datetime64_any_dtype(series) or pd.api.types.is_timedelta64_dtype(series)


def _format_val(v) -> str:
    """Format a scalar for display."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    if isinstance(v, float):
        return f"{v:.4f}"
    return str(v)


def _profile_numeric(series: pd.Series) -> list[str]:
    """Profile a numeric column."""
    lines: list[str] = []
    missing = int(series.isna().sum())
    total = len(series)
    missing_pct = missing / total * 100 if total else 0.0
    lines.append(f"missing={missing} ({missing_pct:.1f}%)")

    valid = series.dropna()
    if len(valid) == 0:
        lines.append("all values are NULL")
        return lines

    # Core stats
    try:
        lines.append(f"min={_format_val(valid.min())}")
        lines.append(f"max={_format_val(valid.max())}")
        lines.append(f"mean={_format_val(valid.mean())}")
        lines.append(f"median={_format_val(valid.median())}")
        lines.append(f"std={_format_val(valid.std())}")
        # skip quantiles
        # q1 = valid.quantile(0.25)
        # q3 = valid.quantile(0.75)
        # lines.append(f"Q1={_format_val(q1)}")
        # lines.append(f"Q3={_format_val(q3)}")
    except Exception:
        pass

    # Special values
    try:
        zero_cnt = int((valid == 0).sum())
        if zero_cnt > 0:
            lines.append(f"zeros={zero_cnt} ({zero_cnt / len(valid) * 100:.1f}%)")
        # skip negatives
        # if (valid < 0).any():
        #     neg_cnt = int((valid < 0).sum())
        #     lines.append(f"negatives={neg_cnt} ({neg_cnt / len(valid) * 100:.1f}%)")
    except Exception:
        pass

    # Skew hint (mean vs median comparison)
    try:
        mean = valid.mean()
        median = valid.median()
        if abs(mean - median) > 0.01 * (valid.max() - valid.min() + 1e-10):
            if mean > median:
                lines.append("skew=right (mean>median)")
            else:
                lines.append("skew=left (mean<median)")
        else:
            lines.append("skew≈symmetric")
    except Exception:
        pass

    return lines


def _profile_text(series: pd.Series) -> list[str]:
    """Profile a text/categorical column."""
    lines: list[str] = []
    missing = int(series.isna().sum())
    total = len(series)
    missing_pct = missing / total * 100 if total else 0.0
    lines.append(f"missing={missing} ({missing_pct:.1f}%)")

    valid = series.dropna()
    if len(valid) == 0:
        lines.append("all values are NULL")
        return lines

    unique = int(valid.nunique(dropna=False))
    unique_pct = unique / len(valid) * 100 if len(valid) else 0.0
    lines.append(f"unique={unique} ({unique_pct:.1f}%)")

    # String length stats (if string type)
    if valid.dtype == object or pd.api.types.is_string_dtype(valid.dtype):
        try:
            str_lengths = valid.astype(str).str.len()
            lines.append(f"str_len_min={int(str_lengths.min())}")
            lines.append(f"str_len_max={int(str_lengths.max())}")
            lines.append(f"str_len_mean={str_lengths.mean():.1f}")
        except Exception:
            pass

    # Empty string count
    try:
        empty_cnt = int((valid.astype(str).str.strip() == "").sum())
        if empty_cnt > 0:
            lines.append(f"empty_str={empty_cnt} ({empty_cnt / len(valid) * 100:.1f}%)")
    except Exception:
        pass

    # Top-5 most frequent values
    try:
        top5 = valid.value_counts().head(5)
        if len(top5) > 0 and len(top5) < len(valid):
            top_items = []
            for val, cnt in top5.items():
                val_str = str(val)[:60]  # truncate long values
                pct = cnt / len(valid) * 100
                top_items.append(f"'{val_str}'={cnt} ({pct:.1f}%)")
            lines.append("top5: [" + ", ".join(top_items) + "]")
    except Exception:
        pass

    return lines


def _profile_temporal(series: pd.Series) -> list[str]:
    """Profile a datetime/timedelta column."""
    lines: list[str] = []
    missing = int(series.isna().sum())
    total = len(series)
    missing_pct = missing / total * 100 if total else 0.0
    lines.append(f"missing={missing} ({missing_pct:.1f}%)")

    valid = series.dropna()
    if len(valid) == 0:
        lines.append("all values are NULL")
        return lines

    try:
        lines.append(f"min={_format_val(valid.min())}")
        lines.append(f"max={_format_val(valid.max())}")
        lines.append(f"range={(valid.max() - valid.min())}")
    except Exception:
        pass

    return lines


def df_profile_markdown(df: Optional[pd.DataFrame], enrich=False) -> str:
    """Return a compact markdown summary for a DataFrame.

    When enrich=False (default), produces minimal output:
      Total: {rows} rows * {cols} columns
      - For each column: missing={n}, unique={n}

    When enrich=True, produces detailed per-column statistics:
      Numerical columns: min, max, mean, median, std, Q1, Q3, zeros, negatives, skew
      Text columns: missing, unique, string length stats, empty string count, top-5 values
      Temporal columns: min, max, range

    Args:
        df: pandas DataFrame or None
        enrich: If True, include richer per-column statistics

    Returns:
        A markdown-formatted string (can be empty on error).
    """
    if df is None:
        return ""

    try:
        rows, cols = df.shape
    except Exception:
        return ""

    lines: list[str] = []
    lines.append(f"Total: {rows} rows * {cols} columns")
    lines.append("")

    if not enrich:
        # Legacy minimal output
        for col in df.columns:
            try:
                series = df[col]
                missing = int(series.isna().sum())
                unique = int(series.nunique(dropna=True))
                lines.append(f"- **{col}**: missing={missing}, unique={unique}")
            except Exception:
                lines.append(f"- **{col}**: missing=?, unique=?")
    else:
        # Rich profile output
        for col in df.columns:
            try:
                series = df[col]
                dtype_str = str(series.dtype)

                if _is_temporal(series):
                    stats = _profile_temporal(series)
                    dtype_tag = "temporal"
                elif _is_numeric(series):
                    stats = _profile_numeric(series)
                    dtype_tag = "numeric"
                else:
                    stats = _profile_text(series)
                    dtype_tag = "text"

                col_line = f"- **{col}** ({dtype_tag}, {dtype_str}): " + ", ".join(stats)
                lines.append(col_line)
            except Exception:
                lines.append(f"- **{col}**: profile_error")

    return "\n".join(lines)
