"""FastAPI endpoints for AutoML benchmark training, Model Registry, Versioning, and Inference."""

from typing import Any, Dict, List, Optional, Tuple
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_user,
    get_current_workspace,
    get_db,
    require_workspace_role,
)
from app.models.membership import WorkspaceMembership, WorkspaceRole
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.ml import (
    AutoMLTrainRequest,
    AutoMLTrainResponse,
    InferenceRequest,
    InferenceResponse,
    MLExperimentRead,
    MLModelDetailRead,
    MLModelRead,
    MLModelVersionRead,
)
from app.services.ml.service import (
    delete_model,
    execute_model_inference,
    get_model_detail,
    list_workspace_experiments,
    list_workspace_models,
    promote_model_version,
    train_automl_model,
)

router = APIRouter()


@router.post(
    "/train",
    response_model=AutoMLTrainResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Train AutoML model on dataset",
)
async def train_model(
    train_in: AutoMLTrainRequest,
    db: AsyncSession = Depends(get_db),
    ws_ctx: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
    _: WorkspaceMembership = Depends(
        require_workspace_role([WorkspaceRole.OWNER, WorkspaceRole.ADMIN, WorkspaceRole.MEMBER])
    ),
) -> AutoMLTrainResponse:
    """Benchmark candidate machine learning algorithms, auto-select champion, and register version."""
    workspace, _ = ws_ctx
    return await train_automl_model(db, workspace.id, train_in)


@router.get(
    "/models",
    response_model=List[MLModelRead],
    summary="List registered models in workspace",
)
async def get_models(
    db: AsyncSession = Depends(get_db),
    ws_ctx: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
) -> List[MLModelRead]:
    """Retrieve all registered ML models with active champion versions."""
    workspace, _ = ws_ctx
    return await list_workspace_models(db, workspace.id)


@router.get(
    "/models/{model_id}",
    response_model=MLModelDetailRead,
    summary="Get model detail and version history",
)
async def get_model(
    model_id: str,
    db: AsyncSession = Depends(get_db),
    ws_ctx: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
) -> MLModelDetailRead:
    """Retrieve model details with complete version lineage and hyperparameters."""
    workspace, _ = ws_ctx
    return await get_model_detail(db, model_id, workspace.id)


@router.delete(
    "/models/{model_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete model and serialized artifacts",
)
async def remove_model(
    model_id: str,
    db: AsyncSession = Depends(get_db),
    ws_ctx: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
    _: WorkspaceMembership = Depends(
        require_workspace_role([WorkspaceRole.OWNER, WorkspaceRole.ADMIN])
    ),
) -> Dict[str, Any]:
    """Delete registered model and its physical artifact binaries from storage."""
    workspace, _ = ws_ctx
    await delete_model(db, model_id, workspace.id)
    return {"status": "deleted", "model_id": model_id}


@router.post(
    "/models/{model_id}/versions/{version_id}/promote",
    response_model=MLModelVersionRead,
    summary="Promote version to champion",
)
async def promote_version(
    model_id: str,
    version_id: str,
    db: AsyncSession = Depends(get_db),
    ws_ctx: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
    _: WorkspaceMembership = Depends(
        require_workspace_role([WorkspaceRole.OWNER, WorkspaceRole.ADMIN, WorkspaceRole.MEMBER])
    ),
) -> MLModelVersionRead:
    """Set model version as champion for active production inference."""
    workspace, _ = ws_ctx
    return await promote_model_version(db, model_id, version_id, workspace.id)


@router.post(
    "/models/{model_id}/predict",
    response_model=InferenceResponse,
    summary="Execute real-time model inference",
)
async def predict_model(
    model_id: str,
    infer_in: InferenceRequest,
    version_id: Optional[str] = Query(None, description="Optional specific version ID to test"),
    db: AsyncSession = Depends(get_db),
    ws_ctx: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
) -> InferenceResponse:
    """Run real-time inference prediction on input feature payload."""
    workspace, _ = ws_ctx
    return await execute_model_inference(
        db=db,
        model_id=model_id,
        inputs=infer_in.inputs,
        workspace_id=workspace.id,
        version_id=version_id,
    )


@router.get(
    "/experiments",
    response_model=List[MLExperimentRead],
    summary="List training experiments in workspace",
)
async def get_experiments(
    db: AsyncSession = Depends(get_db),
    ws_ctx: Tuple[Workspace, WorkspaceMembership] = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
) -> List[MLExperimentRead]:
    """List all AutoML training experiment benchmarks."""
    workspace, _ = ws_ctx
    return await list_workspace_experiments(db, workspace.id)
