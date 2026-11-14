from pathlib import Path

import pandas as pd


# ============================================================
# PATHS
# ============================================================

INPUT_FILE = Path(
    "data/processed/hotspots_clean.parquet"
)

OUTPUT_DIR = Path(
    "data/processed/calibration"
)

QA_DIR = Path("outputs")


# ============================================================
# SENSOR PAIRS
# ============================================================

SENSOR_PAIRS = [
    ("MODIS_Aqua", "VIIRS_SNPP"),
    ("MODIS_Aqua", "VIIRS_NOAA20"),
    ("MODIS_Aqua", "VIIRS_NOAA21"),

    ("MODIS_Terra", "VIIRS_SNPP"),
    ("MODIS_Terra", "VIIRS_NOAA20"),
    ("MODIS_Terra", "VIIRS_NOAA21"),
]


# ============================================================
# REQUIRED COLUMNS
# ============================================================

REQUIRED_COLUMNS = [
    "sensor",
    "grid_id",
    "timestamp_utc",
    "daynight",
    "frp",
]


# ============================================================
# LOAD AND VALIDATE DATA
# ============================================================

def load_data():

    print("\nLoading cleaned detections...")

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Input file not found: {INPUT_FILE}"
        )

    df = pd.read_parquet(INPUT_FILE)

    missing = [
        col
        for col in REQUIRED_COLUMNS
        if col not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Missing required columns: {missing}"
        )

    df = df[REQUIRED_COLUMNS].copy()

    # --------------------------------------------------------
    # TIMESTAMP
    # --------------------------------------------------------

    df["timestamp_utc"] = pd.to_datetime(
        df["timestamp_utc"],
        utc=True,
        errors="coerce",
    )

    # --------------------------------------------------------
    # FRP
    # --------------------------------------------------------

    df["frp"] = pd.to_numeric(
        df["frp"],
        errors="coerce",
    )

    # --------------------------------------------------------
    # SENSOR AND GRID VALIDATION
    # --------------------------------------------------------

    df["sensor"] = (
        df["sensor"]
        .astype("string")
        .str.strip()
    )

    df["grid_id"] = (
        df["grid_id"]
        .astype("string")
        .str.strip()
    )

    # --------------------------------------------------------
    # NORMALIZE DAY/NIGHT
    # --------------------------------------------------------

    daynight = (
        df["daynight"]
        .astype("string")
        .str.strip()
        .str.upper()
    )

    daynight_mapping = {
        "D": "D",
        "DAY": "D",
        "N": "N",
        "NIGHT": "N",
    }

    df["daynight"] = daynight.map(
        daynight_mapping
    )

    # --------------------------------------------------------
    # CHECK INVALID RECORDS
    # --------------------------------------------------------

    invalid_mask = (
        df["sensor"].isna()
        | df["grid_id"].isna()
        | df["timestamp_utc"].isna()
        | df["daynight"].isna()
        | df["frp"].isna()
    )

    invalid_count = int(invalid_mask.sum())

    if invalid_count > 0:

        print(
            "\nWARNING: Invalid rows found:",
            invalid_count
        )

        print(
            "Invalid rows by reason:"
        )

        print(
            df[invalid_mask][REQUIRED_COLUMNS]
            .isna()
            .sum()
            .to_string()
        )

        raise ValueError(
            "Invalid records found. "
            "Investigate before building overlap pairs."
        )

    # --------------------------------------------------------
    # EXPECTED SENSORS
    # --------------------------------------------------------

    expected_sensors = {
        sensor
        for pair in SENSOR_PAIRS
        for sensor in pair
    }

    actual_sensors = set(
        df["sensor"].unique()
    )

    print("\nSensor inventory:")

    print(
        df["sensor"]
        .value_counts()
        .to_string()
    )

    unexpected = actual_sensors - expected_sensors

    if unexpected:
        print(
            "\nWARNING: Unexpected sensors:",
            sorted(unexpected)
        )

    missing_sensors = expected_sensors - actual_sensors

    if missing_sensors:
        print(
            "\nWARNING: Sensors missing from dataset:",
            sorted(missing_sensors)
        )

    # --------------------------------------------------------
    # WEEK START: MONDAY
    # --------------------------------------------------------

    df["week_start"] = (
        df["timestamp_utc"].dt.normalize()
        - pd.to_timedelta(
            df["timestamp_utc"].dt.day_of_week,
            unit="D",
        )
    )

    print("\nRows loaded:", len(df))

    print(
        "Date range:",
        df["timestamp_utc"].min(),
        "to",
        df["timestamp_utc"].max(),
    )

    print(
        "Day/night distribution:",
        df["daynight"].value_counts().to_dict()
    )

    print(
        "Unique grid cells:",
        df["grid_id"].nunique()
    )

    return df


