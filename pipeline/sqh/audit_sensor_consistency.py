from pathlib import Path
import json

import pandas as pd
import geopandas as gpd


# ============================================================
# CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parents[2]

RAW_FILES = {
    "MODIS_Terra": (
        ROOT
        / "data/raw/MODIS/DL_FIRE_M-C61_845709/"
        / "fire_archive_M-C61_845709.csv"
    ),
    "VIIRS_SNPP": (
        ROOT
        / "data/raw/VIIRS/SNPP/DL_FIRE_SV-C2_845715/"
        / "fire_archive_SV-C2_845715.csv"
    ),
}

BOUNDARY_FILE = (
    ROOT
    / "data/boundaries/punjab_state_boundary.geojson"
)
SQH_FILE = (
    ROOT
    / "data/processed/sqh/hotspots_sqh.parquet"
)

OUTPUT_DIR = ROOT / "outputs/sqh/sensor_consistency_audit"

TABLE_DIR = OUTPUT_DIR / "tables"

CHUNK_SIZE = 200_000


# ============================================================
# HELPERS
# ============================================================

def prepare_output():
    TABLE_DIR.mkdir(parents=True, exist_ok=True)


def load_punjab_boundary():
    print("\nLoading Punjab boundary...")

    districts = gpd.read_file(BOUNDARY_FILE)

    if districts.crs is None:
        raise ValueError("Punjab boundary has no CRS.")

    districts = districts.to_crs("EPSG:4326")

    boundary = districts.geometry.union_all()

    if boundary.is_empty or not boundary.is_valid:
        raise ValueError("Punjab boundary is empty or invalid.")

    print("Boundary loaded successfully.")

    return boundary

def load_raw_archive(sensor, path, boundary):

    print(f"\nReading raw archive: {sensor}")

    if not path.exists():
        raise FileNotFoundError(path)

    retained_chunks = []
    total_rows = 0
    invalid_coordinates = 0

    for chunk in pd.read_csv(
        path,
        chunksize=CHUNK_SIZE,
        low_memory=False,
    ):

        total_rows += len(chunk)

        # Separate actual Terra records from Aqua.
        if sensor == "MODIS_Terra":

            satellite = (
                chunk["satellite"]
                .astype("string")
                .str.strip()
                .str.lower()
            )

            chunk = chunk.loc[
                satellite == "terra"
            ].copy()

        # Validate coordinates.
        chunk["latitude"] = pd.to_numeric(
            chunk["latitude"],
            errors="coerce",
        )

        chunk["longitude"] = pd.to_numeric(
            chunk["longitude"],
            errors="coerce",
        )

        valid = (
            chunk["latitude"].between(-90, 90)
            & chunk["longitude"].between(-180, 180)
        )

        invalid_coordinates += int((~valid).sum())

        chunk = chunk.loc[valid].copy()

        # Broad bounding-box filter.
        chunk = chunk.loc[
            chunk["latitude"].between(29.4, 32.7)
            & chunk["longitude"].between(73.7, 77.1)
        ].copy()

        if chunk.empty:
            continue

        points = gpd.GeoDataFrame(
            chunk,
            geometry=gpd.points_from_xy(
                chunk["longitude"],
                chunk["latitude"],
            ),
            crs="EPSG:4326",
        )

        # Exact Punjab polygon filtering.
        inside = points.geometry.intersects(boundary)

        points = points.loc[inside].copy()

        if not points.empty:

            points["sensor"] = sensor

            retained_chunks.append(
                pd.DataFrame(
                    points.drop(columns="geometry")
                )
            )

    if retained_chunks:

        result = pd.concat(
            retained_chunks,
            ignore_index=True,
        )

    else:

        result = pd.DataFrame()

    if not result.empty:

        result["acq_date"] = pd.to_datetime(
            result["acq_date"],
            errors="coerce",
        )

        result["frp"] = pd.to_numeric(
            result["frp"],
            errors="coerce",
        )

        result["year"] = result["acq_date"].dt.year

        result["month"] = (
            result["acq_date"]
            .dt.to_period("M")
            .astype(str)
        )

    print("Original archive rows:", total_rows)
    print("Invalid coordinate rows:", invalid_coordinates)
    print("Punjab detections:", len(result))
    return result

def summarize_records(df, source_name):

    if df.empty:
        return pd.DataFrame()

    result = (
        df.groupby(["sensor", "year"], dropna=False)
        .agg(
            detections=("acq_date", "size"),
            detection_dates=("acq_date", "nunique"),
            frp_sum=("frp", "sum"),
            frp_mean=("frp", "mean"),
        )
        .reset_index()
    )

    result["source"] = source_name

    return result


# ============================================================
# MAIN AUDIT
# ============================================================

def main():

    prepare_output()

    print("=" * 65)
    print("SENSOR CONSISTENCY AUDIT")
    print("=" * 65)

    boundary = load_punjab_boundary()

    # --------------------------------------------------------
    # 1. Load and spatially filter raw archives
    # --------------------------------------------------------

    raw_frames = []

    for sensor, path in RAW_FILES.items():

        raw = load_raw_archive(
            sensor=sensor,
            path=path,
            boundary=boundary,
        )

        if not raw.empty:
            raw_frames.append(raw)

    if not raw_frames:
        raise ValueError("No raw Punjab detections were found.")

    raw_df = pd.concat(
        raw_frames,
        ignore_index=True,
    )

