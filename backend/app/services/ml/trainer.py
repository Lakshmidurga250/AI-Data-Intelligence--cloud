"""AutoML trainer benchmarking candidate algorithms, ranking scorecards, and artifact serialization."""

import hashlib
import json
import math
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import (
    GradientBoostingClassifier,
    GradientBoostingRegressor,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor

from app.schemas.ml import AlgorithmLeaderboardItem
from app.services.ml.preprocessor import TabularPreprocessor, TargetEncoder


def get_candidate_estimators(task_type: str, selected_names: Optional[List[str]] = None) -> Dict[str, Any]:
    """Retrieve mapping of candidate model instances for a given task type."""
    if task_type == "classification":
        all_candidates = {
            "RandomForestClassifier": RandomForestClassifier(n_estimators=40, max_depth=8, random_state=42),
            "GradientBoostingClassifier": GradientBoostingClassifier(n_estimators=40, max_depth=4, random_state=42),
            "LogisticRegression": LogisticRegression(max_iter=500, random_state=42),
            "DecisionTreeClassifier": DecisionTreeClassifier(max_depth=8, random_state=42),
        }
    else:
        all_candidates = {
            "RandomForestRegressor": RandomForestRegressor(n_estimators=40, max_depth=8, random_state=42),
            "GradientBoostingRegressor": GradientBoostingRegressor(n_estimators=40, max_depth=4, random_state=42),
            "RidgeRegression": Ridge(alpha=1.0, random_state=42),
            "DecisionTreeRegressor": DecisionTreeRegressor(max_depth=8, random_state=42),
        }

    if not selected_names:
        return all_candidates

    # Filter to requested names case-insensitively
    lowered = [s.lower().replace("_", "").replace(" ", "") for s in selected_names]
    filtered = {
        name: inst
        for name, inst in all_candidates.items()
        if name.lower().replace("_", "") in lowered
    }
    return filtered or all_candidates


def compute_metrics(
    task_type: str,
    y_test: np.ndarray,
    y_pred: np.ndarray,
    y_proba: Optional[np.ndarray] = None,
) -> Dict[str, float]:
    """Calculate standardized metrics scorecard for classification or regression."""
    metrics: Dict[str, float] = {}

    if task_type == "classification":
        acc = float(accuracy_score(y_test, y_pred))
        prec = float(precision_score(y_test, y_pred, average="macro", zero_division=0))
        rec = float(recall_score(y_test, y_pred, average="macro", zero_division=0))
        f1 = float(f1_score(y_test, y_pred, average="macro", zero_division=0))
        metrics["accuracy"] = round(acc, 4)
        metrics["precision"] = round(prec, 4)
        metrics["recall"] = round(rec, 4)
        metrics["f1_score"] = round(f1, 4)

        # Optional ROC-AUC
        if y_proba is not None:
            try:
                if y_proba.shape[1] == 2:
                    metrics["roc_auc"] = round(float(roc_auc_score(y_test, y_proba[:, 1])), 4)
                elif y_proba.shape[1] > 2:
                    metrics["roc_auc"] = round(float(roc_auc_score(y_test, y_proba, multi_class="ovr")), 4)
            except Exception:
                pass
    else:
        mse = float(mean_squared_error(y_test, y_pred))
        rmse = float(math.sqrt(mse))
        mae = float(mean_absolute_error(y_test, y_pred))
        r2 = float(r2_score(y_test, y_pred))
        metrics["mse"] = round(mse, 4)
        metrics["rmse"] = round(rmse, 4)
        metrics["mae"] = round(mae, 4)
        metrics["r2_score"] = round(r2, 4)

    return metrics


def extract_feature_importances(model: Any, feature_names: List[str]) -> Dict[str, float]:
    """Extract and normalize feature importance coefficients."""
    raw_scores: Optional[np.ndarray] = None

    if hasattr(model, "feature_importances_"):
        raw_scores = np.array(model.feature_importances_, dtype=np.float64)
    elif hasattr(model, "coef_"):
        coefs = np.array(model.coef_, dtype=np.float64)
        if coefs.ndim > 1:
            raw_scores = np.mean(np.abs(coefs), axis=0)
        else:
            raw_scores = np.abs(coefs)

    if raw_scores is None or len(raw_scores) != len(feature_names):
        return {fn: 0.0 for fn in feature_names}

    total = np.sum(raw_scores)
    if total > 1e-9:
        normalized = raw_scores / total
    else:
        normalized = np.ones_like(raw_scores) / max(len(raw_scores), 1)

    # Sort descending
    pairs = sorted(zip(feature_names, normalized.tolist()), key=lambda x: x[1], reverse=True)
    return {fn: round(float(score), 4) for fn, score in pairs}


class AutoMLTrainer:
    """End-to-end benchmark and training execution engine."""

    def __init__(
        self,
        task_type: str,
        test_size: float = 0.2,
        candidate_algorithms: Optional[List[str]] = None,
    ) -> None:
        self.task_type = task_type
        self.test_size = test_size
        self.candidate_algorithms = candidate_algorithms

    def run_benchmark(
        self,
        df: pd.DataFrame,
        target_column: str,
        feature_columns: Optional[List[str]] = None,
    ) -> Tuple[Any, TabularPreprocessor, TargetEncoder, Dict[str, Any], List[AlgorithmLeaderboardItem], Dict[str, float]]:
        """Run training benchmark across algorithms on dataset slice."""
        if target_column not in df.columns:
            raise ValueError(f"Target column '{target_column}' does not exist in dataset.")

        # Filter features
        if feature_columns:
            available_features = [c for c in feature_columns if c in df.columns and c != target_column]
        else:
            available_features = [c for c in df.columns if c != target_column]

        if not available_features:
            raise ValueError("No feature columns available to train model.")

        X_df = df[available_features]
        y_series = df[target_column]

        # Preprocess features & targets
        preprocessor = TabularPreprocessor()
        X_mat = preprocessor.fit_transform(X_df)

        target_encoder = TargetEncoder(self.task_type)
        y_vec = target_encoder.fit_transform(y_series)

        # Train/Test Split
        stratify = y_vec if (self.task_type == "classification" and len(np.unique(y_vec)) > 1 and len(df) >= 20) else None
        try:
            X_train, X_test, y_train, y_test = train_test_split(
                X_mat, y_vec, test_size=self.test_size, random_state=42, stratify=stratify
            )
        except Exception:
            # Fallback without stratification
            X_train, X_test, y_train, y_test = train_test_split(
                X_mat, y_vec, test_size=self.test_size, random_state=42
            )

        candidates = get_candidate_estimators(self.task_type, self.candidate_algorithms)
        leaderboard: List[AlgorithmLeaderboardItem] = []

        fitted_models: Dict[str, Any] = {}
        model_metrics: Dict[str, Dict[str, float]] = {}

        for name, estimator in candidates.items():
            start_t = time.perf_counter()
            estimator.fit(X_train, y_train)
            dur_ms = round((time.perf_counter() - start_t) * 1000.0, 2)

            y_pred = estimator.predict(X_test)
            y_proba = None
            if self.task_type == "classification" and hasattr(estimator, "predict_proba"):
                try:
                    y_proba = estimator.predict_proba(X_test)
                except Exception:
                    pass

            metrics = compute_metrics(self.task_type, y_test, y_pred, y_proba)
            fitted_models[name] = estimator
            model_metrics[name] = metrics

            leaderboard.append(
                AlgorithmLeaderboardItem(
                    algorithm=name,
                    metrics=metrics,
                    training_time_ms=dur_ms,
                    is_best=False,
                )
            )

        # Determine champion based on primary metric
        if self.task_type == "classification":
            # Higher F1 score is better
            leaderboard.sort(key=lambda x: x.metrics.get("f1_score", 0.0), reverse=True)
        else:
            # Higher R2 score is better
            leaderboard.sort(key=lambda x: x.metrics.get("r2_score", -999.0), reverse=True)

        leaderboard[0].is_best = True
        champion_name = leaderboard[0].algorithm
        champion_model = fitted_models[champion_name]
        champion_metrics = model_metrics[champion_name]

        # Feature importances of champion
        feature_importances = extract_feature_importances(champion_model, preprocessor.feature_names_out_)

        best_summary = {
            "algorithm": champion_name,
            "metrics": champion_metrics,
            "feature_names": preprocessor.feature_names_out_,
            "feature_importances": feature_importances,
            "hyperparameters": {
                k: str(v) for k, v in champion_model.get_params().items()
                if isinstance(v, (int, float, str, bool, type(None)))
            },
        }

        return champion_model, preprocessor, target_encoder, best_summary, leaderboard, feature_importances

    def save_artifact(
        self,
        artifact_path: Path,
        model: Any,
        preprocessor: TabularPreprocessor,
        target_encoder: TargetEncoder,
        best_summary: Dict[str, Any],
    ) -> str:
        """Serialize model bundle using joblib and compute SHA-256 fingerprint."""
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        bundle = {
            "model": model,
            "preprocessor": preprocessor,
            "target_encoder": target_encoder,
            "metadata": best_summary,
        }
        joblib.dump(bundle, str(artifact_path))

        # Calculate SHA-256
        hasher = hashlib.sha256()
        with open(artifact_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()
