from pathlib import Path

import numpy as np
import pandas as pd


# --------------------------------------------------
# PATHS AND SETTINGS
# --------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]

CALIBRATION_DIR = ROOT / "data" / "processed" / "calibration"
OUTPUT_DIR = ROOT / "outputs"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TRAIN_END = pd.Timestamp("2024-12-30", tz="UTC")


PAIRS = [
    "modis_aqua_viirs_snpp_pairs.parquet",
    "modis_aqua_viirs_noaa20_pairs.parquet",
    "modis_aqua_viirs_noaa21_pairs.parquet",
    "modis_terra_viirs_snpp_pairs.parquet",
    "modis_terra_viirs_noaa20_pairs.parquet",
    "modis_terra_viirs_noaa21_pairs.parquet",
]


# Possible column names in the overlap datasets.
COLUMN_CANDIDATES = {
    "modis_count": [
        "modis_count",
        "modis_detections",
        "modis_hotspot_count",
    ],
    "viirs_count": [
        "viirs_count",
        "viirs_detections",
        "viirs_hotspot_count",
    ],
    "modis_frp": [
        "modis_frp",
        "modis_frp_sum",
    ],
    "viirs_frp": [
        "viirs_frp",
        "viirs_frp_sum",
    ],
}


def find_column(df, candidates):
    for column in candidates:
        if column in df.columns:
            return column
    return None


# --------------------------------------------------
# MODEL METRICS
# --------------------------------------------------

def calculate_metrics(actual, predicted):

    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)

    errors = predicted - actual

    mae = np.mean(np.abs(errors))
    rmse = np.sqrt(np.mean(errors ** 2))

    denominator = np.sum((actual - np.mean(actual)) ** 2)

    if denominator == 0:
        r2 = np.nan
    else:
        r2 = 1 - np.sum(errors ** 2) / denominator

    return mae, rmse, r2


# --------------------------------------------------
# REGIONAL AGGREGATION
# --------------------------------------------------

def create_regional_data(filename):

    path = CALIBRATION_DIR / filename

    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")

    df = pd.read_parquet(path)

    required = ["week_start", "daynight"]

    for column in required:
        if column not in df.columns:
            raise ValueError(
                f"{filename}: Missing required column '{column}'. "
                f"Available columns: {list(df.columns)}"
            )

    columns = {}

    for name, candidates in COLUMN_CANDIDATES.items():

        found = find_column(df, candidates)

        if found is None:
            raise ValueError(
                f"{filename}: Could not identify {name}. "
                f"Available columns: {list(df.columns)}"
            )

        columns[name] = found

    df["week_start"] = pd.to_datetime(df["week_start"])

    for name, source in columns.items():
        df[name] = pd.to_numeric(df[source], errors="coerce").fillna(0)

    # Aggregate all Punjab grid cells into weekly regional totals.
    regional = (
        df.groupby(["week_start", "daynight"], as_index=False)
        .agg(
            modis_count=("modis_count", "sum"),
            viirs_count=("viirs_count", "sum"),
            modis_frp=("modis_frp", "sum"),
            viirs_frp=("viirs_frp", "sum"),
        )
    )

    return regional


# --------------------------------------------------
# FIT AND VALIDATE MODELS
# --------------------------------------------------

