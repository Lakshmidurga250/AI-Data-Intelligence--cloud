"""Conversational analytics, natural language query translation, and automated anomaly discovery engine."""

import math
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

from app.schemas.assistant import InsightItem, NLQueryTranslation


def sanitize_val(val: Any) -> Any:
    """Safely sanitize pandas/numpy values for JSON serialization."""
    if val is None:
        return None
    if isinstance(val, (np.floating, float)):
        if math.isnan(val) or math.isinf(val):
            return None
        return round(float(val), 4)
    if isinstance(val, (np.integer, int)):
        return int(val)
    if isinstance(val, (np.bool_, bool)):
        return bool(val)
    if isinstance(val, (pd.Timestamp, datetime)):
        return val.isoformat()
    return str(val)


def classify_user_intent(prompt: str) -> str:
    """Classifies user interaction intent into one of the core platform capabilities."""
    p = prompt.strip().lower()

    # Overview & Dataset Summary (checked before nl_query so 'summarize' doesn't trigger 'sum')
    if any(k in p for k in [
        "summarize", "summary", "overview", "describe dataset", "describe columns",
        "schema", "what is this data", "dataset stats", "describe table"
    ]):
        return "data_summary"

    # Anomaly / Quality / Outlier discovery
    if any(k in p for k in [
        "anomaly", "anomalies", "outlier", "outliers", "defect", "issues",
        "missing value", "null count", "quality score", "discover insights",
        "health check", "skew", "distribution check", "imbalance"
    ]):
        return "anomaly_insights"

    # Tabular Aggregations / Queries
    if any(k in p for k in [
        "group by", "grouped by", "breakdown", "top 5", "top 10",
        "filter where", "show rows", "how many", "average", "mean"
    ]) or re.search(r"\b(avg|sum|count|max|min|maximum|minimum|highest|lowest|total)\b", p):
        return "nl_query"

    # Platform navigation & capability guidance
    if any(k in p for k in [
        "how do i", "how to", "where is", "navigate", "help", "guide",
        "pipeline", "etl", "automl", "celery", "schedule", "lineage",
        "governance", "dashboard", "api"
    ]):
        return "navigation"

    return "general"


