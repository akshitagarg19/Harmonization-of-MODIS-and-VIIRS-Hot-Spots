"""
Punjab Fire Calendar
SQH Detection Preparation
-------------------------

Purpose:
    Prepare a separate detection-level dataset for SQH.

Operations:
    1. Read existing cleaned hotspot dataset.
    2. Retain MODIS Terra and VIIRS SNPP.
    3. Preserve Terra observations before 2012.
    4. Project coordinates to EPSG:32643.
    5. Calculate aligned 1 km grid indices.
    6. Assign sqh_cell_id.
    7. Validate all assignments.
    8. Save a new Parquet dataset and QA report.

IMPORTANT:
    The original hotspots_clean.parquet is never modified.
"""

from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd
from pyproj import Transformer

from pipeline.sqh.settings import (
    PROJECT_NAME,
    SQH_SENSORS,
    TARGET_CRS,
    CELL_SIZE_METRES,
    OVERLAP_START_DATE,
)


# ============================================================
# 1. PATHS AND CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

SOURCE_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "hotspots_clean.parquet"
)

GRID_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "sqh"
    / "punjab_1km_grid.parquet"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "sqh"
)

OUTPUT_FILE = (
    OUTPUT_DIR
    / "hotspots_sqh.parquet"
)

QA_DIR = (
    PROJECT_ROOT
    / "outputs"
    / "sqh"
)

QA_FILE = (
    QA_DIR
    / "detection_assignment_qa.json"
)


# ============================================================
# 2. REQUIRED COLUMNS
# ============================================================

REQUIRED_SOURCE_COLUMNS = [
    "sensor",
    "latitude",
    "longitude",
    "acq_date",
    "frp",
    "daynight",
    "timestamp_utc",
    "timestamp_ist",
    "grid_id",
]

REQUIRED_GRID_COLUMNS = [
    "sqh_cell_id",
    "grid_row",
    "grid_col",
]


# ============================================================
# 3. HELPER FUNCTIONS
# ============================================================

def print_section(message):

    print("\n" + "=" * 65)
    print(message)
    print("=" * 65)


def ensure_directories():

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    QA_DIR.mkdir(
        parents=True,
        exist_ok=True
    )


def check_file_exists(path):

    if not path.exists():

        raise FileNotFoundError(
            f"Required file not found:\n{path}"
        )


def validate_columns(df, required, dataset_name):

    missing = [
        column
        for column in required
        if column not in df.columns
    ]

    if missing:

        raise ValueError(
            f"{dataset_name} is missing columns: {missing}"
        )


# ============================================================
# 4. LOAD SOURCE DATASET
# ============================================================

def load_source_dataset():

    print_section("[1/7] LOADING CLEANED HOTSPOTS")

    check_file_exists(SOURCE_FILE)

    df = pd.read_parquet(SOURCE_FILE)

    validate_columns(
        df,
        REQUIRED_SOURCE_COLUMNS,
        "Cleaned hotspot dataset"
    )

    print(f"Original shape: {df.shape}")

    print("\nOriginal sensor counts:")

    print(
        df["sensor"].value_counts(dropna=False)
    )

    return df


# ============================================================
# 5. FILTER REQUIRED SENSORS
# ============================================================

def filter_required_sensors(df):

    print_section("[2/7] FILTERING PROJECT SENSORS")

    print("Required sensors:", SQH_SENSORS)

    original_count = len(df)

    filtered = df[
        df["sensor"].isin(SQH_SENSORS)
    ].copy()

    if filtered.empty:

        raise ValueError(
            "No detections found for the configured sensors."
        )

    print(f"Original detections: {original_count:,}")
    print(f"Retained detections: {len(filtered):,}")
    print(
        f"Excluded detections: "
        f"{original_count - len(filtered):,}"
    )

    print("\nRetained sensor counts:")

    print(
        filtered["sensor"].value_counts()
    )

    print("\nRetained date ranges:")

    for sensor in SQH_SENSORS:

        sensor_df = filtered[
            filtered["sensor"] == sensor
        ]

        if not sensor_df.empty:

            print(
                f"{sensor}: "
                f"{sensor_df['acq_date'].min()} "
                f"to "
                f"{sensor_df['acq_date'].max()}"
            )

    return filtered


# ============================================================
# 6. LOAD SQH GRID
# ============================================================

