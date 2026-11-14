from pathlib import Path
import json
import warnings

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# ============================================================
# CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parents[2]

INPUT_FILE = (
    ROOT
    / "data"
    / "processed"
    / "sqh"
    / "hotspots_sqh.parquet"
)

OUTPUT_DIR = (
    ROOT
    / "outputs"
    / "sqh"
    / "temporal_stability"
)

TABLE_DIR = OUTPUT_DIR / "tables"
PLOT_DIR = OUTPUT_DIR / "plots"

START_DATE = pd.Timestamp("2012-01-01")

SENSORS = [
    "MODIS_Terra",
    "VIIRS_SNPP",
]

TABLE_DIR.mkdir(parents=True, exist_ok=True)
PLOT_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# HELPERS
# ============================================================

def section(title):
    print("\n" + "=" * 75)
    print(title)
    print("=" * 75)


def save_table(df, filename):
    path = TABLE_DIR / filename
    df.to_csv(path, index=False)
    print(f"Saved: {path}")


def safe_ratio(numerator, denominator):
    if pd.isna(denominator) or denominator == 0:
        return np.nan

    return numerator / denominator


def normalize_daynight(series):
    values = series.astype("string").str.strip().str.lower()

    return values.replace({
        "d": "day",
        "day": "day",
        "n": "night",
        "night": "night",
    })


def save_plot(filename):
    path = PLOT_DIR / filename
    plt.tight_layout()
    plt.savefig(path, dpi=180, bbox_inches="tight")
    plt.close()
    print(f"Saved plot: {path}")


# ============================================================
# STEP 1: LOAD DATA
# ============================================================

section("STEP 1: LOADING SQH DETECTIONS")

if not INPUT_FILE.exists():
    raise FileNotFoundError(
        f"Required input file not found: {INPUT_FILE}"
    )

df = pd.read_parquet(INPUT_FILE)

print("Shape:", df.shape)
print("Columns:", list(df.columns))

required = ["sensor", "acq_date", "frp"]

missing = [
    column for column in required
    if column not in df.columns
]

if missing:
    raise ValueError(f"Missing required columns: {missing}")


# ============================================================
# STEP 2: PREPARE COMPARISON DATA
# ============================================================

section("STEP 2: PREPARING COMPARISON PERIOD")

df["acq_date"] = pd.to_datetime(
    df["acq_date"],
    errors="coerce"
)

df["frp"] = pd.to_numeric(
    df["frp"],
    errors="coerce"
)

df = df.dropna(subset=["acq_date", "sensor"])

df = df[
    df["sensor"].isin(SENSORS)
].copy()

# Keep only the common Terra-SNPP comparison period.
df = df[
    df["acq_date"] >= START_DATE
].copy()

df["year"] = df["acq_date"].dt.year
df["month_number"] = df["acq_date"].dt.month

# Monday-start weekly periods.
df["week_start"] = (
    df["acq_date"]
    .dt.to_period("W-SUN")
    .dt.start_time
)

# Calendar month.
df["month_start"] = (
    df["acq_date"]
    .dt.to_period("M")
    .dt.to_timestamp()
)

print("Comparison rows:", len(df))
print("\nDetections by sensor:")
print(df["sensor"].value_counts())

print("\nDate range:")
print(df["acq_date"].min(), "to", df["acq_date"].max())


# ============================================================
# STEP 3: YEARLY SENSOR SUMMARY
# ============================================================

section("STEP 3: YEARLY SENSOR COMPARISON")

yearly = (
    df.groupby(["year", "sensor"])
    .agg(
        detection_count=("sensor", "size"),
        frp_sum=("frp", "sum"),
        frp_mean=("frp", "mean"),
        frp_median=("frp", "median"),
        frp_max=("frp", "max"),
    )
    .reset_index()
)

