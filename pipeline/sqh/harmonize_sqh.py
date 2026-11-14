from pathlib import Path
import json
import pandas as pd
import numpy as np


ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = ROOT / "data" / "processed" / "sqh"
OUTPUT_DIR = DATA_DIR / "harmonized"
QA_DIR = ROOT / "outputs" / "sqh" / "harmonization"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
QA_DIR.mkdir(parents=True, exist_ok=True)


CONFIG = {
    "weekly": {
        "cell_file": "weekly_cell_sqh.parquet",
        "aoi_file": "weekly_aoi_sqh.parquet",
        "period_column": "week_start",
    },
    "monthly": {
        "cell_file": "monthly_cell_sqh.parquet",
        "aoi_file": "monthly_aoi_sqh.parquet",
        "period_column": "month_start",
    },
}

SENSORS = ["MODIS_Terra", "VIIRS_SNPP"]

METRICS = [
    "detection_count",
    "frp_sum",
    "active_cells_1km",
]


def prepare_level(path, level, period_column):

    df = pd.read_parquet(path).copy()

    required = [
        period_column,
        "sensor",
        "detection_count",
        "frp_sum",
    ]

    missing = [c for c in required if c not in df.columns]

    if missing:
        raise ValueError(
            f"Missing columns in {path.name}: {missing}"
        )

    df["sensor"] = df["sensor"].astype(str)

    unexpected = set(df["sensor"].unique()) - set(SENSORS)

    if unexpected:
        raise ValueError(
            f"Unexpected sensors in {path.name}: {unexpected}"
        )

    df[period_column] = pd.to_datetime(df[period_column])

    df["level"] = level

    if level == "aoi":
        df["sqh_cell_id"] = pd.NA

        if "active_cells_1km" not in df.columns:
            raise ValueError(
                "AOI data must contain active_cells_1km"
            )

    else:
        if "sqh_cell_id" not in df.columns:
            raise ValueError(
                "Cell data must contain sqh_cell_id"
            )

        df["active_cells_1km"] = np.nan

    return df


def add_percentiles(df, period_type):

    parameters = []

    group_columns = ["sensor", "level"]

    for metric in METRICS:

        if metric not in df.columns:
            df[metric] = np.nan

        output_column = {
            "detection_count": "detection_percentile",
            "frp_sum": "frp_sum_percentile",
            "active_cells_1km": "active_cells_percentile",
        }[metric]

        df[output_column] = np.nan

        for (sensor, level), indices in df.groupby(
            group_columns,
            dropna=False
        ).groups.items():

            values = pd.to_numeric(
                df.loc[indices, metric],
                errors="coerce"
            )

            valid = values.notna() & (values > 0)
            zero_values = values.notna() & (values == 0)

# Positive records receive their empirical percentile.
            if valid.sum() > 0:

             ranks = values.loc[valid].rank(
              method="average",
              pct=True
             ) * 100

            df.loc[ranks.index, output_column] = ranks

# A measured zero is assigned percentile zero.
            df.loc[values.index[zero_values], output_column] = 0.0


            if valid.sum() == 0:
             continue

            positive = values.loc[valid]

            parameters.append({
                "period_type": period_type,
                "sensor": sensor,
                "level": level,
                "metric": metric,
                "normalization_basis": (
                    "Historical positive detection records only"
                ),
                "observations": int(len(positive)),
                "minimum": float(positive.min()),
                "q10": float(positive.quantile(0.10)),
                "median": float(positive.median()),
                "q90": float(positive.quantile(0.90)),
                "maximum": float(positive.max()),
            })

    percentile_columns = [
        "detection_percentile",
        "frp_sum_percentile",
        "active_cells_percentile",
    ]

    df["activity_index"] = df[percentile_columns].mean(
        axis=1,
        skipna=True
    )

    df["normalization_method"] = (
        "sensor_specific_historical_positive_record_percentile"
    )

    df["normalization_scope"] = (
        "retrospective_full_available_history"
    )

    return df, parameters


