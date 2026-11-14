"""
Punjab Fire Calendar
--------------------
Generate a clipped 1 km x 1 km grid for SQH (Stratified Quantile
Harmonization).

Important:
- Uses the existing Punjab district boundary GeoJSON.
- Dissolves the 22 districts into one Punjab state boundary.
- Projects the boundary to EPSG:32643 (UTM Zone 43N).
- Generates a globally aligned 1 km grid.
- Clips grid cells to the actual Punjab boundary.
- Preserves the existing 0.25-degree grid and its grid_id.
- Does not modify hotspots_clean.parquet.
- Runs QA before saving final outputs.

Outputs:
    data/processed/sqh/punjab_boundary.geojson
    data/processed/sqh/punjab_1km_grid.parquet
    outputs/sqh/grid_qa.json
"""

from pathlib import Path
import json
import math
import sys

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import box
from shapely.ops import unary_union


# ============================================================
# 1. PROJECT PATHS AND SETTINGS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

BOUNDARY_FILE = (
    PROJECT_ROOT
    / "data"
    / "boundaries"
    / "india_districts.geojson"
    / "district_nwic.GeoJSON"
)

PROCESSED_DIR = PROJECT_ROOT / "data" / "processed" / "sqh"
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "sqh"

BOUNDARY_OUTPUT = PROCESSED_DIR / "punjab_boundary.geojson"
GRID_OUTPUT = PROCESSED_DIR / "punjab_1km_grid.parquet"
QA_OUTPUT = OUTPUT_DIR / "grid_qa.json"

SOURCE_CRS = "EPSG:7755"
GRID_CRS = "EPSG:32643"
OUTPUT_CRS = "EPSG:4326"

CELL_SIZE_METRES = 1000

# Ignore extremely tiny geometry fragments caused by clipping.
MIN_CELL_AREA_M2 = 0.01

# Tolerance for checking whether grid cells extend outside Punjab.
OUTSIDE_AREA_TOLERANCE_M2 = 0.01

# Tolerance for checking overlapping cell areas.
OVERLAP_AREA_TOLERANCE_M2 = 0.01

# Relative tolerance for total grid area vs Punjab boundary area.
AREA_RELATIVE_TOLERANCE = 1e-8


# ============================================================
# 2. HELPER FUNCTIONS
# ============================================================

def print_section(message):
    print("\n" + "=" * 65)
    print(message)
    print("=" * 65)


