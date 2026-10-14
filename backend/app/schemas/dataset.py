"""Dataset validation and presentation schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ColumnSchema(BaseModel):
    """Schema descriptor for a single tabular column."""

    name: str
    data_type: str
    null_count: int = 0
    null_percentage: float = 0.0
    sample_values: List[Any] = Field(default_factory=list)


class DatasetBase(BaseModel):
    """Base fields for a dataset."""

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=2000)


class DatasetRead(DatasetBase):
    """Public metadata descriptor for an ingested dataset."""

    id: str
    workspace_id: str
    filename: str
    format: str
    size_bytes: int
    row_count: int
    column_count: int
    sha256: str
    version: int
    created_at: datetime
    columns: List[ColumnSchema] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class DatasetDetailRead(DatasetRead):
    """Detailed dataset descriptor including head preview records."""

    preview_rows: List[Dict[str, Any]] = Field(default_factory=list)


class DatasetUpdate(BaseModel):
    """Schema for updating dataset metadata."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=2000)
