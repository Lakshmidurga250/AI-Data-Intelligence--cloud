"""High-performance analytical aggregation and query execution engine."""

import time
from typing import Any, Dict, List
import numpy as np
import pandas as pd

from app.schemas.dashboard import (
    AnalyticsQueryRequest,
    AnalyticsQueryResponse,
    FilterSpec,
    MetricSpec,
)
from app.services.ingestion.parser import sanitize_records_for_json


def apply_query_filters(df: pd.DataFrame, filters: List[FilterSpec]) -> pd.DataFrame:
    """Apply declarative filter expressions sequentially to DataFrame."""
    if not filters or df.empty:
        return df

    filtered = df
    for flt in filters:
        col = flt.column
        if col not in filtered.columns:
            continue

        op = flt.operator
        val = flt.value

        try:
            if op == "==":
                filtered = filtered[filtered[col] == val]
            elif op == "!=":
                filtered = filtered[filtered[col] != val]
            elif op == ">":
                num_val = float(val) if val is not None else 0
                filtered = filtered[pd.to_numeric(filtered[col], errors="coerce") > num_val]
            elif op == "<":
                num_val = float(val) if val is not None else 0
                filtered = filtered[pd.to_numeric(filtered[col], errors="coerce") < num_val]
            elif op == ">=":
                num_val = float(val) if val is not None else 0
                filtered = filtered[pd.to_numeric(filtered[col], errors="coerce") >= num_val]
            elif op == "<=":
                num_val = float(val) if val is not None else 0
                filtered = filtered[pd.to_numeric(filtered[col], errors="coerce") <= num_val]
            elif op == "in":
                target_list = val if isinstance(val, list) else [val]
                filtered = filtered[filtered[col].isin(target_list)]
            elif op == "contains":
                filtered = filtered[filtered[col].astype(str).str.contains(str(val), case=False, na=False)]
            elif op == "is_null":
                filtered = filtered[filtered[col].isna()]
            elif op == "not_null":
                filtered = filtered[filtered[col].notna()]
        except Exception:
            # Skip invalid filter step gracefully rather than halting execution
            continue

    return filtered


def apply_temporal_bucketing(
    df: pd.DataFrame,
    time_column: str,
    time_grain: str,
) -> pd.DataFrame:
    """Bucket timestamp column to requested temporal frequency format."""
    if time_column not in df.columns or df.empty:
        return df

    res = df.copy()
    dt_series = pd.to_datetime(res[time_column], errors="coerce")

    if time_grain == "day":
        res[time_column] = dt_series.dt.strftime("%Y-%m-%d")
    elif time_grain == "week":
        res[time_column] = dt_series.dt.strftime("%Y-W%U")
    elif time_grain == "month":
        res[time_column] = dt_series.dt.strftime("%Y-%m")
    elif time_grain == "year":
        res[time_column] = dt_series.dt.strftime("%Y")

    res[time_column] = res[time_column].fillna("Unknown")
    return res


