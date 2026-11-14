from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from config.punjab import GRID_SIZE


# --------------------------------------------------
# PATHS
# --------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]

INPUT_FILE = (
    ROOT / "data" / "processed" /
    "hotspots_punjab_clipped.parquet"
)

OUTPUT_FILE = (
    ROOT / "data" / "processed" /
    "hotspots_clean.parquet"
)

REPORT_FILE = (
    ROOT / "outputs" /
    "cleaning_qa_report.csv"
)

DATA_DICTIONARY = (
    ROOT / "docs" /
    "cleaning_rules.md"
)

OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
DATA_DICTIONARY.parent.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------
# CONFIDENCE STANDARDISATION
# --------------------------------------------------

def classify_confidence(row):

    value = row["confidence"]

    if pd.isna(value):
        return "unknown"

    text = str(value).strip().lower()

    # VIIRS categorical confidence
    categories = {
        "l": "low",
        "low": "low",
        "n": "nominal",
        "nominal": "nominal",
        "h": "high",
        "high": "high",
    }

    if text in categories:
        return categories[text]

    # Numeric MODIS confidence, with numeric VIIRS
    # values handled using the same documented thresholds.
    try:
        number = float(text)

        if number < 30:
            return "low"
        elif number <= 80:
            return "nominal"
        else:
            return "high"

    except ValueError:
        return "unknown"


# --------------------------------------------------
# MAIN CLEANING
# --------------------------------------------------