def ensure_directories():
    """Create output directories if they do not exist."""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_punjab_boundary():
    """
    Load Punjab districts, validate geometries, and dissolve
    them into one state-level polygon.
    """

    print_section("[1/6] LOADING PUNJAB DISTRICTS")

    if not BOUNDARY_FILE.exists():
        raise FileNotFoundError(
            f"Boundary file not found:\n{BOUNDARY_FILE}"
        )

    print(f"Boundary file: {BOUNDARY_FILE}")

    # Read only Punjab features to avoid loading the entire
    # 168 MB national dataset unnecessarily.
    try:
        districts = gpd.read_file(
            BOUNDARY_FILE,
            where="state_name = 'Punjab'"
        )
    except Exception as exc:
        raise RuntimeError(
            "Could not read Punjab features using the GeoJSON "
            "filter. Check the boundary file and its state_name field."
        ) from exc

    if districts.empty:
        raise ValueError(
            "No Punjab districts were found. "
            "Check the state_name field in the boundary file."
        )

    if districts.crs is None:
        raise ValueError("Boundary dataset has no CRS.")

    print(f"District count: {len(districts)}")
    print(f"Source CRS: {districts.crs}")

    # Repair invalid district geometries if necessary.
    print("\nChecking district geometries...")

    invalid_before = int((~districts.geometry.is_valid).sum())
    empty_before = int(districts.geometry.is_empty.sum())

    print(f"Invalid before repair: {invalid_before}")
    print(f"Empty geometries: {empty_before}")

    districts = districts[
        districts.geometry.notna()
        & ~districts.geometry.is_empty
    ].copy()

    if districts.empty:
        raise ValueError("No usable district geometries remain.")

    if invalid_before > 0:
        districts.geometry = districts.geometry.make_valid()

    invalid_after = int((~districts.geometry.is_valid).sum())

    if invalid_after > 0:
        raise RuntimeError(
            f"{invalid_after} district geometries remain invalid."
        )

    # Dissolve all Punjab districts into one state geometry.
    print("\nDissolving districts...")

    punjab_geometry = unary_union(districts.geometry.tolist())

    if punjab_geometry.is_empty:
        raise ValueError("Dissolved Punjab geometry is empty.")

    if not punjab_geometry.is_valid:
        punjab_geometry = shapely.make_valid(punjab_geometry)

    if not punjab_geometry.is_valid:
        raise RuntimeError(
            "Punjab geometry is invalid even after repair."
        )

    # Create GeoDataFrame in source CRS.
    boundary = gpd.GeoDataFrame(
        {"state_name": ["Punjab"]},
        geometry=[punjab_geometry],
        crs=districts.crs
    )

    # Project to UTM Zone 43N.
    boundary = boundary.to_crs(GRID_CRS)

    polygon = boundary.geometry.iloc[0]

    boundary_area_km2 = polygon.area / 1_000_000

    print(f"Target CRS: {GRID_CRS}")
    print(f"Boundary geometry type: {polygon.geom_type}")
    print(f"Punjab area: {boundary_area_km2:,.3f} km²")

    return boundary, polygon


# ============================================================
# 3. GENERATE AND CLIP THE 1 KM GRID
# ============================================================

def generate_grid(polygon):
    """
    Generate a globally aligned 1 km grid and clip it to Punjab.

    IDs are based on the 1 km grid's row and column indices.
    The grid origin is aligned to multiples of 1000 metres
    in EPSG:32643.
    """

    print_section("[2/6] GENERATING 1 KM GRID")

    min_x, min_y, max_x, max_y = polygon.bounds

    # Align the grid to multiples of CELL_SIZE_METRES.
    min_col = math.floor(min_x / CELL_SIZE_METRES)
    max_col = math.ceil(max_x / CELL_SIZE_METRES)

    min_row = math.floor(min_y / CELL_SIZE_METRES)
    max_row = math.ceil(max_y / CELL_SIZE_METRES)

    print("Projected Punjab bounds:")
    print(f"  X: {min_x:.3f} to {max_x:.3f}")
    print(f"  Y: {min_y:.3f} to {max_y:.3f}")

    print("\nGrid settings:")
    print(f"  Cell size: {CELL_SIZE_METRES} metres")
    print(f"  CRS: {GRID_CRS}")
    print(f"  Column range: {min_col} to {max_col - 1}")
    print(f"  Row range: {min_row} to {max_row - 1}")

    columns = np.arange(min_col, max_col, dtype=np.int64)
    rows = np.arange(min_row, max_row, dtype=np.int64)

    col_grid, row_grid = np.meshgrid(columns, rows)

    col_indices = col_grid.ravel()
    row_indices = row_grid.ravel()

    x_min = col_indices * CELL_SIZE_METRES
    y_min = row_indices * CELL_SIZE_METRES

    x_max = x_min + CELL_SIZE_METRES
    y_max = y_min + CELL_SIZE_METRES

    print("\nCreating candidate grid cells...")

    candidate_boxes = shapely.box(
        x_min,
        y_min,
        x_max,
        y_max
    )

    print(f"Candidate cells: {len(candidate_boxes):,}")

    # Clip candidate squares to the actual Punjab geometry.
    print("Clipping cells to Punjab boundary...")

    clipped_geometries = shapely.intersection(
        candidate_boxes,
        polygon
    )

    clipped_areas = shapely.area(clipped_geometries)

    # Remove empty and extremely small fragments.
    keep = (
        ~shapely.is_empty(clipped_geometries)
        & (clipped_areas > MIN_CELL_AREA_M2)
    )

    clipped_geometries = clipped_geometries[keep]
    kept_rows = row_indices[keep]
    kept_cols = col_indices[keep]

    clipped_areas = clipped_areas[keep]

    print(f"Retained cells: {len(clipped_geometries):,}")

    if len(clipped_geometries) == 0:
        raise RuntimeError("No grid cells were generated.")

    # Stable IDs derived from the aligned grid indices.
    cell_ids = [
        f"PB43N_{row}_{col}"
        for row, col in zip(kept_rows, kept_cols)
    ]

    grid = gpd.GeoDataFrame(
        {
            "sqh_cell_id": cell_ids,
            "grid_row": kept_rows,
            "grid_col": kept_cols,
            "cell_area_m2": clipped_areas,
            "cell_area_km2": clipped_areas / 1_000_000,
        },
        geometry=clipped_geometries,
        crs=GRID_CRS
    )

    # Calculate projected centroids.
    print("\nCalculating cell centroids...")

    centroids = grid.geometry.centroid

    grid["centroid_x"] = centroids.x
    grid["centroid_y"] = centroids.y

    # Also store centroid coordinates in WGS84.
    centroid_gdf = gpd.GeoDataFrame(
        geometry=centroids,
        crs=GRID_CRS
    ).to_crs(OUTPUT_CRS)

    grid["centroid_lon"] = centroid_gdf.geometry.x
    grid["centroid_lat"] = centroid_gdf.geometry.y

    return grid


