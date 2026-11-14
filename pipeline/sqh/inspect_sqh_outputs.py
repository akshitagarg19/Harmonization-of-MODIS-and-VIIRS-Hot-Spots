from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

FILES = {
    "hotspots_sqh": ROOT / "data/processed/sqh/hotspots_sqh.parquet",
    "weekly_cell_sqh": ROOT / "data/processed/sqh/weekly_cell_sqh.parquet",
    "monthly_cell_sqh": ROOT / "data/processed/sqh/monthly_cell_sqh.parquet",
    "weekly_aoi_sqh": ROOT / "data/processed/sqh/weekly_aoi_sqh.parquet",
    "monthly_aoi_sqh": ROOT / "data/processed/sqh/monthly_aoi_sqh.parquet",
}

PERIOD_COLUMNS = ["week_start", "month_start"]

for name, path in FILES.items():

    print("\n" + "=" * 75)
    print(f"FILE: {name}")
    print("=" * 75)

    if not path.exists():
        print(f"MISSING FILE: {path}")
        continue

    df = pd.read_parquet(path)

    print(f"\nPath: {path}")
    print(f"Shape: {df.shape}")

    print("\nColumns:")
    print(df.columns.tolist())

    print("\nData types:")
    print(df.dtypes.to_string())

    if "sensor" in df.columns:
        print("\nRows by sensor:")
        print(df["sensor"].value_counts(dropna=False).to_string())

    period_col = next(
        (col for col in PERIOD_COLUMNS if col in df.columns),
        None
    )

    if period_col:
        df[period_col] = pd.to_datetime(df[period_col])

        print(f"\n{period_col} range:")
        print("Minimum:", df[period_col].min())
        print("Maximum:", df[period_col].max())

        overlap = df[df[period_col] >= "2012-01-01"]

        print("\nRows from common comparison period (2012 onward):")
        print(len(overlap))

        if "sensor" in overlap.columns:
            print("\nCommon-period rows by sensor:")
            print(overlap["sensor"].value_counts().to_string())

    if "acq_date" in df.columns:
        df["acq_date"] = pd.to_datetime(df["acq_date"])

        print("\nAcquisition date range:")
        print("Minimum:", df["acq_date"].min())
        print("Maximum:", df["acq_date"].max())

        print("\nRows by sensor:")
        print(df.groupby("sensor").size().to_string())

    important_columns = [
        "detection_count",
        "frp_sum",
        "frp_mean",
        "frp_max",
        "active_cells_1km",
        "sqh_cell_id",
    ]

    available = [
        col for col in important_columns
        if col in df.columns
    ]

    if available:
        print("\nMissing values in important columns:")
        print(df[available].isna().sum().to_string())

    # Check whether the expected cell-period-sensor key is unique.
    if (
        "sqh_cell_id" in df.columns
        and "sensor" in df.columns
        and period_col is not None
    ):
        key = [period_col, "sensor", "sqh_cell_id"]
        duplicate_count = df.duplicated(subset=key).sum()

        print("\nCell-period-sensor key:")
        print(key)
        print("Duplicate key rows:", duplicate_count)

    print("\nFirst 3 rows:")
    print(df.head(3).to_string(index=False))

print("\n\nINSPECTION COMPLETED")