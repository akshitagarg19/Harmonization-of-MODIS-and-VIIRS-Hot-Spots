from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

DETECTIONS = ROOT / "data/processed/sqh/hotspots_sqh.parquet"
WEEKLY = ROOT / "data/processed/sqh/weekly_cell_sqh.parquet"
MONTHLY = ROOT / "data/processed/sqh/monthly_cell_sqh.parquet"

print("=" * 70)
print("1. RAW DAY/NIGHT VALUES")
print("=" * 70)

df = pd.read_parquet(
    DETECTIONS,
    columns=["sensor", "daynight", "acq_date"]
)

print("\nUnique daynight values:")
print(df["daynight"].value_counts(dropna=False))

print("\nDay/night values by sensor:")
print(
    pd.crosstab(
        df["sensor"],
        df["daynight"],
        dropna=False
    )
)

print("\n" + "=" * 70)
print("2. EXPECTED COUNTS FROM RAW DETECTIONS")
print("=" * 70)

df["daynight_normalized"] = (
    df["daynight"]
    .astype("string")
    .str.strip()
    .str.lower()
)

print("\nNormalized values:")
print(df["daynight_normalized"].value_counts(dropna=False))

print("\nExpected day/night totals by sensor:")

expected = (
    df.assign(
        day_count=df["daynight_normalized"].isin(
            ["day", "d"]
        ).astype(int),
        night_count=df["daynight_normalized"].isin(
            ["night", "n"]
        ).astype(int)
    )
    .groupby("sensor")
    .agg(
        total_detections=("daynight", "size"),
        expected_day_count=("day_count", "sum"),
        expected_night_count=("night_count", "sum")
    )
)

print(expected)

print("\n" + "=" * 70)
print("3. STORED WEEKLY AGGREGATION")
print("=" * 70)

weekly = pd.read_parquet(WEEKLY)

print(
    weekly.groupby("sensor")[
        ["day_count", "night_count", "detection_count"]
    ].sum()
)

print("\n" + "=" * 70)
print("4. STORED MONTHLY AGGREGATION")
print("=" * 70)

monthly = pd.read_parquet(MONTHLY)

print(
    monthly.groupby("sensor")[
        ["day_count", "night_count", "detection_count"]
    ].sum()
)

print("\n" + "=" * 70)
print("5. CHECK RAW DAY/NIGHT NULLS")
print("=" * 70)

print(
    df.groupby("sensor")["daynight"]
    .apply(lambda x: x.isna().sum())
)

print("\nDAY/NIGHT CHECK COMPLETED")