"""ML Registry & AutoML domain service orchestrating models, versions, and experiments."""

import json
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.dataset import Dataset
from app.models.ml import MLExperiment, MLModel, MLModelVersion
from app.schemas.ml import (
    AlgorithmLeaderboardItem,
    AutoMLTrainRequest,
    AutoMLTrainResponse,
    InferenceResponse,
    MLExperimentRead,
    MLModelDetailRead,
    MLModelRead,
    MLModelVersionRead,
)
from app.services.ingestion.parser import read_file_to_dataframe
from app.services.lineage.service import create_edge_if_not_exists, register_or_get_node
from app.services.ml.inference import run_inference
from app.services.ml.trainer import AutoMLTrainer


def get_model_storage_dir(workspace_id: str, model_id: str, base_dir: str = "data") -> Path:
    """Return local disk storage directory for model artifacts."""
    model_dir = Path(base_dir).resolve() / "workspaces" / workspace_id / "models" / model_id
    model_dir.mkdir(parents=True, exist_ok=True)
    return model_dir


async def train_automl_model(
    db: AsyncSession,
    workspace_id: str,
    request: AutoMLTrainRequest,
) -> AutoMLTrainResponse:
    """Execute AutoML benchmark, register model version, and record experiment."""
    # 1. Fetch source dataset
    dataset_res = await db.execute(
        select(Dataset).where(
            Dataset.id == request.dataset_id,
            Dataset.workspace_id == workspace_id,
        )
    )
    dataset = dataset_res.scalar_one_or_none()
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{request.dataset_id}' not found in active workspace.",
        )

    # 2. Parse file into DataFrame
    try:
        df = read_file_to_dataframe(Path(dataset.storage_path), dataset.format)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read dataset for training: {str(e)}",
        )

    if len(df) < 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Dataset has only {len(df)} rows. At least 5 rows are required for ML training.",
        )

    if request.target_column not in df.columns:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Target column '{request.target_column}' does not exist in dataset.",
        )

    # 3. Check or create MLModel entry
    model_res = await db.execute(
        select(MLModel)
        .where(
            MLModel.workspace_id == workspace_id,
            MLModel.name == request.model_name.strip(),
        )
        .options(selectinload(MLModel.versions))
    )
    ml_model = model_res.scalar_one_or_none()

    if not ml_model:
        ml_model = MLModel(
            workspace_id=workspace_id,
            name=request.model_name.strip(),
            description=request.description,
            task_type=request.task_type,
            target_column=request.target_column,
            framework="scikit-learn",
        )
        db.add(ml_model)
        await db.flush()
        version_number = 1
    else:
        v_res = await db.execute(
            select(func.max(MLModelVersion.version_number)).where(
                MLModelVersion.model_id == ml_model.id
            )
        )
        max_v = v_res.scalar() or 0
        version_number = max_v + 1

    # 4. Create MLExperiment record
    experiment = MLExperiment(
        workspace_id=workspace_id,
        model_id=ml_model.id,
        dataset_id=dataset.id,
        name=f"{request.model_name} Training v{version_number}",
        task_type=request.task_type,
        target_column=request.target_column,
        status="running",
    )
    db.add(experiment)
    await db.flush()

    # 5. Run AutoML benchmark
    start_time = time.perf_counter()
    trainer = AutoMLTrainer(
        task_type=request.task_type,
        test_size=request.test_size,
        candidate_algorithms=request.candidate_algorithms,
    )

    try:
        (
            champion_model,
            preprocessor,
            target_encoder,
            best_summary,
            leaderboard,
            feature_importances,
        ) = trainer.run_benchmark(df, request.target_column, request.feature_columns)
    except Exception as e:
        experiment.status = "failed"
        experiment.logs = str(e)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"AutoML training benchmark failed: {str(e)}",
        )

    training_duration_ms = int((time.perf_counter() - start_time) * 1000)

    # 6. Save artifact bundle
    model_dir = get_model_storage_dir(workspace_id, ml_model.id)
    artifact_path = model_dir / f"model_v{version_number}.joblib"
    sha256_hash = trainer.save_artifact(
        artifact_path,
        champion_model,
        preprocessor,
        target_encoder,
        best_summary,
    )

    # 7. Update existing versions to candidate status
    await db.execute(
        update(MLModelVersion)
        .where(
            MLModelVersion.model_id == ml_model.id,
            MLModelVersion.status == "champion",
        )
        .values(status="candidate")
    )

    # 8. Create MLModelVersion record
    model_version = MLModelVersion(
        model_id=ml_model.id,
        version_number=version_number,
        experiment_id=experiment.id,
        artifact_path=str(artifact_path),
        sha256=sha256_hash,
        algorithm=best_summary["algorithm"],
        status="champion",
        metrics_json=json.dumps(best_summary["metrics"]),
        hyperparameters_json=json.dumps(best_summary["hyperparameters"]),
        feature_names_json=json.dumps(best_summary["feature_names"]),
        feature_importance_json=json.dumps(feature_importances),
    )
    db.add(model_version)
    await db.flush()

    # Update model active version
    ml_model.active_version_id = model_version.id

    # 9. Complete experiment record
    experiment.status = "completed"
    experiment.best_algorithm = best_summary["algorithm"]
    experiment.leaderboard_json = json.dumps([item.model_dump() for item in leaderboard])
    experiment.training_duration_ms = training_duration_ms
    experiment.logs = f"Benchmark completed successfully in {training_duration_ms} ms. Best estimator: {best_summary['algorithm']}."

    # 10. Automatic Lineage Registration
    try:
        ds_node = await register_or_get_node(
            db,
            workspace_id=workspace_id,
            name=dataset.name,
            node_type="dataset",
            resource_id=dataset.id,
        )
        ml_node = await register_or_get_node(
            db,
            workspace_id=workspace_id,
            name=f"ML: {ml_model.name} (v{version_number})",
            node_type="model",
            resource_id=ml_model.id,
            metadata_json={"algorithm": best_summary["algorithm"], "task_type": request.task_type},
        )
        await create_edge_if_not_exists(
            db,
            workspace_id=workspace_id,
            source_node_id=ds_node.id,
            target_node_id=ml_node.id,
            edge_type="trains_model",
            transformation_summary=f"Trained {best_summary['algorithm']} on {request.target_column}",
        )
    except Exception:
        # Graceful non-blocking lineage attachment
        pass

    await db.commit()
    await db.refresh(model_version)

    return AutoMLTrainResponse(
        model_id=ml_model.id,
        version_id=model_version.id,
        experiment_id=experiment.id,
        model_name=ml_model.name,
        task_type=ml_model.task_type,
        target_column=ml_model.target_column,
        best_algorithm=best_summary["algorithm"],
        metrics=best_summary["metrics"],
        feature_names=best_summary["feature_names"],
        feature_importances=feature_importances,
        leaderboard=leaderboard,
        training_duration_ms=training_duration_ms,
    )