def discover_dataset_insights(df: pd.DataFrame, dataset_name: str) -> List[InsightItem]:
    """Automated anomaly, skewness, missing value, correlation, and trend discovery."""
    insights: List[InsightItem] = []
    row_count = len(df)
    if row_count == 0:
        return [
            InsightItem(
                insight_type="distribution_anomaly",
                severity="critical",
                column=None,
                title="Empty Dataset Quarantined",
                description="Dataset contains 0 tabular rows.",
                metric_value=0,
                recommendation="Verify upstream data source or ingestion streaming job.",
            )
        ]

    # 1. Missing Values Severity Inspection
    for col in df.columns:
        null_count = int(df[col].isnull().sum())
        null_pct = round((null_count / row_count) * 100, 2)
        if null_pct > 50.0:
            insights.append(
                InsightItem(
                    insight_type="missing_values",
                    severity="critical",
                    column=col,
                    title=f"Severe Missingness in '{col}' ({null_pct}%)",
                    description=f"Column has {null_count:,} missing values out of {row_count:,} total records.",
                    metric_value=null_pct,
                    recommendation=f"Consider dropping '{col}' or applying median/mode imputation via Transformation Studio.",
                )
            )
        elif null_pct > 15.0:
            insights.append(
                InsightItem(
                    insight_type="missing_values",
                    severity="high",
                    column=col,
                    title=f"High Missingness in '{col}' ({null_pct}%)",
                    description=f"{null_count:,} records have null values for this feature.",
                    metric_value=null_pct,
                    recommendation="Impute with constant or forward-fill before training ML models.",
                )
            )

    # 2. Numerical Skewness & Outliers
    num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    for col in num_cols:
        series = df[col].dropna()
        if len(series) < 5:
            continue

        # Check for zero inflation
        zero_count = int((series == 0).sum())
        zero_pct = round((zero_count / len(series)) * 100, 2)
        if zero_pct > 40.0 and len(series.unique()) > 2:
            insights.append(
                InsightItem(
                    insight_type="distribution_anomaly",
                    severity="medium",
                    column=col,
                    title=f"Zero-Inflation Detected in '{col}' ({zero_pct}%)",
                    description=f"{zero_count:,} rows contain zero values in continuous numeric column.",
                    metric_value=zero_pct,
                    recommendation="Evaluate if zeros represent missing defaults or distinct operational states.",
                )
            )

        # Skewness
        try:
            skew = float(series.skew())
            if abs(skew) > 2.5:
                direction = "positive (right-tailed)" if skew > 0 else "negative (left-tailed)"
                insights.append(
                    InsightItem(
                        insight_type="distribution_anomaly",
                        severity="medium",
                        column=col,
                        title=f"Heavy Distribution Skewness in '{col}' (skew={round(skew, 2)})",
                        description=f"Distribution is heavily {direction}. May bias linear and distance-based estimators.",
                        metric_value=round(skew, 2),
                        recommendation="Apply log or Box-Cox transformation in Phase 4 transformations.",
                    )
                )
        except Exception:
            pass

        # IQR Outliers
        try:
            q25 = float(series.quantile(0.25))
            q75 = float(series.quantile(0.75))
            iqr = q75 - q25
            if iqr > 0:
                outliers = ((series < (q25 - 1.5 * iqr)) | (series > (q75 + 1.5 * iqr))).sum()
                outlier_pct = round((outliers / len(series)) * 100, 2)
                if outlier_pct > 8.0:
                    insights.append(
                        InsightItem(
                            insight_type="outlier_risk",
                            severity="high",
                            column=col,
                            title=f"High Outlier Frequency in '{col}' ({outlier_pct}%)",
                            description=f"{outliers:,} observations fall outside 1.5x Interquartile Range bounds.",
                            metric_value=outlier_pct,
                            recommendation="Cap extreme values using Z-score or IQR winsorization.",
                        )
                    )
        except Exception:
            pass

    # 3. High Multicollinearity
    if len(num_cols) >= 2:
        try:
            corr_matrix = df[num_cols].corr()
            checked_pairs = set()
            for c1 in num_cols:
                for c2 in num_cols:
                    if c1 != c2 and (c2, c1) not in checked_pairs:
                        checked_pairs.add((c1, c2))
                        val = float(corr_matrix.loc[c1, c2])
                        if not math.isnan(val) and abs(val) >= 0.85:
                            insights.append(
                                InsightItem(
                                    insight_type="high_correlation",
                                    severity="medium",
                                    column=f"{c1} & {c2}",
                                    title=f"High Multicollinearity (|r|={round(abs(val), 2)})",
                                    description=f"Strong linear correlation between '{c1}' and '{c2}'.",
                                    metric_value=round(val, 3),
                                    recommendation="Drop one feature before training linear models to eliminate redundancy.",
                                )
                            )
        except Exception:
            pass

    # 4. Target & Categorical Imbalance
    cat_cols = df.select_dtypes(include=["object", "string", "category", "bool"]).columns.tolist()
    for col in cat_cols:
        series = df[col].dropna()
        if len(series) == 0:
            continue
        unique_cnt = series.nunique()
        if unique_cnt > 1 and unique_cnt <= 10:
            val_counts = series.value_counts(normalize=True)
            min_class_pct = round(float(val_counts.iloc[-1]) * 100, 2)
            if min_class_pct < 5.0:
                insights.append(
                    InsightItem(
                        insight_type="target_imbalance",
                        severity="high",
                        column=col,
                        title=f"Severe Class Imbalance in '{col}' (Minority={min_class_pct}%)",
                        description=f"Minority category '{val_counts.index[-1]}' accounts for only {min_class_pct}% of cases.",
                        metric_value=min_class_pct,
                        recommendation="Use stratified train/test split and PR-AUC metric in Phase 9 AutoML.",
                    )
                )

    # 5. Baseline overview insight
    insights.insert(
        0,
        InsightItem(
            insight_type="trend_indicator",
            severity="info",
            column=None,
            title=f"Dataset Health Baseline: {dataset_name}",
            description=f"Analyzed {row_count:,} rows and {len(df.columns)} columns across {len(num_cols)} numeric and {len(cat_cols)} categorical fields.",
            metric_value=row_count,
            recommendation="Review flagged anomalies prior to pipeline aggregation and AutoML training.",
        ),
    )

    return insights