# ============================================================
# AGGREGATE ONE SENSOR
# ============================================================

def aggregate_sensor(
    df,
    sensor_name,
    start_date,
    end_date,
):

    start_day = (
        pd.Timestamp(start_date)
        .normalize()
    )

    end_day_exclusive = (
        pd.Timestamp(end_date)
        .normalize()
        + pd.Timedelta(days=1)
    )

    sensor_df = df[
        (df["sensor"] == sensor_name)
        & (df["timestamp_utc"] >= start_day)
        & (df["timestamp_utc"] < end_day_exclusive)
    ].copy()

    grouped = (
        sensor_df
        .groupby(
            [
                "week_start",
                "grid_id",
                "daynight",
            ],
            observed=True,
        )
        .agg(
            detections=("frp", "size"),
            frp_sum=("frp", "sum"),
        )
        .reset_index()
    )

    return grouped


# ============================================================
# BUILD ONE MODIS-VIIRS PAIR
# ============================================================

def build_pair(
    df,
    modis_sensor,
    viirs_sensor,
):

    print(
        f"\nBuilding pair: "
        f"{modis_sensor} vs {viirs_sensor}"
    )

    modis = df[
        df["sensor"] == modis_sensor
    ]

    viirs = df[
        df["sensor"] == viirs_sensor
    ]

    if modis.empty or viirs.empty:

        print(
            "WARNING: One sensor has no records."
        )

        return None

    # --------------------------------------------------------
    # COMMON DATE RANGE
    # --------------------------------------------------------

    overlap_start = max(
        modis["timestamp_utc"].min(),
        viirs["timestamp_utc"].min(),
    )

    overlap_end = min(
        modis["timestamp_utc"].max(),
        viirs["timestamp_utc"].max(),
    )

    if overlap_start > overlap_end:

        print(
            "WARNING: No overlapping date range."
        )

        return None

    print("Overlap start:", overlap_start)
    print("Overlap end:", overlap_end)

    # --------------------------------------------------------
    # AGGREGATE BOTH SENSORS
    # --------------------------------------------------------

    modis_agg = aggregate_sensor(
        df,
        modis_sensor,
        overlap_start,
        overlap_end,
    )

    viirs_agg = aggregate_sensor(
        df,
        viirs_sensor,
        overlap_start,
        overlap_end,
    )

    modis_agg = modis_agg.rename(
        columns={
            "detections": "modis_detections",
            "frp_sum": "modis_frp_sum",
        }
    )

    viirs_agg = viirs_agg.rename(
        columns={
            "detections": "viirs_detections",
            "frp_sum": "viirs_frp_sum",
        }
    )

    # --------------------------------------------------------
    # VALIDATE AGGREGATION KEYS
    # --------------------------------------------------------

    join_keys = [
        "week_start",
        "grid_id",
        "daynight",
    ]

    if modis_agg.duplicated(
        subset=join_keys
    ).any():

        raise ValueError(
            f"Duplicate MODIS aggregation keys: "
            f"{modis_sensor}"
        )

    if viirs_agg.duplicated(
        subset=join_keys
    ).any():

        raise ValueError(
            f"Duplicate VIIRS aggregation keys: "
            f"{viirs_sensor}"
        )

    # --------------------------------------------------------
    # OUTER JOIN
    # --------------------------------------------------------

    pairs = pd.merge(
        modis_agg,
        viirs_agg,
        on=join_keys,
        how="outer",
        validate="one_to_one",
    )

    # Missing means no recorded detections
    # in that sensor's aggregated cell-week.

    numeric_columns = [
        "modis_detections",
        "modis_frp_sum",
        "viirs_detections",
        "viirs_frp_sum",
    ]

    pairs[numeric_columns] = (
        pairs[numeric_columns]
        .fillna(0)
    )

    pairs["modis_detections"] = (
        pairs["modis_detections"]
        .astype("int32")
    )

    pairs["viirs_detections"] = (
        pairs["viirs_detections"]
        .astype("int32")
    )

    pairs["modis_sensor"] = modis_sensor
    pairs["viirs_sensor"] = viirs_sensor

    pairs = pairs.sort_values(
        join_keys
    ).reset_index(drop=True)

    # --------------------------------------------------------
    # FINAL PAIR VALIDATION
    # --------------------------------------------------------

    if pairs.duplicated(
        subset=join_keys
    ).any():

        raise ValueError(
            "Duplicate keys found in final pair table."
        )

    if (
        (pairs["modis_detections"] == 0)
        & (pairs["viirs_detections"] == 0)
    ).any():

        raise ValueError(
            "Unexpected rows with zero detections "
            "from both sensors."
        )

    print("MODIS aggregated rows:", len(modis_agg))
    print("VIIRS aggregated rows:", len(viirs_agg))
    print("Combined pair rows:", len(pairs))

    print(
        "Both sensors nonzero:",
        int(
            (
                (pairs["modis_detections"] > 0)
                & (pairs["viirs_detections"] > 0)
            ).sum()
        )
    )

    return (
        pairs,
        overlap_start,
        overlap_end,
    )


