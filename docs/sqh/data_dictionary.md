# Punjab Fire Calendar — Harmonised Data Dictionary

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