async def list_workspace_models(
    db: AsyncSession,
    workspace_id: str,
) -> List[MLModelRead]:
    """List all registered models within workspace."""
    result = await db.execute(
        select(MLModel)
        .where(MLModel.workspace_id == workspace_id)
        .options(selectinload(MLModel.versions))
        .order_by(MLModel.created_at.desc())
    )
    models = result.scalars().all()

    model_reads: List[MLModelRead] = []
    for m in models:
        versions = m.versions or []
        active_v = None
        if m.active_version_id:
            active_v = next((v for v in versions if v.id == m.active_version_id), None)
        if not active_v and versions:
            active_v = next((v for v in versions if v.status == "champion"), versions[0])

        active_v_read = MLModelVersionRead.model_validate(active_v) if active_v else None

        model_reads.append(
            MLModelRead(
                id=m.id,
                workspace_id=m.workspace_id,
                name=m.name,
                description=m.description,
                task_type=m.task_type,
                target_column=m.target_column,
                framework=m.framework,
                active_version_id=m.active_version_id,
                versions_count=len(versions),
                active_version=active_v_read,
                created_at=m.created_at,
                updated_at=m.updated_at,
            )
        )

    return model_reads


async def get_model_detail(
    db: AsyncSession,
    model_id: str,
    workspace_id: str,
) -> MLModelDetailRead:
    """Retrieve full model specification with all versions."""
    result = await db.execute(
        select(MLModel)
        .where(
            MLModel.id == model_id,
            MLModel.workspace_id == workspace_id,
        )
        .options(selectinload(MLModel.versions))
    )
    m = result.scalar_one_or_none()
    if not m:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model '{model_id}' not found in active workspace.",
        )

    versions = m.versions or []
    version_reads = [MLModelVersionRead.model_validate(v) for v in versions]
    active_v = next((v for v in version_reads if v.id == m.active_version_id), None)
    if not active_v and version_reads:
        active_v = next((v for v in version_reads if v.status == "champion"), version_reads[0])

    return MLModelDetailRead(
        id=m.id,
        workspace_id=m.workspace_id,
        name=m.name,
        description=m.description,
        task_type=m.task_type,
        target_column=m.target_column,
        framework=m.framework,
        active_version_id=m.active_version_id,
        versions_count=len(versions),
        active_version=active_v,
        versions=version_reads,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


async def delete_model(
    db: AsyncSession,
    model_id: str,
    workspace_id: str,
) -> bool:
    """Delete registered model and its physical artifacts from disk."""
    result = await db.execute(
        select(MLModel).where(
            MLModel.id == model_id,
            MLModel.workspace_id == workspace_id,
        )
    )
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model '{model_id}' not found in active workspace.",
        )

    # Remove storage files
    model_dir = get_model_storage_dir(workspace_id, model_id)
    if model_dir.exists():
        shutil.rmtree(model_dir, ignore_errors=True)

    await db.delete(model)
    await db.commit()
    return True


