# ============================================================
# SQH PROJECT CONFIGURATION
# ============================================================

PROJECT_NAME = "Punjab Fire Calendar"

# Only two satellites for the entire project.

SQH_SENSORS = [
    "MODIS_Terra",
    "VIIRS_SNPP",
]

# Common historical comparison period.

OVERLAP_START_DATE = "2012-01-01"

# Spatial configuration.

TARGET_CRS = "EPSG:32643"

CELL_SIZE_METRES = 1000

# Temporal configuration.

TIMEZONE = "Asia/Kolkata"

# Measurements retained independently.

METRICS = [
    "detection_count",
    "active_cells",
    "frp_sum",
]