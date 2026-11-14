from pathlib import Path

import pandas as pd


# --------------------------------------------------
# PATHS
# --------------------------------------------------

INPUT_FILE = Path("data/processed/hotspots_clean.parquet")

OUTPUT_DIR = Path("data/processed/calibration")

QA_DIR = Path("outputs")


# --------------------------------------------------
# SENSOR PAIRS
# --------------------------------------------------

SENSOR_PAIRS = [
    ("MODIS_Aqua", "VIIRS_SNPP"),
    ("MODIS_Aqua", "VIIRS_NOAA20"),
    ("MODIS_Aqua", "VIIRS_NOAA21"),

    ("MODIS_Terra", "VIIRS_SNPP"),
    ("MODIS_Terra", "VIIRS_NOAA20"),
    ("MODIS_Terra", "VIIRS_NOAA21"),
]


# --------------------------------------------------
# LOAD DATA
# --------------------------------------------------

def load_data():

    print("\nLoading cleaned detections...")

    df = pd.read_parquet(INPUT_FILE)

    required_columns = [
        "sensor",
        "grid_id",
        "acq_timestamp_utc",
        "daynight",
        "frp",
    ]

    missing = [
        col for col in required_columns
        if col not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Missing required columns: {missing}"
        )

    df = df[required_columns].copy()

    df["acq_timestamp_utc"] = pd.to_datetime(
        df["acq_timestamp_utc"],
        utc=True,
        errors="coerce",
    )

    df["frp"] = pd.to_numeric(
        df["frp"],
        errors="coerce",
    )

    df = df.dropna(
        subset=[
            "sensor",
            "grid_id",
            "acq_timestamp_utc",
            "daynight",
            "frp",
        ]
    )

    df = df[df["daynight"].isin(["D", "N"])].copy()

    # Monday-based weekly periods.
    df["week_start"] = (
        df["acq_timestamp_utc"]
        .dt.normalize()
        - pd.to_timedelta(
           df["acq_timestamp_utc"].dt.day_of_week ,
            unit="D",
        )
    )

    print("Rows loaded:", len(df))
    print("Sensors:", sorted(df["sensor"].unique()))
    print("Day/night:", df["daynight"].value_counts().to_dict())

    return df


# --------------------------------------------------
# AGGREGATE ONE SENSOR
# --------------------------------------------------
def aggregate_sensor(df, sensor_name, start_date, end_date):

    start_day = pd.Timestamp(start_date).normalize()

    end_day_exclusive = (
        pd.Timestamp(end_date).normalize()
        + pd.Timedelta(days=1)
    )

    sensor_df = df[
        (df["sensor"] == sensor_name)
        & (df["acq_timestamp_utc"] >= start_day)
        & (df["acq_timestamp_utc"] < end_day_exclusive)
    ].copy()

    grouped = (
        sensor_df
        .groupby(
            ["week_start", "grid_id", "daynight"],
            observed=True,
        )
        .agg(
            detections=("frp", "size"),
            frp_sum=("frp", "sum"),
        )
        .reset_index()
    )

    return grouped
# --------------------------------------------------
# BUILD ONE MODIS-VIIRS PAIR
# --------------------------------------------------

def build_pair(df, modis_sensor, viirs_sensor):

    print(
        f"\nBuilding pair: "
        f"{modis_sensor} vs {viirs_sensor}"
    )

    modis = df[df["sensor"] == modis_sensor]
    viirs = df[df["sensor"] == viirs_sensor]

    if modis.empty or viirs.empty:
        print("WARNING: One sensor has no records.")
        return None

    # Restrict both sensors to their common date range.
    overlap_start = max(
        modis["acq_timestamp_utc"].min(),
        viirs["acq_timestamp_utc"].min(),
    )

    overlap_end = min(
        modis["acq_timestamp_utc"].max(),
        viirs["acq_timestamp_utc"].max(),
    )

    if overlap_start > overlap_end:
        print("WARNING: No overlapping date range.")
        return None

    print("Overlap start:", overlap_start)
    print("Overlap end:", overlap_end)

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

    # Outer join preserves detections from either sensor.
    pairs = pd.merge(
        modis_agg,
        viirs_agg,
        on=["week_start", "grid_id", "daynight"],
        how="outer",
    )

    # Missing means no recorded detections for that
    # sensor in that cell-week-day/night combination.
    numeric_columns = [
        "modis_detections",
        "modis_frp_sum",
        "viirs_detections",
        "viirs_frp_sum",
    ]

    pairs[numeric_columns] = (
        pairs[numeric_columns].fillna(0)
    )

    pairs["modis_detections"] = (
        pairs["modis_detections"].astype("int32")
    )

    pairs["viirs_detections"] = (
        pairs["viirs_detections"].astype("int32")
    )

    pairs["modis_sensor"] = modis_sensor
    pairs["viirs_sensor"] = viirs_sensor

    pairs = pairs.sort_values(
        ["week_start", "grid_id", "daynight"]
    ).reset_index(drop=True)

    return pairs, overlap_start, overlap_end


# --------------------------------------------------
# MAIN
# --------------------------------------------------

def main():

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    df = load_data()

    qa_rows = []

    for modis_sensor, viirs_sensor in SENSOR_PAIRS:

        result = build_pair(
            df,
            modis_sensor,
            viirs_sensor,
        )

        if result is None:
            continue

        pairs, overlap_start, overlap_end = result

        filename = (
            f"{modis_sensor.lower()}_"
            f"{viirs_sensor.lower()}_pairs.parquet"
        )

        output_path = OUTPUT_DIR / filename

        pairs.to_parquet(
            output_path,
            index=False,
        )

        print("\nSaved:", output_path)
        print("Pair rows:", len(pairs))

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

                "modis_detections": int(
                    subset["modis_detections"].sum()
                ),

                "viirs_detections": int(
                    subset["viirs_detections"].sum()
                ),

                "both_sensors_nonzero": int(
                    (
                        (subset["modis_detections"] > 0)
                        &
                        (subset["viirs_detections"] > 0)
                    ).sum()
                ),

                "modis_only_cells_weeks": int(
                    (
                        (subset["modis_detections"] > 0)
                        &
                        (subset["viirs_detections"] == 0)
                    ).sum()
                ),

                "viirs_only_cells_weeks": int(
                    (
                        (subset["modis_detections"] == 0)
                        &
                        (subset["viirs_detections"] > 0)
                    ).sum()
                ),

            })

    # Save QA report.
    qa = pd.DataFrame(qa_rows)

    qa_path = QA_DIR / "overlap_pair_qa.csv"

    qa.to_csv(
        qa_path,
        index=False,
    )

    print("\n===================================")
    print("OVERLAP PAIR GENERATION COMPLETE")
    print("===================================")

    print("\nQA report:")
    print(qa.to_string(index=False))

    print("\nSaved QA:", qa_path)


if __name__ == "__main__":
    main()