def execute_analytics_query(
    df: pd.DataFrame,
    request: AnalyticsQueryRequest,
) -> AnalyticsQueryResponse:
    """Execute analytical aggregation query against an in-memory DataFrame."""
    start_time = time.perf_counter()

    if df.empty:
        return AnalyticsQueryResponse(
            columns=[],
            data=[],
            row_count=0,
            execution_time_ms=0.0,
        )

    # 1. Apply pre-filters
    work_df = apply_query_filters(df, request.filters or [])

    # 2. Apply temporal bucketing if requested
    dimensions = list(request.dimensions or [])
    if request.time_column and request.time_grain and request.time_column in work_df.columns:
        work_df = apply_temporal_bucketing(work_df, request.time_column, request.time_grain)
        if request.time_column not in dimensions:
            dimensions.append(request.time_column)

    # Filter dimensions to columns existing in work_df
    valid_dims = [d for d in dimensions if d in work_df.columns]

    # 3. Handle Grouping & Aggregations
    if valid_dims:
        # Dimensional aggregation
        grouped = work_df.groupby(valid_dims, as_index=False, dropna=False)
        result_cols = list(valid_dims)
        aggregated_dict: Dict[str, Any] = {}

        # First copy dimension columns
        dim_df = grouped.first()[valid_dims]

        metric_series_list = []
        for metric in request.metrics:
            out_name = metric.alias or (
                f"{metric.aggregation}_{metric.column}" if metric.column != "*" else f"{metric.aggregation}_count"
            )
            col = metric.column
            agg_type = metric.aggregation

            if agg_type == "count":
                if col == "*" or col not in work_df.columns:
                    s = grouped.size()["size"]
                else:
                    s = grouped[col].count()[col]
            elif agg_type == "distinct_count":
                target_col = col if col in work_df.columns else work_df.columns[0]
                s = grouped[target_col].nunique()[target_col]
            else:
                if col in work_df.columns:
                    num_series = pd.to_numeric(work_df[col], errors="coerce")
                    temp_df = work_df[valid_dims].copy()
                    temp_df["_val"] = num_series
                    temp_grouped = temp_df.groupby(valid_dims, as_index=False, dropna=False)

                    if agg_type == "sum":
                        s = temp_grouped["_val"].sum()["_val"]
                    elif agg_type == "avg":
                        s = temp_grouped["_val"].mean()["_val"]
                    elif agg_type == "min":
                        s = temp_grouped["_val"].min()["_val"]
                    elif agg_type == "max":
                        s = temp_grouped["_val"].max()["_val"]
                    else:
                        s = temp_grouped["_val"].sum()["_val"]
                else:
                    s = pd.Series([0] * len(dim_df))

            s.name = out_name
            metric_series_list.append(s)
            result_cols.append(out_name)

        # Concatenate dimensions and calculated metric columns
        agg_result_df = pd.concat([dim_df] + metric_series_list, axis=1)

    else:
        # Non-dimensional KPI single summary row
        row_dict: Dict[str, Any] = {}
        result_cols = []
        for metric in request.metrics:
            out_name = metric.alias or (
                f"{metric.aggregation}_{metric.column}" if metric.column != "*" else f"{metric.aggregation}_count"
            )
            col = metric.column
            agg_type = metric.aggregation

            if agg_type == "count":
                val = len(work_df) if (col == "*" or col not in work_df.columns) else int(work_df[col].count())
            elif agg_type == "distinct_count":
                target_col = col if col in work_df.columns else work_df.columns[0]
                val = int(work_df[target_col].nunique())
            else:
                if col in work_df.columns:
                    num_series = pd.to_numeric(work_df[col], errors="coerce").dropna()
                    if num_series.empty:
                        val = 0.0
                    elif agg_type == "sum":
                        val = float(num_series.sum())
                    elif agg_type == "avg":
                        val = float(num_series.mean())
                    elif agg_type == "min":
                        val = float(num_series.min())
                    elif agg_type == "max":
                        val = float(num_series.max())
                    else:
                        val = float(num_series.sum())
                else:
                    val = 0.0

            row_dict[out_name] = val
            result_cols.append(out_name)

        agg_result_df = pd.DataFrame([row_dict])

    # 4. Sorting
    sort_by_col = request.sort_by
    if sort_by_col and sort_by_col in agg_result_df.columns:
        ascending = (request.sort_order == "asc")
        agg_result_df = agg_result_df.sort_values(by=sort_by_col, ascending=ascending)
    elif len(agg_result_df) > 1 and len(result_cols) > len(valid_dims):
        # Default: sort descending by the primary metric column
        primary_metric_col = result_cols[len(valid_dims)]
        agg_result_df = agg_result_df.sort_values(by=primary_metric_col, ascending=False)

    # 5. Limit
    limit = request.limit or 500
    agg_result_df = agg_result_df.head(limit)

    # 6. JSON serialization sanitization
    raw_records = agg_result_df.to_dict(orient="records")
    clean_records = sanitize_records_for_json(raw_records)

    elapsed_ms = (time.perf_counter() - start_time) * 1000.0

    return AnalyticsQueryResponse(
        columns=result_cols,
        data=clean_records,
        row_count=len(clean_records),
        execution_time_ms=round(elapsed_ms, 2),
    )