def translate_and_execute_nl_query(
    df: pd.DataFrame, prompt: str, dataset_id: str
) -> Optional[NLQueryTranslation]:
    """Translates user natural language into Pandas analytical aggregations and filters."""
    p = prompt.lower().strip()
    col_map = {c.lower(): c for c in df.columns}
    cols = list(df.columns)
    num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    cat_cols = df.select_dtypes(exclude=[np.number]).columns.tolist()

    # Determine metric aggregation type
    agg_op = None
    if "average" in p or "avg" in p or "mean" in p:
        agg_op = "avg"
    elif "sum" in p or "total" in p:
        agg_op = "sum"
    elif "min" in p or "minimum" in p or "lowest" in p:
        agg_op = "min"
    elif "max" in p or "maximum" in p or "highest" in p:
        agg_op = "max"
    elif "count" in p or "how many" in p:
        agg_op = "count"

    # Identify referenced columns
    matched_cols = [col_map[k] for k in col_map if k in p]
    target_metric_col = None
    dimension_col = None

    for c in matched_cols:
        if c in num_cols and not target_metric_col:
            target_metric_col = c
        elif c in cat_cols and not dimension_col:
            dimension_col = c
        elif not dimension_col:
            dimension_col = c

    # Fallbacks if columns weren't explicitly matched
    if not target_metric_col and num_cols:
        target_metric_col = num_cols[0]
    if not dimension_col and cat_cols:
        dimension_col = cat_cols[0]

    # 1. Group By dimensional breakdown query
    if dimension_col and (agg_op or "group by" in p or "by" in p):
        if not agg_op:
            agg_op = "count"
        target_col = target_metric_col if (target_metric_col and agg_op != "count") else dimension_col

        try:
            if agg_op == "count":
                res_df = df.groupby(dimension_col).size().reset_index(name="count")
                metric_alias = "count"
            elif agg_op == "sum":
                res_df = df.groupby(dimension_col)[target_col].sum().reset_index(name=f"sum_{target_col}")
                metric_alias = f"sum_{target_col}"
            elif agg_op == "avg":
                res_df = df.groupby(dimension_col)[target_col].mean().reset_index(name=f"avg_{target_col}")
                metric_alias = f"avg_{target_col}"
            elif agg_op == "min":
                res_df = df.groupby(dimension_col)[target_col].min().reset_index(name=f"min_{target_col}")
                metric_alias = f"min_{target_col}"
            elif agg_op == "max":
                res_df = df.groupby(dimension_col)[target_col].max().reset_index(name=f"max_{target_col}")
                metric_alias = f"max_{target_col}"
            else:
                res_df = df.groupby(dimension_col).size().reset_index(name="count")
                metric_alias = "count"

            res_df = res_df.sort_values(by=metric_alias, ascending=False).head(15)
            records = [
                {k: sanitize_val(v) for k, v in row.items()}
                for row in res_df.to_dict(orient="records")
            ]

            return NLQueryTranslation(
                dataset_id=dataset_id,
                operation="aggregate",
                explanation=f"Grouped dataset by **{dimension_col}** and computed **{agg_op.upper()}**({target_col}). Sorted descending by {metric_alias}.",
                query_spec={
                    "dimension": dimension_col,
                    "metric": target_col,
                    "aggregation": agg_op,
                    "limit": 15,
                },
                columns=list(res_df.columns),
                data=records,
                suggested_chart="bar" if len(records) > 1 else "kpi",
            )
        except Exception:
            pass

    # 2. Global Metric Summary query (KPI)
    if agg_op and target_metric_col:
        try:
            series = df[target_metric_col].dropna()
            if agg_op == "sum":
                val = float(series.sum())
            elif agg_op == "avg":
                val = float(series.mean())
            elif agg_op == "min":
                val = float(series.min())
            elif agg_op == "max":
                val = float(series.max())
            else:
                val = float(len(series))

            records = [{"metric": f"{agg_op.upper()}({target_metric_col})", "value": sanitize_val(val)}]
            return NLQueryTranslation(
                dataset_id=dataset_id,
                operation="summary",
                explanation=f"Evaluated global aggregate **{agg_op.upper()}** on feature column **{target_metric_col}**.",
                query_spec={"metric": target_metric_col, "aggregation": agg_op},
                columns=["metric", "value"],
                data=records,
                suggested_chart="kpi",
            )
        except Exception:
            pass

    # 3. Top records ranking / filter
    top_n = 5
    top_match = re.search(r"top\s+(\d+)", p)
    if top_match:
        top_n = min(int(top_match.group(1)), 25)

    sort_col = target_metric_col or cols[0]
    preview_df = df.sort_values(by=sort_col, ascending=False).head(top_n)
    records = [
        {k: sanitize_val(v) for k, v in row.items()}
        for row in preview_df.to_dict(orient="records")
    ]
    return NLQueryTranslation(
        dataset_id=dataset_id,
        operation="filter",
        explanation=f"Ranked dataset by **{sort_col}** (descending) and retrieved top {top_n} observations.",
        query_spec={"sort_by": sort_col, "ascending": False, "limit": top_n},
        columns=list(preview_df.columns),
        data=records,
        suggested_chart="table",
    )


