from pathlib import Path
import pandas as pd

ROOT = Path("data/processed")

EXPECTED_CLEAN_ROWS = 1_876_200

FILES = [
    "hotspots_punjab_clipped.parquet",
    "hotspots_clean.parquet",
    "weekly_cell.parquet",
    "monthly_cell.parquet",
    "weekly_aoi.parquet",
    "monthly_aoi.parquet",
    "weekly_district.parquet",
    "monthly_district.parquet",
    "weekly_district_family.parquet",
    "monthly_district_family.parquet",
]

SENSORS_EXPECTED = {
    "VIIRS_SNPP": 936691,
    "VIIRS_NOAA20": 472650,
    "MODIS_Aqua": 294548,
    "VIIRS_NOAA21": 97373,
    "MODIS_Terra": 74938,
}

def check(condition, message):
    print(
        ("PASS: " if condition else "FAIL: ") + message
    )

def main():

    print("\n========== PROCESSED DATA AUDIT ==========\n")

    for filename in FILES:

        path = ROOT / filename

        check(
            path.exists(),
            f"{filename} exists"
        )

        if path.exists():

            df = pd.read_parquet(path)

            print(
                f"  Rows: {len(df):,} | "
                f"Columns: {len(df.columns)}"
            )

    print("\n========== CLEAN DATA VALIDATION ==========\n")

    path = ROOT / "hotspots_clean.parquet"

    df = pd.read_parquet(path)

    check(
        len(df) == EXPECTED_CLEAN_ROWS,
        f"Clean row count = {len(df):,}"
    )

    required = [
        "sensor",
        "latitude",
        "longitude",
        "timestamp_utc",
        "grid_id",
        "confidence_class",
    ]

    for column in required:

        check(
            column in df.columns,
            f"Required column exists: {column}"
        )

    if all(column in df.columns for column in required):

        check(
            df["sensor"].notna().all(),
            "No missing sensor values"
        )

        check(
            df["latitude"].notna().all()
            and df["longitude"].notna().all(),
            "No missing coordinates"
        )

        check(
            df["timestamp_utc"].notna().all(),
            "No missing timestamps"
        )

        check(
            df["grid_id"].notna().all(),
            "No missing grid assignments"
        )

        print("\nSensor counts:")

        actual = df["sensor"].value_counts()

        print(actual.to_string())

        for sensor, expected in SENSORS_EXPECTED.items():

            observed = int(actual.get(sensor, 0))

            check(
                observed == expected,
                f"{sensor}: {observed:,} / {expected:,}"
            )

        print("\nConfidence distribution:")

        print(
            df["confidence_class"]
            .value_counts(dropna=False)
            .to_string()
        )

        # Check complete-row duplicates.
        duplicate_count = int(
            df.duplicated().sum()
        )

        print(
            "\nExact duplicate rows across all columns:",
            duplicate_count
        )

        print("\nDate range:")

        print(
            df["timestamp_utc"].min(),
            "to",
            df["timestamp_utc"].max()
        )

    print("\n========== AUDIT FINISHED ==========")

if __name__ == "__main__":
    main()