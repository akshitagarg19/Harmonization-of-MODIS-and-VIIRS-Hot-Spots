"""
Punjab Fire Calendar
SQH: Terra-SNPP Sensor Comparison and Diagnostics

Purpose:
    Compare MODIS_Terra and VIIRS_SNPP over their
    common period beginning 2012-01-01.

Inputs:
    data/processed/sqh/hotspots_sqh.parquet
    data/processed/sqh/weekly_cell_sqh.parquet
    data/processed/sqh/monthly_cell_sqh.parquet
    data/processed/sqh/weekly_aoi_sqh.parquet
    data/processed/sqh/monthly_aoi_sqh.parquet

Outputs:
    outputs/sqh/sensor_comparison/

Important:
    - No zero-filling of missing detections.
    - No sensor harmonisation is performed.
    - Sensors remain separate.
    - Terra pre-2012 data remains untouched.
    - Spatial comparisons distinguish shared and
      sensor-exclusive positive cell-period records.
"""

from pathlib import Path
import json
import time

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# ============================================================
# 1. CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parents[2]

INPUT_DIR = ROOT / "data/processed/sqh"

OUTPUT_DIR = (
    ROOT / "outputs/sqh/sensor_comparison"
)

PLOT_DIR = OUTPUT_DIR / "plots"
TABLE_DIR = OUTPUT_DIR / "tables"

SENSORS = [
    "MODIS_Terra",
    "VIIRS_SNPP",
]

TERRA = "MODIS_Terra"
SNPP = "VIIRS_SNPP"

OVERLAP_START = pd.Timestamp("2012-01-01")

FRP_TOLERANCE = 1e-8


FILES = {
    "detections": INPUT_DIR / "hotspots_sqh.parquet",

    "weekly_cell": INPUT_DIR / "weekly_cell_sqh.parquet",
    "monthly_cell": INPUT_DIR / "monthly_cell_sqh.parquet",

    "weekly_aoi": INPUT_DIR / "weekly_aoi_sqh.parquet",
    "monthly_aoi": INPUT_DIR / "monthly_aoi_sqh.parquet",
}


# ============================================================
# 2. GENERAL HELPERS
# ============================================================

def check(condition, message):

    if not condition:
        raise AssertionError(message)


def save_csv(df, filename):

    path = TABLE_DIR / filename

    df.to_csv(
        path,
        index=False
    )

    print("Saved:", path)


def save_plot(filename):

    path = PLOT_DIR / filename

    plt.tight_layout()

    plt.savefig(
        path,
        dpi=180,
        bbox_inches="tight"
    )

    plt.close()

    print("Saved plot:", path)


def safe_corr(x, y, method="pearson"):

    valid = (
        pd.DataFrame({
            "x": x,
            "y": y
        })
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )

    if len(valid) < 2:
        return None

    if valid["x"].nunique() < 2:
        return None

    if valid["y"].nunique() < 2:
        return None

    return float(
        valid["x"].corr(
            valid["y"],
            method=method
        )
    )


def distribution_summary(series):

    values = pd.to_numeric(
        series,
        errors="coerce"
    ).dropna()

    values = values[
        np.isfinite(values)
    ]

    if len(values) == 0:
        return {}

    return {
        "n": int(len(values)),
        "mean": float(values.mean()),
        "median": float(values.median()),
        "std": float(values.std()),
        "min": float(values.min()),
        "max": float(values.max()),

        "q05": float(values.quantile(0.05)),
        "q25": float(values.quantile(0.25)),
        "q50": float(values.quantile(0.50)),
        "q75": float(values.quantile(0.75)),
        "q90": float(values.quantile(0.90)),
        "q95": float(values.quantile(0.95)),
        "q99": float(values.quantile(0.99)),
    }


# ============================================================
# 3. LOAD DATA
# ============================================================

def load_data():

    print("\n" + "=" * 75)
    print("STEP 1: LOADING SQH DATA")
    print("=" * 75)

    for name, path in FILES.items():

        check(
            path.exists(),
            f"Missing input: {path}"
        )

    data = {}

    for name, path in FILES.items():

        print("\nLoading:", name)

        data[name] = pd.read_parquet(path)

        print("Shape:", data[name].shape)

    return data