def generate_platform_guidance(prompt: str) -> str:
    """Provides conversational guidance for platform studios, APIs, and workflows."""
    p = prompt.lower()

    if "pipeline" in p or "etl" in p or "dag" in p:
        return (
            "### 🚀 Visual ETL Pipeline Engine Guide\n\n"
            "- **Create DAG**: Navigate to **Visual ETL Pipelines Studio** and click **New Pipeline**.\n"
            "- **Supported Nodes**: `Source` (Dataset), `Filter` (Predicates), `Transform` (Cleaning), `GroupBy` (Aggregations), `Join` (Relational), and `Sink` (Materialization).\n"
            "- **Topological Execution**: Nodes execute in topologically sorted order with Kahn's cycle protection.\n"
            "- **REST Endpoint**: `POST /api/v1/pipelines/{id}/run`."
        )

    if "automl" in p or "model" in p or "ml" in p or "predict" in p:
        return (
            "### 🧠 AutoML & Model Registry Guide\n\n"
            "- **Benchmarking**: Open **AutoML & Model Registry Studio** and select **Train AutoML Model**.\n"
            "- **Estimators**: Benchmarks `RandomForest`, `GradientBoosting`, `LogisticRegression`, and `DecisionTree`.\n"
            "- **Artifacts**: Serialized with `joblib` into workspace storage with SHA-256 fingerprinting.\n"
            "- **Online Inference**: Call `POST /api/v1/ml/models/{id}/predict` for sub-millisecond predictions."
        )

    if "quality" in p or "alert" in p or "contract" in p:
        return (
            "### 🛡️ Declarative Data Quality & Alerts Guide\n\n"
            "- **Rules Supported**: `null_threshold`, `uniqueness`, `value_range`, `regex_match`, `set_membership`, `expression`.\n"
            "- **Health Scoring**: Automated grades (A through F) with violation counts and row quarantine.\n"
            "- **REST Endpoint**: `POST /api/v1/quality/suites/{id}/evaluate`."
        )

    if "dashboard" in p or "chart" in p or "bi" in p or "analytics" in p:
        return (
            "### 📊 Interactive Analytics & BI Dashboards Guide\n\n"
            "- **Dashboard Canvas**: Create custom dashboards in **Interactive Analytics Studio**.\n"
            "- **Widgets**: Supports `Bar`, `Line`, `Area`, `Pie/Donut`, `KPI Summary`, and `Table`.\n"
            "- **Query Execution**: Evaluates temporal date bucketing and multi-metric aggregations in real time.\n"
            "- **REST Endpoint**: `POST /api/v1/dashboards` & `GET /api/v1/dashboards/{id}/widgets/{w_id}/query`."
        )

    if "schedule" in p or "celery" in p or "worker" in p or "cron" in p:
        return (
            "### ⚡ Async Workers & Celery Schedulers Guide\n\n"
            "- **Distributed Tasks**: Background tasks stream state transitions and progress percentages.\n"
            "- **Cron Triggers**: Standard 5-field cron parsing with deterministic next-run scheduling.\n"
            "- **Diagnostics**: View worker thread telemetry via `GET /api/v1/jobs/diagnostics`."
        )

    return (
        "### 🌟 AI Data Intelligence Cloud Platform Overview\n\n"
        "I can help you analyze dataset anomalies, translate natural language into aggregations and filters, "
        "explain ML model performance, check data lineage, and configure platform ETL pipelines.\n\n"
        "**Try asking:**\n"
        "- *'Find anomalies and outliers in this dataset'*\n"
        "- *'What is the average balance by churn status?'*\n"
        "- *'Show top 5 rows with highest values'*\n"
        "- *'How do I create a Visual ETL pipeline?'*"
    )