yearly_wide = yearly.pivot(
    index="year",
    columns="sensor",
    values=[
        "detection_count",
        "frp_sum",
        "frp_mean",
        "frp_median",
        "frp_max",
    ],
)

yearly_wide.columns = [
    f"{metric}_{sensor}"
    for metric, sensor in yearly_wide.columns
]

yearly_wide = yearly_wide.reset_index()

for metric in [
    "detection_count",
    "frp_sum",
    "frp_mean",
    "frp_median",
    "frp_max",
]:

    terra_col = f"{metric}_MODIS_Terra"
    snpp_col = f"{metric}_VIIRS_SNPP"

    if terra_col in yearly_wide.columns:
        yearly_wide[f"{metric}_SNPP_Terra_ratio"] = (
            yearly_wide[snpp_col]
            / yearly_wide[terra_col].replace(0, np.nan)
        )

print(yearly_wide.to_string(index=False))

save_table(
    yearly_wide,
    "yearly_sensor_comparison.csv"
)


# ============================================================
# STEP 4: MONTHLY COMPARISON
# ============================================================

section("STEP 4: MONTHLY SENSOR COMPARISON")

monthly = (
    df.groupby(["month_start", "sensor"])
    .agg(
        detection_count=("sensor", "size"),
        frp_sum=("frp", "sum"),
        frp_mean=("frp", "mean"),
        active_days=("acq_date", "nunique"),
    )
    .reset_index()
)

monthly_wide = monthly.pivot(
    index="month_start",
    columns="sensor",
    values=[
        "detection_count",
        "frp_sum",
        "frp_mean",
        "active_days",
    ],
)

monthly_wide.columns = [
    f"{metric}_{sensor}"
    for metric, sensor in monthly_wide.columns
]

monthly_wide = monthly_wide.reset_index()

# Explicit record-presence indicators.
for sensor in SENSORS:
    count_col = f"detection_count_{sensor}"

    monthly_wide[f"has_record_{sensor}"] = (
        monthly_wide[count_col].notna()
    )

# Fill count columns only for reporting recorded detections.
# A zero here means no detection record in that sensor-month,
# NOT confirmed zero fire or confirmed observation coverage.
for metric in [
    "detection_count",
    "frp_sum",
    "active_days",
]:
    for sensor in SENSORS:
        column = f"{metric}_{sensor}"

        if column in monthly_wide.columns:
            monthly_wide[column] = (
                monthly_wide[column].fillna(0)
            )

# Calculate ratios only when both sensors have positive counts.
monthly_wide["detection_ratio_SNPP_Terra"] = (
    monthly_wide["detection_count_VIIRS_SNPP"]
    / monthly_wide["detection_count_MODIS_Terra"].replace(
        0, np.nan
    )
)

monthly_wide["frp_ratio_SNPP_Terra"] = (
    monthly_wide["frp_sum_VIIRS_SNPP"]
    / monthly_wide["frp_sum_MODIS_Terra"].replace(
        0, np.nan
    )
)

print("Monthly rows:", len(monthly_wide))
print("\nMonths with detection records:")
print(
    monthly_wide[
        [
            "has_record_MODIS_Terra",
            "has_record_VIIRS_SNPP",
        ]
    ].sum()
)

save_table(
    monthly_wide,
    "monthly_sensor_comparison.csv"
)


# ============================================================
# STEP 5: WEEKLY DETECTION RECORD PRESENCE
# ============================================================

section("STEP 5: WEEKLY DETECTION RECORD PRESENCE")

weekly = (
    df.groupby(["week_start", "sensor"])
    .agg(
        detection_count=("sensor", "size"),
        frp_sum=("frp", "sum"),
    )
    .reset_index()
)

weekly_wide = weekly.pivot(
    index="week_start",
    columns="sensor",
    values=[
        "detection_count",
        "frp_sum",
    ],
)

weekly_wide.columns = [
    f"{metric}_{sensor}"
    for metric, sensor in weekly_wide.columns
]