def load_sqh_grid():

    print_section("[3/7] LOADING 1 KM SQH GRID")

    check_file_exists(GRID_FILE)

    grid = pd.read_parquet(GRID_FILE)

    validate_columns(
        grid,
        REQUIRED_GRID_COLUMNS,
        "SQH grid"
    )

    if grid.empty:

        raise ValueError(
            "SQH grid contains no cells."
        )

    duplicate_ids = grid["sqh_cell_id"].duplicated().sum()

    if duplicate_ids:

        raise ValueError(
            f"Grid contains {duplicate_ids} duplicate cell IDs."
        )

    duplicate_indices = grid.duplicated(
        subset=["grid_row", "grid_col"]
    ).sum()

    if duplicate_indices:

        raise ValueError(
            f"Grid contains {duplicate_indices} duplicate row/column pairs."
        )

    print(f"Grid cells: {len(grid):,}")
    print(
        "Unique SQH cell IDs:",
        grid["sqh_cell_id"].nunique()
    )

    # Build a lookup:
    #
    # (grid_row, grid_col) -> sqh_cell_id
    #
    # Geometry is not required for this operation.

    cell_lookup = {
        (int(row), int(col)): cell_id

        for row, col, cell_id in zip(
            grid["grid_row"],
            grid["grid_col"],
            grid["sqh_cell_id"]
        )
    }

    return grid, cell_lookup


# ============================================================
# 7. ASSIGN DETECTIONS TO SQH CELLS
# ============================================================

def assign_sqh_cells(df, cell_lookup):

    print_section("[4/7] ASSIGNING 1 KM SQH CELL IDS")

    # Ensure coordinates are numeric.
    df["latitude"] = pd.to_numeric(
        df["latitude"],
        errors="coerce"
    )

    df["longitude"] = pd.to_numeric(
        df["longitude"],
        errors="coerce"
    )

    invalid_coordinates = (
        ~np.isfinite(df["latitude"])
        | ~np.isfinite(df["longitude"])
        | ~df["latitude"].between(-90, 90)
        | ~df["longitude"].between(-180, 180)
    )

    invalid_coordinate_count = int(
        invalid_coordinates.sum()
    )

    print(
        "Invalid coordinate records:",
        invalid_coordinate_count
    )

    if invalid_coordinate_count > 0:

        raise RuntimeError(
            "Invalid coordinates found. "
            "Investigate the source dataset before assignment."
        )

    # Transform WGS84 coordinates into UTM Zone 43N.
    transformer = Transformer.from_crs(
        "EPSG:4326",
        TARGET_CRS,
        always_xy=True
    )

    x, y = transformer.transform(
        df["longitude"].to_numpy(),
        df["latitude"].to_numpy()
    )

    x = np.asarray(x)
    y = np.asarray(y)

    # Calculate globally aligned 1 km grid indices.
    #
    # Same origin and cell size used by create_sqh_grid.py.

    sqh_grid_col = np.floor(
        x / CELL_SIZE_METRES
    ).astype(np.int64)

    sqh_grid_row = np.floor(
        y / CELL_SIZE_METRES
    ).astype(np.int64)

    df["sqh_grid_row"] = sqh_grid_row

    df["sqh_grid_col"] = sqh_grid_col

    # Map each detection to exactly one grid cell.
    cell_keys = list(
        zip(
            sqh_grid_row,
            sqh_grid_col
        )
    )

    assigned_ids = [
        cell_lookup.get(key)
        for key in cell_keys
    ]

    df["sqh_cell_id"] = assigned_ids

    unmatched_mask = df["sqh_cell_id"].isna()

    unmatched_count = int(
        unmatched_mask.sum()
    )

    assigned_count = len(df) - unmatched_count

    print(f"Total detections: {len(df):,}")

    print(
        f"Successfully assigned: {assigned_count:,}"
    )

    print(
        f"Unmatched detections: {unmatched_count:,}"
    )

    # If any detection is unmatched, save diagnostics
    # and stop rather than silently losing observations.

    if unmatched_count > 0:

        print("\nUNMATCHED DETECTION EXAMPLES:")

        diagnostic_columns = [
            "sensor",
            "latitude",
            "longitude",
            "acq_date",
            "sqh_grid_row",
            "sqh_grid_col",
        ]

        print(
            df.loc[
                unmatched_mask,
                diagnostic_columns
            ].head(20).to_string(index=False)
        )

        raise RuntimeError(
            f"{unmatched_count} detections could not be "
            "assigned to an SQH grid cell. "
            "Investigate before continuing."
        )

    # Ensure every assigned ID exists in the grid.
    valid_ids = set(cell_lookup.values())

    invalid_ids = int(
        (~df["sqh_cell_id"].isin(valid_ids)).sum()
    )

    if invalid_ids:

        raise RuntimeError(
            f"{invalid_ids} detections have invalid SQH cell IDs."
        )

    # Ensure one output row per input detection.
    if len(df) != assigned_count:

        raise RuntimeError(
            "Detection count changed during cell assignment."
        )

    print("\nAssignment successful.")

    return df


# ============================================================
# 8. FINAL VALIDATION
# ============================================================

