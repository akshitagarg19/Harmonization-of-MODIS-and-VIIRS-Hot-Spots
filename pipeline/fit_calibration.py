from pathlib import Path

import numpy as np
import pandas as pd


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

INPUT_DIR = Path("data/processed/calibration")
OUTPUT_DIR = Path("data/processed/calibration")
QA_DIR = Path("outputs")

TRAIN_END = pd.Timestamp("2024-12-30", tz="UTC")

MIN_TRAIN_ROWS = 30
MIN_SHARED_NONZERO = 10

SENSOR_PAIRS = [
    ("MODIS_Aqua", "VIIRS_SNPP"),
    ("MODIS_Aqua", "VIIRS_NOAA20"),
    ("MODIS_Aqua", "VIIRS_NOAA21"),
    ("MODIS_Terra", "VIIRS_SNPP"),
    ("MODIS_Terra", "VIIRS_NOAA20"),
    ("MODIS_Terra", "VIIRS_NOAA21"),
]

METRICS = {
    "detections": (
        "modis_detections",
        "viirs_detections",
    ),
    "frp": (
        "modis_frp_sum",
        "viirs_frp_sum",
    ),
}


# --------------------------------------------------
# MODEL FUNCTIONS
# --------------------------------------------------

def fit_ratio(x, y):

    denominator = np.sum(x ** 2)

    if denominator == 0:
        return None

    return float(np.sum(x * y) / denominator)


def fit_linear(x, y):

    if len(x) < 2 or np.ptp(x) == 0:
        return None

    slope, intercept = np.polyfit(x, y, 1)

    return {
        "slope": float(slope),
        "intercept": float(intercept),
    }


def predict_ratio(x, ratio):

    return ratio * x


def predict_linear(x, model):

    return model["intercept"] + model["slope"] * x


# --------------------------------------------------
# METRICS
# --------------------------------------------------

def calculate_metrics(actual, predicted):

    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)

    residual = actual - predicted

    mae = np.mean(np.abs(residual))
    rmse = np.sqrt(np.mean(residual ** 2))

    ss_res = np.sum(residual ** 2)
    ss_total = np.sum((actual - np.mean(actual)) ** 2)

    if ss_total == 0:
        r2 = np.nan
    else:
        r2 = 1 - ss_res / ss_total

    return {
        "mae": float(mae),
        "rmse": float(rmse),
        "r2": float(r2) if not np.isnan(r2) else np.nan,
        "bias": float(np.mean(predicted - actual)),
    }


# --------------------------------------------------
# FIT AND EVALUATE ONE MODEL
# --------------------------------------------------

