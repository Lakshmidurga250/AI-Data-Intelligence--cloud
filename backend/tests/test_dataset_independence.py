"""
Comprehensive Dataset Independence Test Suite
Verifies that the ADIC platform operates dynamically across multiple distinct schemas:
1. Sales Dataset (orders, dates, categories, quantities, revenues)
2. Customers Dataset (customer IDs, ages, cities, signup dates, churn risk)
3. Employees Dataset (employee IDs, departments, salaries, hire dates, ratings)
4. Generic IoT Sensor Dataset (temperatures, pressures, timestamps, machine status)
5. Quality-Degraded Dataset (missing values, duplicate rows)
6. Empty, Malformed, and Unsupported Files (rejection and error handling)
7. Dataset Isolation & State Leak Prevention
"""

import os
import io
import pytest
from pathlib import Path

from scripts.platform_service import (
    seed_default_datasets_if_needed,
    list_datasets,
    get_dataset,
    get_dataset_preview,
    profile_dataset,
    clean_dataset,
    execute_etl_pipeline,
    get_dataset_analytics,
    assistant_ask,
    train_automl_benchmark,
    upload_dataset_file,
    delete_dataset
)


class MockFileStorage:
    def __init__(self, filename: str, content: bytes):
        self.filename = filename
        self.content = content

    def save(self, destination: str):
        with open(destination, "wb") as f:
            f.write(self.content)


@pytest.fixture(scope="module", autouse=True)
def setup_datasets():
    seed_default_datasets_if_needed()


def test_sales_dataset_workflow():
    """Verify primary sales dataset end-to-end workflow."""
    datasets = list_datasets()
    sales_ds = next((d for d in datasets if "Sales" in d["name"]), None)
    assert sales_ds is not None, "Sales dataset must be present in catalog."
    ds_id = sales_ds["id"]

    # 1. Preview
    preview = get_dataset_preview(ds_id, limit=10)
    assert preview["row_count"] >= 100
    assert preview["column_count"] == 10
    assert len(preview["preview_data"]) == 10

    # 2. Profiling
    prof = profile_dataset(ds_id)
    assert prof["row_count"] >= 100
    assert prof["column_count"] == 10
    col_names = [c["name"] for c in prof["columns"]]
    assert "total_sales" in col_names
    assert "quantity" in col_names
    assert "unit_price" in col_names
    # Check numeric stats computed
    sales_col_prof = next(c for c in prof["columns"] if c["name"] == "total_sales")
    assert sales_col_prof["numeric_stats"] is not None
    assert sales_col_prof["numeric_stats"]["mean"] > 0
    assert sales_col_prof["numeric_stats"]["min"] > 0

    # 3. Dynamic Analytics
    analytics = get_dataset_analytics(ds_id)
    assert analytics["dataset_type"] == "sales"
    assert len(analytics["kpis"]) == 4
    kpi_titles = [k["title"] for k in analytics["kpis"]]
    assert "Total Revenue" in kpi_titles
    assert "Total Orders" in kpi_titles
    assert len(analytics["category_chart"]["data"]) > 0
    assert len(analytics["region_chart"]["data"]) > 0

    # 4. AI Copilot
    ans_sales = assistant_ask(ds_id, "What are the total sales?")
    assert "total sales" in ans_sales["answer"].lower()
    assert "$" in ans_sales["answer"]


def test_customer_dataset_adaptive():
    """Verify platform adapts dynamically to customer schema (no sales columns)."""
    datasets = list_datasets()
    cust_ds = next((d for d in datasets if "Customer" in d["name"]), None)
    assert cust_ds is not None
    ds_id = cust_ds["id"]

    # 1. Preview
    preview = get_dataset_preview(ds_id, limit=5)
    assert preview["row_count"] == 80
    assert preview["column_count"] == 7
    col_names = [c["name"] for c in preview["columns"]]
    assert "age" in col_names
    assert "city" in col_names
    assert "total_sales" not in col_names

    # 2. Profiling
    prof = profile_dataset(ds_id)
    assert prof["row_count"] == 80
    age_prof = next(c for c in prof["columns"] if c["name"] == "age")
    assert age_prof["numeric_stats"]["min"] >= 18
    assert age_prof["numeric_stats"]["max"] <= 75

    # 3. Dynamic Analytics adapts without hardcoded sales
    analytics = get_dataset_analytics(ds_id)
    assert analytics["dataset_type"] == "generic"
    assert len(analytics["kpis"]) >= 2
    # Verify city distribution exists
    assert len(analytics["category_chart"]["data"]) > 0

    # 4. AI Copilot adapts to customer questions
    copilot_res = assistant_ask(ds_id, "Show summary of customers")
    assert copilot_res["answer"] is not None


def test_employee_dataset_adaptive():
    """Verify platform adapts dynamically to employee schema."""
    datasets = list_datasets()
    emp_ds = next((d for d in datasets if "Employee" in d["name"]), None)
    assert emp_ds is not None
    ds_id = emp_ds["id"]

    # Profiler
    prof = profile_dataset(ds_id)
    assert prof["row_count"] == 74
    col_names = [c["name"] for c in prof["columns"]]
    assert "department" in col_names
    assert "salary" in col_names

    salary_prof = next(c for c in prof["columns"] if c["name"] == "salary")
    assert salary_prof["numeric_stats"]["mean"] > 40000

    # Dynamic Analytics
    analytics = get_dataset_analytics(ds_id)
    assert analytics["dataset_type"] == "generic"
    assert any("salary" in k["title"].lower() for k in analytics["kpis"])