# ============================================================
# 4. FILTER COMMON COMPARISON PERIOD
# ============================================================

def prepare_data(data):

    print("\n" + "=" * 75)
    print("STEP 2: PREPARING COMMON COMPARISON PERIOD")
    print("=" * 75)

    # Keep all Terra historical data in the original
    # source file. Only comparison copies are filtered.

    period_columns = {
        "weekly_cell": "week_start",
        "monthly_cell": "month_start",
        "weekly_aoi": "week_start",
        "monthly_aoi": "month_start",
    }

    prepared = {}

    for name, df in data.items():

        df = df.copy()

        if "sensor" in df.columns:

            df = df[
                df["sensor"].isin(SENSORS)
            ].copy()

        if name in period_columns:

            col = period_columns[name]

            df[col] = pd.to_datetime(
                df[col]
            )

            df = df[
                df[col] >= OVERLAP_START
            ].copy()

        elif name == "detections":

            df["acq_date"] = pd.to_datetime(
                df["acq_date"]
            )

            df = df[
                df["acq_date"] >= OVERLAP_START
            ].copy()

        prepared[name] = df

        print(
            f"{name}: {len(df):,} comparison-period rows"
        )

        if "sensor" in df.columns:

            print(
                df["sensor"].value_counts().to_string()
            )

    # Verify both sensors are represented.
    for name, df in prepared.items():

        if "sensor" in df.columns:

            found = set(df["sensor"].unique())

            check(
                found == set(SENSORS),
                f"Missing sensor in {name}: {found}"
            )

    return prepared


# ============================================================
# 5. AOI TEMPORAL COMPARISON
# ============================================================

def compare_aoi_time_series(
    terra_df,
    snpp_df,
    period_column,
    label
):

    print("\n" + "=" * 75)
    print(f"STEP 3: {label.upper()} AOI TEMPORAL COMPARISON")
    print("=" * 75)

    metrics = [
        "detection_count",
        "frp_sum",
        "frp_mean",
        "frp_max",
        "day_count",
        "night_count",
        "active_cells_1km",
    ]

    terra = terra_df[
        terra_df["sensor"] == TERRA
    ].copy()

    snpp = snpp_df[
        snpp_df["sensor"] == SNPP
    ].copy()

    terra = terra[
        [period_column] + metrics
    ]

    snpp = snpp[
        [period_column] + metrics
    ]

    terra = terra.rename(
        columns={
            metric: f"{metric}_terra"
            for metric in metrics
        }
    )

    snpp = snpp.rename(
        columns={
            metric: f"{metric}_snpp"
            for metric in metrics
        }
    )

    # Inner join: only periods where both sensors
    # have positive AOI detection records.
    paired = terra.merge(
        snpp,
        on=period_column,
        how="inner",
        validate="one_to_one"
    )

    check(
        len(paired) > 0,
        f"No common AOI periods for {label}."
    )

    paired = paired.sort_values(
        period_column
    ).reset_index(drop=True)

    # Differences and ratios are calculated only
    # for matched positive AOI periods.
    for metric in metrics:

        a = paired[f"{metric}_terra"]
        b = paired[f"{metric}_snpp"]

        paired[f"{metric}_difference_snpp_minus_terra"] = (
            b - a
        )

        paired[f"{metric}_ratio_snpp_to_terra"] = (
            b / a.where(a != 0)
        )

    print("Terra periods:", len(terra))
    print("SNPP periods:", len(snpp))
    print("Matched periods:", len(paired))

    print("\nMatched-period correlations:")

    correlations = {}

    for metric in metrics:

        corr = safe_corr(
            paired[f"{metric}_terra"],
            paired[f"{metric}_snpp"]
        )

        correlations[metric] = corr

        print(metric, ":", corr)

    print("\nMedian SNPP / Terra ratios:")

    ratios = {}

    for metric in metrics:

        ratio = (
            paired[f"{metric}_ratio_snpp_to_terra"]
            .replace([np.inf, -np.inf], np.nan)
            .dropna()
        )

        ratios[metric] = (
            float(ratio.median())
            if len(ratio)
            else None
        )

        print(metric, ":", ratios[metric])

    save_csv(
        paired,
        f"{label}_aoi_paired_comparison.csv"
    )

    return paired, {
        "terra_periods": len(terra),
        "snpp_periods": len(snpp),
        "matched_periods": len(paired),
        "correlations": correlations,
        "median_snpp_to_terra_ratios": ratios,
    }


