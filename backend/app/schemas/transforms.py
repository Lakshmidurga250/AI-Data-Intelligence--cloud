"""Schemas for data cleaning, transformation operators, and recipe pipelines."""

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

from app.schemas.dataset import ColumnSchema

TransformStepType = Literal[
    "impute",
    "drop_columns",
    "rename_columns",
    "cast_type",
    "text_transform",
    "drop_duplicates",
    "handle_outliers",
    "filter_rows",
    "derive_column",
]


class TransformStep(BaseModel):
    """Specification of an atomic transformation operation within a recipe."""

    step_type: TransformStepType
    params: Dict[str, Any] = Field(default_factory=dict)


class TransformPreviewRequest(BaseModel):
    """Request payload to preview transformation results non-destructively on sample rows."""

    steps: List[TransformStep]
    sample_size: int = Field(default=50, ge=5, le=500)


class TransformPreviewResponse(BaseModel):
    """Response comparing dataset state before and after transformation execution."""

    original_row_count: int
    transformed_row_count: int
    rows_affected: int
    original_columns: List[ColumnSchema]
    transformed_columns: List[ColumnSchema]
    preview_before: List[Dict[str, Any]]
    preview_after: List[Dict[str, Any]]
    step_summaries: List[str]


class TransformRecipeRequest(BaseModel):
    """Payload to execute an ordered transformation recipe and persist output."""

    name: Optional[str] = None
    description: Optional[str] = None
    steps: List[TransformStep]
    save_as_new_dataset: bool = Field(
        default=True,
        description="If True, creates a new dataset asset. If False, updates in-place with a new version snapshot.",
    )


class TransformApplyResponse(BaseModel):
    """Result of committing transformation pipeline to persistent storage."""

    dataset_id: str
    name: str
    version: int
    row_count: int
    column_count: int
    size_bytes: int
    format: str
    steps_applied: int
    step_summaries: List[str]
