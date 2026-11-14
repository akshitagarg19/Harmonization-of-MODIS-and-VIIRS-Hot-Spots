from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

INPUT = (
    ROOT
    / "data"
    / "processed"
    / "calibration"
    / "modis_aqua_viirs_snpp_pairs.parquet"
)

OUTPUT = ROOT / "outputs" / "aqua_snpp_monthly_ratio.csv"


def main():

    print("Loading Aqua-SNPP overlap pairs...")

    df = pd.read_parquet(INPUT)

    required_columns = [
        "week_start",
        "daynight",
        "modis_detections",
        "viirs_detections",
    ]

    missing = [
        col for col in required_columns
        if col not in df.columns
    ]

    if missing:
        raise ValueError(f"Missing columns: {missing}")

    df["week_start"] = pd.to_datetime(df["week_start"])

    df["modis_detections"] = pd.to_numeric(
        df["modis_detections"], errors="coerce"
    ).fillna(0)

    df["viirs_detections"] = pd.to_numeric(
        df["viirs_detections"], errors="coerce"
    ).fillna(0)

    # Daytime observations only
    df = df[df["daynight"] == "D"].copy()

    # --------------------------------------------------
    # STEP 1: Aggregate all Punjab grid cells by week
    # --------------------------------------------------

    weekly = (
        df.groupby("week_start", as_index=False)
        .agg(
            modis_total=("modis_detections", "sum"),
            viirs_total=("viirs_detections", "sum"),
        )
    )

    weekly["modis_positive"] = weekly["modis_total"] > 0
    weekly["viirs_positive"] = weekly["viirs_total"] > 0

    # --------------------------------------------------
    # STEP 2: Assign calendar year and month
    # --------------------------------------------------

    weekly["year"] = weekly["week_start"].dt.year
    weekly["month"] = weekly["week_start"].dt.month

    # --------------------------------------------------
    # STEP 3: Monthly regional summary
    # --------------------------------------------------

    monthly = (
        weekly.groupby(["year", "month"], as_index=False)
        .agg(
            weeks=("week_start", "nunique"),
            modis_total=("modis_total", "sum"),
            viirs_total=("viirs_total", "sum"),
            modis_positive_weeks=("modis_positive", "sum"),
            viirs_positive_weeks=("viirs_positive", "sum"),
        )
    )

    monthly["both_positive_weeks"] = (
        weekly.assign(
            both_positive=(
                weekly["modis_positive"]
                & weekly["viirs_positive"]
            )
        )
        .groupby(["year", "month"])["both_positive"]
        .sum()
        .values
    )

    monthly["ratio"] = (
        monthly["viirs_total"]
        / monthly["modis_total"].replace(0, float("nan"))
    )

    monthly["ratio"] = monthly["ratio"].round(3)

    # --------------------------------------------------
    # STEP 4: Save detailed results
    # --------------------------------------------------

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    monthly.to_csv(OUTPUT, index=False)

    print("\nMonthly diagnostic saved:")
    print(OUTPUT)

    # --------------------------------------------------
    # STEP 5: Compare monthly behaviour across years
    # --------------------------------------------------

    summary = (
        monthly[monthly["ratio"].notna()]
        .groupby("month")
        .agg(
            years=("year", "nunique"),
            mean_ratio=("ratio", "mean"),
            median_ratio=("ratio", "median"),
            min_ratio=("ratio", "min"),
            max_ratio=("ratio", "max"),
        )
        .round(2)
    )

    print("\nMONTH-WISE RATIO STABILITY")
    print(summary.to_string())

    print("\nYEAR-WISE MONTHLY RESULTS")

    print(
        monthly.to_string(index=False)
    )


if __name__ == "__main__":
    main()