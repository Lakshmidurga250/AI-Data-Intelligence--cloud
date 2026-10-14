"""Schemas for dataset statistical profiling, correlation analysis, and version snapshots."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class NumericColumnStats(BaseModel):
    """Detailed summary statistics for a numeric column."""

    min: Optional[float] = None
    max: Optional[float] = None
    mean: Optional[float] = None
    std: Optional[float] = None
    variance: Optional[float] = None
    median: Optional[float] = None
    q25: Optional[float] = None
    q75: Optional[float] = None
    skew: Optional[float] = None
    zeros_count: int = 0
    negatives_count: int = 0


class ValueFrequency(BaseModel):
    """Frequency descriptor for categorical values."""

    value: str
    count: int
    percentage: float


class CategoricalColumnStats(BaseModel):
    """Cardinality and frequency distribution for categorical or string columns."""

    distinct_count: int = 0
    distinct_percentage: float = 0.0
    top_values: List[ValueFrequency] = Field(default_factory=list)
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    avg_length: Optional[float] = None


class ColumnFullProfile(BaseModel):
    """In-depth statistical profile of a single dataset column."""

    name: str
    data_type: str
    total_count: int
    null_count: int
    null_percentage: float
    is_numeric: bool
    is_categorical: bool
    numeric_stats: Optional[NumericColumnStats] = None
    categorical_stats: Optional[CategoricalColumnStats] = None


class CorrelationPair(BaseModel):
    """Pearson correlation coefficient between two numeric columns."""

    column_a: str
    column_b: str
    coefficient: float


class DatasetProfileResponse(BaseModel):
    """Comprehensive statistical profile and health scorecard for a dataset."""

    dataset_id: str
    dataset_name: str
    row_count: int
    column_count: int
    memory_bytes: int
    duplicate_rows_count: int
    duplicate_rows_percentage: float
    completeness_score: float
    columns: List[ColumnFullProfile]
    correlations: List[CorrelationPair]
    profiled_at: str


class DatasetVersionRead(BaseModel):
    """Public descriptor for an immutable dataset version snapshot."""

    id: str
    dataset_id: str
    version_number: int
    row_count: int
    column_count: int
    size_bytes: int
    sha256: str
    change_summary: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DatasetVersionCreate(BaseModel):
    """Payload to trigger creation of a new dataset snapshot."""

    change_summary: str = Field(..., min_length=2, max_length=255)