# ============================================================
# 6. AOI TEMPORAL PLOTS
# ============================================================

def plot_aoi_comparison(
    paired,
    period_column,
    label
):

    print("\nCreating AOI plots:", label)

    metrics = [
        ("detection_count", "Detection count"),
        ("frp_sum", "FRP sum"),
        ("active_cells_1km", "Active 1 km cells"),
    ]

    for metric, title in metrics:

        plt.figure(figsize=(13, 5))

        plt.plot(
            paired[period_column],
            paired[f"{metric}_terra"],
            label=TERRA,
            linewidth=1.3
        )

        plt.plot(
            paired[period_column],
            paired[f"{metric}_snpp"],
            label=SNPP,
            linewidth=1.3
        )

        plt.title(
            f"{label.capitalize()} AOI comparison: {title}"
        )

        plt.xlabel("Period")
        plt.ylabel(title)

        plt.legend()
        plt.grid(alpha=0.25)

        save_plot(
            f"{label}_aoi_{metric}.png"
        )


# ============================================================
# 7. CELL-LEVEL SPATIAL COMPARISON
# ============================================================

def compare_spatial_cells(
    terra_df,
    snpp_df,
    period_column,
    label
):

    print("\n" + "=" * 75)
    print(f"STEP 4: {label.upper()} SPATIAL COMPARISON")
    print("=" * 75)

    keys = [
        period_column,
        "sqh_cell_id",
    ]

    metrics = [
        "detection_count",
        "frp_sum",
        "frp_mean",
        "frp_max",
    ]

    terra = terra_df[
        terra_df["sensor"] == TERRA
    ][keys + metrics].copy()

    snpp = snpp_df[
        snpp_df["sensor"] == SNPP
    ][keys + metrics].copy()

    terra = terra.rename(
        columns={
            metric: f"{metric}_terra"
            for metric in metrics
        }
    )

    snpp = snpp.rename(
        columns={
            metric: f"{metric}_snpp"
            for metric in metrics
        }
    )

    # Outer join is intentional.
    # It identifies shared and sensor-exclusive
    # positive cell-period records.
    #
    # Missing values are NOT replaced with zero.

    spatial = terra.merge(
        snpp,
        on=keys,
        how="outer",
        indicator=True,
        validate="one_to_one"
    )

    both = spatial[
        spatial["_merge"] == "both"
    ].copy()

    terra_only = spatial[
        spatial["_merge"] == "left_only"
    ].copy()

    snpp_only = spatial[
        spatial["_merge"] == "right_only"
    ].copy()

    n_both = len(both)
    n_terra_only = len(terra_only)
    n_snpp_only = len(snpp_only)

    union = len(spatial)

    jaccard = (
        n_both / union
        if union > 0
        else None
    )

    # Compare measurements only where both sensors
    # have positive detections in the same cell-period.
    correlations = {}

    for metric in metrics:

        correlations[metric] = safe_corr(
            both[f"{metric}_terra"],
            both[f"{metric}_snpp"]
        )

    print("Terra positive cell-periods:", len(terra))
    print("SNPP positive cell-periods:", len(snpp))

    print("Shared positive cell-periods:", n_both)
    print("Terra-only positive cell-periods:", n_terra_only)
    print("SNPP-only positive cell-periods:", n_snpp_only)

    print("Positive-key Jaccard similarity:", jaccard)

    print("\nCorrelations within shared positive cell-periods:")

    for metric, value in correlations.items():

        print(metric, ":", value)

    # Save detailed shared and exclusive records.
    save_csv(
        both,
        f"{label}_shared_positive_cell_periods.csv"
    )

    save_csv(
        terra_only,
        f"{label}_terra_only_positive_cell_periods.csv"
    )

    save_csv(
        snpp_only,
        f"{label}_snpp_only_positive_cell_periods.csv"
    )

    summary = {
        "period": label,
        "terra_positive_cell_periods": len(terra),
        "snpp_positive_cell_periods": len(snpp),
        "shared_positive_cell_periods": n_both,
        "terra_only_positive_cell_periods": n_terra_only,
        "snpp_only_positive_cell_periods": n_snpp_only,
        "union_positive_cell_periods": union,
        "positive_key_jaccard": jaccard,
        "shared_positive_correlations": correlations,
    }

    return summary