async def promote_model_version(
    db: AsyncSession,
    model_id: str,
    version_id: str,
    workspace_id: str,
) -> MLModelVersionRead:
    """Promote candidate model version to champion status."""
    result = await db.execute(
        select(MLModel)
        .where(
            MLModel.id == model_id,
            MLModel.workspace_id == workspace_id,
        )
        .options(selectinload(MLModel.versions))
    )
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model '{model_id}' not found in active workspace.",
        )

    target_version_res = await db.execute(
        select(MLModelVersion).where(
            MLModelVersion.id == version_id,
            MLModelVersion.model_id == model_id,
        )
    )
    target_version = target_version_res.scalar_one_or_none()
    if not target_version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Version '{version_id}' not found on model '{model_id}'.",
        )

    # Demote current champions
    await db.execute(
        update(MLModelVersion)
        .where(
            MLModelVersion.model_id == model_id,
            MLModelVersion.status == "champion",
        )
        .values(status="candidate")
    )

    target_version.status = "champion"
    model.active_version_id = version_id
    await db.commit()
    await db.refresh(target_version)
    return MLModelVersionRead.model_validate(target_version)


async def list_workspace_experiments(
    db: AsyncSession,
    workspace_id: str,
) -> List[MLExperimentRead]:
    """List all training experiments in workspace."""
    result = await db.execute(
        select(MLExperiment)
        .where(MLExperiment.workspace_id == workspace_id)
        .order_by(MLExperiment.created_at.desc())
    )
    experiments = result.scalars().all()
    return [MLExperimentRead.model_validate(exp) for exp in experiments]


async def execute_model_inference(
    db: AsyncSession,
    model_id: str,
    inputs: Any,
    workspace_id: str,
    version_id: Optional[str] = None,
) -> InferenceResponse:
    """Execute prediction inference against active or specified model version."""
    result = await db.execute(
        select(MLModel)
        .where(
            MLModel.id == model_id,
            MLModel.workspace_id == workspace_id,
        )
        .options(selectinload(MLModel.versions))
    )
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model '{model_id}' not found in active workspace.",
        )

    if version_id:
        v_res = await db.execute(
            select(MLModelVersion).where(
                MLModelVersion.id == version_id,
                MLModelVersion.model_id == model_id,
            )
        )
        target_version = v_res.scalar_one_or_none()
        if not target_version:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Version '{version_id}' not found on model '{model_id}'.",
            )
    else:
        if model.active_version_id:
            v_res = await db.execute(
                select(MLModelVersion).where(
                    MLModelVersion.id == model.active_version_id,
                    MLModelVersion.model_id == model_id,
                )
            )
            target_version = v_res.scalar_one_or_none()
        else:
            v_res = await db.execute(
                select(MLModelVersion)
                .where(
                    MLModelVersion.model_id == model_id,
                    MLModelVersion.status == "champion",
                )
                .order_by(MLModelVersion.version_number.desc())
            )
            target_version = v_res.scalar_one_or_none()

    if not target_version:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Model '{model_id}' has no trained versions.",
        )

    res = run_inference(
        artifact_path=target_version.artifact_path,
        inputs=inputs,
        model_id=model.id,
        version_id=target_version.id,
    )

    return InferenceResponse(**res)
