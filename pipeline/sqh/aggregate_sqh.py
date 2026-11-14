"""
Punjab Fire Calendar
Sensor Quantile Harmonisation (SQH)
Weekly and Monthly Aggregation

Input:
    data/processed/sqh/hotspots_sqh.parquet

Outputs:
    data/processed/sqh/weekly_cell_sqh.parquet
    data/processed/sqh/weekly_aoi_sqh.parquet
    data/processed/sqh/monthly_cell_sqh.parquet
    data/processed/sqh/monthly_aoi_sqh.parquet

QA:
    outputs/sqh/aggregation_qa.json

Important:
    - Keeps MODIS_Terra and VIIRS_SNPP separate.
    - Preserves Terra detections before 2012.
    - Uses the 1 km SQH grid.
    - Does not zero-fill missing sensor observations.
    - Correctly handles Day/Night and D/N values.
    - Validates detection counts and FRP against raw detections.
    - Independently validates AOI counts and FRP against
      the original team aggregation outputs.
"""

from pathlib import Path
import json
import time

import numpy as np
import pandas as pd


# ============================================================
# 1. PROJECT PATHS AND CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parents[2]

INPUT_FILE = (
    ROOT / "data/processed/sqh/hotspots_sqh.parquet"
)

OUTPUT_DIR = (
    ROOT / "data/processed/sqh"
)

QA_DIR = (
    ROOT / "outputs/sqh"
)

# Existing original team outputs.
# These are read-only validation references.
REFERENCE_WEEKLY_AOI = (
    ROOT / "data/processed/weekly_aoi.parquet"
)

REFERENCE_MONTHLY_AOI = (
    ROOT / "data/processed/monthly_aoi.parquet"
)

SENSORS = [
    "MODIS_Terra",
    "VIIRS_SNPP",
]

OVERLAP_START_DATE = pd.Timestamp("2012-01-01")

FRP_TOLERANCE = 1e-8


# ============================================================
# 2. OUTPUT FILES
# ============================================================

OUTPUT_FILES = {
    "weekly_cell": OUTPUT_DIR / "weekly_cell_sqh.parquet",
    "weekly_aoi": OUTPUT_DIR / "weekly_aoi_sqh.parquet",
    "monthly_cell": OUTPUT_DIR / "monthly_cell_sqh.parquet",
    "monthly_aoi": OUTPUT_DIR / "monthly_aoi_sqh.parquet",
}

QA_FILE = QA_DIR / "aggregation_qa.json"


# ============================================================
# 3. GENERAL VALIDATION HELPERS
# ============================================================

def check(condition, message):
    """
    Stop execution if a validation fails.
    """
    if not condition:
        raise AssertionError(message)


def json_safe(value):
    """
    Convert numpy and pandas values into JSON-compatible values.
    """
    if isinstance(value, dict):
        return {
            str(k): json_safe(v)
            for k, v in value.items()
        }

    if isinstance(value, list):
        return [
            json_safe(v)
            for v in value
        ]

    if isinstance(value, tuple):
        return [
            json_safe(v)
            for v in value
        ]

    if isinstance(value, (np.integer,)):
        return int(value)

    if isinstance(value, (np.floating,)):
        return float(value)

    if isinstance(value, (np.bool_,)):
        return bool(value)

    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()

    if pd.isna(value):
        return None

    return value


# ============================================================
# 4. LOAD AND PREPARE DETECTIONS
# ============================================================