weekly_wide = weekly_wide.reset_index()

for sensor in SENSORS:
    count_col = f"detection_count_{sensor}"

    weekly_wide[f"has_record_{sensor}"] = (
        weekly_wide[count_col].notna()
    )

for metric in ["detection_count", "frp_sum"]:
    for sensor in SENSORS:
        column = f"{metric}_{sensor}"

        if column in weekly_wide.columns:
            weekly_wide[column] = (
                weekly_wide[column].fillna(0)
            )

weekly_wide["record_status"] = np.select(
    [
        (
            weekly_wide["has_record_MODIS_Terra"]
            & weekly_wide["has_record_VIIRS_SNPP"]
        ),
        weekly_wide["has_record_MODIS_Terra"],
        weekly_wide["has_record_VIIRS_SNPP"],
    ],
    [
        "Both sensors have detection records",
        "Terra only has detection records",
        "SNPP only has detection records",
    ],
    default="Neither has detection records",
)

print(
    weekly_wide["record_status"].value_counts()
)

save_table(
    weekly_wide,
    "weekly_detection_record_presence.csv"
)


# ============================================================
# STEP 6: DAY/NIGHT BY YEAR
# ============================================================

section("STEP 6: DAY/NIGHT YEARLY COMPARISON")

if "daynight" in df.columns:

    df["daynight_normalized"] = normalize_daynight(
        df["daynight"]
    )

    daynight = (
        df[
            df["daynight_normalized"].isin(["day", "night"])
        ]
        .groupby(
            ["year", "sensor", "daynight_normalized"]
        )
        .agg(
            detection_count=("sensor", "size"),
            frp_sum=("frp", "sum"),
            frp_mean=("frp", "mean"),
        )
        .reset_index()
    )

    print(daynight.to_string(index=False))

    save_table(
        daynight,
        "yearly_daynight_comparison.csv"
    )

else:
    warnings.warn(
        "No daynight column found. Skipping day/night analysis."
    )


# ============================================================
# STEP 7: PRODUCT AND VERSION DISTRIBUTION
# ============================================================

section("STEP 7: PRODUCT AND VERSION DISTRIBUTION")

product_columns = [
    column
    for column in ["source_product", "satellite", "instrument", "version"]
    if column in df.columns
]

if product_columns:

    product_summary = (
        df.groupby(
            ["sensor"] + product_columns,
            dropna=False
        )
        .agg(
            detection_count=("sensor", "size"),
            frp_sum=("frp", "sum"),
            first_date=("acq_date", "min"),
            last_date=("acq_date", "max"),
        )
        .reset_index()
    )

    print(product_summary.to_string(index=False))

    save_table(
        product_summary,
        "product_version_distribution.csv"
    )

else:
    warnings.warn("No product/version columns found.")


# ============================================================
# STEP 8: PLOTS
# ============================================================

section("STEP 8: CREATING DIAGNOSTIC PLOTS")


# Yearly detection totals.
plt.figure(figsize=(11, 5))

for sensor in SENSORS:
    subset = yearly[
        yearly["sensor"] == sensor
    ]

    plt.plot(
        subset["year"],
        subset["detection_count"],
        marker="o",
        label=sensor,
    )

plt.title("Yearly Detection Counts: Terra vs SNPP")
plt.xlabel("Year")
plt.ylabel("Recorded detections")
plt.legend()
plt.grid(alpha=0.25)

save_plot("yearly_detection_counts.png")


# Yearly FRP totals.
plt.figure(figsize=(11, 5))

for sensor in SENSORS:
    subset = yearly[
        yearly["sensor"] == sensor
    ]

    plt.plot(
        subset["year"],
        subset["frp_sum"],
        marker="o",
        label=sensor,
    )

plt.title("Yearly FRP Sum: Terra vs SNPP")
plt.xlabel("Year")
plt.ylabel("FRP sum (MW)")
plt.legend()
plt.grid(alpha=0.25)

