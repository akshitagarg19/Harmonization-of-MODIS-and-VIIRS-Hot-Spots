from pathlib import Path

import numpy as np
import pandas as pd


# ==================================================
# CONFIGURATION
# ==================================================

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


# ==================================================
# COLUMN IDENTIFICATION
# ==================================================

def find_column(df, candidates):

    for column in candidates:
        if column in df.columns:
            return column

    return None


# ==================================================
# LOAD AND AGGREGATE REGIONAL DATA
# ==================================================

def create_regional_data(filename):

    path = CALIBRATION_DIR / filename

    if not path.exists():
        raise FileNotFoundError(path)

    df = pd.read_parquet(path)

    required = ["week_start", "daynight"]

    for column in required:
        if column not in df.columns:
            raise ValueError(
                f"Missing {column} in {filename}"
            )

    column_map = {}

    for name, candidates in COLUMN_CANDIDATES.items():

        found = find_column(df, candidates)

        if found is None:
            raise ValueError(
                f"Cannot identify {name} in {filename}. "
                f"Available columns: {list(df.columns)}"
            )

        column_map[name] = found

    df["week_start"] = pd.to_datetime(
        df["week_start"], utc=True
    )

    for name, source in column_map.items():

        df[name] = pd.to_numeric(
            df[source], errors="coerce"
        ).fillna(0)

    regional = (
        df.groupby(
            ["week_start", "daynight"],
            as_index=False
        )
        .agg(
            modis_count=("modis_count", "sum"),
            viirs_count=("viirs_count", "sum"),
            modis_frp=("modis_frp", "sum"),
            viirs_frp=("viirs_frp", "sum"),
        )
    )

    regional["year"] = regional["week_start"].dt.year

    return regional


# ==================================================
# METRICS
# ==================================================

def calculate_metrics(actual, predicted):

    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)

    residuals = actual - predicted

    mae = np.mean(np.abs(residuals))
    rmse = np.sqrt(np.mean(residuals ** 2))

    denominator = np.sum(
        (actual - np.mean(actual)) ** 2
    )

    if denominator == 0:
        r2 = np.nan
    else:
        r2 = 1 - (
            np.sum(residuals ** 2) / denominator
        )

    bias = np.mean(predicted - actual)

    return {
        "weeks": len(actual),
        "actual_total": np.sum(actual),
        "predicted_total": np.sum(predicted),
        "MAE": mae,
        "RMSE": rmse,
        "R2": r2,
        "mean_bias": bias,
        "residual_p10": np.percentile(residuals, 10),
        "residual_p90": np.percentile(residuals, 90),
    }


# ==================================================
# FIT MODELS USING TRAINING DATA
# ==================================================

def fit_models(train_df, metric):

    x = train_df[f"modis_{metric}"].to_numpy(dtype=float)
    y = train_df[f"viirs_{metric}"].to_numpy(dtype=float)

    models = {}

    denominator = np.sum(x ** 2)

    if denominator > 0:

        ratio = np.sum(x * y) / denominator

        models["ratio"] = {
            "intercept": 0.0,
            "slope": ratio,
        }

    if len(x) >= 2:

        X = np.column_stack([
            np.ones(len(x)),
            x
        ])

        intercept, slope = np.linalg.lstsq(
            X, y, rcond=None
        )[0]

        models["linear"] = {
            "intercept": intercept,
            "slope": slope,
        }

    return models


# ==================================================
# MAIN VALIDATION
# ==================================================