def test_sensor_dataset_adaptive():
    """Verify platform adapts dynamically to IoT sensor schema."""
    datasets = list_datasets()
    sensor_ds = next((d for d in datasets if "Sensor" in d["name"]), None)
    assert sensor_ds is not None
    ds_id = sensor_ds["id"]

    prof = profile_dataset(ds_id)
    assert prof["row_count"] == 100
    col_names = [c["name"] for c in prof["columns"]]
    assert "temperature" in col_names
    assert "pressure_psi" in col_names

    analytics = get_dataset_analytics(ds_id)
    assert analytics["dataset_type"] == "generic"


def test_data_cleaning_operations():
    """Verify real data cleaning: duplicate removal, imputation, and derived dataset persistence."""
    datasets = list_datasets()
    sales_ds = next((d for d in datasets if d["name"] == "Sample Sales Dataset (Primary)"), None)
    assert sales_ds is not None
    ds_id = sales_ds["id"]

    # The raw sample sales has 2 duplicates and controlled missing values
    clean_res = clean_dataset(ds_id, {
        "remove_duplicates": True,
        "fill_numeric_strategy": "median",
        "fill_categorical_strategy": "mode"
    })

    assert clean_res["success"] is True
    assert clean_res["new_dataset_id"] is not None
    assert clean_res["metrics_after"]["duplicates"] == 0
    assert clean_res["metrics_after"]["rows"] <= clean_res["metrics_before"]["rows"]

    # Verify original dataset was preserved
    orig_ds = get_dataset(ds_id)
    assert orig_ds["row_count"] == 122

    # Verify new derived dataset exists in catalog
    derived_ds = get_dataset(clean_res["new_dataset_id"])
    assert derived_ds is not None
    assert derived_ds["row_count"] == 120

    # Cleanup derived test dataset
    delete_dataset(clean_res["new_dataset_id"])


def test_visual_etl_pipeline_execution():
    """Verify Visual ETL Pipeline executes stages and materializes output dataset."""
    datasets = list_datasets()
    sales_ds = next((d for d in datasets if "Sales" in d["name"]), datasets[0])
    ds_id = sales_ds["id"]

    res = execute_etl_pipeline(
        source_dataset_id=ds_id,
        nodes=[
            {"type": "deduplicate", "config": {}},
            {"type": "filter", "config": {"column": "quantity", "operator": ">=", "value": 5}},
            {"type": "impute", "config": {"strategy": "median"}}
        ],
        output_name="test_pipeline_sink.csv"
    )

    assert res["success"] is True
    assert res["output_dataset_id"] is not None
    assert res["total_stages"] >= 4
    assert res["output_rows"] < res["input_rows"]

    # Output dataset should be registered in catalog
    out_meta = get_dataset(res["output_dataset_id"])
    assert out_meta is not None
    assert out_meta["row_count"] == res["output_rows"]

    # Clean up test output dataset
    delete_dataset(res["output_dataset_id"])


def test_empty_and_malformed_file_rejection():
    """Verify robust error handling for empty, malformed, or invalid files."""
    # 1. Unsupported extension
    with pytest.raises(ValueError, match="Unsupported file type"):
        upload_dataset_file(MockFileStorage("test.exe", b"malicious executable"))

    # 2. Empty file (0 bytes)
    with pytest.raises(ValueError, match="empty"):
        upload_dataset_file(MockFileStorage("empty.csv", b""))

    # 3. Malformed file (0 columns or unparseable)
    with pytest.raises(ValueError):
        upload_dataset_file(MockFileStorage("corrupt.csv", b"\x00\x01\x02\x03\xff\xfe"))


def test_dataset_isolation_and_no_leakage():
    """Verify changing dataset switches context completely without leaking state."""
    datasets = list_datasets()
    sales_ds = next((d for d in datasets if "Sales" in d["name"]), None)
    emp_ds = next((d for d in datasets if "Employee" in d["name"]), None)
    assert sales_ds is not None and emp_ds is not None

    sales_analytics = get_dataset_analytics(sales_ds["id"])
    emp_analytics = get_dataset_analytics(emp_ds["id"])

    # Sales dataset must contain sales KPIs
    assert sales_analytics["dataset_type"] == "sales"
    assert any("revenue" in k["title"].lower() for k in sales_analytics["kpis"])

    # Employee dataset must NOT contain sales revenue or sales KPIs
    assert emp_analytics["dataset_type"] == "generic"
    assert not any("revenue" in k["title"].lower() for k in emp_analytics["kpis"])
    assert any("salary" in k["title"].lower() for k in emp_analytics["kpis"])

    # Copilot queries must be scoped to the specified dataset
    ans_sales = assistant_ask(sales_ds["id"], "What are total sales?")
    ans_emp = assistant_ask(emp_ds["id"], "What are total sales?")
    # Employee dataset has no sales column, so it does not invent sales numbers
    assert "Sample Sales" in ans_sales["answer"] or "sales" in ans_sales["answer"].lower()
    assert "Sample Sales" not in ans_emp["answer"]
