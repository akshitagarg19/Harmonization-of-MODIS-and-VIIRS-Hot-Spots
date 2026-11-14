
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyarrow.parquet as pq


# ============================================================
# PATHS AND SETTINGS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

INPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "hotspots_clean.parquet"
)

DISTRICT_FILE = (
    PROJECT_ROOT
    / "data"
    / "boundaries"
    / "punjab_districts.geojson"
)

OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"
QA_DIR = PROJECT_ROOT / "outputs"

BATCH_SIZE = 100_000

# Maximum permitted distance for fallback assignment.
FALLBACK_DISTANCE_METRES = 30

# Punjab is within UTM Zone 43N.
METRIC_CRS = "EPSG:32643"


# ============================================================
# SENSOR FAMILY MAPPING
# ============================================================

SENSOR_FAMILY_MAP = {
    "MODIS_Terra": "MODIS",
    "MODIS_Aqua": "MODIS",
    "VIIRS_SNPP": "VIIRS",
    "VIIRS_NOAA20": "VIIRS",
    "VIIRS_NOAA21": "VIIRS",
}


# ============================================================
# LOAD DISTRICT BOUNDARIES
# ============================================================

def load_districts():

    print("\nLoading Punjab district boundaries...")

    districts = gpd.read_file(DISTRICT_FILE)

    if districts.empty:
        raise ValueError(
            "District boundary file is empty."
        )

    required_columns = [
        "district",
        "dtcode",
        "geometry"
    ]

    missing = [
        column
        for column in required_columns
        if column not in districts.columns
    ]

    if missing:
        raise ValueError(
            f"District boundary file is missing columns: {missing}"
        )

    districts = districts[
        ["district", "dtcode", "geometry"]
    ].copy()

    districts = districts.dropna(
        subset=["district", "dtcode", "geometry"]
    )

    if districts.crs is None:
        raise ValueError(
            "District boundary file has no CRS defined."
        )

    districts = districts.to_crs("EPSG:4326")

    if not districts.geometry.is_valid.all():
        raise ValueError(
            "Invalid district geometries found. "
            "Resolve them before aggregation."
        )

    if districts.geometry.is_empty.any():
        raise ValueError(
            "Empty district geometries found."
        )

    if districts["district"].duplicated().any():
        duplicates = districts.loc[
            districts["district"].duplicated(),
            "district"
        ].tolist()

        raise ValueError(
            f"Duplicate district names found: {duplicates}"
        )

    districts = districts.reset_index(drop=True)

    print(f"Districts loaded: {len(districts)}")

    print(
        "District names:",
        ", ".join(sorted(districts["district"].astype(str)))
    )

    return districts


# ============================================================
# ASSIGN HOTSPOTS TO DISTRICTS
# ============================================================