# ============================================================
# 4. GRID QUALITY ASSURANCE
# ============================================================

def calculate_outside_area(grid, polygon):
    """
    Calculate actual area of every grid cell outside Punjab.

    This is more reliable than covered_by() for this QA check.
    """

    differences = shapely.difference(
        grid.geometry.array,
        polygon
    )

    outside_areas = shapely.area(differences)

    outside_count = int(
        (outside_areas > OUTSIDE_AREA_TOLERANCE_M2).sum()
    )

    maximum_outside_area = float(
        outside_areas.max()
    )

    total_outside_area = float(
        outside_areas.sum()
    )

    return (
        outside_count,
        maximum_outside_area,
        total_outside_area
    )


def calculate_overlap_area(grid):
    """
    Check for positive-area overlaps between grid cells.

    Cells that only touch along an edge or corner are not
    considered overlapping.

    Uses the spatial index to avoid comparing every cell
    against every other cell.
    """

    print("\nChecking cell overlaps...")

    spatial_index = grid.sindex

    # Query intersecting candidate pairs.
    # The spatial index returns pairs of positional indices.
    pairs = spatial_index.query(
        grid.geometry.array,
        predicate="intersects"
    )

    if pairs.size == 0:
        return 0.0, 0

    left_indices = pairs[0]
    right_indices = pairs[1]

    # Remove self-pairs and duplicate pair directions.
    unique_pairs = left_indices < right_indices

    left_indices = left_indices[unique_pairs]
    right_indices = right_indices[unique_pairs]

    if len(left_indices) == 0:
        return 0.0, 0

    print(
        f"Potential intersecting cell pairs: "
        f"{len(left_indices):,}"
    )

    # Calculate actual intersection areas.
    intersections = shapely.intersection(
        grid.geometry.array.take(left_indices),
        grid.geometry.array.take(right_indices)
    )

    intersection_areas = shapely.area(intersections)

    positive_overlaps = (
        intersection_areas > OVERLAP_AREA_TOLERANCE_M2
    )

    overlapping_area_m2 = float(
        intersection_areas[positive_overlaps].sum()
    )

    overlapping_pair_count = int(
        positive_overlaps.sum()
    )

    return overlapping_area_m2, overlapping_pair_count