def process_period(period_type, config):

    print(f"\nProcessing {period_type} data...")

    period_column = config["period_column"]

    cell_path = DATA_DIR / config["cell_file"]
    aoi_path = DATA_DIR / config["aoi_file"]

    cell = prepare_level(
        cell_path,
        "cell",
        period_column
    )

    aoi = prepare_level(
        aoi_path,
        "aoi",
        period_column
    )

    original_cell_rows = len(cell)
    original_aoi_rows = len(aoi)

    combined = pd.concat(
        [cell, aoi],
        ignore_index=True,
        sort=False
    )

    combined, parameters = add_percentiles(
        combined,
        period_type
    )

    # Keep predictable column order for backend integration.
    preferred = [
        period_column,
        "level",
        "sensor",
        "sqh_cell_id",
        "detection_count",
        "frp_sum",
        "frp_mean",
        "frp_max",
        "active_cells_1km",
        "day_count",
        "night_count",
        "detection_percentile",
        "frp_sum_percentile",
        "active_cells_percentile",
        "activity_index",
        "normalization_method",
        "normalization_scope",
    ]

    for column in preferred:
        if column not in combined.columns:
            combined[column] = np.nan

    combined = combined[preferred].sort_values(
        [period_column, "level", "sensor"],
        kind="stable"
    ).reset_index(drop=True)

    output_path = OUTPUT_DIR / f"{period_type}_harmonized.parquet"

    combined.to_parquet(
        output_path,
        index=False
    )

    # Verify original measurements were preserved.
    checks = {}

    for sensor in SENSORS:

        source_cell = cell[cell["sensor"] == sensor]
        output_cell = combined[
            (combined["sensor"] == sensor)
            & (combined["level"] == "cell")
        ]

        source_aoi = aoi[aoi["sensor"] == sensor]
        output_aoi = combined[
            (combined["sensor"] == sensor)
            & (combined["level"] == "aoi")
        ]

        checks[sensor] = {
            "cell_source_rows": int(len(source_cell)),
            "cell_output_rows": int(len(output_cell)),
            "aoi_source_rows": int(len(source_aoi)),
            "aoi_output_rows": int(len(output_aoi)),
            "cell_detection_count_preserved": (
                int(source_cell["detection_count"].sum())
                == int(output_cell["detection_count"].sum())
            ),
            "aoi_detection_count_preserved": (
                int(source_aoi["detection_count"].sum())
                == int(output_aoi["detection_count"].sum())
            ),
            "cell_frp_preserved": bool(np.isclose(
                source_cell["frp_sum"].sum(),
                output_cell["frp_sum"].sum()
            )),
            "aoi_frp_preserved": bool(np.isclose(
                source_aoi["frp_sum"].sum(),
                output_aoi["frp_sum"].sum()
            )),
        }

    all_passed = all(
        check["cell_source_rows"] == check["cell_output_rows"]
        and check["aoi_source_rows"] == check["aoi_output_rows"]
        and check["cell_detection_count_preserved"]
        and check["aoi_detection_count_preserved"]
        and check["cell_frp_preserved"]
        and check["aoi_frp_preserved"]
        for check in checks.values()
    )

    if not all_passed:
        raise RuntimeError(
            f"{period_type} harmonisation QA failed: {checks}"
        )

    print("Output:", output_path)
    print("Rows:", len(combined))
    print("Cell rows:", original_cell_rows)
    print("AOI rows:", original_aoi_rows)
    print("QA: PASSED")

    return combined, parameters, checks