# ============================================================
# 8. DISTRIBUTION COMPARISON
# ============================================================

def compare_distributions(
    weekly_cell,
    monthly_cell,
    detections
):

    print("\n" + "=" * 75)
    print("STEP 5: DISTRIBUTION COMPARISON")
    print("=" * 75)

    results = []

    datasets = {
        "weekly_cell": weekly_cell,
        "monthly_cell": monthly_cell,
    }

    metrics = [
        "detection_count",
        "frp_sum",
        "frp_mean",
        "frp_max",
    ]

    for dataset_name, df in datasets.items():

        for sensor in SENSORS:

            sensor_df = df[
                df["sensor"] == sensor
            ]

            for metric in metrics:

                summary = distribution_summary(
                    sensor_df[metric]
                )

                results.append({
                    "dataset": dataset_name,
                    "sensor": sensor,
                    "metric": metric,
                    **summary,
                })

    # Detection-level FRP distributions.
    for sensor in SENSORS:

        sensor_df = detections[
            detections["sensor"] == sensor
        ]

        for metric in ["frp", "brightness"]:

            if metric not in sensor_df.columns:
                continue

            summary = distribution_summary(
                sensor_df[metric]
            )

            results.append({
                "dataset": "individual_detections",
                "sensor": sensor,
                "metric": metric,
                **summary,
            })

    result_df = pd.DataFrame(results)

    save_csv(
        result_df,
        "sensor_distribution_summary.csv"
    )

    print("\nDistribution summary:")
    print(
        result_df[
            [
                "dataset",
                "sensor",
                "metric",
                "n",
                "mean",
                "median",
                "q90",
                "q95",
                "q99",
            ]
        ].to_string(index=False)
    )

    return result_df


# ============================================================
# 9. DISTRIBUTION PLOTS
# ============================================================

def plot_distributions(
    weekly_cell,
    monthly_cell,
    detections
):

    print("\nCreating distribution plots.")

    plot_datasets = {
        "weekly": weekly_cell,
        "monthly": monthly_cell,
    }

    for label, df in plot_datasets.items():

        for metric in [
            "detection_count",
            "frp_sum",
            "frp_mean",
            "frp_max",
        ]:

            plt.figure(figsize=(10, 5))

            for sensor in SENSORS:

                values = df.loc[
                    df["sensor"] == sensor,
                    metric
                ].dropna()

                values = values[
                    np.isfinite(values)
                ]

                plt.hist(
                    values,
                    bins=60,
                    alpha=0.5,
                    density=True,
                    label=sensor
                )

            plt.title(
                f"{label.capitalize()} cell distribution: {metric}"
            )

            plt.xlabel(metric)
            plt.ylabel("Density")

            plt.legend()
            plt.grid(alpha=0.2)

            save_plot(
                f"{label}_distribution_{metric}.png"
            )

    # Individual detection FRP.
    plt.figure(figsize=(10, 5))

    for sensor in SENSORS:

        values = detections.loc[
            detections["sensor"] == sensor,
            "frp"
        ].dropna()

        values = values[
            np.isfinite(values)
        ]

        plt.hist(
            values,
            bins=80,
            alpha=0.5,
            density=True,
            label=sensor
        )

    plt.title("Individual detection FRP distributions")
    plt.xlabel("FRP")
    plt.ylabel("Density")

    plt.legend()
    plt.grid(alpha=0.2)

    save_plot(
        "individual_detection_frp_distribution.png"
    )


# ============================================================
# 10. SEASONAL COMPARISON
# ============================================================