# Preserve mixed sensor confidence values consistently.
# MODIS uses numeric confidence; VIIRS uses categorical labels.
    raw_df["confidence"] = raw_df["confidence"].astype("string")

    raw_df.to_parquet(
    OUTPUT_DIR / "raw_punjab_archive.parquet",
    index=False,
)

    # --------------------------------------------------------
    # 2. Load processed SQH dataset
    # --------------------------------------------------------

    print("\nLoading processed SQH dataset...")

    sqh = pd.read_parquet(SQH_FILE)

    sqh = sqh.loc[
        sqh["sensor"].isin(
            ["MODIS_Terra", "VIIRS_SNPP"]
        )
    ].copy()

    sqh["acq_date"] = pd.to_datetime(
        sqh["acq_date"],
        errors="coerce",
    )

    sqh["frp"] = pd.to_numeric(
        sqh["frp"],
        errors="coerce",
    )

    sqh["year"] = sqh["acq_date"].dt.year
    sqh["month"] = sqh["acq_date"].dt.to_period("M").astype(str)

    # --------------------------------------------------------
    # 3. Version distribution
    # --------------------------------------------------------

    version_summary = (
        raw_df.groupby(
            ["sensor", "version"],
            dropna=False,
        )
        .agg(
            detections=("acq_date", "size"),
            first_date=("acq_date", "min"),
            last_date=("acq_date", "max"),
        )
        .reset_index()
    )

    version_summary.to_csv(
        TABLE_DIR / "raw_version_summary.csv",
        index=False,
    )

    # --------------------------------------------------------
    # 4. Yearly comparison
    # --------------------------------------------------------

    raw_yearly = summarize_records(
        raw_df,
        "raw_archive",
    )

    sqh_yearly = summarize_records(
        sqh,
        "processed_sqh",
    )

    yearly = pd.concat(
        [raw_yearly, sqh_yearly],
        ignore_index=True,
    )

    yearly.to_csv(
        TABLE_DIR / "yearly_raw_vs_sqh.csv",
        index=False,
    )

    # --------------------------------------------------------
    # 5. Monthly comparison
    # --------------------------------------------------------

    raw_monthly = (
        raw_df.groupby(
            ["sensor", "month"],
        )
        .agg(
            detections=("acq_date", "size"),
            detection_dates=("acq_date", "nunique"),
            frp_sum=("frp", "sum"),
        )
        .reset_index()
    )

    raw_monthly["source"] = "raw_archive"

    sqh_monthly = (
        sqh.groupby(
            ["sensor", "month"],
        )
        .agg(
            detections=("acq_date", "size"),
            detection_dates=("acq_date", "nunique"),
            frp_sum=("frp", "sum"),
        )
        .reset_index()
    )

    sqh_monthly["source"] = "processed_sqh"

    monthly = pd.concat(
        [raw_monthly, sqh_monthly],
        ignore_index=True,
    )

    monthly.to_csv(
        TABLE_DIR / "monthly_raw_vs_sqh.csv",
        index=False,
    )

    # --------------------------------------------------------
    # 6. Day/night distribution
    # --------------------------------------------------------

    if "daynight" in raw_df.columns:

        daynight = (
            raw_df.groupby(
                ["sensor", "year", "daynight"],
                dropna=False,
            )
            .size()
            .reset_index(name="detections")
        )

        daynight.to_csv(
            TABLE_DIR / "raw_daynight_yearly.csv",
            index=False,
        )

    # --------------------------------------------------------
    # 7. Basic QA
    # --------------------------------------------------------

    qa = {
        "raw_punjab_rows": int(len(raw_df)),
        "sqh_rows": int(len(sqh)),
        "raw_sensor_counts": {
            str(k): int(v)
            for k, v in raw_df["sensor"].value_counts().items()
        },
        "sqh_sensor_counts": {
            str(k): int(v)
            for k, v in sqh["sensor"].value_counts().items()
        },
        "raw_date_range": [
            str(raw_df["acq_date"].min()),
            str(raw_df["acq_date"].max()),
        ],
        "sqh_date_range": [
            str(sqh["acq_date"].min()),
            str(sqh["acq_date"].max()),
        ],
        "interpretation_warning": (
            "Raw archive and SQH counts may differ because of "
            "preprocessing, filtering, source snapshots, or "
            "download cutoffs. Count differences alone do not "
            "establish missing observations or sensor coverage."
        ),
    }

    with open(
        OUTPUT_DIR / "sensor_consistency_qa.json",
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            qa,
            f,
            indent=4,
        )

    # --------------------------------------------------------
    # 8. Print summary
    # --------------------------------------------------------

    print("\n" + "=" * 65)
    print("AUDIT COMPLETE")
    print("=" * 65)

    print("\nRaw Punjab detections:")
    print(raw_df["sensor"].value_counts().to_string())

    print("\nProcessed SQH detections:")
    print(sqh["sensor"].value_counts().to_string())

    print("\nRaw version summary:")
    print(version_summary.to_string(index=False))

    print("\nYearly raw vs SQH:")
    print(
        yearly.sort_values(
            ["sensor", "year", "source"]
        ).to_string(index=False)
    )

    print("\nOutputs saved to:")
    print(OUTPUT_DIR)


if __name__ == "__main__":
    main()