def assign_districts(df, districts):

    """
    Assign every hotspot to a Punjab district.

    1. First use strict point-within-polygon assignment.
    2. Unassigned points receive nearest-district fallback.
    3. Fallback is permitted only within 30 metres.
    4. Preserve all original hotspot attributes.
    """

    df = df.copy().reset_index(drop=True)

    required_columns = [
        "latitude",
        "longitude",
        "sensor"
    ]

    missing = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Hotspot batch is missing columns: {missing}"
        )

    df["_row_id"] = np.arange(len(df))

    # Validate coordinates.
    df["latitude"] = pd.to_numeric(
        df["latitude"],
        errors="coerce"
    )

    df["longitude"] = pd.to_numeric(
        df["longitude"],
        errors="coerce"
    )

    invalid_coordinates = (
        df["latitude"].isna()
        | df["longitude"].isna()
        | ~df["latitude"].between(-90, 90)
        | ~df["longitude"].between(-180, 180)
    )

    if invalid_coordinates.any():
        raise ValueError(
            "Invalid hotspot coordinates found."
        )

    points = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(
            df["longitude"],
            df["latitude"]
        ),
        crs="EPSG:4326"
    )

    # --------------------------------------------------------
    # 1. STRICT POINT-IN-POLYGON ASSIGNMENT
    # --------------------------------------------------------

    joined = gpd.sjoin(
        points,
        districts,
        how="left",
        predicate="within"
    )

    duplicate_matches = joined["_row_id"].duplicated(
        keep=False
    )

    if duplicate_matches.any():

        duplicate_ids = joined.loc[
            duplicate_matches,
            "_row_id"
        ].unique()

        raise ValueError(
            "Some detections match multiple district polygons. "
            f"Example row IDs: {duplicate_ids[:10].tolist()}"
        )

    strict = joined[
        joined["district"].notna()
    ].copy()

    unassigned_ids = set(
        joined.loc[
            joined["district"].isna(),
            "_row_id"
        ].tolist()
    )

    fallback_count = len(unassigned_ids)

    fallback_assigned_count = 0
    maximum_fallback_distance = 0.0

    # --------------------------------------------------------
    # 2. NEAREST-DISTRICT FALLBACK
    # --------------------------------------------------------

    if fallback_count > 0:

        print(
            "Points requiring nearest-district fallback:",
            fallback_count
        )

        boundary_points = points[
            points["_row_id"].isin(unassigned_ids)
        ].copy()

        boundary_points = boundary_points.to_crs(
            METRIC_CRS
        )

        metric_districts = districts.to_crs(
            METRIC_CRS
        )

        nearest = gpd.sjoin_nearest(
            boundary_points,
            metric_districts,
            how="left",
            distance_col="_distance_m"
        )

        # Resolve exact-distance ties deterministically.
        nearest = nearest.sort_values(
            ["_row_id", "_distance_m", "district"]
        )

        nearest = nearest.drop_duplicates(
            subset="_row_id",
            keep="first"
        )

        if nearest["_distance_m"].isna().any():
            raise ValueError(
                "Nearest-district calculation returned missing distances."
            )

        acceptable = nearest[
            nearest["_distance_m"]
            <= FALLBACK_DISTANCE_METRES
        ].copy()

        rejected = nearest[
            nearest["_distance_m"]
            > FALLBACK_DISTANCE_METRES
        ]

        if len(rejected) > 0:

            examples = rejected[
                ["_row_id", "_distance_m"]
            ].head(10).to_dict("records")

            raise ValueError(
                "Some detections are farther than the permitted "
                f"{FALLBACK_DISTANCE_METRES} metres from every district. "
                f"Examples: {examples}"
            )

        if acceptable["district"].isna().any():
            raise ValueError(
                "Nearest-district fallback returned missing districts."
            )

        fallback_assigned_count = len(acceptable)

        if fallback_assigned_count != fallback_count:
            raise ValueError(
                "Not all unassigned detections received fallback."
            )

        maximum_fallback_distance = float(
            acceptable["_distance_m"].max()
        )

        print(
            "Assigned through fallback:",
            fallback_assigned_count
        )

        print(
            "Maximum fallback distance (m):",
            round(maximum_fallback_distance, 3)
        )

        # Preserve original hotspot attributes.
        fallback = pd.DataFrame(
            acceptable.drop(
                columns=[
                    "geometry",
                    "index_right",
                    "_distance_m"
                ],
                errors="ignore"
            )
        )

        strict = pd.DataFrame(
            strict.drop(
                columns=[
                    "geometry",
                    "index_right"
                ],
                errors="ignore"
            )
        )

        assigned = pd.concat(
            [strict, fallback],
            ignore_index=True
        )

    else:

        assigned = pd.DataFrame(
            strict.drop(
                columns=[
                    "geometry",
                    "index_right"
                ],
                errors="ignore"
            )
        )

    # --------------------------------------------------------
    # 3. FINAL ASSIGNMENT VALIDATION
    # --------------------------------------------------------

    assigned = assigned.sort_values(
        "_row_id"
    ).reset_index(drop=True)

    if len(assigned) != len(df):
        raise ValueError(
            "District assignment row count mismatch: "
            f"{len(assigned)} assigned vs {len(df)} input."
        )

    if assigned["_row_id"].duplicated().any():
        raise ValueError(
            "Duplicate hotspot assignments detected."
        )

    if assigned["district"].isna().any():
        raise ValueError(
            "Some hotspots remain without a district."
        )

    if assigned["dtcode"].isna().any():
        raise ValueError(
            "Some hotspots have missing district codes."
        )

    if assigned["sensor"].isna().any():
        raise ValueError(
            "Sensor values became missing during district assignment."
        )

    assigned = assigned.drop(
        columns=["_row_id"],
        errors="ignore"
    )

    return (
        assigned,
        fallback_count,
        fallback_assigned_count,
        maximum_fallback_distance
    )


