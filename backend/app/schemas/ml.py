"""Pydantic schemas for AutoML, Model Registry, Versioning, and Real-time Inference."""

import json
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, ConfigDict, Field, field_validator

MLTaskType = Literal["classification", "regression"]
TaskType = MLTaskType
ModelVersionStatus = Literal["candidate", "champion", "archived"]
ExperimentStatus = Literal["pending", "running", "completed", "failed"]


class AlgorithmLeaderboardItem(BaseModel):
    """Performance evaluation item for a candidate algorithm in an experiment."""

    algorithm: str
    metrics: Dict[str, float] = Field(default_factory=dict)
    training_time_ms: float = 0.0
    is_best: bool = False


class AutoMLTrainRequest(BaseModel):
    """Payload to initiate an automated machine learning training run."""

    dataset_id: str = Field(..., description="ID of source tabular dataset")
    model_name: str = Field(..., min_length=2, max_length=255, description="Registered model name")
    target_column: str = Field(..., min_length=1, max_length=255, description="Target label column to predict")
    task_type: TaskType = Field(..., description="ML task type: classification or regression")
    test_size: float = Field(0.2, ge=0.05, le=0.5, description="Holdout validation fraction")
    candidate_algorithms: Optional[List[str]] = Field(
        None,
        description="Optional list of algorithms to benchmark. If None, benchmarks all standard estimators.",
    )
    feature_columns: Optional[List[str]] = Field(
        None,
        description="Optional subset of features. If None, all columns except target are used.",
    )
    description: Optional[str] = Field(None, max_length=1000, description="Model notes or intended use-case")


class AutoMLTrainResponse(BaseModel):
    """Summary result of an AutoML training benchmark."""

    model_id: str
    version_id: str
    experiment_id: str
    model_name: str
    task_type: str
    target_column: str
    best_algorithm: str
    metrics: Dict[str, float]
    feature_names: List[str]
    feature_importances: Dict[str, float]
    leaderboard: List[AlgorithmLeaderboardItem]
    training_duration_ms: int


class MLModelVersionRead(BaseModel):
    """Schema for a versioned model snapshot in the registry."""

    id: str
    model_id: str
    version_number: int
    experiment_id: Optional[str] = None
    artifact_path: str
    sha256: str
    algorithm: str
    status: ModelVersionStatus
    metrics: Dict[str, float] = Field(default_factory=dict)
    hyperparameters: Optional[Dict[str, Any]] = None
    feature_names: List[str] = Field(default_factory=list)
    feature_importance: Dict[str, float] = Field(default_factory=dict)
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("metrics", mode="before")
    @classmethod
    def parse_metrics(cls, v: Any) -> Dict[str, float]:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return {}
        if isinstance(v, dict):
            return v
        return {}

    @field_validator("hyperparameters", mode="before")
    @classmethod
    def parse_hyperparams(cls, v: Any) -> Optional[Dict[str, Any]]:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return None
        if isinstance(v, dict):
            return v
        return None

    @field_validator("feature_names", mode="before")
    @classmethod
    def parse_features(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return []
        if isinstance(v, list):
            return v
        return []

    @field_validator("feature_importance", mode="before")
    @classmethod
    def parse_importance(cls, v: Any) -> Dict[str, float]:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return {}
        if isinstance(v, dict):
            return v
        return {}


class MLModelRead(BaseModel):
    """Schema for a registered ML model summary."""

    id: str
    workspace_id: str
    name: str
    description: Optional[str] = None
    task_type: str
    target_column: str
    framework: str
    active_version_id: Optional[str] = None
    versions_count: int = 0
    active_version: Optional[MLModelVersionRead] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class MLModelDetailRead(MLModelRead):
    """Detailed registered model schema including all historical versions."""

    versions: List[MLModelVersionRead] = Field(default_factory=list)


class MLExperimentRead(BaseModel):
    """Schema for an AutoML training experiment."""

    id: str
    workspace_id: str
    model_id: Optional[str] = None
    dataset_id: Optional[str] = None
    name: str
    task_type: str
    target_column: str
    status: ExperimentStatus
    best_algorithm: Optional[str] = None
    leaderboard: List[AlgorithmLeaderboardItem] = Field(default_factory=list)
    logs: Optional[str] = None
    training_duration_ms: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("leaderboard", mode="before")
    @classmethod
    def parse_leaderboard(cls, v: Any) -> List[AlgorithmLeaderboardItem]:
        if isinstance(v, str):
            try:
                data = json.loads(v)
                return [AlgorithmLeaderboardItem(**item) for item in data]
            except Exception:
                return []
        if isinstance(v, list):
            return [
                item if isinstance(item, AlgorithmLeaderboardItem) else AlgorithmLeaderboardItem(**item)
                for item in v
            ]
        return []


class InferenceRequest(BaseModel):
    """Request payload for online inference."""

    inputs: Union[Dict[str, Any], List[Dict[str, Any]]] = Field(
        ...,
        description="Single feature dictionary or list of feature dictionaries matching model training features.",
    )


class InferenceResponse(BaseModel):
    """Prediction result from model inference."""

    model_id: str
    version_id: str
    algorithm: str
    task_type: str
    predictions: List[Any]
    probabilities: Optional[List[Dict[str, float]]] = None
    latency_ms: float