def load_detections():

    print("\n" + "=" * 75)
    print("STEP 1: LOADING SQH DETECTIONS")
    print("=" * 75)

    check(
        INPUT_FILE.exists(),
        f"Missing input file: {INPUT_FILE}"
    )

    df = pd.read_parquet(INPUT_FILE)

    print("Original shape:", df.shape)

    required_columns = [
        "sensor",
        "acq_date",
        "frp",
        "daynight",
        "sqh_cell_id",
    ]

    missing_columns = [
        col for col in required_columns
        if col not in df.columns
    ]

    check(
        not missing_columns,
        f"Missing required columns: {missing_columns}"
    )

    # Keep only the two SQH comparison sensors.
    df = df[
        df["sensor"].isin(SENSORS)
    ].copy()

    check(
        not df.empty,
        "No Terra/SNPP detections found."
    )

    # Standardize date.
    df["acq_date"] = pd.to_datetime(
        df["acq_date"],
        errors="coerce"
    )

    check(
        df["acq_date"].notna().all(),
        "Invalid acquisition dates found."
    )

    # Ensure FRP is numeric.
    df["frp"] = pd.to_numeric(
        df["frp"],
        errors="coerce"
    )

    check(
        df["frp"].notna().all(),
        "Missing or invalid FRP values found."
    )

    check(
        np.isfinite(df["frp"]).all(),
        "Infinite FRP values found."
    )

    check(
        (df["frp"] >= 0).all(),
        "Negative FRP values found."
    )

    # Ensure every detection belongs to an SQH cell.
    check(
        df["sqh_cell_id"].notna().all(),
        "Missing SQH cell IDs found."
    )

    # --------------------------------------------------------
    # CORRECT DAY/NIGHT NORMALIZATION
    # --------------------------------------------------------

    df["daynight_normalized"] = (
        df["daynight"]
        .astype("string")
        .str.strip()
        .str.lower()
    )

    # Accept both long and short representations.
    day_values = ["day", "d"]
    night_values = ["night", "n"]

    unknown_values = (
        df.loc[
            ~df["daynight_normalized"].isin(
                day_values + night_values
            ),
            "daynight"
        ]
        .value_counts(dropna=False)
    )

    # Do not silently classify unknown values.
    check(
        len(unknown_values) == 0,
        (
            "Unexpected daynight values found:\n"
            f"{unknown_values}"
        )
    )

    df["day_flag"] = (
        df["daynight_normalized"]
        .isin(day_values)
        .astype("int8")
    )

    df["night_flag"] = (
        df["daynight_normalized"]
        .isin(night_values)
        .astype("int8")
    )

    # Check that each detection is classified exactly once.
    check(
        (
            df["day_flag"] + df["night_flag"]
        ).eq(1).all(),
        "Some detections are not classified as day or night."
    )

    # --------------------------------------------------------
    # SENSOR VALIDATION
    # --------------------------------------------------------

    sensor_counts = (
        df["sensor"]
        .value_counts()
        .to_dict()
    )

    print("\nSensor counts:")
    print(df["sensor"].value_counts())

    print("\nDate range:")
    print("Start:", df["acq_date"].min())
    print("End:", df["acq_date"].max())

    print("\nDay/night counts:")
    print(
        pd.crosstab(
            df["sensor"],
            df["daynight_normalized"]
        )
    )

    print("\nPre-2012 Terra detections:")

    terra_pre_2012 = df[
        (df["sensor"] == "MODIS_Terra")
        &
        (df["acq_date"] < OVERLAP_START_DATE)
    ]

    print(len(terra_pre_2012))

    # Make sure both sensors exist.
    check(
        set(df["sensor"].unique()) == set(SENSORS),
        "One or more expected SQH sensors are missing."
    )

    return df, sensor_counts


# ============================================================
# 5. CREATE TIME PERIODS
# ============================================================

def add_period_columns(df):

    print("\n" + "=" * 75)
    print("STEP 2: CREATING WEEKLY AND MONTHLY PERIODS")
    print("=" * 75)

    # Monday-start weeks.
    df["week_start"] = (
        df["acq_date"]
        .dt.to_period("W-SUN")
        .dt.start_time
    )

    # Calendar months.
    df["month_start"] = (
        df["acq_date"]
        .dt.to_period("M")
        .dt.start_time
    )

    check(
        df["week_start"].notna().all(),
        "Invalid weekly periods."
    )

    check(
        df["month_start"].notna().all(),
        "Invalid monthly periods."
    )

    print("Weekly periods:", df["week_start"].nunique())
    print("Monthly periods:", df["month_start"].nunique())

    return df


# ============================================================
# 6. CELL-LEVEL AGGREGATION
# ============================================================