def main():

    annual_results = []
    overall_results = []
    prediction_records = []

    print("\nTEMPORAL CALIBRATION STABILITY TEST")
    print("=" * 70)

    for filename in PAIRS:

        pair_name = filename.replace(
            "_pairs.parquet", ""
        )

        print(f"\nProcessing: {pair_name}")

        regional = create_regional_data(filename)

        print(
            f"Regional weekly observations: {len(regional)}"
        )

        for daynight in ["D", "N"]:

            subset = regional[
                regional["daynight"] == daynight
            ].copy()

            train = subset[
                subset["week_start"] <= TRAIN_END
            ].copy()

            validation = subset[
                subset["week_start"] > TRAIN_END
            ].copy()

            if len(train) < 30 or len(validation) < 10:

                print(
                    f"  {daynight}: insufficient data"
                )
                continue

            print(
                f"  {daynight}: "
                f"{len(train)} training weeks, "
                f"{len(validation)} validation weeks"
            )

            for metric in ["count", "frp"]:

                models = fit_models(train, metric)

                for model_name, parameters in models.items():

                    intercept = parameters["intercept"]
                    slope = parameters["slope"]

                    # Overall validation
                    x_val = validation[
                        f"modis_{metric}"
                    ].to_numpy(dtype=float)

                    y_val = validation[
                        f"viirs_{metric}"
                    ].to_numpy(dtype=float)

                    predictions = intercept + slope * x_val

                    overall = calculate_metrics(
                        y_val, predictions
                    )

                    overall_results.append({
                        "pair": pair_name,
                        "daynight": daynight,
                        "metric": metric,
                        "model": model_name,
                        "intercept": intercept,
                        "slope": slope,
                        **overall,
                    })

                    # Year-wise validation
                    for year in sorted(
                        validation["year"].unique()
                    ):

                        year_df = validation[
                            validation["year"] == year
                        ]

                        x_year = year_df[
                            f"modis_{metric}"
                        ].to_numpy(dtype=float)

                        y_year = year_df[
                            f"viirs_{metric}"
                        ].to_numpy(dtype=float)

                        year_predictions = (
                            intercept + slope * x_year
                        )

                        metrics = calculate_metrics(
                            y_year,
                            year_predictions
                        )

                        annual_results.append({
                            "pair": pair_name,
                            "daynight": daynight,
                            "metric": metric,
                            "model": model_name,
                            "year": int(year),
                            "intercept": intercept,
                            "slope": slope,
                            **metrics,
                        })

                        # Save individual weekly predictions
                        for i, (_, row) in enumerate(
                            year_df.iterrows()
                        ):

                            prediction_records.append({
                                "pair": pair_name,
                                "daynight": daynight,
                                "metric": metric,
                                "model": model_name,
                                "week_start": row["week_start"],
                                "year": int(year),
                                "modis_actual": x_year[i],
                                "viirs_actual": y_year[i],
                                "viirs_predicted": (
                                    year_predictions[i]
                                ),
                                "residual": (
                                    y_year[i] -
                                    year_predictions[i]
                                ),
                                "intercept": intercept,
                                "slope": slope,
                            })

    # ==================================================
    # SAVE OUTPUTS
    # ==================================================

    annual_df = pd.DataFrame(annual_results)

    overall_df = pd.DataFrame(overall_results)

    predictions_df = pd.DataFrame(
        prediction_records
    )

    annual_file = (
        OUTPUT_DIR /
        "calibration_yearly_validation.csv"
    )

    overall_file = (
        OUTPUT_DIR /
        "calibration_overall_validation.csv"
    )

    predictions_file = (
        OUTPUT_DIR /
        "calibration_weekly_predictions.csv"
    )

    annual_df.to_csv(annual_file, index=False)

    overall_df.to_csv(overall_file, index=False)

    predictions_df.to_csv(
        predictions_file,
        index=False
    )

    print("\n" + "=" * 70)
    print("TEMPORAL STABILITY TEST COMPLETED")
    print("=" * 70)

    print(f"\nSaved: {annual_file}")
    print(f"Saved: {overall_file}")
    print(f"Saved: {predictions_file}")

    if not annual_df.empty:

        print("\nYEAR-WISE VALIDATION RESULTS:\n")

        columns = [
            "pair",
            "daynight",
            "metric",
            "model",
            "year",
            "weeks",
            "R2",
            "MAE",
            "RMSE",
            "mean_bias",
        ]

        print(
            annual_df[columns].to_string(
                index=False
            )
        )


if __name__ == "__main__":
    main()