# ============================================================
# BUILD QA REPORT
# ============================================================

def build_qa_rows(
    pairs,
    modis_sensor,
    viirs_sensor,
    overlap_start,
    overlap_end,
):

    qa_rows = []

    for daynight in ["D", "N"]:

        subset = pairs[
            pairs["daynight"] == daynight
        ]

        qa_rows.append({

            "modis_sensor": modis_sensor,

            "viirs_sensor": viirs_sensor,

            "daynight": daynight,

            "overlap_start": overlap_start,

            "overlap_end": overlap_end,

            "pair_rows": len(subset),

            "unique_grid_cells": (
                subset["grid_id"].nunique()
            ),

            "unique_weeks": (
                subset["week_start"].nunique()
            ),

            "modis_detections": int(
                subset["modis_detections"].sum()
            ),

            "viirs_detections": int(
                subset["viirs_detections"].sum()
            ),

            "both_sensors_nonzero": int(
                (
                    (subset["modis_detections"] > 0)
                    & (subset["viirs_detections"] > 0)
                ).sum()
            ),

            "modis_only_cells_weeks": int(
                (
                    (subset["modis_detections"] > 0)
                    & (subset["viirs_detections"] == 0)
                ).sum()
            ),

            "viirs_only_cells_weeks": int(
                (
                    (subset["modis_detections"] == 0)
                    & (subset["viirs_detections"] > 0)
                ).sum()
            ),

        })

    return qa_rows


# ============================================================
# MAIN
# ============================================================

def main():

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    QA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    df = load_data()

    qa_rows = []

    successful_pairs = 0

    for modis_sensor, viirs_sensor in SENSOR_PAIRS:

        result = build_pair(
            df,
            modis_sensor,
            viirs_sensor,
        )

        if result is None:
            continue

        (
            pairs,
            overlap_start,
            overlap_end,
        ) = result

        filename = (
            f"{modis_sensor.lower()}_"
            f"{viirs_sensor.lower()}_pairs.parquet"
        )

        output_path = OUTPUT_DIR / filename

        pairs.to_parquet(
            output_path,
            index=False,
        )

        successful_pairs += 1

        print("\nSaved:", output_path)

        qa_rows.extend(
            build_qa_rows(
                pairs,
                modis_sensor,
                viirs_sensor,
                overlap_start,
                overlap_end,
            )
        )

    # --------------------------------------------------------
    # SAVE QA
    # --------------------------------------------------------

    qa = pd.DataFrame(qa_rows)

    qa_path = QA_DIR / "overlap_pair_qa.csv"

    qa.to_csv(
        qa_path,
        index=False,
    )

    print("\n===================================")
    print("OVERLAP PAIR GENERATION COMPLETE")
    print("===================================")

    print(
        "\nSuccessful sensor pairs:",
        successful_pairs,
        "of",
        len(SENSOR_PAIRS),
    )

    print("\nQA report:")

    if not qa.empty:
        print(
            qa.to_string(index=False)
        )
    else:
        print("No sensor pairs were generated.")

    print("\nSaved QA:", qa_path)

    if successful_pairs != len(SENSOR_PAIRS):

        print(
            "\nWARNING: Not all six sensor pairs "
            "were generated."
        )


if __name__ == "__main__":
    main()