def aggregate_cells(df, period_column):

    print(
        f"\nAggregating cell-level data: {period_column}"
    )

    group_columns = [
        period_column,
        "sensor",
        "sqh_cell_id",
    ]

    result = (
        df.groupby(
            group_columns,
            observed=True,
            sort=False
        )
        .agg(
            detection_count=("frp", "size"),
            frp_sum=("frp", "sum"),
            frp_mean=("frp", "mean"),
            frp_max=("frp", "max"),
            day_count=("day_flag", "sum"),
            night_count=("night_flag", "sum"),
        )
        .reset_index()
    )

    result["detection_count"] = (
        result["detection_count"].astype("int64")
    )

    result["day_count"] = (
        result["day_count"].astype("int64")
    )

    result["night_count"] = (
        result["night_count"].astype("int64")
    )

    # Every cell-period-sensor combination must be unique.
    check(
        not result.duplicated(
            subset=group_columns
        ).any(),
        f"Duplicate cell aggregation keys: {period_column}"
    )

    # Detection counts must be positive.
    check(
        (result["detection_count"] > 0).all(),
        "Non-positive cell detection counts found."
    )

    # Day/night detections must account for every detection.
    check(
        (
            result["day_count"] + result["night_count"]
            ==
            result["detection_count"]
        ).all(),
        f"Day/night mismatch in {period_column} cell aggregation."
    )

    check(
        result["frp_sum"].notna().all(),
        "Missing FRP sums."
    )

    check(
        result["frp_mean"].notna().all(),
        "Missing FRP means."
    )

    check(
        result["frp_max"].notna().all(),
        "Missing FRP maxima."
    )

    print("Cell aggregation rows:", len(result))

    return result


# ============================================================
# 7. AOI-LEVEL AGGREGATION
# ============================================================

def aggregate_aoi(df, cell_df, period_column):

    print(
        f"\nAggregating AOI-level data: {period_column}"
    )

    # Aggregate directly from detections.
    # This ensures AOI FRP mean is detection-weighted.
    aoi = (
        df.groupby(
            [period_column, "sensor"],
            observed=True,
            sort=False
        )
        .agg(
            detection_count=("frp", "size"),
            frp_sum=("frp", "sum"),
            frp_mean=("frp", "mean"),
            frp_max=("frp", "max"),
            day_count=("day_flag", "sum"),
            night_count=("night_flag", "sum"),
        )
        .reset_index()
    )

    # Active 1 km cells are calculated from the cell-level
    # aggregation, not from the old 0.25-degree grid.
    active_cells = (
        cell_df.groupby(
            [period_column, "sensor"],
            observed=True,
            sort=False
        )
        .agg(
            active_cells_1km=(
                "sqh_cell_id",
                "nunique"
            )
        )
        .reset_index()
    )

    aoi = aoi.merge(
        active_cells,
        on=[period_column, "sensor"],
        how="left",
        validate="one_to_one"
    )

    aoi["active_cells_1km"] = (
        aoi["active_cells_1km"].astype("int64")
    )

    aoi["detection_count"] = (
        aoi["detection_count"].astype("int64")
    )

    aoi["day_count"] = (
        aoi["day_count"].astype("int64")
    )

    aoi["night_count"] = (
        aoi["night_count"].astype("int64")
    )

    check(
        (
            aoi["day_count"] + aoi["night_count"]
            ==
            aoi["detection_count"]
        ).all(),
        f"Day/night mismatch in {period_column} AOI aggregation."
    )

    check(
        (aoi["active_cells_1km"] > 0).all(),
        "Non-positive active 1 km cell counts."
    )

    check(
        not aoi.duplicated(
            subset=[period_column, "sensor"]
        ).any(),
        f"Duplicate AOI keys: {period_column}"
    )

    print("AOI aggregation rows:", len(aoi))

    return aoi


# ============================================================
# 8. VALIDATE AGAINST RAW DETECTIONS
# ============================================================