# ============================================================
# PREPARE BATCH
# ============================================================

def prepare_batch(df):

    df = df.copy()

    # --------------------------------------------------------
    # 1. SENSOR FAMILY
    # --------------------------------------------------------

    df["sensor_family"] = df["sensor"].map(
        SENSOR_FAMILY_MAP
    )

    if df["sensor_family"].isna().any():

        unknown = df.loc[
            df["sensor_family"].isna(),
            "sensor"
        ].unique().tolist()

        raise ValueError(
            f"Unknown sensors found: {unknown}"
        )

    # --------------------------------------------------------
    # 2. ACQUISITION TIMESTAMP
    # --------------------------------------------------------

    if "timestamp_utc" not in df.columns:
        raise ValueError(
            "Cleaned dataset is missing timestamp_utc."
        )

    df["timestamp_utc"] = pd.to_datetime(
        df["timestamp_utc"],
        utc=True,
        errors="coerce"
    )

    if df["timestamp_utc"].isna().any():
        raise ValueError(
            "Invalid acquisition timestamps found."
        )

    timestamps = df["timestamp_utc"]

    # Weekly periods start on Monday.
    df["week_start"] = (
        timestamps.dt.normalize()
        - pd.to_timedelta(
            timestamps.dt.day_of_week,
            unit="D"
        )
    )

    # Monthly periods start on the first day.
    df["month_start"] = pd.to_datetime(
        timestamps.dt.strftime("%Y-%m-01"),
        utc=True
    )

    # --------------------------------------------------------
    # 3. DAY / NIGHT
    # --------------------------------------------------------

    daynight = (
        df["daynight"]
        .astype("string")
        .str.strip()
        .str.upper()
    )

    df["day_flag"] = daynight.isin(
        ["D", "DAY"]
    ).astype("int64")

    df["night_flag"] = daynight.isin(
        ["N", "NIGHT"]
    ).astype("int64")

    unknown_daynight = ~daynight.isin(
        ["D", "DAY", "N", "NIGHT"]
    )

    if unknown_daynight.any():

        examples = (
            daynight[unknown_daynight]
            .value_counts()
            .to_dict()
        )

        raise ValueError(
            f"Unexpected daynight values: {examples}"
        )

    # --------------------------------------------------------
    # 4. FRP
    # --------------------------------------------------------

    df["frp"] = pd.to_numeric(
        df["frp"],
        errors="coerce"
    )

    if df["frp"].isna().any():
        raise ValueError(
            "Invalid FRP values found."
        )

    # --------------------------------------------------------
    # 5. CONFIDENCE
    # --------------------------------------------------------

    df["high_confidence_flag"] = (
        df["confidence_class"]
        .astype("string")
        .str.strip()
        .str.lower()
        .eq("high")
        .astype("int64")
    )

    return df


# ============================================================
# AGGREGATE A CHUNK
# ============================================================

def aggregate_chunk(
    df,
    period_column,
    include_sensor
):

    group_columns = [
        period_column,
        "district",
        "dtcode",
        "sensor_family"
    ]

    if include_sensor:
        group_columns.append("sensor")

    grouped = (
        df.groupby(
            group_columns,
            observed=True,
            dropna=False
        )
        .agg(
            n_detections=("frp", "size"),
            frp_sum=("frp", "sum"),
            frp_mean=("frp", "mean"),
            frp_max=("frp", "max"),
            day_count=("day_flag", "sum"),
            night_count=("night_flag", "sum"),
            high_confidence_count=(
                "high_confidence_flag",
                "sum"
            )
        )
        .reset_index()
    )

    # Preserve distinct grid-cell records for final counting.
    active_cells = (
        df[
            group_columns + ["grid_id"]
        ]
        .drop_duplicates()
        .copy()
    )

    return grouped, active_cells