def main():

    all_parameters = []
    qa = {
        "method": (
            "Sensor-specific empirical percentile ranking "
            "of positive historical records"
        ),
        "sensors": SENSORS,
        "important_limitations": [
            "Percentiles are calculated separately for each sensor.",
            "Positive values receive empirical percentiles; measured zero values receive percentile zero.",
            "Missing detection records are not treated as zero.",
            "Percentiles use the full available historical dataset, "
            "so they are retrospective and not leakage-free forecasts.",
            "The activity index is a relative descriptive indicator, "
            "not proof of sensor equivalence.",
            "Terra and SNPP raw measurements remain separate.",
            "No universal sensor correction factor is applied."
        ],
        "periods": {},
    }

    for period_type, config in CONFIG.items():

        combined, parameters, checks = process_period(
            period_type,
            config
        )

        all_parameters.extend(parameters)

        qa["periods"][period_type] = {
            "output_rows": int(len(combined)),
            "sensor_checks": checks,
            "null_activity_index": int(
                combined["activity_index"].isna().sum()
            ),
            "percentile_ranges": {
                column: {
                    "minimum": (
                        float(combined[column].min())
                        if combined[column].notna().any()
                        else None
                    ),
                    "maximum": (
                        float(combined[column].max())
                        if combined[column].notna().any()
                        else None
                    ),
                }
                for column in [
                    "detection_percentile",
                    "frp_sum_percentile",
                    "active_cells_percentile",
                    "activity_index",
                ]
            },
        }

    parameters_df = pd.DataFrame(all_parameters)

    parameters_path = (
        OUTPUT_DIR / "harmonization_parameters.csv"
    )

    parameters_df.to_csv(
        parameters_path,
        index=False
    )

    qa["overall_status"] = "PASSED"

    qa_path = QA_DIR / "harmonization_qa.json"

    with open(qa_path, "w", encoding="utf-8") as file:
        json.dump(
            qa,
            file,
            indent=4,
            default=str
        )

    dictionary = """# Punjab Fire Calendar — Harmonised Data Dictionary

## Output files

- weekly_harmonized.parquet
- monthly_harmonized.parquet
- harmonization_parameters.csv
- harmonization_qa.json

## Row structure

Each Parquet file combines two data levels:

- `aoi`: Punjab-wide period summary.
- `cell`: one active 1 km grid cell in a period.

The `sensor` column always identifies MODIS_Terra or VIIRS_SNPP.
The `sqh_cell_id` is populated for cell rows and null for AOI rows.

## Important columns

| Column | Meaning |
|---|---|
| week_start / month_start | Period start |
| level | `aoi` or `cell` |
| sensor | MODIS_Terra or VIIRS_SNPP |
| sqh_cell_id | Stable Punjab 1 km cell identifier |
| detection_count | Number of FIRMS detections |
| frp_sum | Sum of fire radiative power |
| frp_mean | Mean FRP |
| frp_max | Maximum FRP |
| active_cells_1km | Number of active 1 km cells; AOI rows only |
| day_count | Daytime detections |
| night_count | Nighttime detections |
| detection_percentile | Sensor-specific historical percentile of positive detection count |
| frp_sum_percentile | Sensor-specific historical percentile of positive FRP sum |
| active_cells_percentile | Sensor-specific AOI percentile of active 1 km cells |
| activity_index | Mean of the available percentile indicators |
| normalization_method | Method used to calculate percentiles |
| normalization_scope | Full available historical record |

## How to use

- Filter `level = 'aoi'` for Punjab-wide time series and KPI cards.
- Filter `level = 'cell'` for map layers and grid-level analysis.
- Filter `sensor` to select Terra or SNPP.
- Use original `detection_count` and `frp_sum` when displaying physical measurements.
- Use percentile fields and `activity_index` for relative activity visualisation.

## Important limitations

These percentiles are calculated separately for each sensor, using positive
historical records across the full available period.

They are retrospective descriptive ranks, not prospective anomaly scores.
A missing row is not an observed zero. FIRMS detections alone do not provide
complete sensor observation coverage.

Terra and SNPP are not declared equivalent. Do not add their measurements
together or interpret equal percentile scores as equal fire counts or FRP.
"""

    dictionary_path = OUTPUT_DIR / "data_dictionary.md"

    dictionary_path.write_text(
        dictionary,
        encoding="utf-8"
    )

    print("\n" + "=" * 55)
    print("HARMONISATION COMPLETED")
    print("=" * 55)
    print("Weekly:", OUTPUT_DIR / "weekly_harmonized.parquet")
    print("Monthly:", OUTPUT_DIR / "monthly_harmonized.parquet")
    print("Parameters:", parameters_path)
    print("QA:", qa_path)
    print("Data dictionary:", dictionary_path)


if __name__ == "__main__":
    main()
