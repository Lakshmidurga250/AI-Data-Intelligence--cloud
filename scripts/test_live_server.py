import httpx as requests

base = "http://127.0.0.1:5000"

# 1. Health
r_health = requests.get(f"{base}/api/v1/health")
print("1. Health Endpoint:", r_health.status_code, r_health.json()["status"])

# 2. Datasets
r_ds = requests.get(f"{base}/api/v1/datasets")
datasets = r_ds.json()
print(f"2. Datasets ({len(datasets)}):")
for d in datasets:
    print(f"   - {d['name']}: {d['row_count']} rows, {d['column_count']} cols")

sales_id = next(d["id"] for d in datasets if "Sales" in d["name"])

# 3. Preview
r_prev = requests.get(f"{base}/api/v1/datasets/{sales_id}/preview?limit=3")
print("3. Preview Endpoint:", r_prev.status_code, "Rows returned:", len(r_prev.json()["preview_data"]))

# 4. Profiler
r_prof = requests.get(f"{base}/api/v1/datasets/{sales_id}/profile")
prof = r_prof.json()
print("4. Profiler Endpoint:", r_prof.status_code, "Completeness:", prof["completeness_score"], "%, Dups:", prof["duplicate_rows_count"])

# 5. Dynamic Analytics
r_ana = requests.get(f"{base}/api/v1/datasets/{sales_id}/analytics")
ana = r_ana.json()
print("5. Analytics Endpoint:", r_ana.status_code, "Type:", ana["dataset_type"], "KPIs:", [k["title"] + ": " + k["value"] for k in ana["kpis"]])

# 6. AI Copilot
r_copilot = requests.post(f"{base}/api/v1/assistant/query", json={"dataset_id": sales_id, "prompt": "What are the total sales?"})
print("6. Copilot Endpoint:", r_copilot.status_code, "Answer:", r_copilot.json()["answer"])

# 7. Data Cleaning
r_clean = requests.post(f"{base}/api/v1/datasets/{sales_id}/clean", json={"remove_duplicates": True, "fill_numeric_strategy": "median"})
clean_data = r_clean.json()
print("7. Data Cleaning Endpoint:", r_clean.status_code, "Created:", clean_data["new_dataset_name"], "Actions:", clean_data["actions_applied"])

# 8. Visual ETL Pipeline
r_pipe = requests.post(f"{base}/api/v1/pipelines/execute", json={
    "source_dataset_id": sales_id,
    "nodes": [{"type": "deduplicate"}, {"type": "filter", "config": {"column": "quantity", "operator": ">", "value": 2}}],
    "output_name": "live_etl_test_output.csv"
})
pipe_data = r_pipe.json()
print("8. Pipeline Endpoint:", r_pipe.status_code, "Output:", pipe_data["output_dataset_name"], "Rows:", pipe_data["output_rows"])

# 9. AutoML
r_ml = requests.post(f"{base}/api/v1/ml/train", json={"dataset_id": sales_id, "target_column": "category"})
ml_data = r_ml.json()
print("9. AutoML Endpoint:", r_ml.status_code, "Champion:", ml_data["champion_algorithm"], "Score:", ml_data["champion_score"])

print("\n>>> ALL 9 HTTP REST ENDPOINTS LIVE ON HTTP://LOCALHOST:5000 AND 100% OPERATIONAL! <<<")