# ============================================================
# FINALIZE AGGREGATION
# ============================================================

def finalize_aggregation(
    partial_groups,
    active_cell_parts,
    period_column
):

    if not partial_groups:
        raise ValueError(
            f"No aggregation results for {period_column}."
        )

    group_columns = [
        period_column,
        "district",
        "dtcode",
        "sensor_family"
    ]

    if "sensor" in partial_groups[0].columns:
        group_columns.append("sensor")

    # Combine partial aggregation results.
    combined = pd.concat(
        partial_groups,
        ignore_index=True
    )

    final = (
        combined.groupby(
            group_columns,
            observed=True,
            dropna=False
        )
        .agg(
            n_detections=("n_detections", "sum"),
            frp_sum=("frp_sum", "sum"),
            day_count=("day_count", "sum"),
            night_count=("night_count", "sum"),
            high_confidence_count=(
                "high_confidence_count",
                "sum"
            )
        )
        .reset_index()
    )

    # Recalculate weighted mean FRP.
    final["frp_mean"] = (
        final["frp_sum"]
        / final["n_detections"]
    )

    # Maximum FRP across all batches.
    max_values = (
        combined.groupby(
            group_columns,
            observed=True,
            dropna=False
        )["frp_max"]
        .max()
        .reset_index()
    )

    final = final.merge(
        max_values,
        on=group_columns,
        how="left",
        validate="one_to_one"
    )

    # Count unique active grid cells across all batches.
    all_active_cells = pd.concat(
        active_cell_parts,
        ignore_index=True
    )

    all_active_cells = all_active_cells.drop_duplicates()

    cell_counts = (
        all_active_cells.groupby(
            group_columns,
            observed=True,
            dropna=False
        )["grid_id"]
        .nunique()
        .reset_index(name="n_cells_active")
    )

    final = final.merge(
        cell_counts,
        on=group_columns,
        how="left",
        validate="one_to_one"
    )

    final["n_cells_active"] = (
        final["n_cells_active"]
        .fillna(0)
        .astype("int64")
    )

    final = final.sort_values(
        group_columns
    ).reset_index(drop=True)

    return final


# ============================================================
# SAVE OUTPUT
# ============================================================

