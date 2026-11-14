from pathlib import Path

import numpy as np
import pandas as pd

from config.punjab import GRID_SIZE


# ============================================================
# PATHS
# ============================================================

ROOT = Path(__file__).resolve().parents[1]

INPUT_FILE = (
    ROOT
    / "data"
    / "processed"
    / "hotspots_punjab_clipped.parquet"
)

OUTPUT_FILE = (
    ROOT
    / "data"
    / "processed"
    / "hotspots_clean.parquet"
)

QA_REPORT = (
    ROOT
    / "outputs"
    / "cleaning_qa_report.csv"
)

RULES_FILE = (
    ROOT
    / "docs"
    / "cleaning_rules.md"
)


# ============================================================
# CONFIDENCE CLASSIFICATION
# ============================================================

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

    # MODIS numeric confidence
    try:
        number = float(text)

        if number < 30:
            return "low"

        elif number < 80:
            return "nominal"

        elif number <= 100:
            return "high"

        else:
            return "unknown"

    except ValueError:
        return "unknown"


# ============================================================
# GRID ASSIGNMENT
# ============================================================

def assign_grid_cells(df):

    df = df.copy()

    df["grid_row"] = np.floor(
        df["latitude"] / GRID_SIZE
    ).astype("int64")

    df["grid_col"] = np.floor(
        df["longitude"] / GRID_SIZE
    ).astype("int64")

    df["grid_lat"] = (
        df["grid_row"] * GRID_SIZE
    )

    df["grid_lon"] = (
        df["grid_col"] * GRID_SIZE
    )

    df["grid_id"] = (
        "PB_"
        + df["grid_row"].astype(str)
        + "_"
        + df["grid_col"].astype(str)
    )

    return df


# ============================================================
# DOCUMENTATION
# ============================================================

def write_cleaning_rules():

    RULES_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    documentation = """
# Punjab Fire Calendar - Cleaning Rules

## 1. Geographic filtering

Only detections inside the Punjab study area are processed.
The input dataset is the previously clipped Punjab dataset.

## 2. Coordinate validation

Rows with missing, non-numeric, or invalid latitude and
longitude values are removed.

## 3. Confidence filtering

Low-confidence detections are removed.

Nominal, high, and unknown-confidence detections are retained.

### MODIS numeric confidence

- Below 30: low
- 30 to below 80: nominal
- 80 to 100: high
- Missing or unrecognised values: unknown

### VIIRS categorical confidence

- l: low
- n: nominal
- h: high
- Missing or unrecognised values: unknown

## 4. Brightness standardisation

A common brightness_standard field is created.

- MODIS uses its brightness field.
- VIIRS uses bright_ti4.

Original sensor-specific brightness fields are preserved.
Brightness values are not assumed to be directly equivalent
between sensors.

## 5. Day and night standardisation

Day/night values are standardised to:

- Day
- Night
- Unknown

## 6. Timestamps

Acquisition date and time are used to create:

- timestamp_utc
- timestamp_ist

IST means Indian Standard Time (Asia/Kolkata).

## 7. Exact duplicate removal

Exact duplicates are removed using:

- sensor
- latitude
- longitude
- acq_date
- acq_time
- frp

## 8. Approximate duplicate removal

Approximate spatial/time deduplication is disabled.

Detections close to one another are preserved because they
may represent legitimate observations.

No 1 km / 30-minute grouping is used.

## 9. Grid assignment

Each detection is assigned to a 0.25-degree grid cell.

Grid identifiers use the format:

PB_<row>_<column>

## 10. Date validation

Rows with invalid acquisition dates are removed.

## 11. Preserved attributes

Original hotspot attributes are retained wherever possible.

## 12. Limitations

This cleaning process does not perform advanced cross-sensor
duplicate correction, land-cover filtering, or industrial
hotspot filtering.
"""

    RULES_FILE.write_text(
        documentation.strip() + "\n",
        encoding="utf-8"
    )


# ============================================================
# MAIN CLEANING PIPELINE
# ============================================================

