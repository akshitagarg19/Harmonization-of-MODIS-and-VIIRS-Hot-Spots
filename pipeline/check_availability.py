import os
import requests
import pandas as pd

from io import StringIO
from dotenv import load_dotenv


load_dotenv()

MAP_KEY = os.getenv("FIRMS_MAP_KEY")

if not MAP_KEY:
    raise ValueError(
        "FIRMS_MAP_KEY missing. Check your .env file."
    )


URL = (
    f"https://firms.modaps.eosdis.nasa.gov/"
    f"api/data_availability/csv/{MAP_KEY}/all"
)


def check_availability():

    print("\nChecking NASA FIRMS data availability...\n")

    response = requests.get(URL, timeout=60)

    response.raise_for_status()

    df = pd.read_csv(StringIO(response.text))

    required_sensors = [
        "MODIS_SP",
        "VIIRS_SNPP_SP",
        "VIIRS_NOAA20_SP",
        "VIIRS_NOAA21_SP",
    ]

    result = df[
        df["data_id"].isin(required_sensors)
    ].copy()

    result["min_date"] = pd.to_datetime(
        result["min_date"]
    )

    result["max_date"] = pd.to_datetime(
        result["max_date"]
    )

    result = result.sort_values("data_id")

    print("HISTORICAL DATA AVAILABILITY")
    print("=" * 65)

    print(
        result.to_string(index=False)
    )

    os.makedirs("outputs", exist_ok=True)

    result.to_csv(
        "outputs/data_availability.csv",
        index=False
    )

    print("\nSaved: outputs/data_availability.csv")

    missing = set(required_sensors) - set(result["data_id"])

    if missing:
        print("\nWARNING: Missing products:", missing)

    else:
        print("\nAll four standard-processing products found.")


if __name__ == "__main__":
    check_availability()