def validate_against_raw(df, cell_df, aoi_df, period_column):

    print(
        f"\nValidating aggregation against raw detections: "
        f"{period_column}"
    )

    raw = (
        df.groupby(
            [period_column, "sensor"],
            observed=True
        )
        .agg(
            expected_detections=("frp", "size"),
            expected_frp_sum=("frp", "sum"),
            expected_day_count=("day_flag", "sum"),
            expected_night_count=("night_flag", "sum"),
        )
        .reset_index()
    )

    actual = (
        aoi_df.rename(
            columns={
                "detection_count": "actual_detections",
                "frp_sum": "actual_frp_sum",
                "day_count": "actual_day_count",
                "night_count": "actual_night_count",
            }
        )
    )

    comparison = raw.merge(
        actual,
        on=[period_column, "sensor"],
        how="outer",
        indicator=True,
        validate="one_to_one"
    )

    check(
        (comparison["_merge"] == "both").all(),
        f"Missing AOI period/sensor combinations: {period_column}"
    )

    count_diff = (
        comparison["expected_detections"]
        -
        comparison["actual_detections"]
    ).abs()

    frp_diff = (
        comparison["expected_frp_sum"]
        -
        comparison["actual_frp_sum"]
    ).abs()

    day_diff = (
        comparison["expected_day_count"]
        -
        comparison["actual_day_count"]
    ).abs()

    night_diff = (
        comparison["expected_night_count"]
        -
        comparison["actual_night_count"]
    ).abs()

    check(
        (count_diff == 0).all(),
        f"Detection count mismatch: {period_column}"
    )

    check(
        (frp_diff <= FRP_TOLERANCE).all(),
        f"FRP sum mismatch: {period_column}"
    )

    check(
        (day_diff == 0).all(),
        f"Day count mismatch: {period_column}"
    )

    check(
        (night_diff == 0).all(),
        f"Night count mismatch: {period_column}"
    )

    # Cell aggregation must also preserve raw detection totals.
    cell_totals = (
        cell_df.groupby(
            [period_column, "sensor"],
            observed=True
        )
        .agg(
            cell_detection_total=("detection_count", "sum"),
            cell_frp_total=("frp_sum", "sum"),
            cell_day_total=("day_count", "sum"),
            cell_night_total=("night_count", "sum"),
        )
        .reset_index()
    )

    cell_check = raw.merge(
        cell_totals,
        on=[period_column, "sensor"],
        how="outer",
        indicator=True,
        validate="one_to_one"
    )

    check(
        (cell_check["_merge"] == "both").all(),
        f"Cell/raw period mismatch: {period_column}"
    )

    check(
        (
            cell_check["expected_detections"]
            ==
            cell_check["cell_detection_total"]
        ).all(),
        f"Cell detection totals mismatch: {period_column}"
    )

    check(
        (
            (
                cell_check["expected_frp_sum"]
                -
                cell_check["cell_frp_total"]
            ).abs()
            <= FRP_TOLERANCE
        ).all(),
        f"Cell FRP totals mismatch: {period_column}"
    )

    check(
        (
            cell_check["expected_day_count"]
            ==
            cell_check["cell_day_total"]
        ).all(),
        f"Cell day totals mismatch: {period_column}"
    )

    check(
        (
            cell_check["expected_night_count"]
            ==
            cell_check["cell_night_total"]
        ).all(),
        f"Cell night totals mismatch: {period_column}"
    )

    print("Detection count differences: 0")
    print("FRP sum maximum difference:", frp_diff.max())
    print("Day count differences: 0")
    print("Night count differences: 0")
    print("CELL VALIDATION PASSED")
    print("AOI VALIDATION PASSED")

    return {
        "period_column": period_column,
        "comparison_rows": len(comparison),
        "max_detection_difference": int(count_diff.max()),
        "max_frp_difference": float(frp_diff.max()),
        "max_day_difference": int(day_diff.max()),
        "max_night_difference": int(night_diff.max()),
        "validation_passed": True,
    }


# ============================================================
# 9. VALIDATE AGAINST ORIGINAL TEAM AOI OUTPUTS
# ============================================================