def validate_output(df, original_sensor_counts):

    print_section("[5/7] VALIDATING SQH DETECTIONS")

    # Check required output fields.
    required_output = [
        "sensor",
        "latitude",
        "longitude",
        "sqh_grid_row",
        "sqh_grid_col",
        "sqh_cell_id",
    ]

    validate_columns(
        df,
        required_output,
        "SQH detection dataset"
    )

    null_cell_ids = int(
        df["sqh_cell_id"].isna().sum()
    )

    duplicate_rows = int(
        df.duplicated().sum()
    )

    sensor_counts = {
        str(sensor): int(count)

        for sensor, count in
        df["sensor"].value_counts().items()
    }

    sensor_count_check = (
        sensor_counts == original_sensor_counts
    )

    # The overlap comparison period is recorded separately.
    dates = pd.to_datetime(
        df["acq_date"]
    )

    overlap_start = pd.Timestamp(
        OVERLAP_START_DATE
    )

    comparison_period_count = int(
        (dates >= overlap_start).sum()
    )

    terra_pre_overlap_count = int(
        (
            (df["sensor"] == "MODIS_Terra")
            & (dates < overlap_start)
        ).sum()
    )

    report = {

        "project": PROJECT_NAME,

        "processing_stage": (
            "SQH detection preparation and cell assignment"
        ),

        "source_file": str(SOURCE_FILE),

        "grid_file": str(GRID_FILE),

        "output_file": str(OUTPUT_FILE),

        "target_crs": TARGET_CRS,

        "cell_size_metres": CELL_SIZE_METRES,

        "configured_sensors": SQH_SENSORS,

        "overlap_start_date": OVERLAP_START_DATE,

        "total_sqh_detections": int(len(df)),

        "sensor_counts": sensor_counts,

        "null_sqh_cell_ids": null_cell_ids,

        "duplicate_full_rows": duplicate_rows,

        "comparison_period_detections": (
            comparison_period_count
        ),

        "terra_pre_2012_detections_preserved": (
            terra_pre_overlap_count
        ),

        "sensor_counts_match_filtered_source": (
            bool(sensor_count_check)
        ),

        "validation_passed": (
            null_cell_ids == 0
            and sensor_count_check
        ),
    }

    print("Total SQH detections:", len(df))

    print("\nSensor counts:")

    print(df["sensor"].value_counts())

    print(
        "\nNull SQH cell IDs:",
        null_cell_ids
    )

    print(
        "Full-row duplicates:",
        duplicate_rows
    )

    print(
        "Detections from comparison period onwards:",
        comparison_period_count
    )

    print(
        "Terra detections before 2012:",
        terra_pre_overlap_count
    )

    print(
        "\nSensor counts match filtered source:",
        sensor_count_check
    )

    print(
        "\nVALIDATION:",
        "PASSED"
        if report["validation_passed"]
        else "FAILED"
    )

    return report


# ============================================================
# 9. SAVE OUTPUTS
# ============================================================

def save_outputs(df, report):

    print_section("[6/7] SAVING SQH DETECTIONS")

    if not report["validation_passed"]:

        raise RuntimeError(
            "Validation failed. Output dataset will not be saved."
        )

    # Write to a separate output file.
    df.to_parquet(
        OUTPUT_FILE,
        index=False
    )

    with open(
        QA_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            report,
            file,
            indent=4,
            ensure_ascii=False
        )

    print(f"SQH dataset saved:\n{OUTPUT_FILE}")

    print(f"\nQA report saved:\n{QA_FILE}")


# ============================================================
# 10. MAIN
# ============================================================

def main():

    print("\n")
    print("#" * 65)
    print("PUNJAB FIRE CALENDAR - SQH DETECTION PREPARATION")
    print("#" * 65)

    ensure_directories()

    # Step 1: Load source dataset.
    source = load_source_dataset()

    # Step 2: Filter the two project sensors.
    filtered = filter_required_sensors(source)

    original_sensor_counts = {
        str(sensor): int(count)

        for sensor, count in
        filtered["sensor"].value_counts().items()
    }

    # Release the full source dataframe.
    del source

    # Step 3: Load the SQH grid.
    grid, cell_lookup = load_sqh_grid()

    del grid

    # Step 4: Assign detections to grid cells.
    prepared = assign_sqh_cells(
        filtered,
        cell_lookup
    )

    del filtered

    # Step 5: Validate.
    report = validate_output(
        prepared,
        original_sensor_counts
    )

    # Step 6: Save.
    save_outputs(
        prepared,
        report
    )

    print_section("[7/7] SQH DETECTION PREPARATION COMPLETE")

    print("Successfully prepared SQH detection dataset.")

    print(f"Total detections: {len(prepared):,}")

    print(f"Output: {OUTPUT_FILE}")

    print("\nOriginal cleaned dataset was not modified.")


if __name__ == "__main__":

    try:

        main()

    except Exception as error:

        print("\nERROR:")
        print(error)

        sys.exit(1)