from pathlib import Path

import geopandas as gpd


# Project paths
INPUT_FILE = Path(
    "data/boundaries/india_districts.geojson/district_nwic.GeoJSON"
)

OUTPUT_FILE = Path(
    "data/boundaries/punjab_districts.geojson"
)


def main():

    print("Reading national district boundaries...")

    districts = gpd.read_file(INPUT_FILE)

    print("Total national features:", len(districts))

    # Select Punjab only
    punjab = districts[
        (districts["state"] == "PB")
        & (districts["state_name"].str.strip().str.lower() == "punjab")
    ].copy()

    print("\nPunjab districts found:", len(punjab))

    # Keep useful attributes
    columns = [
        "district",
        "dtcode",
        "state",
        "state_name",
        "geometry",
    ]

    punjab = punjab[columns]

    # Check district names
    print("\nDistrict names:")
    for name in sorted(punjab["district"].tolist()):
        print("-", name)

    # Check duplicate district names
    if punjab["district"].duplicated().any():
        raise ValueError("Duplicate district names found!")

    # Check geometry validity
    invalid_count = (~punjab.geometry.is_valid).sum()

    print("\nInvalid geometries:", invalid_count)

    if invalid_count > 0:
        punjab["geometry"] = punjab.geometry.make_valid()

    # Remove empty geometries
    punjab = punjab[
        punjab.geometry.notna()
        & ~punjab.geometry.is_empty
    ].copy()

    # Convert to latitude/longitude coordinates
    punjab = punjab.to_crs("EPSG:4326")

    # Final checks
    print("\nFinal CRS:", punjab.crs)
    print("Final district count:", len(punjab))
    print("All geometries valid:", punjab.geometry.is_valid.all())

    print("\nPunjab bounds:")
    print(punjab.total_bounds)

    # Save
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    punjab.to_file(
        OUTPUT_FILE,
        driver="GeoJSON"
    )

    print("\nSaved successfully:")
    print(OUTPUT_FILE)


if __name__ == "__main__":
    main()