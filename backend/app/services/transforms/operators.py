"""Atomic, composable tabular transformation operators for pandas DataFrames."""

import re
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd


def op_impute(df: pd.DataFrame, params: Dict[str, Any]) -> Tuple[pd.DataFrame, str]:
    """Impute missing values using statistical strategies or constant values."""
    cols = params.get("columns", [])
    if isinstance(cols, str):
        cols = [cols]
    if not cols or cols == ["all"] or cols == "all":
        cols = list(df.columns)

    strategy = str(params.get("strategy", "mean")).lower()
    fill_value = params.get("fill_value")

    valid_cols = [c for c in cols if c in df.columns]
    if not valid_cols:
        return df, "No matching columns found for imputation."

    df_out = df.copy()
    initial_nulls = int(df_out[valid_cols].isna().sum().sum())

    if strategy == "drop":
        df_out = df_out.dropna(subset=valid_cols)
        dropped_count = len(df) - len(df_out)
        return df_out, f"Dropped {dropped_count} rows with nulls in {valid_cols}."

    for col in valid_cols:
        series = df_out[col]
        if series.isna().sum() == 0:
            continue

        if strategy == "mean":
            if pd.api.types.is_numeric_dtype(series):
                mean_val = series.mean()
                df_out[col] = series.fillna(mean_val)
        elif strategy == "median":
            if pd.api.types.is_numeric_dtype(series):
                median_val = series.median()
                df_out[col] = series.fillna(median_val)
        elif strategy == "mode":
            mode_series = series.mode()
            if not mode_series.empty:
                df_out[col] = series.fillna(mode_series.iloc[0])
        elif strategy == "constant":
            if fill_value is not None:
                # If target is numeric, attempt numeric conversion of constant
                if pd.api.types.is_numeric_dtype(series):
                    try:
                        fv = float(fill_value) if "." in str(fill_value) else int(fill_value)
                    except ValueError:
                        fv = fill_value
                else:
                    fv = fill_value
                df_out[col] = series.fillna(fv)
        elif strategy == "ffill":
            df_out[col] = series.ffill()
        elif strategy == "bfill":
            df_out[col] = series.bfill()

    final_nulls = int(df_out[valid_cols].isna().sum().sum())
    imputed_count = max(0, initial_nulls - final_nulls)
    return df_out, f"Imputed {imputed_count} missing cells in {valid_cols} using '{strategy}'."


def op_drop_columns(df: pd.DataFrame, params: Dict[str, Any]) -> Tuple[pd.DataFrame, str]:
    """Remove designated columns from the DataFrame."""
    cols = params.get("columns", [])
    if isinstance(cols, str):
        cols = [cols]
    existing = [c for c in cols if c in df.columns]
    if not existing:
        return df, "No specified columns existed to drop."

    df_out = df.drop(columns=existing)
    return df_out, f"Dropped {len(existing)} column(s): {', '.join(existing)}."


def op_rename_columns(df: pd.DataFrame, params: Dict[str, Any]) -> Tuple[pd.DataFrame, str]:
    """Rename columns according to key-value mappings."""
    mapping = params.get("mapping", {})
    if not isinstance(mapping, dict):
        return df, "Invalid mapping dictionary provided for column renaming."

    clean_map = {k: v for k, v in mapping.items() if k in df.columns and str(v).strip()}
    if not clean_map:
        return df, "No applicable column rename pairs found."

    df_out = df.rename(columns=clean_map)
    summary_parts = [f"'{k}' -> '{v}'" for k, v in clean_map.items()]
    return df_out, f"Renamed columns: {', '.join(summary_parts)}."


def op_cast_type(df: pd.DataFrame, params: Dict[str, Any]) -> Tuple[pd.DataFrame, str]:
    """Cast column data type to integer, float, string, boolean, or datetime."""
    col = params.get("column")
    target_type = str(params.get("target_type", "")).lower()

    if not col or col not in df.columns:
        return df, f"Column '{col}' not found for type cast."

    df_out = df.copy()
    try:
        if target_type in ["int", "integer", "int64"]:
            df_out[col] = pd.to_numeric(df_out[col], errors="coerce").astype("Int64")
        elif target_type in ["float", "float64"]:
            df_out[col] = pd.to_numeric(df_out[col], errors="coerce")
        elif target_type in ["str", "string"]:
            df_out[col] = df_out[col].astype(str).replace({"nan": None, "None": None})
        elif target_type in ["bool", "boolean"]:
            df_out[col] = df_out[col].astype(bool)
        elif target_type in ["datetime", "date"]:
            df_out[col] = pd.to_datetime(df_out[col], errors="coerce")
        else:
            return df, f"Unsupported target type '{target_type}'."
        return df_out, f"Cast column '{col}' to '{target_type}'."
    except Exception as e:
        return df, f"Failed to cast column '{col}' to '{target_type}': {str(e)}."


