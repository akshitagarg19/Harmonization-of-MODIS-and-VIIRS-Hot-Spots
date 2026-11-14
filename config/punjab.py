PROJECT_NAME = "Punjab Fire Calendar"

PUNJAB_BBOX = {
    "min_lat": 29.5,
    "max_lat": 32.5,
    "min_lon": 73.8,
    "max_lon": 77.0,
}

START_YEAR = 2000

GRID_SIZE = 0.25

TIMEZONE = "Asia/Kolkata"

SENSORS = [
    "MODIS_Terra",
    "MODIS_Aqua",
    "VIIRS_SNPP",
    "VIIRS_NOAA20",
    "VIIRS_NOAA21",
]

OUTPUT_FORMAT = "parquet"