save_plot("yearly_frp_sum.png")


# Yearly detection ratio.
ratio_data = yearly_wide.dropna(
    subset=["detection_count_SNPP_Terra_ratio"]
)

plt.figure(figsize=(11, 5))

plt.plot(
    ratio_data["year"],
    ratio_data["detection_count_SNPP_Terra_ratio"],
    marker="o",
)

plt.axhline(
    1,
    linestyle="--",
    label="Equal recorded detection counts",
)

plt.title("Yearly SNPP / Terra Detection Count Ratio")
plt.xlabel("Year")
plt.ylabel("SNPP / Terra ratio")
plt.legend()
plt.grid(alpha=0.25)

save_plot("yearly_detection_ratio.png")


# Monthly ratio by calendar month.
valid_months = monthly_wide.dropna(
    subset=["detection_ratio_SNPP_Terra"]
).copy()

valid_months["calendar_month"] = (
    valid_months["month_start"].dt.month
)

monthly_ratio_summary = (
    valid_months.groupby("calendar_month")
    ["detection_ratio_SNPP_Terra"]
    .agg(
        median="median",
        mean="mean",
        count="count",
    )
    .reset_index()
)

save_table(
    monthly_ratio_summary,
    "seasonal_detection_ratio.csv"
)

plt.figure(figsize=(11, 5))

plt.plot(
    monthly_ratio_summary["calendar_month"],
    monthly_ratio_summary["median"],
    marker="o",
)

plt.xticks(range(1, 13))
plt.title("Median SNPP / Terra Detection Ratio by Calendar Month")
plt.xlabel("Calendar month")
plt.ylabel("Median detection ratio")
plt.grid(alpha=0.25)

save_plot("seasonal_detection_ratio.png")


# Day/night yearly trends.
if "daynight" in df.columns:

    plt.figure(figsize=(11, 5))

    for sensor in SENSORS:
        for period in ["day", "night"]:

            subset = daynight[
                (daynight["sensor"] == sensor)
                & (
                    daynight["daynight_normalized"]
                    == period
                )
            ]

            plt.plot(
                subset["year"],
                subset["detection_count"],
                marker="o",
                label=f"{sensor} - {period}",
            )

    plt.title("Yearly Day/Night Detection Counts")
    plt.xlabel("Year")
    plt.ylabel("Recorded detections")
    plt.legend()
    plt.grid(alpha=0.25)

    save_plot("yearly_daynight_detection_counts.png")


# ============================================================
# STEP 9: QA REPORT
# ============================================================

section("STEP 9: SAVING QA REPORT")

qa = {
    "comparison_start_date": str(START_DATE.date()),
    "sensors": SENSORS,
    "input_file": str(INPUT_FILE),
    "comparison_rows": int(len(df)),
    "date_min": str(df["acq_date"].min().date()),
    "date_max": str(df["acq_date"].max().date()),
    "yearly_rows": int(len(yearly)),
    "monthly_periods": int(len(monthly_wide)),
    "weekly_periods": int(len(weekly_wide)),
    "yearly_sensor_detection_totals": {
        str(sensor): int(
            df.loc[df["sensor"] == sensor].shape[0]
        )
        for sensor in SENSORS
    },
    "coverage_warning": (
        "FIRMS detections-only records do not establish "
        "valid observation coverage. Missing records must "
        "not be interpreted as confirmed zero fire or "
        "confirmed sensor observation."
    ),
    "source_files_modified": False,
}

qa_path = OUTPUT_DIR / "temporal_stability_qa.json"

with open(qa_path, "w", encoding="utf-8") as file:
    json.dump(qa, file, indent=4)

print("QA saved:", qa_path)

section("TEMPORAL STABILITY DIAGNOSTICS COMPLETED")

print("Output directory:", OUTPUT_DIR)
print("Tables:", TABLE_DIR)
print("Plots:", PLOT_DIR)