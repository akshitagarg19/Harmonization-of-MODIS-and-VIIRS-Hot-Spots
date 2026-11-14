from pathlib import Path
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = ROOT / "data" / "processed"
OUTPUT_DIR = ROOT / "outputs"

METRICS = [
    "n_detections",
    "frp_sum",
    "frp_max",
    "day_count",
    "night_count",
    "high_confidence_count",
]


def aggregate_family(input_file, period_column, output_file):

    print(f"\nProcessing {input_file.name}...")

    df = pd.read_parquet(input_file)

    required = [
        period_column,
        "grid_id",
        "sensor_family",
        *METRICS,
    ]

    missing = [col for col in required if col not in df.columns]

    if missing:
        raise ValueError(f"Missing columns: {missing}")

    # Combine individual sensors within each family and cell-period.
    groups = [
        period_column,
        "grid_id",
        "sensor_family",
    ]

    family = (
        df.groupby(groups, observed=True)
        .agg(
            n_detections=("n_detections", "sum"),
            frp_sum=("frp_sum", "sum"),
            frp_max=("frp_max", "max"),
            day_count=("day_count", "sum"),
            night_count=("night_count", "sum"),
            high_confidence_count=(
                "high_confidence_count", "sum"
            ),
        )
        .reset_index()
    )

    # Weighted mean: total FRP / total detections.
    family["frp_mean"] = (
        family["frp_sum"] / family["n_detections"]
    )

    # One active cell per family-cell-period combination.
    family["n_cells_active"] = 1

    # Cell-level output.
    family = family.sort_values(
        [period_column, "sensor_family", "grid_id"]
    )

    family.to_parquet(
        output_file,
        index=False
    )

    print(f"Created: {output_file.name}")
    print(f"Rows: {len(family):,}")

    return family


def create_aoi_table(cell_table, period_column, output_file):

    print(f"\nCreating {output_file.name}...")

    groups = [period_column, "sensor_family"]

    # Aggregate cell-level family results to Punjab AOI.
    aoi = (
        cell_table.groupby(groups, observed=True)
        .agg(
            n_detections=("n_detections", "sum"),
            frp_sum=("frp_sum", "sum"),
            frp_max=("frp_max", "max"),
            day_count=("day_count", "sum"),
            night_count=("night_count", "sum"),
            high_confidence_count=(
                "high_confidence_count", "sum"
            ),
            n_cells_active=("grid_id", "nunique"),
        )
        .reset_index()
    )

    aoi["frp_mean"] = (
        aoi["frp_sum"] / aoi["n_detections"]
    )

    aoi = aoi.sort_values(
        [period_column, "sensor_family"]
    )

    aoi.to_parquet(output_file, index=False)

    print(f"Rows: {len(aoi):,}")

    return aoi


def main():

    print("=" * 55)
    print("SENSOR FAMILY AGGREGATION")
    print("=" * 55)

    # Weekly family-level cell aggregation.
    weekly_cell = aggregate_family(
        DATA_DIR / "weekly_cell.parquet",
        "week_start",
        DATA_DIR / "weekly_cell_family.parquet",
    )

    # Monthly family-level cell aggregation.
    monthly_cell = aggregate_family(
        DATA_DIR / "monthly_cell.parquet",
        "month_start",
        DATA_DIR / "monthly_cell_family.parquet",
    )

    # Weekly Punjab-level family aggregation.
    weekly_aoi = create_aoi_table(
        weekly_cell,
        "week_start",
        DATA_DIR / "weekly_aoi_family.parquet",
    )

    # Monthly Punjab-level family aggregation.
    monthly_aoi = create_aoi_table(
        monthly_cell,
        "month_start",
        DATA_DIR / "monthly_aoi_family.parquet",
    )

    # QA: family totals must match individual sensor totals.
    qa_rows = []

    for name, table in {
        "weekly_cell_family": weekly_cell,
        "monthly_cell_family": monthly_cell,
        "weekly_aoi_family": weekly_aoi,
        "monthly_aoi_family": monthly_aoi,
    }.items():

        for family_name, group in table.groupby("sensor_family"):

            qa_rows.append({
                "dataset": name,
                "sensor_family": family_name,
                "rows": len(group),
                "total_detections": group["n_detections"].sum(),
                "total_frp": group["frp_sum"].sum(),
                "active_cell_records": group["n_cells_active"].sum(),
            })

    qa = pd.DataFrame(qa_rows)

    qa.to_csv(
        OUTPUT_DIR / "sensor_family_aggregation_qa.csv",
        index=False
    )

    print("\n" + "=" * 55)
    print("FAMILY AGGREGATION COMPLETED")
    print("=" * 55)

    print("\nFamily detection totals:")

    print(
        weekly_aoi.groupby("sensor_family")["n_detections"]
        .sum()
        .to_string()
    )

    print("\nQA report:")
    print(qa.to_string(index=False))


if __name__ == "__main__":
    main()