def run_grid_qa(grid, polygon):
    """
    Run all grid validation checks.
    """

    print_section("[3/6] RUNNING GRID QUALITY ASSURANCE")

    invalid_count = int(
        (~grid.geometry.is_valid).sum()
    )

    empty_count = int(
        grid.geometry.is_empty.sum()
    )

    missing_geometry_count = int(
        grid.geometry.isna().sum()
    )

    duplicate_ids = int(
        grid["sqh_cell_id"].duplicated().sum()
    )

    null_ids = int(
        grid["sqh_cell_id"].isna().sum()
    )

    # Actual outside-area check.
    (
        outside_count,
        maximum_outside_area,
        total_outside_area
    ) = calculate_outside_area(grid, polygon)

    # Pairwise overlap check.
    (
        overlapping_area_m2,
        overlapping_pair_count
    ) = calculate_overlap_area(grid)

    # Compare total clipped grid area against Punjab area.
    grid_area_m2 = float(
        grid.geometry.area.sum()
    )

    boundary_area_m2 = float(
        polygon.area
    )

    area_difference_m2 = abs(
        grid_area_m2 - boundary_area_m2
    )

    relative_area_error = (
        area_difference_m2 / boundary_area_m2
        if boundary_area_m2 > 0
        else float("inf")
    )

    # Check whether cell areas are sensible.
    maximum_cell_area = float(
        grid["cell_area_m2"].max()
    )

    minimum_cell_area = float(
        grid["cell_area_m2"].min()
    )

    cells_larger_than_1km2 = int(
        (
            grid["cell_area_m2"]
            > CELL_SIZE_METRES ** 2 + 0.01
        ).sum()
    )

    # All checks must pass.
    validation_passed = (
        invalid_count == 0
        and empty_count == 0
        and missing_geometry_count == 0
        and duplicate_ids == 0
        and null_ids == 0
        and outside_count == 0
        and overlapping_pair_count == 0
        and overlapping_area_m2
        <= OVERLAP_AREA_TOLERANCE_M2
        and relative_area_error
        <= AREA_RELATIVE_TOLERANCE
        and cells_larger_than_1km2 == 0
    )

    report = {
        "project": "Punjab Fire Calendar",
        "grid_type": "SQH 1 km clipped grid",
        "grid_crs": GRID_CRS,
        "output_crs": OUTPUT_CRS,
        "cell_size_metres": CELL_SIZE_METRES,

        "grid_cells": int(len(grid)),

        "boundary_area_km2": (
            boundary_area_m2 / 1_000_000
        ),

        "grid_area_km2": (
            grid_area_m2 / 1_000_000
        ),

        "area_difference_m2": area_difference_m2,
        "relative_area_error": relative_area_error,

        "invalid_geometries": invalid_count,
        "empty_geometries": empty_count,
        "missing_geometries": missing_geometry_count,

        "duplicate_ids": duplicate_ids,
        "null_ids": null_ids,

        "cells_outside_boundary": outside_count,
        "maximum_outside_area_m2": maximum_outside_area,
        "total_outside_area_m2": total_outside_area,

        "overlapping_cell_pairs": overlapping_pair_count,
        "overlapping_area_m2": overlapping_area_m2,

        "minimum_cell_area_m2": minimum_cell_area,
        "maximum_cell_area_m2": maximum_cell_area,
        "cells_larger_than_1km2": cells_larger_than_1km2,

        "validation_passed": bool(validation_passed)
    }

    print("\nGRID QA RESULTS")
    print("-" * 45)

    print(f"Grid cells: {len(grid):,}")
    print(f"Invalid geometries: {invalid_count}")
    print(f"Empty geometries: {empty_count}")
    print(f"Missing geometries: {missing_geometry_count}")

    print(f"Duplicate IDs: {duplicate_ids}")
    print(f"Null IDs: {null_ids}")

    print(f"Cells outside Punjab: {outside_count}")
    print(
        "Maximum outside area: "
        f"{maximum_outside_area:.10f} m²"
    )
    print(
        "Total outside area: "
        f"{total_outside_area:.10f} m²"
    )

    print(
        f"Overlapping cell pairs: {overlapping_pair_count}"
    )
    print(
        f"Overlapping area: {overlapping_area_m2:.10f} m²"
    )

    print(
        f"Punjab boundary area: "
        f"{boundary_area_m2 / 1_000_000:,.6f} km²"
    )
    print(
        f"Grid area: "
        f"{grid_area_m2 / 1_000_000:,.6f} km²"
    )

    print(f"Area difference: {area_difference_m2:.10f} m²")
    print(f"Relative area error: {relative_area_error:.12f}")

    print(
        f"Smallest cell: {minimum_cell_area:.3f} m²"
    )
    print(
        f"Largest cell: {maximum_cell_area:.3f} m²"
    )

    print("-" * 45)

    print(
        "VALIDATION:",
        "PASSED" if validation_passed else "FAILED"
    )

    return report