def seasonal_comparison(monthly_aoi):

    print("\n" + "=" * 75)
    print("STEP 6: SEASONAL COMPARISON")
    print("=" * 75)

    df = monthly_aoi.copy()

    df["month_number"] = (
        df["month_start"].dt.month
    )

    df["year"] = (
        df["month_start"].dt.year
    )

    metrics = [
        "detection_count",
        "frp_sum",
        "frp_mean",
        "active_cells_1km",
    ]

    # First calculate sensor-specific seasonal summaries.
    # This does not fill missing sensor-month records.

    seasonal = (
        df.groupby(
            ["sensor", "month_number"],
            observed=True
        )[metrics]
        .agg(["mean", "median", "std", "count"])
        .reset_index()
    )

    seasonal.columns = [
        "_".join(
            str(part)
            for part in col
            if part != ""
        )
        if isinstance(col, tuple)
        else col
        for col in seasonal.columns
    ]

    save_csv(
        seasonal,
        "seasonal_monthly_summary.csv"
    )

    # Monthly time series grouped by sensor.
    for metric in metrics:

        plt.figure(figsize=(10, 5))

        for sensor in SENSORS:

            sensor_df = df[
                df["sensor"] == sensor
            ]

            monthly_mean = (
                sensor_df.groupby("month_number")[metric]
                .mean()
            )

            plt.plot(
                monthly_mean.index,
                monthly_mean.values,
                marker="o",
                label=sensor
            )

        plt.xticks(
            range(1, 13)
        )

        plt.xlabel("Calendar month")
        plt.ylabel(f"Mean {metric}")

        plt.title(
            f"Seasonal pattern: {metric}"
        )

        plt.legend()
        plt.grid(alpha=0.25)

        save_plot(
            f"seasonal_{metric}.png"
        )

    print("\nSeasonal summary:")
    print(seasonal.to_string(index=False))

    return seasonal


# ============================================================
# 11. DAY/NIGHT COMPARISON
# ============================================================

def daynight_comparison(detections):

    print("\n" + "=" * 75)
    print("STEP 7: DAY/NIGHT COMPARISON")
    print("=" * 75)

    df = detections.copy()

    df["daynight_normalized"] = (
        df["daynight"]
        .astype("string")
        .str.strip()
        .str.lower()
    )

    valid_values = ["day", "night"]

    check(
        df["daynight_normalized"]
        .isin(valid_values)
        .all(),
        "Unexpected daynight values in detections."
    )

    # Individual detection-level comparison.
    summary = (
        df.groupby(
            ["sensor", "daynight_normalized"],
            observed=True
        )
        .agg(
            detection_count=("frp", "size"),
            frp_sum=("frp", "sum"),
            frp_mean=("frp", "mean"),
            frp_median=("frp", "median"),
            frp_max=("frp", "max"),
        )
        .reset_index()
    )

    save_csv(
        summary,
        "daynight_detection_summary.csv"
    )

    # Compare FRP distributions separately for day/night.
    for period in valid_values:

        plt.figure(figsize=(10, 5))

        for sensor in SENSORS:

            values = df.loc[
                (df["sensor"] == sensor)
                &
                (df["daynight_normalized"] == period),
                "frp"
            ].dropna()

            plt.hist(
                values,
                bins=60,
                density=True,
                alpha=0.5,
                label=sensor
            )

        plt.title(
            f"Individual detection FRP: {period.capitalize()}"
        )

        plt.xlabel("FRP")
        plt.ylabel("Density")

        plt.legend()
        plt.grid(alpha=0.2)

        save_plot(
            f"daynight_frp_{period}.png"
        )

    print("\nDay/night summary:")
    print(summary.to_string(index=False))

    return summary


# ============================================================
# 12. FINAL QA REPORT
# ============================================================

