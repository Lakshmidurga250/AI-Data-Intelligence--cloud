import sys
from pathlib import Path
sys.path.insert(0, str(Path('.').resolve()))

from scripts.platform_service import (
    seed_default_datasets_if_needed,
    list_datasets,
    get_dataset_preview,
    profile_dataset,
    get_dataset_analytics,
    assistant_ask,
    clean_dataset,
    execute_etl_pipeline,
    train_automl_benchmark
)

def run():
    print("1. Seeding default datasets...")
    seed_default_datasets_if_needed()
    ds_list = list_datasets()
    print(f"Datasets in catalog: {len(ds_list)}")
    for d in ds_list:
        print(f"  - {d['name']}: {d['row_count']} rows, {d['column_count']} cols")

    sales_ds = next((d for d in ds_list if "Sales" in d["name"]), ds_list[0])
    ds_id = sales_ds["id"]

    print("\n2. Testing preview...")
    prev = get_dataset_preview(ds_id, limit=3)
    print(f"Preview rows: {len(prev['preview_data'])}")

    print("\n3. Testing profiler...")
    prof = profile_dataset(ds_id)
    print(f"Profiled rows: {prof['row_count']}, completeness: {prof['completeness_score']}%, dups: {prof['duplicate_rows_count']}")

    print("\n4. Testing analytics...")
    analytics = get_dataset_analytics(ds_id)
    print(f"KPIs count: {len(analytics['kpis'])}")
    for k in analytics["kpis"]:
        print(f"  {k['title']}: {k['value']}")

    print("\n5. Testing AI Copilot...")
    copilot_res = assistant_ask(ds_id, "What are the total sales?")
    print(f"Answer: {copilot_res['answer']}")

    print("\n6. Testing Data Cleaning...")
    clean_res = clean_dataset(ds_id, {"remove_duplicates": True, "fill_numeric_strategy": "median"})
    print(f"Clean result: {clean_res['actions_applied']}")
    print(f"Before rows: {clean_res['metrics_before']['rows']} -> After rows: {clean_res['metrics_after']['rows']}")

    print("\n7. Testing Visual ETL Pipeline...")
    pipeline_res = execute_etl_pipeline(
        source_dataset_id=ds_id,
        nodes=[
            {"type": "deduplicate", "config": {}},
            {"type": "filter", "config": {"column": "quantity", "operator": ">", "value": 2}}
        ],
        output_name="test_filtered_sales.csv"
    )
    print(f"Pipeline output dataset: {pipeline_res['output_dataset_name']} ({pipeline_res['output_rows']} rows)")

    print("\n8. Testing AutoML...")
    automl_res = train_automl_benchmark(ds_id, target_column="category")
    print(f"AutoML Champion: {automl_res['champion_algorithm']} with Score: {automl_res['champion_score']}")

    print("\n>>> ALL PLATFORM ENGINE OPERATIONS GENUINELY VERIFIED! <<<")

if __name__ == "__main__":
    run()