# ============================================================
# 5. SAVE OUTPUTS
# ============================================================

def save_outputs(boundary, grid, report):
    """
    Save the boundary, grid and QA report.

    This function is called only after QA passes.
    """

    print_section("[4/6] SAVING OUTPUTS")

    # Save boundary in WGS84 for easy GIS visualization.
    boundary_wgs84 = boundary.to_crs(OUTPUT_CRS)

    boundary_wgs84.to_file(
        BOUNDARY_OUTPUT,
        driver="GeoJSON"
    )

    print(f"Boundary saved:\n{BOUNDARY_OUTPUT}")

    # Save grid in EPSG:32643.
    grid.to_parquet(GRID_OUTPUT, index=False)

    print(f"\nGrid saved:\n{GRID_OUTPUT}")

    # Save QA report.
    with open(QA_OUTPUT, "w", encoding="utf-8") as file:
        json.dump(
            report,
            file,
            indent=4,
            ensure_ascii=False
        )

    print(f"\nQA report saved:\n{QA_OUTPUT}")


# ============================================================
# 6. MAIN
# ============================================================

def main():

    print("\n")
    print("#" * 65)
    print("PUNJAB FIRE CALENDAR - SQH GRID GENERATION")
    print("#" * 65)

    ensure_directories()

    # Step 1: Load and dissolve Punjab boundary.
    boundary, polygon = load_punjab_boundary()

    # Step 2: Generate and clip 1 km cells.
    grid = generate_grid(polygon)

    # Step 3: Run QA.
    report = run_grid_qa(grid, polygon)

    # Step 4: Save QA report even if validation fails.
    # This allows inspection of the failure.
    with open(QA_OUTPUT, "w", encoding="utf-8") as file:
        json.dump(
            report,
            file,
            indent=4,
            ensure_ascii=False
        )

    print(f"\nQA report written to:\n{QA_OUTPUT}")

    # Never save the final grid if QA fails.
    if not report["validation_passed"]:
        raise RuntimeError(
            "\nSQH GRID QA FAILED.\n"
            "The final boundary and grid outputs were not saved.\n"
            "Inspect outputs/sqh/grid_qa.json before proceeding."
        )

    # Step 5: Save final outputs.
    save_outputs(boundary, grid, report)

    print_section("[6/6] GRID GENERATION COMPLETE")

    print("SQH grid successfully generated.")
    print(f"Total cells: {len(grid):,}")
    print(f"CRS: {GRID_CRS}")
    print(f"Cell size: {CELL_SIZE_METRES} m")
    print("\nExisting hotspots_clean.parquet was not modified.")
    print("Existing 0.25-degree grid was not modified.")

    print("\nFinal files:")
    print(f"1. {BOUNDARY_OUTPUT}")
    print(f"2. {GRID_OUTPUT}")
    print(f"3. {QA_OUTPUT}")


if __name__ == "__main__":
    try:
        main()

    except Exception as error:
        print("\nERROR:")
        print(error)
        sys.exit(1)