from pathlib import Path

import pandas as pd


# ==================================================
# PATHS
# ==================================================

ROOT = Path(__file__).resolve().parents[1]

INPUT_FILE = ROOT / "data" / "processed" / "hotspots_clean.parquet"

OUTPUT_DIR = ROOT / "data" / "processed"

QA_FILE = ROOT / "outputs" / "aggregation_qa_report.csv"


# ==================================================
# SENSOR FAMILY
# ==================================================

SENSOR_FAMILY = {
    "MODIS_Aqua": "MODIS",
    "MODIS_Terra": "MODIS",
    "VIIRS_SNPP": "VIIRS",
    "VIIRS_NOAA20": "VIIRS",
    "VIIRS_NOAA21": "VIIRS",
}


# ==================================================
# AGGREGATION FUNCTION
# ==================================================

def aggregate(data, group_columns):

    result = (
        data.groupby(
            group_columns,
            observed=True
        )
        .agg(
            n_detections=("frp", "size"),
            frp_sum=("frp", "sum"),
            frp_mean=("frp", "mean"),
            frp_max=("frp", "max"),
            day_count=("period", lambda x: (x == "Day").sum()),
            night_count=("period", lambda x: (x == "Night").sum()),
            high_confidence_count=(
                "confidence_class",
                lambda x: (x == "high").sum()
            ),
        )
        .reset_index()
    )

    return result


# ==================================================
# MAIN
# ==================================================