def evaluate_model(df, pair_name, daynight, metric):

    x = df[f"modis_{metric}"].to_numpy(dtype=float)
    y = df[f"viirs_{metric}"].to_numpy(dtype=float)

    dates = df["week_start"]

    train_mask = dates <= TRAIN_END
    val_mask = dates > TRAIN_END

    x_train = x[train_mask]
    y_train = y[train_mask]

    x_val = x[val_mask]
    y_val = y[val_mask]

    train_weeks = len(x_train)
    validation_weeks = len(x_val)

    if train_weeks < 30 or validation_weeks < 10:
        return [
            {
                "pair": pair_name,
                "daynight": daynight,
                "metric": metric,
                "model": "ratio",
                "status": "LOW_SUPPORT",
                "train_weeks": train_weeks,
                "validation_weeks": validation_weeks,
            },
            {
                "pair": pair_name,
                "daynight": daynight,
                "metric": metric,
                "model": "linear",
                "status": "LOW_SUPPORT",
                "train_weeks": train_weeks,
                "validation_weeks": validation_weeks,
            },
        ]

    results = []

    # ----------------------------------------------
    # MODEL 1: RATIO
    # ----------------------------------------------

    denominator = np.sum(x_train ** 2)

    if denominator > 0:

        ratio = np.sum(x_train * y_train) / denominator

        predictions = ratio * x_val

        mae, rmse, r2 = calculate_metrics(y_val, predictions)

        residuals = y_val - predictions

        results.append({
            "pair": pair_name,
            "daynight": daynight,
            "metric": metric,
            "model": "ratio",
            "status": "EVALUATED",
            "train_weeks": train_weeks,
            "validation_weeks": validation_weeks,
            "ratio": ratio,
            "intercept": 0,
            "slope": ratio,
            "validation_MAE": mae,
            "validation_RMSE": rmse,
            "validation_R2": r2,
            "residual_p10": np.percentile(residuals, 10),
            "residual_p90": np.percentile(residuals, 90),
        })

    # ----------------------------------------------
    # MODEL 2: LINEAR REGRESSION
    # VIIRS = intercept + slope * MODIS
    # ----------------------------------------------

    X = np.column_stack([
        np.ones(len(x_train)),
        x_train,
    ])

    intercept, slope = np.linalg.lstsq(
        X, y_train, rcond=None
    )[0]

    predictions = intercept + slope * x_val

    mae, rmse, r2 = calculate_metrics(y_val, predictions)

    residuals = y_val - predictions

    results.append({
        "pair": pair_name,
        "daynight": daynight,
        "metric": metric,
        "model": "linear",
        "status": "EVALUATED",
        "train_weeks": train_weeks,
        "validation_weeks": validation_weeks,
        "ratio": np.nan,
        "intercept": intercept,
        "slope": slope,
        "validation_MAE": mae,
        "validation_RMSE": rmse,
        "validation_R2": r2,
        "residual_p10": np.percentile(residuals, 10),
        "residual_p90": np.percentile(residuals, 90),
    })

    return results


# --------------------------------------------------
# MAIN
# --------------------------------------------------

def main():

    all_results = []

    print("\nREGIONAL CALIBRATION TEST")
    print("=" * 60)

    for filename in PAIRS:

        print(f"\nProcessing: {filename}")

        regional = create_regional_data(filename)

        pair_name = filename.replace("_pairs.parquet", "")

        print(f"Regional weekly rows: {len(regional)}")

        for daynight in ["D", "N"]:

            subset = regional[
                regional["daynight"] == daynight
            ].copy()

            subset = subset.sort_values("week_start")

            if subset.empty:
                print(f"  {daynight}: No observations")
                continue

            print(
                f"  {daynight}: "
                f"{len(subset)} regional weekly observations"
            )

            for metric in ["count", "frp"]:

                results = evaluate_model(
                    subset,
                    pair_name,
                    daynight,
                    metric,
                )

                all_results.extend(results)

    results_df = pd.DataFrame(all_results)

    output_file = OUTPUT_DIR / "regional_calibration_metrics.csv"

    results_df.to_csv(output_file, index=False)

    print("\n" + "=" * 60)
    print("REGIONAL CALIBRATION COMPLETED")
    print("=" * 60)

    print(f"\nSaved results: {output_file}")

    display_columns = [
        "pair",
        "daynight",
        "metric",
        "model",
        "status",
        "train_weeks",
        "validation_weeks",
        "validation_R2",
        "validation_MAE",
        "validation_RMSE",
    ]

    available = [
        col for col in display_columns
        if col in results_df.columns
    ]

    print("\nVALIDATION RESULTS:\n")

    print(
        results_df[available].to_string(index=False)
    )


if __name__ == "__main__":
    main()