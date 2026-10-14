"""Statistical profiling and dataset health analysis engine."""

import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

from app.schemas.profiling import (
    CategoricalColumnStats,
    ColumnFullProfile,
    CorrelationPair,
    DatasetProfileResponse,
    NumericColumnStats,
    ValueFrequency,
)
from app.services.ingestion.parser import read_file_to_dataframe


def safe_float(val: Any) -> Optional[float]:
    """Safely convert numerical metric to float, mapping NaN/inf to None."""
    if val is None or pd.isna(val):
        return None
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return round(f, 4)
    except Exception:
        return None


def profile_dataframe(
    df: pd.DataFrame, dataset_id: str, dataset_name: str
) -> DatasetProfileResponse:
    """Compute exhaustive statistical metrics and correlation matrix for a DataFrame."""
    row_count = int(len(df))
    column_count = int(len(df.columns))

    memory_bytes = int(df.memory_usage(deep=True).sum()) if row_count > 0 else 0
    duplicate_rows = int(df.duplicated().sum()) if row_count > 0 else 0
    duplicate_percentage = (
        round((duplicate_rows / max(row_count, 1)) * 100.0, 2) if row_count > 0 else 0.0
    )

    total_cells = row_count * max(column_count, 1)
    total_nulls = int(df.isna().sum().sum())
    completeness_score = (
        round(((total_cells - total_nulls) / max(total_cells, 1)) * 100.0, 2)
        if total_cells > 0
        else 100.0
    )

    columns_profiles: List[ColumnFullProfile] = []

    for col in df.columns:
        col_name = str(col)
        series = df[col]
        dtype_str = str(series.dtype)
        null_count = int(series.isna().sum())
        null_pct = round((null_count / max(row_count, 1)) * 100.0, 2)
        total_count = row_count - null_count

        is_numeric = (
            pd.api.types.is_numeric_dtype(series)
            and not pd.api.types.is_bool_dtype(series)
        )
        is_categorical = not is_numeric

        numeric_stats: Optional[NumericColumnStats] = None
        categorical_stats: Optional[CategoricalColumnStats] = None

        if is_numeric:
            clean_series = series.dropna()
            if len(clean_series) > 0:
                mean_val = safe_float(clean_series.mean())
                std_val = safe_float(clean_series.std())
                min_val = safe_float(clean_series.min())
                max_val = safe_float(clean_series.max())
                var_val = safe_float(clean_series.var())
                median_val = safe_float(clean_series.median())
                q25_val = safe_float(clean_series.quantile(0.25))
                q75_val = safe_float(clean_series.quantile(0.75))
                skew_val = safe_float(clean_series.skew()) if len(clean_series) > 2 else None

                zeros_count = int((clean_series == 0).sum())
                negatives_count = int((clean_series < 0).sum())

                numeric_stats = NumericColumnStats(
                    min=min_val,
                    max=max_val,
                    mean=mean_val,
                    std=std_val,
                    variance=var_val,
                    median=median_val,
                    q25=q25_val,
                    q75=q75_val,
                    skew=skew_val,
                    zeros_count=zeros_count,
                    negatives_count=negatives_count,
                )
            else:
                numeric_stats = NumericColumnStats()

        else:
            clean_series = series.dropna().astype(str)
            distinct_count = int(clean_series.nunique())
            distinct_pct = round((distinct_count / max(len(clean_series), 1)) * 100.0, 2)

            top_frequencies: List[ValueFrequency] = []
            val_counts = clean_series.value_counts().head(5)
            for val, cnt in val_counts.items():
                pct = round((cnt / max(len(clean_series), 1)) * 100.0, 2)
                top_frequencies.append(
                    ValueFrequency(
                        value=str(val)[:100],
                        count=int(cnt),
                        percentage=pct,
                    )
                )

            lengths = clean_series.str.len()
            min_len = int(lengths.min()) if len(lengths) > 0 else 0
            max_len = int(lengths.max()) if len(lengths) > 0 else 0
            avg_len = safe_float(lengths.mean()) if len(lengths) > 0 else 0.0

            categorical_stats = CategoricalColumnStats(
                distinct_count=distinct_count,
                distinct_percentage=distinct_pct,
                top_values=top_frequencies,
                min_length=min_len,
                max_length=max_len,
                avg_length=avg_len,
            )

        columns_profiles.append(
            ColumnFullProfile(
                name=col_name,
                data_type=dtype_str,
                total_count=total_count,
                null_count=null_count,
                null_percentage=null_pct,
                is_numeric=is_numeric,
                is_categorical=is_categorical,
                numeric_stats=numeric_stats,
                categorical_stats=categorical_stats,
            )
        )

    # Compute correlation matrix for numeric columns
    correlations: List[CorrelationPair] = []
    numeric_cols = [
        col
        for col in df.columns
        if pd.api.types.is_numeric_dtype(df[col]) and not pd.api.types.is_bool_dtype(df[col])
    ]

    if len(numeric_cols) >= 2 and row_count >= 2:
        try:
            corr_matrix = df[numeric_cols].corr(method="pearson")
            col_list = list(numeric_cols)
            for i in range(len(col_list)):
                for j in range(i + 1, len(col_list)):
                    c_a, c_b = col_list[i], col_list[j]
                    raw_corr = corr_matrix.loc[c_a, c_b]
                    cleaned_coeff = safe_float(raw_corr)
                    if cleaned_coeff is not None:
                        correlations.append(
                            CorrelationPair(
                                column_a=str(c_a),
                                column_b=str(c_b),
                                coefficient=cleaned_coeff,
                            )
                        )
        except Exception:
            correlations = []

    # Sort correlations by absolute magnitude descending
    correlations.sort(key=lambda x: abs(x.coefficient), reverse=True)

    return DatasetProfileResponse(
        dataset_id=dataset_id,
        dataset_name=dataset_name,
        row_count=row_count,
        column_count=column_count,
        memory_bytes=memory_bytes,
        duplicate_rows_count=duplicate_rows,
        duplicate_rows_percentage=duplicate_percentage,
        completeness_score=completeness_score,
        columns=columns_profiles,
        correlations=correlations,
        profiled_at=datetime.now(timezone.utc).isoformat(),
    )


def profile_dataset_file(
    file_path: Path,
    format_type: str,
    dataset_id: str,
    dataset_name: str,
) -> DatasetProfileResponse:
    """Read dataset from storage and perform exhaustive statistical profiling."""
    df = read_file_to_dataframe(file_path, format_type)
    return profile_dataframe(df, dataset_id, dataset_name)