def main():

    print("\nLoading clipped Punjab dataset...")

    df = pd.read_parquet(INPUT_FILE)

    initial_rows = len(df)

    print(f"Input rows: {initial_rows:,}")

    report = []

    # --------------------------------------------------
    # 1. STANDARDISE COLUMN NAMES
    # --------------------------------------------------

    df.columns = df.columns.str.strip().str.lower()

    required = [
        "sensor",
        "latitude",
        "longitude",
        "acq_date",
        "acq_time",
        "confidence",
        "daynight",
        "frp",
    ]

    missing = [
        col for col in required
        if col not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Missing required columns: {missing}"
        )

    # --------------------------------------------------
    # 2. REMOVE INVALID COORDINATES
    # --------------------------------------------------

    df["latitude"] = pd.to_numeric(
        df["latitude"], errors="coerce"
    )

    df["longitude"] = pd.to_numeric(
        df["longitude"], errors="coerce"
    )

    valid_coordinates = (
        df["latitude"].between(-90, 90)
        & df["longitude"].between(-180, 180)
    )

    invalid_coordinates = int(
        (~valid_coordinates).sum()
    )

    df = df.loc[valid_coordinates].copy()

    report.append({
        "stage": "invalid_coordinates_removed",
        "rows_removed": invalid_coordinates,
        "rows_remaining": len(df),
    })

    # --------------------------------------------------
    # 3. STANDARDISE CONFIDENCE
    # --------------------------------------------------

    print("Standardising confidence...")

    df["confidence_class"] = df.apply(
        classify_confidence,
        axis=1
    )

    confidence_counts = (
        df["confidence_class"]
        .value_counts(dropna=False)
    )

    print("\nConfidence classes before filtering:")
    print(confidence_counts)

    low_count = int(
        (df["confidence_class"] == "low").sum()
    )

    df = df[
        df["confidence_class"] != "low"
    ].copy()

    report.append({
        "stage": "low_confidence_removed",
        "rows_removed": low_count,
        "rows_remaining": len(df),
    })

    # --------------------------------------------------
    # 4. STANDARDISE BRIGHTNESS
    # --------------------------------------------------

    print("Standardising brightness fields...")

    df["brightness_standard"] = np.nan
    df["brightness_source"] = "unavailable"

    is_modis = df["sensor"].str.startswith(
        "MODIS", na=False
    )

    is_viirs = df["sensor"].str.startswith(
        "VIIRS", na=False
    )

    if "brightness" in df.columns:

        df.loc[is_modis, "brightness_standard"] = (
            pd.to_numeric(
                df.loc[is_modis, "brightness"],
                errors="coerce"
            )
        )

        df.loc[is_modis, "brightness_source"] = (
            "MODIS_brightness"
        )

    if "bright_ti4" in df.columns:

        df.loc[is_viirs, "brightness_standard"] = (
            pd.to_numeric(
                df.loc[is_viirs, "bright_ti4"],
                errors="coerce"
            )
        )

        df.loc[is_viirs, "brightness_source"] = (
            "VIIRS_bright_ti4"
        )

    # Keep original brightness columns.
    # brightness_standard is a convenient common field,
    # not a claim that the sensor measurements are identical.

    # --------------------------------------------------
    # 5. STANDARDISE DAY/NIGHT
    # --------------------------------------------------

    print("Standardising day/night...")

    daynight = (
        df["daynight"]
        .astype("string")
        .str.strip()
        .str.upper()
    )

    df["period"] = daynight.map({
        "D": "Day",
        "DAY": "Day",
        "N": "Night",
        "NIGHT": "Night",
    }).fillna("Unknown")

    # --------------------------------------------------
    # 6. CREATE UTC AND IST TIMESTAMPS
    # --------------------------------------------------

    print("Creating UTC and IST timestamps...")

    date_text = pd.to_datetime(
        df["acq_date"],
        errors="coerce"
    ).dt.strftime("%Y-%m-%d")

    time_text = (
        df["acq_time"]
        .astype("string")
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
        .str.zfill(4)
    )

    valid_time = time_text.str.fullmatch(
        r"\d{4}", na=False
    )

    timestamp_text = (
        date_text + " " + time_text
    )

    df["acq_timestamp_utc"] = pd.to_datetime(
        timestamp_text.where(valid_time),
        format="%Y-%m-%d %H%M",
        errors="coerce",
        utc=True
    )

    df["acq_timestamp_ist"] = (
        df["acq_timestamp_utc"]
        .dt.tz_convert("Asia/Kolkata")
    )

    invalid_dates = int(
        date_text.isna().sum()
    )

    report.append({
        "stage": "invalid_dates_found",
        "rows_removed": 0,
        "rows_remaining": len(df),
        "notes": f"{invalid_dates} rows have invalid dates",
    })

    # Retain detections with a valid date even if acquisition
    # time is unavailable. Their timestamp will remain null.

    # --------------------------------------------------
    # 7. REMOVE EXACT DUPLICATES
    # --------------------------------------------------

    print("Removing exact duplicates...")

    before_exact = len(df)

    exact_columns = [
        "sensor",
        "latitude",
        "longitude",
        "acq_date",
        "acq_time",
        "frp",
    ]

    df = df.drop_duplicates(
        subset=exact_columns
    ).copy()

    exact_removed = before_exact - len(df)

    report.append({
        "stage": "exact_duplicates_removed",
        "rows_removed": exact_removed,
        "rows_remaining": len(df),
    })

    # --------------------------------------------------
    # 8. REMOVE LIKELY OVERLAPPING-PASS DUPLICATES
    # --------------------------------------------------

    print("Removing likely same-sensor overlapping-pass duplicates...")

    before_overlap = len(df)

    # Approximately 1 km coordinate bins.
    df["_lat_bin"] = df["latitude"].round(2)
    df["_lon_bin"] = df["longitude"].round(2)

    # Group acquisition times into 30-minute windows.
    df["_time_bin"] = (
        df["acq_timestamp_utc"]
        .dt.floor("30min")
        .astype("string")
    )

    # Records without a valid timestamp are not subjected
    # to this approximate duplicate rule.
    timed = df["acq_timestamp_utc"].notna()

    overlap_key = [
        "sensor",
        "acq_date",
        "_lat_bin",
        "_lon_bin",
        "_time_bin",
    ]

    # Keep the detection with the highest FRP in each group.
    df = pd.concat([
        df.loc[timed].sort_values(
            "frp",
            ascending=False,
            na_position="last"
        ).drop_duplicates(
            subset=overlap_key,
            keep="first"
        ),
        df.loc[~timed],
    ])

    overlap_removed = before_overlap - len(df)

    df = df.drop(
        columns=[
            "_lat_bin",
            "_lon_bin",
            "_time_bin",
        ]
    )

    report.append({
        "stage": "likely_overlapping_pass_duplicates_removed",
        "rows_removed": overlap_removed,
        "rows_remaining": len(df),
        "notes": (
            "Same sensor, same date, rounded 0.01-degree "
            "coordinates and same 30-minute time window."
        ),
    })

    # --------------------------------------------------
    # 9. ASSIGN 0.25-DEGREE GRID CELLS
    # --------------------------------------------------

    print("Assigning grid cells...")

    grid_size = GRID_SIZE

    df["grid_row"] = np.floor(
        df["latitude"] / grid_size
    ).astype("int32")

    df["grid_col"] = np.floor(
        df["longitude"] / grid_size
    ).astype("int32")

    df["grid_lat"] = (
        df["grid_row"] + 0.5
    ) * grid_size

    df["grid_lon"] = (
        df["grid_col"] + 0.5
    ) * grid_size

    df["grid_id"] = (
        "PB_"
        + df["grid_row"].astype(str)
        + "_"
        + df["grid_col"].astype(str)
    )

    # --------------------------------------------------
    # 10. STANDARDISE DATE/YEAR
    # --------------------------------------------------

    df["acq_date"] = date_text.loc[df.index]

    df["year"] = pd.to_datetime(
        df["acq_date"],
        errors="coerce"
    ).dt.year.astype("Int32")

    # Remove rows without valid dates.
    before_dates = len(df)

    df = df.dropna(
        subset=["acq_date", "year"]
    ).copy()

    invalid_date_rows_removed = before_dates - len(df)

    report.append({
        "stage": "invalid_date_rows_removed",
        "rows_removed": invalid_date_rows_removed,
        "rows_remaining": len(df),
    })

    # --------------------------------------------------
    # 11. SORT AND SAVE
    # --------------------------------------------------

    df = df.sort_values(
        ["acq_date", "sensor", "latitude", "longitude"]
    ).reset_index(drop=True)

    df.to_parquet(
        OUTPUT_FILE,
        index=False,
        compression="snappy"
    )

    # --------------------------------------------------
    # 12. SAVE QA REPORT
    # --------------------------------------------------

    report.append({
        "stage": "final_clean_dataset",
        "rows_removed": 0,
        "rows_remaining": len(df),
        "notes": "Final cleaned Punjab dataset",
    })

    report_df = pd.DataFrame(report)

    report_df.to_csv(
        REPORT_FILE,
        index=False
    )

    # --------------------------------------------------
    # 13. SAVE CLEANING RULE DOCUMENTATION
    # --------------------------------------------------

    documentation = """
# Punjab Fire Calendar - Cleaning Rules

## Source
hotspots_punjab_clipped.parquet

## Confidence standardisation
- MODIS confidence below 30: low
- MODIS confidence 30 to 80 inclusive: nominal
- MODIS confidence above 80: high
- VIIRS low/l: low
- VIIRS nominal/n: nominal
- VIIRS high/h: high
- Unrecognised or missing values: unknown

Low-confidence detections are excluded.
Unknown-confidence detections are retained and labelled unknown.

## Brightness
- MODIS standard brightness uses the brightness field.
- VIIRS standard brightness uses bright_ti4.
- Original sensor-specific brightness fields are preserved.
- These measurements are not assumed to be directly equivalent.

## Time
FIRMS acquisition date and time are interpreted as UTC.
Both UTC and Asia/Kolkata timestamps are stored.
Missing or invalid times produce a null timestamp.
Day/night is standardised to Day, Night, or Unknown.

## Duplicates
Exact duplicates are removed within the same sensor.
Likely overlapping-pass duplicates are also suppressed within
the same sensor, acquisition date, rounded 0.01-degree
coordinate bin, and 30-minute time window.
The record with the highest FRP is retained.
Different sensors are never deduplicated against one another.

This approximate rule may occasionally merge nearby distinct
detections. It is a practical prototype rule.

## Grid
Each detection is assigned to a globally aligned 0.25-degree
latitude/longitude grid cell.

## Non-vegetation heat sources
No industrial-site or land-cover filtering is applied at this
stage. Brick kilns, industrial heat sources and other
non-vegetation thermal sources may remain in the dataset.
A land-cover dataset such as MODIS MCD12Q1 can support a
future filtering or classification stage.
"""

    DATA_DICTIONARY.write_text(
        documentation.strip(),
        encoding="utf-8"
    )

    # --------------------------------------------------
    # FINAL SUMMARY
    # --------------------------------------------------

    print("\n" + "=" * 55)
    print("CLEANING COMPLETED")
    print("=" * 55)

    print(f"Input rows: {initial_rows:,}")
    print(f"Final clean rows: {len(df):,}")
    print(
        f"Total removed: {initial_rows - len(df):,}"
    )

    print("\nConfidence distribution:")
    print(df["confidence_class"].value_counts())

    print("\nSensor distribution:")
    print(df["sensor"].value_counts())

    print("\nDay/night distribution:")
    print(df["period"].value_counts())

    print("\nUnique grid cells:")
    print(df["grid_id"].nunique())

    print("\nOutput files:")
    print(OUTPUT_FILE)
    print(REPORT_FILE)
    print(DATA_DICTIONARY)


if __name__ == "__main__":
    main()