from pathlib import Path
from collections import defaultdict

import pandas as pd
import geopandas as gpd
import numpy as np
import matplotlib.pyplot as plt
import pyarrow as pa
import pyarrow.parquet as pq
import shapely


# --------------------------------------------------
# PATHS
# --------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]

RAW_DIR = ROOT / "data" / "raw"
BOUNDARY_FILE = ROOT / "data" / "boundaries" / "punjab_state_boundary.geojson"

PROCESSED_DIR = ROOT / "data" / "processed"
OUTPUT_DIR = ROOT / "outputs"

PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------
# INPUT ARCHIVES
# --------------------------------------------------

FILES = {
    "MODIS": (
        RAW_DIR / "MODIS/DL_FIRE_M-C61_845709/"
        "fire_archive_M-C61_845709.csv"
    ),
    "VIIRS_SNPP": (
        RAW_DIR / "VIIRS/SNPP/DL_FIRE_SV-C2_845715/"
        "fire_archive_SV-C2_845715.csv"
    ),
    "VIIRS_NOAA20": (
        RAW_DIR / "VIIRS/NOAA_20/DL_FIRE_J1V-C2_845729/"
        "fire_archive_J1V-C2_845729.csv"
    ),
    "VIIRS_NOAA21": (
        RAW_DIR / "VIIRS/NOAA_21/DL_FIRE_J2V-C2_845728/"
        "fire_archive_J2V-C2_845728.csv"
    ),
}

OUTPUT_PARQUET = PROCESSED_DIR / "hotspots_punjab_clipped.parquet"
YEARLY_COUNTS = OUTPUT_DIR / "punjab_sensor_yearly_counts.csv"
YEARLY_PLOT = OUTPUT_DIR / "punjab_sensor_yearly_counts.png"
QA_REPORT = OUTPUT_DIR / "clipping_qa_report.csv"

CHUNK_SIZE = 100_000


# --------------------------------------------------
# COMMON OUTPUT SCHEMA
# --------------------------------------------------

SCHEMA = pa.schema([
    ("sensor", pa.string()),
    ("source_product", pa.string()),
    ("latitude", pa.float64()),
    ("longitude", pa.float64()),
    ("acq_date", pa.string()),
    ("year", pa.int32()),
    ("acq_time", pa.string()),
    ("frp", pa.float64()),
    ("confidence", pa.string()),
    ("daynight", pa.string()),
    ("satellite", pa.string()),
    ("instrument", pa.string()),
    ("brightness", pa.float64()),
    ("bright_ti4", pa.float64()),
    ("bright_ti5", pa.float64()),
    ("bright_t31", pa.float64()),
    ("scan", pa.float64()),
    ("track", pa.float64()),
    ("type", pa.string()),
    ("version", pa.string()),
])


# --------------------------------------------------
# HELPERS
# --------------------------------------------------

def get_polygon():
    boundary = gpd.read_file(BOUNDARY_FILE)

    if boundary.crs is None:
        raise ValueError("Punjab boundary has no CRS.")

    boundary = boundary.to_crs("EPSG:4326")

    if boundary.empty:
        raise ValueError("Punjab boundary file is empty.")

    if not boundary.geometry.is_valid.all():
        raise ValueError("Punjab boundary contains invalid geometry.")

    return boundary.geometry.union_all()


def clip_points(longitudes, latitudes, polygon):
    """
    Vectorised point-in-polygon check.
    Points on the exact boundary are included when supported
    by the installed Shapely version.
    """
    if hasattr(shapely, "intersects_xy"):
        return shapely.intersects_xy(
            polygon, longitudes, latitudes
        )

    return shapely.contains_xy(
        polygon, longitudes, latitudes
    )


def as_string_column(df, column):
    if column in df.columns:
        return df[column].astype("string").fillna(None)

    return pd.Series([None] * len(df), dtype="object")


def as_numeric_column(df, column):
    if column in df.columns:
        return pd.to_numeric(
            df[column], errors="coerce"
        ).astype("float64")

    return pd.Series(
        np.full(len(df), np.nan),
        dtype="float64"
    )