def main():

    print("=" * 55)
    print("PHASE C: COMPLETE AGGREGATION")
    print("=" * 55)

    # ----------------------------------------------
    # LOAD DATA
    # ----------------------------------------------

    print("\nLoading cleaned dataset...")

    df = pd.read_parquet(INPUT_FILE)

    print(f"Input detections: {len(df):,}")

    df["acq_timestamp_utc"] = pd.to_datetime(
        df["acq_timestamp_utc"],
        utc=True,
        errors="coerce"
    )

    df = df.dropna(
        subset=["acq_timestamp_utc", "grid_id", "sensor"]
    ).copy()

    # ----------------------------------------------
    # SENSOR FAMILY
    # ----------------------------------------------

    df["sensor_family"] = df["sensor"].map(SENSOR_FAMILY)

    unknown_sensors = df["sensor_family"].isna().sum()

    if unknown_sensors:
        raise ValueError(
            f"{unknown_sensors} detections have unknown sensor names."
        )

    # ----------------------------------------------
    # WEEKLY AND MONTHLY PERIODS
    # ----------------------------------------------

    print("\nCreating time periods...")

    timestamps = df["acq_timestamp_utc"].dt.tz_localize(None)

    df["week_start"] = (
        timestamps.dt.to_period("W-SUN").dt.start_time
    )

    df["month_start"] = (
        timestamps.dt.to_period("M").dt.start_time
    )

    # ----------------------------------------------
    # GROUPING DIMENSIONS
    # ----------------------------------------------

    sensor_dimensions = [
        "sensor_family",
        "sensor",
    ]

    weekly_cell_groups = [
        "week_start",
        "grid_id",
        *sensor_dimensions,
    ]

    monthly_cell_groups = [
        "month_start",
        "grid_id",
        *sensor_dimensions,
    ]

    weekly_aoi_groups = [
        "week_start",
        *sensor_dimensions,
    ]

    monthly_aoi_groups = [
        "month_start",
        *sensor_dimensions,
    ]

    # ----------------------------------------------
    # 1. WEEKLY CELL
    # ----------------------------------------------

    print("\nCreating weekly_cell...")

    weekly_cell = aggregate(
        df,
        weekly_cell_groups
    )

    weekly_cell["n_cells_active"] = 1

    weekly_cell = weekly_cell.sort_values(
        ["week_start", "grid_id", "sensor"]
    )

    weekly_cell.to_parquet(
        OUTPUT_DIR / "weekly_cell.parquet",
        index=False
    )

    print(f"Weekly cell rows: {len(weekly_cell):,}")

    # ----------------------------------------------
    # 2. MONTHLY CELL
    # ----------------------------------------------

    print("\nCreating monthly_cell...")

    monthly_cell = aggregate(
        df,
        monthly_cell_groups
    )

    monthly_cell["n_cells_active"] = 1

    monthly_cell = monthly_cell.sort_values(
        ["month_start", "grid_id", "sensor"]
    )

    monthly_cell.to_parquet(
        OUTPUT_DIR / "monthly_cell.parquet",
        index=False
    )

    print(f"Monthly cell rows: {len(monthly_cell):,}")

    # ----------------------------------------------
    # 3. WEEKLY PUNJAB AOI
    # ----------------------------------------------

    print("\nCreating weekly_aoi...")

    weekly_aoi = aggregate(
        df,
        weekly_aoi_groups
    )

    weekly_active_cells = (
        df.groupby(
            weekly_aoi_groups,
            observed=True
        )["grid_id"]
        .nunique()
        .rename("n_cells_active")
        .reset_index()
    )

    weekly_aoi = weekly_aoi.merge(
        weekly_active_cells,
        on=weekly_aoi_groups,
        how="left"
    )

    weekly_aoi = weekly_aoi.sort_values(
        ["week_start", "sensor"]
    )

    weekly_aoi.to_parquet(
        OUTPUT_DIR / "weekly_aoi.parquet",
        index=False
    )

    print(f"Weekly AOI rows: {len(weekly_aoi):,}")

    # ----------------------------------------------
    # 4. MONTHLY PUNJAB AOI
    # ----------------------------------------------

    print("\nCreating monthly_aoi...")

    monthly_aoi = aggregate(
        df,
        monthly_aoi_groups
    )

    monthly_active_cells = (
        df.groupby(
            monthly_aoi_groups,
            observed=True
        )["grid_id"]
        .nunique()
        .rename("n_cells_active")
        .reset_index()
    )

    monthly_aoi = monthly_aoi.merge(
        monthly_active_cells,
        on=monthly_aoi_groups,
        how="left"
    )

    monthly_aoi = monthly_aoi.sort_values(
        ["month_start", "sensor"]
    )

    monthly_aoi.to_parquet(
        OUTPUT_DIR / "monthly_aoi.parquet",
        index=False
    )

    print(f"Monthly AOI rows: {len(monthly_aoi):,}")

    # ----------------------------------------------
    # QA REPORT
    # ----------------------------------------------

    print("\nCreating QA report...")

    datasets = {
        "weekly_cell": weekly_cell,
        "monthly_cell": monthly_cell,
        "weekly_aoi": weekly_aoi,
        "monthly_aoi": monthly_aoi,
    }

    qa_rows = []

    for name, table in datasets.items():

        time_column = (
            "week_start"
            if "weekly" in name
            else "month_start"
        )

        qa_rows.append({
            "dataset": name,
            "rows": len(table),
            "sensors": table["sensor"].nunique(),
            "sensor_families": table["sensor_family"].nunique(),
            "total_detections": table["n_detections"].sum(),
            "total_frp": table["frp_sum"].sum(),
            "total_active_cell_records": table["n_cells_active"].sum(),
            "start_period": table[time_column].min(),
            "end_period": table[time_column].max(),
        })

    qa = pd.DataFrame(qa_rows)

    qa.to_csv(QA_FILE, index=False)

    # ----------------------------------------------
    # VALIDATION
    # ----------------------------------------------

    expected_total = len(df)

    print("\nChecking detection totals...")

    for name, table in datasets.items():

        actual_total = int(table["n_detections"].sum())

        status = (
            "PASS"
            if actual_total == expected_total
            else "CHECK"
        )

        print(
            f"{name}: {actual_total:,} / "
            f"{expected_total:,} [{status}]"
        )

    # ----------------------------------------------
    # SUMMARY
    # ----------------------------------------------

    print("\n" + "=" * 55)
    print("PHASE C AGGREGATION COMPLETED")
    print("=" * 55)

    print("\nCreated files:")

    for name in datasets:
        print(f"data/processed/{name}.parquet")

    print("outputs/aggregation_qa_report.csv")

    print("\nWeekly AOI preview:")

    print(
        weekly_aoi[
            [
                "week_start",
                "sensor",
                "n_detections",
                "n_cells_active",
                "frp_sum",
            ]
        ].head(10).to_string(index=False)
    )


if __name__ == "__main__":
    main()