def op_text_transform(df: pd.DataFrame, params: Dict[str, Any]) -> Tuple[pd.DataFrame, str]:
    """Perform text sanitization (trim, casing, regex replace)."""
    cols = params.get("columns", [])
    if isinstance(cols, str):
        cols = [cols]
    operation = str(params.get("operation", "trim")).lower()
    pattern = params.get("pattern", "")
    replacement = params.get("replacement", "")

    valid_cols = [c for c in cols if c in df.columns]
    if not valid_cols:
        return df, "No valid text columns specified."

    df_out = df.copy()
    for col in valid_cols:
        s = df_out[col].astype(str)
        if operation == "trim":
            df_out[col] = s.str.strip()
        elif operation == "lowercase":
            df_out[col] = s.str.lower()
        elif operation == "uppercase":
            df_out[col] = s.str.upper()
        elif operation == "titlecase":
            df_out[col] = s.str.title()
        elif operation == "regex_replace":
            if pattern:
                df_out[col] = s.str.replace(pattern, replacement, regex=True)

        # Restore genuine nulls
        df_out[col] = df_out[col].replace({"nan": None, "None": None})

    return df_out, f"Applied '{operation}' text transformation to {valid_cols}."


def op_drop_duplicates(df: pd.DataFrame, params: Dict[str, Any]) -> Tuple[pd.DataFrame, str]:
    """Remove duplicate rows with optional subset column keys."""
    subset = params.get("subset")
    if subset and isinstance(subset, list):
        subset = [c for c in subset if c in df.columns]
        if not subset:
            subset = None
    else:
        subset = None

    keep = params.get("keep", "first")
    if keep not in ["first", "last", False]:
        keep = "first"

    initial_len = len(df)
    df_out = df.drop_duplicates(subset=subset, keep=keep)
    dropped_count = initial_len - len(df_out)
    subset_desc = f" based on {subset}" if subset else " across all columns"
    return df_out, f"Removed {dropped_count} duplicate row(s){subset_desc}."


def op_handle_outliers(df: pd.DataFrame, params: Dict[str, Any]) -> Tuple[pd.DataFrame, str]:
    """Detect and treat numerical outliers via Interquartile Range (IQR) or Z-score."""
    cols = params.get("columns", [])
    if isinstance(cols, str):
        cols = [cols]
    method = str(params.get("method", "iqr")).lower()
    action = str(params.get("action", "clip")).lower()  # 'clip' or 'drop'
    iqr_factor = float(params.get("factor", 1.5))
    z_threshold = float(params.get("threshold", 3.0))

    valid_cols = [
        c
        for c in cols
        if c in df.columns
        and pd.api.types.is_numeric_dtype(df[c])
        and not pd.api.types.is_bool_dtype(df[c])
    ]
    if not valid_cols:
        return df, "No valid numeric columns identified for outlier treatment."

    df_out = df.copy()
    initial_len = len(df_out)
    total_clipped = 0

    if action == "drop":
        keep_mask = pd.Series(True, index=df_out.index)
        for col in valid_cols:
            clean = df_out[col].dropna()
            if len(clean) < 4:
                continue
            if method == "zscore":
                mean_val = clean.mean()
                std_val = clean.std()
                if std_val > 0:
                    z_scores = np.abs((df_out[col] - mean_val) / std_val)
                    keep_mask &= z_scores <= z_threshold
            else:  # IQR
                q25 = clean.quantile(0.25)
                q75 = clean.quantile(0.75)
                iqr = q75 - q25
                lower_bound = q25 - (iqr_factor * iqr)
                upper_bound = q75 + (iqr_factor * iqr)
                keep_mask &= (df_out[col] >= lower_bound) & (df_out[col] <= upper_bound)

        df_out = df_out[keep_mask]
        dropped_count = initial_len - len(df_out)
        return df_out, f"Dropped {dropped_count} outlier row(s) in {valid_cols} using {method.upper()}."

    else:  # Clip to bounds
        for col in valid_cols:
            clean = df_out[col].dropna()
            if len(clean) < 4:
                continue
            if method == "zscore":
                mean_val = clean.mean()
                std_val = clean.std()
                if std_val > 0:
                    lower_bound = mean_val - (z_threshold * std_val)
                    upper_bound = mean_val + (z_threshold * std_val)
                else:
                    continue
            else:  # IQR
                q25 = clean.quantile(0.25)
                q75 = clean.quantile(0.75)
                iqr = q75 - q25
                lower_bound = q25 - (iqr_factor * iqr)
                upper_bound = q75 + (iqr_factor * iqr)

            outlier_count = int(
                ((df_out[col] < lower_bound) | (df_out[col] > upper_bound)).sum()
            )
            total_clipped += outlier_count
            df_out[col] = df_out[col].clip(lower=lower_bound, upper=upper_bound)

        return (
            df_out,
            f"Clipped {total_clipped} outlier values in {valid_cols} to bounds using {method.upper()}.",
        )