def evaluate_metric(
    pairs,
    modis_column,
    viirs_column,
    metric_name,
    modis_sensor,
    viirs_sensor,
    daynight,
):

    train = pairs[
        pairs["week_start"] <= TRAIN_END
    ].copy()

    validation = pairs[
        pairs["week_start"] > TRAIN_END
    ].copy()

    x_train = train[modis_column].to_numpy(dtype=float)
    y_train = train[viirs_column].to_numpy(dtype=float)

    x_val = validation[modis_column].to_numpy(dtype=float)
    y_val = validation[viirs_column].to_numpy(dtype=float)

    shared_train = int(
        ((x_train > 0) & (y_train > 0)).sum()
    )

    shared_val = int(
        ((x_val > 0) & (y_val > 0)).sum()
    )

    base = {
        "modis_sensor": modis_sensor,
        "viirs_sensor": viirs_sensor,
        "daynight": daynight,
        "metric": metric_name,
        "train_rows": len(train),
        "validation_rows": len(validation),
        "train_shared_nonzero": shared_train,
        "validation_shared_nonzero": shared_val,
    }

    # Require enough data to attempt a model.
    if (
        len(train) < MIN_TRAIN_ROWS
        or shared_train < MIN_SHARED_NONZERO
    ):
        print(
            f"  SKIPPED: insufficient training support "
            f"for {metric_name}"
        )

        return [], []

    results = []
    parameters = []

    models = {}

    # ---------------- RATIO ----------------

    ratio = fit_ratio(x_train, y_train)

    if ratio is not None:

        models["ratio"] = predict_ratio(
            x_val,
            ratio,
        )

        parameters.append({
            **base,
            "model": "ratio",
            "intercept": 0.0,
            "slope": ratio,
        })

    # ---------------- LINEAR ----------------

    linear = fit_linear(x_train, y_train)

    if linear is not None:

        models["linear"] = predict_linear(
            x_val,
            linear,
        )

        parameters.append({
            **base,
            "model": "linear",
            "intercept": linear["intercept"],
            "slope": linear["slope"],
        })

    # ---------------- VALIDATION ----------------

    if len(validation) == 0:

        print("  WARNING: no validation observations.")

        return results, parameters

    for model_name, predictions in models.items():

        residuals = y_val - predictions

        metrics = calculate_metrics(
            y_val,
            predictions,
        )

        # Uncertainty based on validation residuals.
        residual_p10 = float(
            np.percentile(residuals, 10)
        )

        residual_p90 = float(
            np.percentile(residuals, 90)
        )

        # Also assess cases where both sensors detected fire.
        shared_mask = (x_val > 0) & (y_val > 0)

        if shared_mask.any():

            shared_metrics = calculate_metrics(
                y_val[shared_mask],
                predictions[shared_mask],
            )

        else:

            shared_metrics = {
                "mae": np.nan,
                "rmse": np.nan,
                "r2": np.nan,
                "bias": np.nan,
            }

        results.append({
            **base,
            "model": model_name,

            **metrics,

            "residual_p10": residual_p10,
            "residual_p90": residual_p90,

            "shared_mae": shared_metrics["mae"],
            "shared_rmse": shared_metrics["rmse"],
            "shared_r2": shared_metrics["r2"],

            "status": (
                "LOW_SUPPORT"
                if shared_val < MIN_SHARED_NONZERO
                else "EVALUATED"
            ),
        })

    return results, parameters


# --------------------------------------------------
# MAIN
# --------------------------------------------------

def main():

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    all_results = []
    all_parameters = []

    for modis_sensor, viirs_sensor in SENSOR_PAIRS:

        filename = (
            f"{modis_sensor.lower()}_"
            f"{viirs_sensor.lower()}_pairs.parquet"
        )

        input_path = INPUT_DIR / filename

        if not input_path.exists():

            print("\nMissing:", input_path)
            continue

        print(
            f"\n===================================="
            f"\n{modis_sensor} vs {viirs_sensor}"
            f"\n===================================="
        )

        pairs = pd.read_parquet(input_path)

        pairs["week_start"] = pd.to_datetime(
            pairs["week_start"],
            utc=True,
        )

        for daynight in ["D", "N"]:

            subset = pairs[
                pairs["daynight"] == daynight
            ].copy()

            print(
                f"\nDay/night: {daynight} "
                f"| Rows: {len(subset)}"
            )

            for metric_name, columns in METRICS.items():

                print(f"  Metric: {metric_name}")

                results, parameters = evaluate_metric(
                    subset,
                    columns[0],
                    columns[1],
                    metric_name,
                    modis_sensor,
                    viirs_sensor,
                    daynight,
                )

                all_results.extend(results)
                all_parameters.extend(parameters)

    # --------------------------------------------------
    # SAVE OUTPUTS
    # --------------------------------------------------

    results_df = pd.DataFrame(all_results)
    parameters_df = pd.DataFrame(all_parameters)

    results_path = QA_DIR / "calibration_metrics.csv"

    parameters_path = (
        OUTPUT_DIR / "calibration_parameters.csv"
    )

    results_df.to_csv(
        results_path,
        index=False,
    )

    parameters_df.to_csv(
        parameters_path,
        index=False,
    )

    print("\n====================================")
    print("CALIBRATION MODEL FITTING COMPLETE")
    print("====================================")

    print("\nValidation results:")

    if not results_df.empty:

        print(
            results_df[
                [
                    "modis_sensor",
                    "viirs_sensor",
                    "daynight",
                    "metric",
                    "model",
                    "mae",
                    "rmse",
                    "r2",
                    "status",
                ]
            ].to_string(index=False)
        )

    print("\nSaved:")
    print(results_path)
    print(parameters_path)


if __name__ == "__main__":
    main()