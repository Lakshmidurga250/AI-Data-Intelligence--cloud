"""Automated PII detection, sensitivity classification, and data masking heuristics."""

import re
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd

from app.schemas.governance import PIIScanResult

# Regex patterns for high-risk PII identifiers
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
PHONE_REGEX = re.compile(r"^(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}$")
SSN_REGEX = re.compile(r"^\d{3}-\d{2}-\d{4}$")
CREDIT_CARD_REGEX = re.compile(r"^(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|6(?:011|5[0-9]{2})[0-9]{12})$")
IPV4_REGEX = re.compile(r"^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$")

COLUMN_HEURISTICS: Dict[str, str] = {
    "email": "PII_EMAIL",
    "mail": "PII_EMAIL",
    "e_mail": "PII_EMAIL",
    "phone": "PII_PHONE",
    "mobile": "PII_PHONE",
    "telephone": "PII_PHONE",
    "cell": "PII_PHONE",
    "ssn": "PII_SSN",
    "social_security": "PII_SSN",
    "credit_card": "PII_CREDIT_CARD",
    "card_num": "PII_CREDIT_CARD",
    "card_number": "PII_CREDIT_CARD",
    "cc_num": "PII_CREDIT_CARD",
    "ip": "PII_IP",
    "ip_address": "PII_IP",
    "client_ip": "PII_IP",
    "full_name": "PII_NAME",
    "first_name": "PII_NAME",
    "last_name": "PII_NAME",
    "customer_name": "PII_NAME",
    "client_name": "PII_NAME",
}


def mask_sensitive_value(val: str, label: str) -> str:
    """Mask sensitive string value preserving minimal context for audit purposes."""
    s = str(val).strip()
    if not s:
        return ""
    if label == "PII_EMAIL":
        parts = s.split("@")
        if len(parts) == 2:
            prefix = parts[0]
            masked_prefix = prefix[0] + "***" if len(prefix) > 1 else "***"
            return f"{masked_prefix}@{parts[1]}"
        return "***@***"
    if label in ("PII_SSN", "PII_CREDIT_CARD"):
        clean = re.sub(r"[-\s]", "", s)
        suffix = clean[-4:] if len(clean) >= 4 else "0000"
        return f"***-**-{suffix}"
    if label == "PII_PHONE":
        clean = re.sub(r"[-\s().+]", "", s)
        suffix = clean[-4:] if len(clean) >= 4 else "0000"
        return f"***-***-{suffix}"
    if label == "PII_IP":
        parts = s.split(".")
        return f"{parts[0]}.***.***.***" if len(parts) == 4 else "***.***"
    # Name or general
    return s[0] + "***" if len(s) > 1 else "***"


def evaluate_column_pii(
    col_name: str,
    series: pd.Series,
    sample_size: int = 100,
) -> Optional[PIIScanResult]:
    """Inspects a column name and sample series values to determine PII classification."""
    normalized_col = col_name.lower().replace("-", "_").strip()
    heuristic_label = None

    for pattern, label in COLUMN_HEURISTICS.items():
        if pattern == normalized_col or pattern in normalized_col.split("_"):
            heuristic_label = label
            break

    # Sample non-null string values
    non_null_samples = (
        series.dropna().astype(str).loc[lambda x: x.str.strip() != ""].head(sample_size).tolist()
    )
    if not non_null_samples and not heuristic_label:
        return None

    matched_label = heuristic_label
    match_count = 0
    masked_samples: List[str] = []

    if non_null_samples:
        for val in non_null_samples:
            clean_val = val.strip()
            # Regex validation
            if EMAIL_REGEX.match(clean_val):
                matched_label = "PII_EMAIL"
                match_count += 1
            elif SSN_REGEX.match(clean_val):
                matched_label = "PII_SSN"
                match_count += 1
            elif CREDIT_CARD_REGEX.match(re.sub(r"[-\s]", "", clean_val)):
                matched_label = "PII_CREDIT_CARD"
                match_count += 1
            elif IPV4_REGEX.match(clean_val):
                matched_label = "PII_IP"
                match_count += 1
            elif PHONE_REGEX.match(clean_val) and (heuristic_label == "PII_PHONE" or len(clean_val) >= 7):
                matched_label = "PII_PHONE"
                match_count += 1
            elif heuristic_label == "PII_NAME":
                match_count += 1

    if not matched_label:
        return None

    # Confidence calculation
    total_samples = len(non_null_samples) or 1
    if match_count > 0:
        ratio = match_count / total_samples
        confidence = min(1.0, max(0.5, round(ratio * (1.1 if heuristic_label else 0.9), 2)))
    elif heuristic_label:
        confidence = 0.75
    else:
        return None

    for val in non_null_samples[:3]:
        masked_samples.append(mask_sensitive_value(val, matched_label))

    return PIIScanResult(
        column_name=col_name,
        sensitivity_label=matched_label,
        confidence_score=confidence,
        sample_matches_count=match_count or len(non_null_samples),
        sample_masked_values=masked_samples,
    )


def scan_dataframe_pii(df: pd.DataFrame) -> Tuple[List[PIIScanResult], str, bool]:
    """Scan all DataFrame columns and compute overall sensitivity tier and quarantine status."""
    findings: List[PIIScanResult] = []
    has_restricted = False
    has_confidential = False

    for col in df.columns:
        result = evaluate_column_pii(str(col), df[col])
        if result:
            findings.append(result)
            if result.sensitivity_label in ("PII_SSN", "PII_CREDIT_CARD"):
                has_restricted = True
            elif result.sensitivity_label in ("PII_EMAIL", "PII_PHONE", "PII_NAME", "PII_IP"):
                has_confidential = True

    if has_restricted:
        tier = "RESTRICTED_PII"
        quarantine = True
    elif has_confidential:
        tier = "CONFIDENTIAL"
        quarantine = False
    elif findings:
        tier = "INTERNAL"
        quarantine = False
    else:
        tier = "PUBLIC"
        quarantine = False

    return findings, tier, quarantine
