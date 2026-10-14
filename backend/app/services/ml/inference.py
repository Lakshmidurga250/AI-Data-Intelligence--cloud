"""Online real-time model inference engine with artifact caching."""

import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import joblib
import numpy as np
import pandas as pd
from fastapi import HTTPException, status

_MODEL_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}


def load_cached_bundle(artifact_path: str) -> Dict[str, Any]:
    """Load model bundle from disk with cache invalidation based on file mtime."""
    path_obj = Path(artifact_path)
    if not path_obj.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model artifact not found on disk at '{artifact_path}'.",
        )

    mtime = path_obj.stat().st_mtime
    if artifact_path in _MODEL_CACHE:
        cached_mtime, cached_bundle = _MODEL_CACHE[artifact_path]
        if cached_mtime == mtime:
            return cached_bundle

    try:
        bundle = joblib.load(str(path_obj))
        _MODEL_CACHE[artifact_path] = (mtime, bundle)
        return bundle
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load model artifact: {str(e)}",
        )


def run_inference(
    artifact_path: str,
    inputs: Union[Dict[str, Any], List[Dict[str, Any]]],
    model_id: str,
    version_id: str,
) -> Dict[str, Any]:
    """Execute prediction on inputs using serialized bundle."""
    start_time = time.perf_counter()

    bundle = load_cached_bundle(artifact_path)
    model = bundle["model"]
    preprocessor = bundle["preprocessor"]
    target_encoder = bundle["target_encoder"]
    metadata = bundle.get("metadata", {})

    task_type = metadata.get("task_type", getattr(target_encoder, "task_type", "classification"))
    algorithm = metadata.get("algorithm", type(model).__name__)

    # Transform features
    try:
        X_mat = preprocessor.transform(inputs)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to preprocess input records: {str(e)}",
        )

    # Execute predictions
    raw_preds = model.predict(X_mat)
    inverse_preds = target_encoder.inverse_transform(raw_preds)

    # Class probabilities if classification
    probabilities: Optional[List[Dict[str, float]]] = None
    if task_type == "classification" and hasattr(model, "predict_proba"):
        try:
            raw_probas = model.predict_proba(X_mat)
            classes = target_encoder.classes_
            probas_list: List[Dict[str, float]] = []
            for row in raw_probas:
                row_dict = {
                    classes[idx] if idx < len(classes) else str(idx): round(float(prob), 4)
                    for idx, prob in enumerate(row)
                }
                probas_list.append(row_dict)
            probabilities = probas_list
        except Exception:
            pass

    latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)

    return {
        "model_id": model_id,
        "version_id": version_id,
        "algorithm": algorithm,
        "task_type": task_type,
        "predictions": inverse_preds,
        "probabilities": probabilities,
        "latency_ms": latency_ms,
    }