def validate_against_existing(
    new_aoi,
    reference_path,
    period_column,
    reference_period_column
):

    print(
        "\nComparing with existing team AOI aggregation:",
        reference_path.name
    )

    check(
        reference_path.exists(),
        f"Missing reference file: {reference_path}"
    )

    reference = pd.read_parquet(reference_path)

    required = [
        reference_period_column,
        "sensor",
        "n_detections",
        "frp_sum",
    ]

    missing = [
        col for col in required
        if col not in reference.columns
    ]

    check(
        not missing,
        f"Reference AOI file missing columns: {missing}"
    )

    reference = reference[
        reference["sensor"].isin(SENSORS)
    ].copy()

    reference[reference_period_column] = pd.to_datetime(
        reference[reference_period_column]
    )

    new = new_aoi[
        new_aoi[period_column] >= OVERLAP_START_DATE
    ].copy()

    reference = reference[
        reference[reference_period_column] >= OVERLAP_START_DATE
    ].copy()

    reference = reference.rename(
        columns={
            reference_period_column: period_column,
            "n_detections": "reference_detections",
            "frp_sum": "reference_frp_sum",
        }
    )

    new = new.rename(
        columns={
            "detection_count": "new_detections",
            "frp_sum": "new_frp_sum",
        }
    )

    merged = new.merge(
        reference[
            [
                period_column,
                "sensor",
                "reference_detections",
                "reference_frp_sum",
            ]
        ],
        on=[period_column, "sensor"],
        how="outer",
        indicator=True,
        validate="one_to_one"
    )

    both = merged[
        merged["_merge"] == "both"
    ]

    left_only = merged[
        merged["_merge"] == "left_only"
    ]

    right_only = merged[
        merged["_merge"] == "right_only"
    ]

    print("Matched rows:", len(both))
    print("New output only:", len(left_only))
    print("Reference output only:", len(right_only))

    check(
        len(left_only) == 0 and len(right_only) == 0,
        "AOI period/sensor keys do not match original output."
    )

    detection_diff = (
        both["new_detections"]
        -
        both["reference_detections"]
    ).abs()

    frp_diff = (
        both["new_frp_sum"]
        -
        both["reference_frp_sum"]
    ).abs()

    print(
        "Maximum detection difference:",
        detection_diff.max()
    )

    print(
        "Maximum FRP difference:",
        frp_diff.max()
    )

    check(
        (detection_diff == 0).all(),
        "Detection counts differ from original AOI output."
    )

    check(
        (frp_diff <= FRP_TOLERANCE).all(),
        "FRP sums differ from original AOI output."
    )

    print("EXISTING AOI VALIDATION PASSED")

    return {
        "reference_file": reference_path.name,
        "matched_rows": len(both),
        "new_only_rows": len(left_only),
        "reference_only_rows": len(right_only),
        "max_detection_difference": int(
            detection_diff.max()
        ),
        "max_frp_difference": float(
            frp_diff.max()
        ),
        "validation_passed": True,
    }


# ============================================================
# 10. MAIN EXECUTION
# ============================================================