def save_parquet(df, filename):

    output_path = OUTPUT_DIR / filename

    df.to_parquet(
        output_path,
        index=False,
        engine="pyarrow"
    )

    print(
        f"Saved: {filename} | "
        f"Rows: {len(df):,} | "
        f"Detections: {int(df['n_detections'].sum()):,}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    QA_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Cleaned hotspot file not found: {INPUT_FILE}"
        )

    if not DISTRICT_FILE.exists():
        raise FileNotFoundError(
            f"District boundary file not found: {DISTRICT_FILE}"
        )

    districts = load_districts()

    print("\nOpening cleaned hotspot dataset...")

    parquet_file = pq.ParquetFile(INPUT_FILE)

    expected_total = parquet_file.metadata.num_rows

    print(f"Total input rows: {expected_total:,}")
    print(f"Batch size: {BATCH_SIZE:,}")

    # Partial aggregation results.
    weekly_sensor_groups = []
    monthly_sensor_groups = []

    weekly_family_groups = []
    monthly_family_groups = []

    weekly_sensor_cells = []
    monthly_sensor_cells = []

    weekly_family_cells = []
    monthly_family_cells = []

    total_rows = 0
    assigned_rows = 0

    fallback_required_total = 0
    fallback_assigned_total = 0

    maximum_fallback_distance = 0.0

    batch_number = 0

    # --------------------------------------------------------
    # PROCESS INPUT IN BATCHES
    # --------------------------------------------------------

    for batch in parquet_file.iter_batches(
        batch_size=BATCH_SIZE
    ):

        batch_number += 1

        print(
            f"\nProcessing batch {batch_number}..."
        )

        df = batch.to_pandas()

        total_rows += len(df)

        # Assign districts using actual hotspot coordinates.
        (
            assigned,
            fallback_required,
            fallback_assigned,
            max_distance
        ) = assign_districts(
            df,
            districts
        )

        assigned_rows += len(assigned)

        fallback_required_total += fallback_required

        fallback_assigned_total += fallback_assigned

        maximum_fallback_distance = max(
            maximum_fallback_distance,
            max_distance
        )

        # Prepare timestamps, sensor family and metrics.
        assigned = prepare_batch(assigned)

        # ----------------------------------------------------
        # INDIVIDUAL SENSOR: WEEKLY
        # ----------------------------------------------------

        weekly_groups, weekly_cells = aggregate_chunk(
            assigned,
            "week_start",
            include_sensor=True
        )

        weekly_sensor_groups.append(weekly_groups)
        weekly_sensor_cells.append(weekly_cells)

        # ----------------------------------------------------
        # INDIVIDUAL SENSOR: MONTHLY
        # ----------------------------------------------------

        monthly_groups, monthly_cells = aggregate_chunk(
            assigned,
            "month_start",
            include_sensor=True
        )

        monthly_sensor_groups.append(monthly_groups)
        monthly_sensor_cells.append(monthly_cells)

        # ----------------------------------------------------
        # SENSOR FAMILY: WEEKLY
        # ----------------------------------------------------

        weekly_family, weekly_family_active = aggregate_chunk(
            assigned,
            "week_start",
            include_sensor=False
        )

        weekly_family_groups.append(weekly_family)
        weekly_family_cells.append(weekly_family_active)

        # ----------------------------------------------------
        # SENSOR FAMILY: MONTHLY
        # ----------------------------------------------------

        monthly_family, monthly_family_active = aggregate_chunk(
            assigned,
            "month_start",
            include_sensor=False
        )

        monthly_family_groups.append(monthly_family)
        monthly_family_cells.append(monthly_family_active)

        print(
            f"Batch processed: {len(df):,} detections"
        )

    # --------------------------------------------------------
    # INPUT / ASSIGNMENT CHECK
    # --------------------------------------------------------

    print("\n" + "=" * 60)
    print("DISTRICT ASSIGNMENT SUMMARY")
    print("=" * 60)

    print(f"Input detections: {expected_total:,}")
    print(f"Processed detections: {total_rows:,}")
    print(f"Assigned detections: {assigned_rows:,}")

    print(
        "Points requiring fallback:",
        f"{fallback_required_total:,}"
    )

    print(
        "Points assigned through fallback:",
        f"{fallback_assigned_total:,}"
    )

    print(
        "Maximum fallback distance:",
        f"{maximum_fallback_distance:.3f} metres"
    )

    if total_rows != expected_total:
        raise ValueError(
            "Processed row count does not match input metadata."
        )

    if assigned_rows != expected_total:
        raise ValueError(
            "Not all input detections were assigned to districts."
        )

    if fallback_required_total != fallback_assigned_total:
        raise ValueError(
            "Fallback assignment count mismatch."
        )

    # --------------------------------------------------------
    # FINALIZE FOUR OUTPUT TABLES
    # --------------------------------------------------------

    print("\nFinalizing weekly district aggregation...")

    weekly_sensor = finalize_aggregation(
        weekly_sensor_groups,
        weekly_sensor_cells,
        "week_start"
    )

    print("Finalizing monthly district aggregation...")

    monthly_sensor = finalize_aggregation(
        monthly_sensor_groups,
        monthly_sensor_cells,
        "month_start"
    )

    print("Finalizing weekly district family aggregation...")

    weekly_family = finalize_aggregation(
        weekly_family_groups,
        weekly_family_cells,
        "week_start"
    )

    print("Finalizing monthly district family aggregation...")

    monthly_family = finalize_aggregation(
        monthly_family_groups,
        monthly_family_cells,
        "month_start"
    )

    # --------------------------------------------------------
    # SAVE FOUR OUTPUTS
    # --------------------------------------------------------

    print("\nSaving district aggregation outputs...")

    save_parquet(
        weekly_sensor,
        "weekly_district.parquet"
    )

    save_parquet(
        monthly_sensor,
        "monthly_district.parquet"
    )

    save_parquet(
        weekly_family,
        "weekly_district_family.parquet"
    )

    save_parquet(
        monthly_family,
        "monthly_district_family.parquet"
    )

    # --------------------------------------------------------
    # QA CHECKS
    # --------------------------------------------------------

    expected_districts = set(
        districts["district"].astype(str).tolist()
    )

    output_tables = {
        "weekly_district": weekly_sensor,
        "monthly_district": monthly_sensor,
        "weekly_district_family": weekly_family,
        "monthly_district_family": monthly_family
    }

    qa_rows = []

    print("\n" + "=" * 60)
    print("DISTRICT AGGREGATION QA")
    print("=" * 60)

    all_passed = True

    for name, table in output_tables.items():

        detection_total = int(
            table["n_detections"].sum()
        )

        represented_districts = set(
            table["district"].astype(str).unique()
        )

        missing_districts = sorted(
            expected_districts - represented_districts
        )

        unexpected_districts = sorted(
            represented_districts - expected_districts
        )

        missing_assignments = int(
            table["district"].isna().sum()
        )

        passed = (
            detection_total == expected_total
            and missing_assignments == 0
            and len(unexpected_districts) == 0
        )

        all_passed = all_passed and passed

        print(f"\n{name}")
        print(f"Rows: {len(table):,}")
        print(
            f"Districts represented: {len(represented_districts)}"
        )
        print(f"Detection total: {detection_total:,}")
        print(f"Districts with zero detections: {missing_districts}")
        print(f"Unexpected districts: {unexpected_districts}")
        print(f"Status: {'PASS' if passed else 'FAIL'}")

        qa_rows.append({
            "dataset": name,
            "rows": len(table),
            "districts_represented": len(represented_districts),
            "n_detections": detection_total,
            "missing_assignments": missing_assignments,
            "districts_with_zero_detections": ", ".join(
                missing_districts
            ),
            "unexpected_districts": ", ".join(
                unexpected_districts
            ),
            "status": "PASS" if passed else "FAIL"
        })

    # --------------------------------------------------------
    # FAMILY-LEVEL DETECTION TOTALS
    # --------------------------------------------------------

    print("\nFamily-level detection totals:")

    family_totals = (
        weekly_family.groupby("sensor_family")["n_detections"]
        .sum()
    )

    for family, count in family_totals.items():
        print(f"{family}: {int(count):,}")

    family_total = int(family_totals.sum())

    family_passed = family_total == expected_total

    print(
        "Family total:",
        f"{family_total:,}",
        "|",
        "PASS" if family_passed else "FAIL"
    )

    all_passed = all_passed and family_passed

    # --------------------------------------------------------
    # DISTRICT ASSIGNMENT QA
    # --------------------------------------------------------

    qa_rows.append({
        "dataset": "district_assignment",
        "rows": assigned_rows,
        "districts_represented": len(expected_districts),
        "n_detections": assigned_rows,
        "missing_assignments": 0,
        "districts_with_zero_detections": "",
        "unexpected_districts": "",
        "status": (
            "PASS"
            if assigned_rows == expected_total
            else "FAIL"
        )
    })

    # --------------------------------------------------------
    # FALLBACK QA
    # --------------------------------------------------------

    fallback_passed = (
        fallback_required_total == fallback_assigned_total
        and maximum_fallback_distance <= FALLBACK_DISTANCE_METRES
    )

    qa_rows.append({
        "dataset": "fallback_assignment",
        "rows": fallback_assigned_total,
        "districts_represented": "",
        "n_detections": fallback_assigned_total,
        "missing_assignments": "",
        "districts_with_zero_detections": "",
        "unexpected_districts": "",
        "status": "PASS" if fallback_passed else "FAIL"
    })

    all_passed = all_passed and fallback_passed

    # --------------------------------------------------------
    # SAVE QA REPORT
    # --------------------------------------------------------

    qa_report = pd.DataFrame(qa_rows)

    qa_path = QA_DIR / "district_aggregation_qa.csv"

    qa_report.to_csv(
        qa_path,
        index=False
    )

    print(f"\nQA report saved: {qa_path}")

    print("\n" + "=" * 60)

    if not all_passed:
        raise RuntimeError(
            "District aggregation QA failed. "
            "Inspect district_aggregation_qa.csv."
        )

    print("ALL DISTRICT AGGREGATION CHECKS PASSED")
    print("=" * 60)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