def main():

    print("\nLoading clipped Punjab dataset...")

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Input file not found: {INPUT_FILE}"
        )

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    QA_REPORT.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    df = pd.read_parquet(INPUT_FILE)

    input_rows = len(df)

    print("Input rows:", input_rows)

    qa_records = []

    def record_stage(
        stage,
        before,
        after,
        notes=""
    ):

        qa_records.append({
            "stage": stage,
            "rows_removed": before - after,
            "rows_remaining": after,
            "notes": notes
        })

    # --------------------------------------------------------
    # 1. STANDARDISE COLUMN NAMES
    # --------------------------------------------------------

    df.columns = (
        df.columns
        .str.strip()
        .str.lower()
    )

    required_columns = [
        "latitude",
        "longitude",
        "acq_date",
        "acq_time",
        "sensor",
        "confidence",
        "frp"
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing_columns:
        raise ValueError(
            "Missing required columns: "
            f"{missing_columns}"
        )

    # --------------------------------------------------------
    # 2. COORDINATE VALIDATION
    # --------------------------------------------------------

    print("\nChecking coordinates...")

    before = len(df)

    df["latitude"] = pd.to_numeric(
        df["latitude"],
        errors="coerce"
    )

    df["longitude"] = pd.to_numeric(
        df["longitude"],
        errors="coerce"
    )

    valid_coordinates = (
        df["latitude"].between(-90, 90)
        & df["longitude"].between(-180, 180)
    )

    df = df[
        valid_coordinates
    ].copy()

    record_stage(
        "invalid_coordinates_removed",
        before,
        len(df)
    )

    # --------------------------------------------------------
    # 3. CONFIDENCE CLASSIFICATION
    # --------------------------------------------------------

    print("\nStandardising confidence...")

    before = len(df)

    df["confidence_class"] = df.apply(
        classify_confidence,
        axis=1
    )

    print("\nConfidence classes before filtering:")

    print(
        df["confidence_class"]
        .value_counts(dropna=False)
    )

    low_count = int(
        (df["confidence_class"] == "low").sum()
    )

    df = df[
        df["confidence_class"] != "low"
    ].copy()

    record_stage(
        "low_confidence_removed",
        before,
        len(df),
        "Low confidence removed; nominal, high and unknown retained."
    )

    # --------------------------------------------------------
    # 4. BRIGHTNESS STANDARDISATION
    # --------------------------------------------------------

    print("\nStandardising brightness fields...")

    if "brightness" in df.columns:

        modis_brightness = pd.to_numeric(
            df["brightness"],
            errors="coerce"
        )

    else:

        modis_brightness = pd.Series(
            np.nan,
            index=df.index
        )

    if "bright_ti4" in df.columns:

        viirs_brightness = pd.to_numeric(
            df["bright_ti4"],
            errors="coerce"
        )

    else:

        viirs_brightness = pd.Series(
            np.nan,
            index=df.index
        )

    sensor_text = (
        df["sensor"]
        .astype(str)
        .str.upper()
    )

    is_modis = sensor_text.str.contains(
        "MODIS",
        na=False
    )

    df["brightness_standard"] = np.where(
        is_modis,
        modis_brightness,
        viirs_brightness
    )

    # --------------------------------------------------------
    # 5. DAY / NIGHT STANDARDISATION
    # --------------------------------------------------------

    print("\nStandardising day/night...")

    if "daynight" in df.columns:

        daynight = (
            df["daynight"]
            .astype(str)
            .str.strip()
            .str.upper()
        )

        df["daynight"] = daynight.map({
            "D": "Day",
            "DAY": "Day",
            "N": "Night",
            "NIGHT": "Night"
        }).fillna("Unknown")

    else:

        df["daynight"] = "Unknown"

    # --------------------------------------------------------
    # 6. TIMESTAMP CREATION
    # --------------------------------------------------------

    print("\nCreating UTC and IST timestamps...")

    df["acq_date"] = pd.to_datetime(
        df["acq_date"],
        errors="coerce"
    ).dt.strftime("%Y-%m-%d")

    time_text = (
        df["acq_time"]
        .astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.strip()
        .str.zfill(4)
    )

    valid_time = time_text.str.fullmatch(
        r"\d{4}"
    )

    timestamp_text = (
        df["acq_date"].astype(str)
        + " "
        + time_text.str[:2]
        + ":"
        + time_text.str[2:]
    )

    df["timestamp_utc"] = pd.to_datetime(
        timestamp_text.where(valid_time),
        format="%Y-%m-%d %H:%M",
        errors="coerce",
        utc=True
    )

    df["timestamp_ist"] = (
        df["timestamp_utc"]
        .dt.tz_convert("Asia/Kolkata")
    )

    # --------------------------------------------------------
    # 7. EXACT DUPLICATE REMOVAL
    # --------------------------------------------------------

    print("\nRemoving exact duplicates...")

    before = len(df)

    duplicate_columns = [
        "sensor",
        "latitude",
        "longitude",
        "acq_date",
        "acq_time",
        "frp"
    ]

    df = df.drop_duplicates(
        subset=duplicate_columns,
        keep="first"
    ).copy()

    record_stage(
        "exact_duplicates_removed",
        before,
        len(df)
    )

    # --------------------------------------------------------
    # 8. APPROXIMATE DUPLICATES DISABLED
    # --------------------------------------------------------

    print(
        "\nApproximate duplicate removal disabled. "
        "Preserving remaining hotspot detections."
    )

    record_stage(
        "approximate_duplicates_removed",
        len(df),
        len(df),
        "Disabled: nearby detections may be legitimate observations."
    )

    # --------------------------------------------------------
    # 9. GRID ASSIGNMENT
    # --------------------------------------------------------

    print("\nAssigning grid cells...")

    df = assign_grid_cells(df)

    # --------------------------------------------------------
    # 10. DATE AND YEAR STANDARDISATION
    # --------------------------------------------------------

    print("\nStandardising date and year...")

    before = len(df)

    df["acq_date"] = pd.to_datetime(
        df["acq_date"],
        errors="coerce"
    )

    df["year"] = df["acq_date"].dt.year

    df = df[
        df["acq_date"].notna()
        & df["year"].notna()
    ].copy()

    df["year"] = df["year"].astype("int64")

    record_stage(
        "invalid_date_rows_removed",
        before,
        len(df)
    )

    # --------------------------------------------------------
    # 11. SORT AND SAVE
    # --------------------------------------------------------

    print("\nSorting and saving cleaned dataset...")

    df = df.sort_values(
        ["acq_date", "sensor", "latitude", "longitude"]
    ).reset_index(drop=True)

    df.to_parquet(
        OUTPUT_FILE,
        index=False,
        compression="snappy"
    )

    # --------------------------------------------------------
    # 12. SAVE QA REPORT
    # --------------------------------------------------------

    qa_records.append({
        "stage": "final_clean_dataset",
        "rows_removed": 0,
        "rows_remaining": len(df),
        "notes": "Final cleaned Punjab dataset."
    })

    qa_df = pd.DataFrame(qa_records)

    qa_df.to_csv(
        QA_REPORT,
        index=False
    )

    # --------------------------------------------------------
    # 13. WRITE CLEANING DOCUMENTATION
    # --------------------------------------------------------

    write_cleaning_rules()

    # --------------------------------------------------------
    # 14. FINAL SUMMARY
    # --------------------------------------------------------

    print("\n" + "=" * 55)
    print("CLEANING COMPLETED")
    print("=" * 55)

    print("Input rows:", input_rows)
    print("Final clean rows:", len(df))
    print("Total removed:", input_rows - len(df))
    print("Low-confidence rows removed:", low_count)

    print("\nConfidence distribution:")

    print(
        df["confidence_class"]
        .value_counts(dropna=False)
    )

    print("\nSensor distribution:")

    print(
        df["sensor"]
        .value_counts(dropna=False)
    )

    print("\nDay/night distribution:")

    print(
        df["daynight"]
        .value_counts(dropna=False)
    )

    print(
        "\nUnique grid cells:",
        df["grid_id"].nunique()
    )

    print("\nSaved cleaned dataset:")
    print(OUTPUT_FILE)

    print("\nSaved QA report:")
    print(QA_REPORT)

    print("\nSaved cleaning rules:")
    print(RULES_FILE)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()