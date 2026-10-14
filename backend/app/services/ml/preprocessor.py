"""Tabular automated feature preprocessing and target encoding engine."""

from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd


class TabularPreprocessor:
    """Automated preprocessing pipeline for tabular features.

    Imputes missing values, encodes categorical features into dummy/indicator columns,
    normalizes numeric features, and maintains deterministic feature schemas for inference.
    """

    def __init__(self) -> None:
        self.numeric_features: List[str] = []
        self.categorical_features: List[str] = []
        self.numeric_medians: Dict[str, float] = {}
        self.numeric_means: Dict[str, float] = {}
        self.numeric_stds: Dict[str, float] = {}
        self.category_levels: Dict[str, List[Any]] = {}
        self.feature_names_out_: List[str] = []
        self.is_fitted: bool = False

    def fit(self, X: pd.DataFrame) -> "TabularPreprocessor":
        """Fit preprocessor statistics on training features."""
        X_df = X.copy()

        # Identify numeric vs categorical columns
        self.numeric_features = []
        self.categorical_features = []

        for col in X_df.columns:
            if pd.api.types.is_numeric_dtype(X_df[col]):
                self.numeric_features.append(col)
                # Compute median for imputation and mean/std for scaling
                series = pd.to_numeric(X_df[col], errors="coerce")
                med = float(series.median()) if not np.isnan(series.median()) else 0.0
                mean = float(series.mean()) if not np.isnan(series.mean()) else 0.0
                std = float(series.std()) if not np.isnan(series.std()) and series.std() > 1e-6 else 1.0
                self.numeric_medians[col] = med
                self.numeric_means[col] = mean
                self.numeric_stds[col] = std
            else:
                self.categorical_features.append(col)
                # Get unique levels for one-hot encoding (capped at top 50 to avoid explosion)
                levels = X_df[col].dropna().astype(str).value_counts().head(50).index.tolist()
                self.category_levels[col] = levels

        # Determine feature_names_out_
        features_out = list(self.numeric_features)
        for cat_col in self.categorical_features:
            for lvl in self.category_levels.get(cat_col, []):
                features_out.append(f"{cat_col}_{lvl}")
            features_out.append(f"{cat_col}_other")

        self.feature_names_out_ = features_out
        self.is_fitted = True
        return self

    def transform(self, X: Union[pd.DataFrame, Dict[str, Any], List[Dict[str, Any]]]) -> np.ndarray:
        """Transform input data into formatted numerical feature matrix."""
        if not self.is_fitted:
            raise ValueError("TabularPreprocessor must be fitted before transforming.")

        if isinstance(X, dict):
            X_df = pd.DataFrame([X])
        elif isinstance(X, list):
            X_df = pd.DataFrame(X)
        else:
            X_df = X.copy()

        n_samples = len(X_df)
        n_features = len(self.feature_names_out_)
        output_matrix = np.zeros((n_samples, n_features), dtype=np.float64)

        col_idx = 0
        # 1. Numeric features with imputation and standardization
        for num_col in self.numeric_features:
            if num_col in X_df.columns:
                series = pd.to_numeric(X_df[num_col], errors="coerce").fillna(self.numeric_medians[num_col])
                mean = self.numeric_means[num_col]
                std = self.numeric_stds[num_col]
                scaled = (series.to_numpy(dtype=np.float64) - mean) / std
            else:
                # Missing column entirely
                scaled = np.zeros(n_samples, dtype=np.float64)
            output_matrix[:, col_idx] = scaled
            col_idx += 1

        # 2. Categorical features with one-hot encoding
        for cat_col in self.categorical_features:
            levels = self.category_levels.get(cat_col, [])
            if cat_col in X_df.columns:
                str_series = X_df[cat_col].fillna("missing").astype(str).tolist()
            else:
                str_series = ["missing"] * n_samples

            matched_any = np.zeros(n_samples, dtype=bool)
            for lvl in levels:
                is_match = np.array([val == lvl for val in str_series], dtype=np.float64)
                output_matrix[:, col_idx] = is_match
                matched_any = matched_any | (is_match > 0)
                col_idx += 1

            # "other" / unknown column
            output_matrix[:, col_idx] = (~matched_any).astype(np.float64)
            col_idx += 1

        return output_matrix

    def fit_transform(self, X: pd.DataFrame) -> np.ndarray:
        """Fit on X and return transformed matrix."""
        return self.fit(X).transform(X)


class TargetEncoder:
    """Encodes target column for classification or regression tasks."""

    def __init__(self, task_type: str) -> None:
        self.task_type = task_type
        self.classes_: List[Any] = []
        self.class_to_idx: Dict[Any, int] = {}

    def fit_transform(self, y_series: pd.Series) -> np.ndarray:
        """Fit target classes or float conversions."""
        if self.task_type == "classification":
            classes = sorted(list(y_series.dropna().unique()), key=lambda x: str(x))
            self.classes_ = [str(c) for c in classes]
            self.class_to_idx = {str(c): idx for idx, c in enumerate(self.classes_)}
            return y_series.astype(str).map(self.class_to_idx).fillna(0).to_numpy(dtype=np.int64)
        else:
            # Regression: coerce to float64
            cleaned = pd.to_numeric(y_series, errors="coerce")
            med = float(cleaned.median()) if not np.isnan(cleaned.median()) else 0.0
            return cleaned.fillna(med).to_numpy(dtype=np.float64)

    def inverse_transform(self, y_pred: np.ndarray) -> List[Any]:
        """Convert predicted numeric values back to original label space."""
        if self.task_type == "classification" and self.classes_:
            return [self.classes_[int(idx)] if 0 <= int(idx) < len(self.classes_) else str(idx) for idx in y_pred]
        return [float(val) for val in y_pred]