def normalise_chunk(df, source_product, sensor):
    result = pd.DataFrame(index=df.index)

    result["sensor"] = sensor
    result["source_product"] = source_product

    result["latitude"] = as_numeric_column(df, "latitude")
    result["longitude"] = as_numeric_column(df, "longitude")

    dates = pd.to_datetime(
        as_string_column(df, "acq_date"),
        errors="coerce"
    )

    result["acq_date"] = dates.dt.strftime("%Y-%m-%d")
    result["year"] = dates.dt.year.astype("Int32")

    result["acq_time"] = as_string_column(df, "acq_time")
    result["frp"] = as_numeric_column(df, "frp")

    for column in [
        "confidence",
        "daynight",
        "satellite",
        "instrument",
        "type",
        "version",
    ]:
        result[column] = as_string_column(df, column)

    for column in [
        "brightness",
        "bright_ti4",
        "bright_ti5",
        "bright_t31",
        "scan",
        "track",
    ]:
        result[column] = as_numeric_column(df, column)

    return result


# --------------------------------------------------
# MAIN PROCESS
# --------------------------------------------------

def main():

    print("\nLoading Punjab boundary...")
    polygon = get_polygon()
    print("Punjab boundary loaded successfully.")

    print("\nStarting clipping process...")
    print(f"Chunk size: {CHUNK_SIZE:,}")

    yearly_counts = defaultdict(int)
    qa_rows = []

    total_input = 0
    total_clipped = 0
    writer = None

    try:
        for source_product, file_path in FILES.items():

            if not file_path.exists():
                raise FileNotFoundError(
                    f"Missing input file: {file_path}"
                )

            print(f"\nProcessing: {source_product}")
            print(f"File: {file_path.name}")

            product_input = 0
            product_clipped = 0
            product_invalid = 0
            product_unknown_modis = 0

            for chunk_number, chunk in enumerate(
                pd.read_csv(
                    file_path,
                    chunksize=CHUNK_SIZE,
                    low_memory=False
                ),
                start=1
            ):

                product_input += len(chunk)
                total_input += len(chunk)

                # MODIS contains both Terra and Aqua.
                if source_product == "MODIS":

                    satellite_values = (
                        chunk["satellite"]
                        .astype("string")
                        .str.strip()
                        .str.lower()
                    )

                    sensor_values = satellite_values.map({
                        "terra": "MODIS_Terra",
                        "aqua": "MODIS_Aqua",
                    })

                    unknown_mask = sensor_values.isna()
                    product_unknown_modis += int(
                        unknown_mask.sum()
                    )

                    chunk = chunk.loc[~unknown_mask].copy()
                    sensor_values = sensor_values.loc[
                        ~unknown_mask
                    ]

                else:
                    sensor_map = {
                        "VIIRS_SNPP": "VIIRS_SNPP",
                        "VIIRS_NOAA20": "VIIRS_NOAA20",
                        "VIIRS_NOAA21": "VIIRS_NOAA21",
                    }

                    sensor_values = pd.Series(
                        sensor_map[source_product],
                        index=chunk.index
                    )

                if chunk.empty:
                    continue

                # Validate coordinates.
                lat = pd.to_numeric(
                    chunk["latitude"], errors="coerce"
                ).to_numpy(dtype="float64")

                lon = pd.to_numeric(
                    chunk["longitude"], errors="coerce"
                ).to_numpy(dtype="float64")

                valid_coordinates = (
                    np.isfinite(lat)
                    & np.isfinite(lon)
                    & (lat >= -90)
                    & (lat <= 90)
                    & (lon >= -180)
                    & (lon <= 180)
                )

                product_invalid += int(
                    (~valid_coordinates).sum()
                )

                if not valid_coordinates.any():
                    continue

                valid_chunk = chunk.loc[
                    valid_coordinates
                ].copy()

                valid_sensors = sensor_values.loc[
                    valid_chunk.index
                ]

                lat = lat[valid_coordinates]
                lon = lon[valid_coordinates]

                # Clip to the actual Punjab polygon.
                inside = clip_points(lon, lat, polygon)

                if not inside.any():
                    continue

                clipped_raw = valid_chunk.loc[inside].copy()
                clipped_sensors = valid_sensors.loc[
                    clipped_raw.index
                ]

                # Split MODIS into Terra and Aqua.
                for sensor_name in clipped_sensors.unique():

                    sensor_raw = clipped_raw.loc[
                        clipped_sensors == sensor_name
                    ]

                    normalised = normalise_chunk(
                        sensor_raw,
                        source_product,
                        sensor_name
                    )

                    # Drop records with invalid dates or coordinates.
                    normalised = normalised.dropna(
                        subset=[
                            "latitude",
                            "longitude",
                            "acq_date",
                            "year",
                        ]
                    )

                    if normalised.empty:
                        continue

                    normalised["year"] = (
                        normalised["year"].astype("int32")
                    )

                    table = pa.Table.from_pandas(
                        normalised,
                        schema=SCHEMA,
                        preserve_index=False,
                        safe=False
                    )

                    if writer is None:
                        writer = pq.ParquetWriter(
                            OUTPUT_PARQUET,
                            SCHEMA,
                            compression="snappy"
                        )

                    writer.write_table(table)

                    counts = normalised.groupby(
                        "year"
                    ).size()

                    for year, count in counts.items():
                        yearly_counts[
                            (sensor_name, int(year))
                        ] += int(count)

                    written = len(normalised)
                    product_clipped += written
                    total_clipped += written

                if chunk_number % 5 == 0:
                    print(
                        f"  Chunks: {chunk_number} | "
                        f"Read: {product_input:,} | "
                        f"Clipped so far: {product_clipped:,}"
                    )

            qa_rows.append({
                "source_product": source_product,
                "input_rows": product_input,
                "clipped_rows": product_clipped,
                "invalid_coordinate_rows": product_invalid,
                "unknown_modis_satellite_rows": (
                    product_unknown_modis
                ),
            })

            print(
                f"Completed {source_product}: "
                f"{product_clipped:,} rows inside Punjab."
            )

    finally:
        if writer is not None:
            writer.close()

    if total_clipped == 0:
        raise RuntimeError(
            "No records were clipped. Check input files and boundary."
        )

    # --------------------------------------------------
    # SAVE YEARLY COUNTS
    # --------------------------------------------------

    yearly_df = pd.DataFrame([
        {
            "sensor": sensor,
            "year": year,
            "hotspot_count": count,
        }
        for (sensor, year), count in yearly_counts.items()
    ])

    yearly_df = yearly_df.sort_values(
        ["year", "sensor"]
    ).reset_index(drop=True)

    yearly_df.to_csv(YEARLY_COUNTS, index=False)

    # --------------------------------------------------
    # SAVE QA REPORT
    # --------------------------------------------------

    qa_df = pd.DataFrame(qa_rows)
    qa_df.to_csv(QA_REPORT, index=False)

    # --------------------------------------------------
    # YEARLY SENSOR PLOT
    # --------------------------------------------------

    pivot = yearly_df.pivot_table(
        index="year",
        columns="sensor",
        values="hotspot_count",
        aggfunc="sum",
        fill_value=0
    )

    ax = pivot.plot(
        figsize=(13, 7),
        marker="o",
        linewidth=1.8
    )

    ax.set_title(
        "Annual Fire Hotspot Detections in Punjab by Sensor"
    )
    ax.set_xlabel("Year")
    ax.set_ylabel("Number of detections")
    ax.grid(True, alpha=0.3)
    ax.legend(title="Sensor")
    plt.tight_layout()
    plt.savefig(YEARLY_PLOT, dpi=200)
    plt.close()

    # --------------------------------------------------
    # FINAL SUMMARY
    # --------------------------------------------------

    print("\n" + "=" * 55)
    print("PUNJAB CLIPPING COMPLETED")
    print("=" * 55)

    print(f"Total input rows:   {total_input:,}")
    print(f"Total Punjab rows:  {total_clipped:,}")

    print("\nYearly sensor counts:")
    print(
        yearly_df.pivot_table(
            index="sensor",
            columns="year",
            values="hotspot_count",
            aggfunc="sum",
            fill_value=0
        ).to_string()
    )

    print("\nCreated files:")
    print(f"Parquet: {OUTPUT_PARQUET}")
    print(f"Yearly counts: {YEARLY_COUNTS}")
    print(f"Plot: {YEARLY_PLOT}")
    print(f"QA report: {QA_REPORT}")


if __name__ == "__main__":
    main()