def main():

    start_time = time.time()

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    QA_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    qa = {
        "project": "Punjab Fire Calendar",
        "pipeline": "SQH Weekly and Monthly Aggregation",
        "sensors": SENSORS,
        "overlap_start_date": str(
            OVERLAP_START_DATE.date()
        ),
        "grid": {
            "crs": "EPSG:32643",
            "cell_size_metres": 1000,
        },
        "validations": {},
    }

    # --------------------------------------------------------
    # LOAD
    # --------------------------------------------------------

    df, sensor_counts = load_detections()

    qa["input"] = {
        "file": str(INPUT_FILE.relative_to(ROOT)),
        "total_detections": len(df),
        "sensor_counts": sensor_counts,
        "date_min": str(df["acq_date"].min().date()),
        "date_max": str(df["acq_date"].max().date()),
        "terra_pre_2012_detections": int(
            (
                (df["sensor"] == "MODIS_Terra")
                &
                (df["acq_date"] < OVERLAP_START_DATE)
            ).sum()
        ),
        "day_detections": int(df["day_flag"].sum()),
        "night_detections": int(df["night_flag"].sum()),
    }

    # --------------------------------------------------------
    # PERIODS
    # --------------------------------------------------------

    df = add_period_columns(df)

    # --------------------------------------------------------
    # WEEKLY
    # --------------------------------------------------------

    print("\n" + "#" * 75)
    print("WEEKLY AGGREGATION")
    print("#" * 75)

    weekly_cell = aggregate_cells(
        df,
        "week_start"
    )

    weekly_aoi = aggregate_aoi(
        df,
        weekly_cell,
        "week_start"
    )

    weekly_raw_validation = validate_against_raw(
        df,
        weekly_cell,
        weekly_aoi,
        "week_start"
    )

    weekly_reference_validation = validate_against_existing(
        weekly_aoi,
        REFERENCE_WEEKLY_AOI,
        "week_start",
        "week_start"
    )

    qa["validations"]["weekly_raw"] = (
        weekly_raw_validation
    )

    qa["validations"]["weekly_existing_aoi"] = (
        weekly_reference_validation
    )

    # --------------------------------------------------------
    # MONTHLY
    # --------------------------------------------------------

    print("\n" + "#" * 75)
    print("MONTHLY AGGREGATION")
    print("#" * 75)

    monthly_cell = aggregate_cells(
        df,
        "month_start"
    )

    monthly_aoi = aggregate_aoi(
        df,
        monthly_cell,
        "month_start"
    )

    monthly_raw_validation = validate_against_raw(
        df,
        monthly_cell,
        monthly_aoi,
        "month_start"
    )

    monthly_reference_validation = validate_against_existing(
        monthly_aoi,
        REFERENCE_MONTHLY_AOI,
        "month_start",
        "month_start"
    )

    qa["validations"]["monthly_raw"] = (
        monthly_raw_validation
    )

    qa["validations"]["monthly_existing_aoi"] = (
        monthly_reference_validation
    )

    # --------------------------------------------------------
    # GLOBAL TOTALS
    # --------------------------------------------------------

    qa["weekly"] = {
        "cell_rows": len(weekly_cell),
        "aoi_rows": len(weekly_aoi),
        "sensor_counts": (
            weekly_cell.groupby("sensor")[
                "detection_count"
            ].sum().to_dict()
        ),
    }

    qa["monthly"] = {
        "cell_rows": len(monthly_cell),
        "aoi_rows": len(monthly_aoi),
        "sensor_counts": (
            monthly_cell.groupby("sensor")[
                "detection_count"
            ].sum().to_dict()
        ),
    }

    # --------------------------------------------------------
    # SAVE OUTPUTS
    # --------------------------------------------------------

    print("\n" + "=" * 75)
    print("SAVING SQH AGGREGATION OUTPUTS")
    print("=" * 75)

    outputs = {
        "weekly_cell": weekly_cell,
        "weekly_aoi": weekly_aoi,
        "monthly_cell": monthly_cell,
        "monthly_aoi": monthly_aoi,
    }

    # Save only after all validations pass.
    for name, data in outputs.items():

        path = OUTPUT_FILES[name]

        data.to_parquet(
            path,
            index=False
        )

        print(
            f"Saved {name}: "
            f"{len(data):,} rows"
        )

    # --------------------------------------------------------
    # SAVE QA
    # --------------------------------------------------------

    elapsed = time.time() - start_time

    qa["execution"] = {
        "elapsed_seconds": round(elapsed, 2),
        "status": "PASSED",
    }

    qa = json_safe(qa)

    with open(
        QA_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            qa,
            f,
            indent=4,
            ensure_ascii=False
        )

    # --------------------------------------------------------
    # FINAL SUMMARY
    # --------------------------------------------------------

    print("\n" + "=" * 75)
    print("SQH AGGREGATION COMPLETED")
    print("=" * 75)

    print("\nTotal detections:", f"{len(df):,}")

    print("\nSensor totals:")
    print(df["sensor"].value_counts())

    print("\nDay/night totals:")
    print(
        df.groupby("sensor")[
            ["day_flag", "night_flag"]
        ].sum()
    )

    print("\nWeekly cell rows:", f"{len(weekly_cell):,}")
    print("Weekly AOI rows:", f"{len(weekly_aoi):,}")

    print("Monthly cell rows:", f"{len(monthly_cell):,}")
    print("Monthly AOI rows:", f"{len(monthly_aoi):,}")

    print("\nExecution time:", round(elapsed, 2), "seconds")

    print("\nAll validations passed.")
    print("QA report:", QA_FILE)

    print("\nALL SQH AGGREGATION TASKS COMPLETED SUCCESSFULLY")


# ============================================================
# 11. ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()