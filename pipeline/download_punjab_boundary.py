from pathlib import Path
import geopandas as gpd

INPUT_FILE = Path(
    "data/boundaries/india_adm1_geoboundaries.geojson"
)

OUTPUT_FILE = Path(
    "data/boundaries/punjab_state_boundary.geojson"
)


def main():

    print("Reading India state boundaries...")

    states = gpd.read_file(INPUT_FILE)

    # Find Punjab using its exact state name
    punjab = states[
        states["shapeName"].astype(str).str.strip().str.casefold()
        == "punjab"
    ].copy()

    if len(punjab) != 1:
        raise ValueError(
            f"Expected exactly one Punjab feature, found {len(punjab)}"
        )

    # Check coordinate reference system
    if states.crs is None:
        raise ValueError("Boundary CRS is missing.")

    punjab = punjab.to_crs("EPSG:4326")

    # Validate geometry
    geometry = punjab.geometry.iloc[0]

    print("\nBoundary validation:")
    print("State:", punjab.iloc[0]["shapeName"])
    print("ISO:", punjab.iloc[0]["shapeISO"])
    print("CRS:", punjab.crs)
    print("Geometry type:", geometry.geom_type)
    print("Geometry valid:", geometry.is_valid)
    print("Geometry empty:", geometry.is_empty)
    print("Bounds:", geometry.bounds)

    if geometry.is_empty or not geometry.is_valid:
        raise ValueError("Punjab boundary geometry is invalid.")

    # Save Punjab separately
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    punjab.to_file(
        OUTPUT_FILE,
        driver="GeoJSON"
    )

    # Read it back to verify the saved file
    check = gpd.read_file(OUTPUT_FILE)

    if len(check) != 1:
        raise ValueError("Saved boundary verification failed.")

    print("\nSUCCESS!")
    print("Punjab boundary saved:", OUTPUT_FILE)
    print("Saved features:", len(check))


if __name__ == "__main__":
    main()