def save_qa_report(
    prepared,
    weekly_temporal,
    monthly_temporal,
    weekly_spatial,
    monthly_spatial,
    distributions,
    seasonal,
    daynight
):

    print("\n" + "=" * 75)
    print("STEP 8: SAVING COMPARISON QA")
    print("=" * 75)

    qa = {
        "project": "Punjab Fire Calendar",

        "analysis": "Terra-SNPP Sensor Comparison",

        "comparison_period": {
            "start": str(OVERLAP_START.date()),
            "end": str(
                prepared["detections"]["acq_date"].max().date()
            ),
        },

        "sensors": SENSORS,

        "methodology": {
            "grid": "1 km x 1 km",
            "crs": "EPSG:32643",
            "missing_detection_policy": (
                "Missing detection records are not treated as zero."
            ),
            "harmonisation_performed": False,
            "comparison_scope": (
                "Observed positive detections and matched "
                "positive AOI/cell-period records."
            ),
        },

        "temporal": {
            "weekly": weekly_temporal,
            "monthly": monthly_temporal,
        },

        "spatial": {
            "weekly": weekly_spatial,
            "monthly": monthly_spatial,
        },

        "distribution_rows": len(distributions),

        "seasonal_rows": len(seasonal),

        "daynight_rows": len(daynight),

        "status": "COMPLETED",
    }

    qa_path = OUTPUT_DIR / "sensor_comparison_qa.json"

    with open(
        qa_path,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            qa,
            f,
            indent=4,
            ensure_ascii=False,
            default=str
        )

    print("QA saved:", qa_path)


# ============================================================
# 13. MAIN
# ============================================================

def main():

    start_time = time.time()

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    TABLE_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    PLOT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    print("\n")
    print("#" * 75)
    print("TERRA-SNPP SENSOR COMPARISON")
    print("#" * 75)

    # Load.
    data = load_data()

    # Prepare common period.
    prepared = prepare_data(data)

    # --------------------------------------------------------
    # WEEKLY AOI
    # --------------------------------------------------------

    weekly_paired, weekly_temporal = (
        compare_aoi_time_series(
            prepared["weekly_aoi"],
            prepared["weekly_aoi"],
            "week_start",
            "weekly"
        )
    )

    plot_aoi_comparison(
        weekly_paired,
        "week_start",
        "weekly"
    )

    # --------------------------------------------------------
    # MONTHLY AOI
    # --------------------------------------------------------

    monthly_paired, monthly_temporal = (
        compare_aoi_time_series(
            prepared["monthly_aoi"],
            prepared["monthly_aoi"],
            "month_start",
            "monthly"
        )
    )

    plot_aoi_comparison(
        monthly_paired,
        "month_start",
        "monthly"
    )

    # --------------------------------------------------------
    # WEEKLY SPATIAL
    # --------------------------------------------------------

    weekly_spatial = compare_spatial_cells(
        prepared["weekly_cell"],
        prepared["weekly_cell"],
        "week_start",
        "weekly"
    )

    # --------------------------------------------------------
    # MONTHLY SPATIAL
    # --------------------------------------------------------

    monthly_spatial = compare_spatial_cells(
        prepared["monthly_cell"],
        prepared["monthly_cell"],
        "month_start",
        "monthly"
    )

    # --------------------------------------------------------
    # DISTRIBUTIONS
    # --------------------------------------------------------

    distributions = compare_distributions(
        prepared["weekly_cell"],
        prepared["monthly_cell"],
        prepared["detections"]
    )

    plot_distributions(
        prepared["weekly_cell"],
        prepared["monthly_cell"],
        prepared["detections"]
    )

    # --------------------------------------------------------
    # SEASONALITY
    # --------------------------------------------------------

    seasonal = seasonal_comparison(
        prepared["monthly_aoi"]
    )

    # --------------------------------------------------------
    # DAY/NIGHT
    # --------------------------------------------------------

    daynight = daynight_comparison(
        prepared["detections"]
    )

    # --------------------------------------------------------
    # QA
    # --------------------------------------------------------

    save_qa_report(
        prepared,
        weekly_temporal,
        monthly_temporal,
        weekly_spatial,
        monthly_spatial,
        distributions,
        seasonal,
        daynight
    )

    elapsed = time.time() - start_time

    print("\n" + "#" * 75)
    print("SENSOR COMPARISON COMPLETED")
    print("#" * 75)

    print("Execution time:", round(elapsed, 2), "seconds")

    print("\nOutput directory:")
    print(OUTPUT_DIR)

    print("\nTables:")
    print(TABLE_DIR)

    print("\nPlots:")
    print(PLOT_DIR)


if __name__ == "__main__":
    main()