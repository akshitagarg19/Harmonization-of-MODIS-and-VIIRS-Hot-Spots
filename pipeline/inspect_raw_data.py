from pathlib import Path
import pandas as pd

RAW_DIR = Path("data/raw")
OUTPUT_DIR = Path("outputs")

BBOX = {
    "min_lat": 29.5,
    "max_lat": 32.5,
    "min_lon": 73.8,
    "max_lon": 77.0,
}

FILES = {
    "MODIS": RAW_DIR / "MODIS/DL_FIRE_M-C61_845709/fire_archive_M-C61_845709.csv",
    "VIIRS_SNPP": RAW_DIR / "VIIRS/SNPP/DL_FIRE_SV-C2_845715/fire_archive_SV-C2_845715.csv",
    "VIIRS_NOAA20": RAW_DIR / "VIIRS/NOAA_20/DL_FIRE_J1V-C2_845729/fire_archive_J1V-C2_845729.csv",
    "VIIRS_NOAA21": RAW_DIR / "VIIRS/NOAA_21/DL_FIRE_J2V-C2_845728/fire_archive_J2V-C2_845728.csv",
}


def inspect_file(product, path):

    print(f"\nInspecting {product}...")

    yearly_counts = {}
    sensor_counts = {}
    total_rows = 0
    outside_bbox = 0

    min_lat = float("inf")
    max_lat = float("-inf")
    min_lon = float("inf")
    max_lon = float("-inf")

    min_date = None
    max_date = None

    for chunk in pd.read_csv(path, chunksize=100_000):

        total_rows += len(chunk)

        chunk["acq_date"] = pd.to_datetime(
            chunk["acq_date"], errors="coerce"
        )

        chunk["year"] = chunk["acq_date"].dt.year

        yearly = chunk.groupby("year").size()

        for year, count in yearly.items():
            yearly_counts[year] = (
                yearly_counts.get(year, 0) + count
            )

        if "satellite" in chunk.columns:

            sensors = chunk.groupby("satellite").size()

            for sensor, count in sensors.items():
                sensor_counts[sensor] = (
                    sensor_counts.get(sensor, 0) + count
                )

        min_date = min(
            min_date,
            chunk["acq_date"].min()
        ) if min_date is not None else chunk["acq_date"].min()

        max_date = max(
            max_date,
            chunk["acq_date"].max()
        ) if max_date is not None else chunk["acq_date"].max()

        min_lat = min(min_lat, chunk["latitude"].min())
        max_lat = max(max_lat, chunk["latitude"].max())

        min_lon = min(min_lon, chunk["longitude"].min())
        max_lon = max(max_lon, chunk["longitude"].max())

        outside = (
            (chunk["latitude"] < BBOX["min_lat"]) |
            (chunk["latitude"] > BBOX["max_lat"]) |
            (chunk["longitude"] < BBOX["min_lon"]) |
            (chunk["longitude"] > BBOX["max_lon"])
        )

        outside_bbox += int(outside.sum())

    print(f"Rows: {total_rows:,}")
    print(f"Date range: {min_date} to {max_date}")
    print(f"Satellite values: {sensor_counts}")
    print(f"Outside bounding box: {outside_bbox:,}")

    print(
        f"Latitude range: {min_lat:.5f} to {max_lat:.5f}"
    )

    print(
        f"Longitude range: {min_lon:.5f} to {max_lon:.5f}"
    )

    print(f"Yearly counts: {yearly_counts}")

    return {
        "product": product,
        "total_rows": total_rows,
        "outside_bbox": outside_bbox,
        "first_date": min_date,
        "last_date": max_date,
        "yearly_counts": yearly_counts,
    }


def main():

    OUTPUT_DIR.mkdir(exist_ok=True)

    all_yearly = []
    spatial_results = []

    for product, path in FILES.items():

        if not path.exists():
            print(f"ERROR: Missing file: {path}")
            continue

        result = inspect_file(product, path)

        spatial_results.append({
            "product": product,
            "total_rows": result["total_rows"],
            "outside_bbox": result["outside_bbox"],
            "first_date": result["first_date"],
            "last_date": result["last_date"],
        })

        for year, count in result["yearly_counts"].items():

            all_yearly.append({
                "product": product,
                "year": year,
                "detections": count,
            })

    pd.DataFrame(all_yearly).to_csv(
        OUTPUT_DIR / "raw_yearly_counts.csv",
        index=False
    )

    pd.DataFrame(spatial_results).to_csv(
        OUTPUT_DIR / "raw_spatial_qa.csv",
        index=False
    )

    print("\nSaved:")
    print("outputs/raw_yearly_counts.csv")
    print("outputs/raw_spatial_qa.csv")


if __name__ == "__main__":
    main()