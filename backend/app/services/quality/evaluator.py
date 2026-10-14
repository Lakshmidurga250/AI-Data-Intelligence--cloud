"""Data Quality Rules Evaluator Engine.

Validates pandas DataFrames against declarative data quality rules:
- null_threshold: ensures null/empty percentage does not exceed maximum bound
- uniqueness: ensures distinct value ratio meets minimum threshold
- value_range: verifies numeric bounds [min_val, max_val]
- regex_match: validates string format against regular expressions
- set_membership: ensures categorical values belong to allowed member sets
- expression: evaluates boolean expressions on dataframe columns
"""

import math
import re
from typing import Any, Dict, List, Tuple
import numpy as np
import pandas as pd

from app.schemas.quality import EvaluationGrade, RuleEvaluationResult


def sanitize_row_for_json(row_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure all dictionary values are JSON serializable (handling NaN, inf, NaT)."""
    sanitized: Dict[str, Any] = {}
    for k, v in row_dict.items():
        if v is None:
            sanitized[k] = None
        elif isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            sanitized[k] = None
        elif isinstance(v, (np.floating, float)):
            sanitized[k] = float(v)
        elif isinstance(v, (np.integer, int)):
            sanitized[k] = int(v)
        elif isinstance(v, pd.Timestamp):
            sanitized[k] = v.isoformat()
        else:
            sanitized[k] = str(v)
    return sanitized


def extract_sample_violations(
    df: pd.DataFrame,
    fail_mask: pd.Series,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """Extract sample rows failing quality evaluation, sanitizing numerical primitives."""
    if not bool(fail_mask.any()):
        return []
    sample_df = df[fail_mask].head(limit)
    return [sanitize_row_for_json(r) for r in sample_df.to_dict(orient="records")]


def compute_health_grade(score: float) -> EvaluationGrade:
    """Assign letter grade based on numeric quality score (0.0 to 100.0)."""
    if score >= 90.0:
        return "A"
    if score >= 80.0:
        return "B"
    if score >= 70.0:
        return "C"
    if score >= 60.0:
        return "D"
    return "F"


def evaluate_single_rule(
    df: pd.DataFrame,
    rule_id: str,
    rule_name: str,
    rule_type: str,
    target_column: str,
    parameters: Dict[str, Any],
    severity: str = "critical",
) -> RuleEvaluationResult:
    """Evaluate a single validation rule against a pandas DataFrame."""
    total_rows = len(df)
    if total_rows == 0:
        return RuleEvaluationResult(
            rule_id=rule_id,
            rule_name=rule_name,
            rule_type=rule_type,
            target_column=target_column,
            severity=severity,
            passed=True,
            total_rows=0,
            failed_rows=0,
            failure_rate_pct=0.0,
            message="Dataset is empty; rule evaluated with 0 rows.",
            sample_violations=[],
        )

    if target_column not in df.columns:
        return RuleEvaluationResult(
            rule_id=rule_id,
            rule_name=rule_name,
            rule_type=rule_type,
            target_column=target_column,
            severity=severity,
            passed=False,
            total_rows=total_rows,
            failed_rows=total_rows,
            failure_rate_pct=100.0,
            message=f"Target column '{target_column}' does not exist in dataset schema.",
            sample_violations=[],
        )

    col = df[target_column]

    if rule_type == "null_threshold":
        max_null_pct = float(parameters.get("max_null_pct", parameters.get("threshold", 0.0)))
        fail_mask = col.isna() | (col.astype(str).str.strip().isin(["", "null", "none", "nan", "nat"]))
        failed_count = int(fail_mask.sum())
        failure_pct = round((failed_count / total_rows) * 100.0, 2)
        passed = failure_pct <= max_null_pct
        msg = (
            f"Null percentage {failure_pct}% <= threshold {max_null_pct}%"
            if passed
            else f"Null percentage {failure_pct}% exceeds maximum permitted {max_null_pct}%"
        )
        return RuleEvaluationResult(
            rule_id=rule_id,
            rule_name=rule_name,
            rule_type=rule_type,
            target_column=target_column,
            severity=severity,
            passed=passed,
            total_rows=total_rows,
            failed_rows=failed_count,
            failure_rate_pct=failure_pct,
            message=msg,
            sample_violations=extract_sample_violations(df, fail_mask),
        )

    if rule_type == "uniqueness":
        min_unique_pct = float(parameters.get("min_unique_pct", parameters.get("threshold", 100.0)))
        non_null_col = col.dropna()
        non_null_count = len(non_null_col)
        if non_null_count == 0:
            distinct_count = 0
            unique_pct = 0.0
            fail_mask = pd.Series(True, index=df.index)
        else:
            distinct_count = int(non_null_col.nunique())
            unique_pct = round((distinct_count / non_null_count) * 100.0, 2)
            fail_mask = col.duplicated(keep="first")

        failed_count = int(fail_mask.sum())
        passed = unique_pct >= min_unique_pct
        msg = (
            f"Uniqueness {unique_pct}% >= minimum requirement {min_unique_pct}%"
            if passed
            else f"Uniqueness {unique_pct}% is below required {min_unique_pct}% ({failed_count} duplicate rows)"
        )
        return RuleEvaluationResult(
            rule_id=rule_id,
            rule_name=rule_name,
            rule_type=rule_type,
            target_column=target_column,
            severity=severity,
            passed=passed,
            total_rows=total_rows,
            failed_rows=failed_count,
            failure_rate_pct=round((failed_count / total_rows) * 100.0, 2),
            message=msg,
            sample_violations=extract_sample_violations(df, col.duplicated(keep=False)),
        )

    if rule_type == "value_range":
        min_val = parameters.get("min")
        max_val = parameters.get("max")
        numeric_series = pd.to_numeric(col, errors="coerce")

        fail_mask = pd.Series(False, index=df.index)
        if min_val is not None:
            fail_mask = fail_mask | (numeric_series < float(min_val))
        if max_val is not None:
            fail_mask = fail_mask | (numeric_series > float(max_val))
        fail_mask = fail_mask | (numeric_series.isna() & col.notna())

        failed_count = int(fail_mask.sum())
        failure_pct = round((failed_count / total_rows) * 100.0, 2)
        passed = failed_count == 0
        bound_desc = f"[{min_val if min_val is not None else '-inf'}, {max_val if max_val is not None else '+inf'}]"
        msg = (
            f"All values fall within required range {bound_desc}"
            if passed
            else f"{failed_count} values violate numerical range {bound_desc} ({failure_pct}%)"
        )
        return RuleEvaluationResult(
            rule_id=rule_id,
            rule_name=rule_name,
            rule_type=rule_type,
            target_column=target_column,
            severity=severity,
            passed=passed,
            total_rows=total_rows,
            failed_rows=failed_count,
            failure_rate_pct=failure_pct,
            message=msg,
            sample_violations=extract_sample_violations(df, fail_mask),
        )

    if rule_type == "regex_match":
        pattern = parameters.get("pattern", "")
        if not pattern:
            return RuleEvaluationResult(
                rule_id=rule_id,
                rule_name=rule_name,
                rule_type=rule_type,
                target_column=target_column,
                severity=severity,
                passed=True,
                total_rows=total_rows,
                failed_rows=0,
                failure_rate_pct=0.0,
                message="No regex pattern provided; pass-through check.",
                sample_violations=[],
            )

        try:
            compiled = re.compile(pattern)
        except re.error as e:
            return RuleEvaluationResult(
                rule_id=rule_id,
                rule_name=rule_name,
                rule_type=rule_type,
                target_column=target_column,
                severity=severity,
                passed=False,
                total_rows=total_rows,
                failed_rows=total_rows,
                failure_rate_pct=100.0,
                message=f"Invalid regex pattern '{pattern}': {str(e)}",
                sample_violations=[],
            )

        str_series = col.astype(str)
        fail_mask = ~str_series.apply(lambda v: bool(compiled.search(v)) if pd.notna(v) else False)
        failed_count = int(fail_mask.sum())
        failure_pct = round((failed_count / total_rows) * 100.0, 2)
        passed = failed_count == 0
        msg = (
            f"All values match pattern '{pattern}'"
            if passed
            else f"{failed_count} rows violate regex pattern '{pattern}' ({failure_pct}%)"
        )
        return RuleEvaluationResult(
            rule_id=rule_id,
            rule_name=rule_name,
            rule_type=rule_type,
            target_column=target_column,
            severity=severity,
            passed=passed,
            total_rows=total_rows,
            failed_rows=failed_count,
            failure_rate_pct=failure_pct,
            message=msg,
            sample_violations=extract_sample_violations(df, fail_mask),
        )

    if rule_type == "set_membership":
        allowed = parameters.get("allowed_values", [])
        allowed_set = {str(a).strip().lower() for a in allowed}
        str_series = col.astype(str).str.strip().str.lower()
        fail_mask = ~str_series.isin(allowed_set)
        failed_count = int(fail_mask.sum())
        failure_pct = round((failed_count / total_rows) * 100.0, 2)
        passed = failed_count == 0
        msg = (
            f"All values belong to allowed set ({len(allowed)} members)"
            if passed
            else f"{failed_count} rows contain values outside allowed set ({failure_pct}%)"
        )
        return RuleEvaluationResult(
            rule_id=rule_id,
            rule_name=rule_name,
            rule_type=rule_type,
            target_column=target_column,
            severity=severity,
            passed=passed,
            total_rows=total_rows,
            failed_rows=failed_count,
            failure_rate_pct=failure_pct,
            message=msg,
            sample_violations=extract_sample_violations(df, fail_mask),
        )

    if rule_type == "expression":
        expr = parameters.get("expression", "")
        if not expr:
            return RuleEvaluationResult(
                rule_id=rule_id,
                rule_name=rule_name,
                rule_type=rule_type,
                target_column=target_column,
                severity=severity,
                passed=True,
                total_rows=total_rows,
                failed_rows=0,
                failure_rate_pct=0.0,
                message="No expression defined; pass-through check.",
                sample_violations=[],
            )

        try:
            eval_mask = df.eval(expr)
            if not isinstance(eval_mask, pd.Series):
                eval_mask = pd.Series(eval_mask, index=df.index)
            fail_mask = ~eval_mask.fillna(False)
            failed_count = int(fail_mask.sum())
            failure_pct = round((failed_count / total_rows) * 100.0, 2)
            passed = failed_count == 0
            msg = (
                f"All rows satisfy condition '{expr}'"
                if passed
                else f"{failed_count} rows violate condition '{expr}' ({failure_pct}%)"
            )
            return RuleEvaluationResult(
                rule_id=rule_id,
                rule_name=rule_name,
                rule_type=rule_type,
                target_column=target_column,
                severity=severity,
                passed=passed,
                total_rows=total_rows,
                failed_rows=failed_count,
                failure_rate_pct=failure_pct,
                message=msg,
                sample_violations=extract_sample_violations(df, fail_mask),
            )
        except Exception as e:
            return RuleEvaluationResult(
                rule_id=rule_id,
                rule_name=rule_name,
                rule_type=rule_type,
                target_column=target_column,
                severity=severity,
                passed=False,
                total_rows=total_rows,
                failed_rows=total_rows,
                failure_rate_pct=100.0,
                message=f"Expression evaluation failed: {str(e)}",
                sample_violations=[],
            )

    return RuleEvaluationResult(
        rule_id=rule_id,
        rule_name=rule_name,
        rule_type=rule_type,
        target_column=target_column,
        severity=severity,
        passed=False,
        total_rows=total_rows,
        failed_rows=total_rows,
        failure_rate_pct=100.0,
        message=f"Unsupported quality rule type '{rule_type}'.",
        sample_violations=[],
    )


def evaluate_suite_on_dataframe(
    df: pd.DataFrame,
    rules: List[Dict[str, Any]],
) -> Tuple[float, EvaluationGrade, int, int, int, List[RuleEvaluationResult]]:
    """Evaluate all active rules in a suite against a DataFrame.

    Returns:
        (score, grade, total_rules, passed_rules, failed_rules, rule_results)
    """
    if not rules:
        return 100.0, "A", 0, 0, 0, []

    results: List[RuleEvaluationResult] = []
    passed_count = 0
    failed_count = 0

    for r in rules:
        res = evaluate_single_rule(
            df=df,
            rule_id=str(r.get("id", "")),
            rule_name=str(r.get("name", "Unnamed Rule")),
            rule_type=str(r.get("rule_type", "null_threshold")),
            target_column=str(r.get("target_column", "")),
            parameters=r.get("parameters", {}) if isinstance(r.get("parameters"), dict) else {},
            severity=str(r.get("severity", "critical")),
        )
        results.append(res)
        if res.passed:
            passed_count += 1
        else:
            failed_count += 1

    total_rules = len(rules)
    score = round((passed_count / total_rules) * 100.0, 2)
    grade = compute_health_grade(score)

    return score, grade, total_rules, passed_count, failed_count, results