def op_filter_rows(df: pd.DataFrame, params: Dict[str, Any]) -> Tuple[pd.DataFrame, str]:
    """Filter rows satisfying relational or text search conditions."""
    col = params.get("column")
    op = str(params.get("operator", "==")).lower()
    value = params.get("value")

    if not col or col not in df.columns:
        return df, f"Filter column '{col}' not found."

    df_out = df.copy()
    initial_len = len(df_out)

    if op == "is_null":
        mask = df_out[col].isna()
    elif op == "not_null":
        mask = df_out[col].notna()
    elif op in ["contains", "like"]:
        mask = df_out[col].astype(str).str.contains(str(value), case=False, na=False)
    elif op in ["not_contains"]:
        mask = ~df_out[col].astype(str).str.contains(str(value), case=False, na=False)
    else:
        # Numeric or equality filter
        target_val = value
        if pd.api.types.is_numeric_dtype(df_out[col]):
            try:
                target_val = float(value) if "." in str(value) else int(value)
            except (ValueError, TypeError):
                target_val = value

        if op == "==":
            mask = df_out[col] == target_val
        elif op == "!=":
            mask = df_out[col] != target_val
        elif op == ">":
            mask = df_out[col] > target_val
        elif op == ">=":
            mask = df_out[col] >= target_val
        elif op == "<":
            mask = df_out[col] < target_val
        elif op == "<=":
            mask = df_out[col] <= target_val
        else:
            return df, f"Unsupported filter operator '{op}'."

    df_out = df_out[mask]
    retained_len = len(df_out)
    return (
        df_out,
        f"Filtered rows where '{col}' {op} '{value}': retained {retained_len}/{initial_len} rows.",
    )


def op_derive_column(df: pd.DataFrame, params: Dict[str, Any]) -> Tuple[pd.DataFrame, str]:
    """Derive a new numerical feature using arithmetic operations."""
    new_col = str(params.get("new_column", "")).strip()
    operation = str(params.get("operation", "add")).lower()
    op_a = params.get("operand_a")
    op_b = params.get("operand_b")

    if not new_col:
        return df, "New column name cannot be empty."
    if not op_a or op_a not in df.columns:
        return df, f"Operand column '{op_a}' not found."

    df_out = df.copy()
    val_a = pd.to_numeric(df_out[op_a], errors="coerce")

    # Operand B can be another column or a scalar
    if isinstance(op_b, str) and op_b in df.columns:
        val_b = pd.to_numeric(df_out[op_b], errors="coerce")
        b_label = f"'{op_b}'"
    else:
        try:
            val_b = float(op_b) if "." in str(op_b) else int(op_b)
            b_label = str(op_b)
        except (ValueError, TypeError):
            return df, f"Invalid operand B '{op_b}'."

    try:
        if operation in ["add", "+"]:
            df_out[new_col] = val_a + val_b
        elif operation in ["subtract", "-"]:
            df_out[new_col] = val_a - val_b
        elif operation in ["multiply", "*"]:
            df_out[new_col] = val_a * val_b
        elif operation in ["divide", "/"]:
            # Guard against division by zero
            denom = val_b.replace(0, np.nan) if isinstance(val_b, pd.Series) else (np.nan if val_b == 0 else val_b)
            df_out[new_col] = val_a / denom
        else:
            return df, f"Unsupported derivation operation '{operation}'."

        return df_out, f"Derived column '{new_col}' = '{op_a}' {operation} {b_label}."
    except Exception as e:
        return df, f"Failed to derive column '{new_col}': {str(e)}."


# Registry mapping step_type strings to operator functions
OPERATORS_REGISTRY = {
    "impute": op_impute,
    "drop_columns": op_drop_columns,
    "rename_columns": op_rename_columns,
    "cast_type": op_cast_type,
    "text_transform": op_text_transform,
    "drop_duplicates": op_drop_duplicates,
    "handle_outliers": op_handle_outliers,
    "filter_rows": op_filter_rows,
    "derive_column": op_derive_column,
}
