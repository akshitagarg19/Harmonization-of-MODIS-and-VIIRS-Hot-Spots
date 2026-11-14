from pathlib import Path
import json

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

INPUTS = {
    "weekly": ROOT / "data/processed/sqh/weekly_aoi_sqh.parquet",
    "monthly": ROOT / "data/processed/sqh/monthly_aoi_sqh.parquet",
}

ANOMALY_DIR = ROOT / "data/processed/sqh/anomalies"

BASELINE_QA_DIR = ROOT / "outputs/sqh/baselines"

METRICS = [
    "detection_count",
    "frp_sum",
    "active_cells_1km",
]

MIN_HISTORY = 3

ANOMALY_DIR.mkdir(parents=True, exist_ok=True)
BASELINE_QA_DIR.mkdir(parents=True, exist_ok=True)


def prepare_data(df, frequency):
    date_col = "week_start" if frequency == "weekly" else "month_start"

    required = [date_col, "sensor", *METRICS]

    missing = set(required) - set(df.columns)

    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")

    df = df.copy()

    df[date_col] = pd.to_datetime(df[date_col])

    if df[required].isnull().any().any():
        raise ValueError("Input contains missing required values.")

    if frequency == "weekly":
        iso = df[date_col].dt.isocalendar()
        df["_year"] = iso.year.astype(int)
        df["_season"] = iso.week.astype(int)
    else:
        df["_year"] = df[date_col].dt.year
        df["_season"] = df[date_col].dt.month

    duplicate_key = ["sensor", "_year", "_season"]

    if df.duplicated(duplicate_key).any():
        raise ValueError(
            f"Duplicate sensor/year/season records in {frequency} data."
        )

    return df, date_col


def calculate_historical_statistics(history, value):
    values = np.asarray(history, dtype=float)

    return {
        "history_count": len(values),
        "baseline_p25": float(np.quantile(values, 0.25)),
        "baseline_median": float(np.quantile(values, 0.50)),
        "baseline_p75": float(np.quantile(values, 0.75)),
        "baseline_p90": float(np.quantile(values, 0.90)),
        "historical_percentile_rank": float(
            100 * np.mean(values <= value)
        ),
    }


def classify(value, p75, p90):
    if pd.isna(p75) or pd.isna(p90):
        return "insufficient_history"

    if value > p90:
        return "extreme"

    if value > p75:
        return "elevated"

    return "normal"


def build_frequency(frequency, input_path):

    print(f"\nProcessing {frequency} data...")

    df = pd.read_parquet(input_path)

    df, date_col = prepare_data(df, frequency)

    results = []

    grouping = df.groupby(["sensor", "_season"], sort=False)

    for (sensor, season), group in grouping:

        group = group.sort_values("_year")

        for _, row in group.iterrows():

            previous = group[group["_year"] < row["_year"]]

            result = row.to_dict()

            metric_ranks = []

            for metric in METRICS:

                if len(previous) < MIN_HISTORY:

                    statistics = {
                        "history_count": len(previous),
                        "baseline_p25": np.nan,
                        "baseline_median": np.nan,
                        "baseline_p75": np.nan,
                        "baseline_p90": np.nan,
                        "historical_percentile_rank": np.nan,
                    }

                else:

                    statistics = calculate_historical_statistics(
                        previous[metric].values,
                        row[metric],
                    )

                for key, value in statistics.items():
                    result[f"{metric}_{key}"] = value

                result[f"{metric}_anomaly"] = classify(
                    row[metric],
                    statistics["baseline_p75"],
                    statistics["baseline_p90"],
                )

                rank = statistics["historical_percentile_rank"]

                if not pd.isna(rank):
                    metric_ranks.append(rank)

            if len(metric_ranks) == len(METRICS):
                result["activity_score"] = float(
                    np.mean(metric_ranks)
                )
            else:
                result["activity_score"] = np.nan

            if pd.isna(result["activity_score"]):
                result["overall_anomaly"] = "insufficient_history"
            elif result["activity_score"] > 90:
                result["overall_anomaly"] = "extreme"
            elif result["activity_score"] > 75:
                result["overall_anomaly"] = "elevated"
            else:
                result["overall_anomaly"] = "normal"

            result["baseline_method"] = (
                "previous_years_same_season_sensor_specific"
            )

            results.append(result)

    output = pd.DataFrame(results)

    output = output.drop(columns=["_year", "_season"])

    output = output.sort_values(["sensor", date_col])

    # Save the consolidated baseline and anomaly results once.
    anomaly_path = ANOMALY_DIR / f"{frequency}_aoi_anomalies.parquet"

    output.to_parquet(anomaly_path, index=False)

    # Save elevated and extreme periods.
    critical = output[
        output["overall_anomaly"].isin(["elevated", "extreme"])
    ].copy()

    critical = critical.sort_values(
        ["activity_score", "detection_count"],
        ascending=False,
    )

    critical_path = ANOMALY_DIR / f"{frequency}_critical_periods.csv"

    critical.to_csv(critical_path, index=False)

    # Save quality-assurance summary.
    qa = {
        "frequency": frequency,
        "input_rows": int(len(df)),
        "output_rows": int(len(output)),
        "sensors": sorted(output["sensor"].unique().tolist()),
        "minimum_history": MIN_HISTORY,
        "anomaly_counts": {
            str(k): int(v)
            for k, v in output["overall_anomaly"]
            .value_counts().items()
        },
        "critical_periods": int(len(critical)),
        "missing_activity_scores": int(
            output["activity_score"].isna().sum()
        ),
        "baseline_method": (
            "Previous years, same seasonal period, "
            "calculated separately for each sensor."
        ),
        "missing_period_warning": (
            "Input contains recorded AOI periods only. "
            "Absent periods are not interpreted as zero activity."
        ),
    }

    qa_path = BASELINE_QA_DIR / f"{frequency}_baseline_qa.json"

    with open(qa_path, "w", encoding="utf-8") as f:
        json.dump(qa, f, indent=4)

    print(f"Input rows: {len(df):,}")
    print(f"Output rows: {len(output):,}")
    print("Anomaly counts:", qa["anomaly_counts"])
    print(f"Critical periods: {len(critical):,}")
    print("Saved:", anomaly_path)
    print("Saved:", critical_path)
    print("Saved:", qa_path)


def main():

    for frequency, input_path in INPUTS.items():

        if not input_path.exists():
            raise FileNotFoundError(input_path)

        build_frequency(frequency, input_path)

    print("\nBaseline and anomaly processing completed.")


if __name__ == "__main__":
    main()