# MODIS–VIIRS Sensor Harmonization Methodology

## 1. Overview

The Punjab Fire Calendar project uses satellite-derived active fire detections from two NASA FIRMS products:

1. **MODIS Terra — Standard Processing (`MODIS_SP`)**
2. **VIIRS Suomi-NPP — Standard Processing (`VIIRS_SNPP_SP`)**

These sensors differ in their spatial resolution, detection characteristics, observation systems, and historical coverage. Consequently, their raw hotspot counts cannot be assumed to be directly equivalent.

The purpose of harmonization is to create a consistent framework for analysing fire activity across both sensors while preserving their individual identities and characteristics.

Our implemented approach is called:

**Sensor-aware Relative Activity Harmonization**

It aligns spatial and temporal aggregation and uses sensor-specific historical percentile indicators to compare relative activity.

It does not apply an unvalidated universal conversion factor between MODIS and VIIRS hotspot counts.

---

## 2. Selected Satellite Products

Only two products are included in the current harmonization analysis.

| Property | MODIS | VIIRS |
|---|---|---|
| Satellite | Terra | Suomi-NPP |
| Product | MODIS_SP | VIIRS_SNPP_SP |
| Processing | Standard Processing | Standard Processing |
| Instrument | MODIS | VIIRS |
| Historical availability checked | 2000-11-01 | 2012-01-20 |
| End of availability checked | 2026-08-31 | 2026-07-31 |

**Important:**

- The direct MODIS–VIIRS comparison uses their common historical period, beginning on 2012-01-20.
- MODIS Terra observations before 2012 are retained for MODIS-only historical analysis.
- MODIS Aqua, VIIRS NOAA-20, VIIRS NOAA-21, and NRT products are excluded from this current comparison.
- Product availability dates do not guarantee that valid observations exist for every date.

---

## 3. Why Harmonization Is Necessary

MODIS and VIIRS are different satellite instruments.

Their observations may differ because of:

- Spatial resolution.
- Sensor sensitivity.
- Detection algorithms.
- Satellite observation characteristics.
- Processing versions.
- Differences in the number and distribution of detected hotspots.

For this reason, directly combining their raw detection counts could introduce misleading trends.

For example, a higher VIIRS hotspot count than MODIS does not automatically mean that actual fire activity increased.

Our methodology addresses this by establishing common spatial and temporal units and comparing each sensor against its own historical behaviour.

---

## 4. Spatial Harmonization

### 4.1 Area of Interest

The project focuses on Punjab, India.

The initial acquisition uses a bounding box:

| Boundary | Coordinate |
|---|---:|
| Minimum latitude | 29.5° N |
| Maximum latitude | 32.5° N |
| Minimum longitude | 73.8° E |
| Maximum longitude | 77.0° E |

Actual spatial clipping is performed using the Punjab geographic boundary rather than relying only on the bounding box.

### 4.2 Common Spatial Grid

A common grid was created for spatial aggregation.

| Parameter | Value |
|---|---|
| Coordinate Reference System | EPSG:32643 |
| Projection | WGS 84 / UTM Zone 43N |
| Grid resolution | 1 km |
| Total grid cells | 51,410 |
| AOI | Punjab, India |

Each valid hotspot detection is assigned to a common grid cell.

This allows MODIS and VIIRS detections to be aggregated using the same spatial framework.

**Why use a common grid?**

- Provides consistent spatial aggregation.
- Allows comparison of activity across the same geographic cells.
- Supports weekly and monthly cell-level analysis.
- Enables calculation of the number of active 1 km cells.

**Limitation:** A common grid does not make the original sensor observations identical. It standardizes the analysis framework, not the physical detection capabilities of the instruments.

---

## 5. Data Cleaning and Preparation

Before harmonization, the two products are processed using a consistent cleaning and spatial-assignment workflow.

The preparation pipeline:

1. Loads the acquired MODIS and VIIRS observations.
2. Preserves sensor and product identity.
3. Checks latitude and longitude values.
4. Removes invalid spatial records.
5. Clips detections to the Punjab boundary.
6. Assigns detections to the common 1 km grid.
7. Checks duplicate records and missing grid assignments.
8. Saves the cleaned observations.

### 5.1 Prepared Dataset

Output:

`hotspots_sqh.parquet`

Dataset summary:

| QA Metric | Result |
|---|---:|
| Total cleaned detections | 1,011,629 |
| Invalid coordinates | 0 |
| Unmatched grid assignments | 0 |
| Null grid IDs | 0 |
| Duplicate records | 0 |
| Pre-2012 MODIS Terra detections retained | 41,764 |

Pre-2012 MODIS detections are retained for historical MODIS analysis but are not included in direct MODIS–VIIRS comparison.

---

## 6. Temporal Harmonization

The cleaned observations are aggregated into common weekly and monthly periods.

### 6.1 Weekly Aggregation

- Weeks begin on Monday.
- Detections are grouped by sensor, week, and spatial grid cell.
- Weekly AOI-level summaries are also generated.

### 6.2 Monthly Aggregation

- Detections are grouped by sensor, calendar month, and spatial grid cell.
- Monthly AOI-level summaries are generated.

### 6.3 Aggregated Metrics

The following metrics are calculated:

| Metric | Meaning |
|---|---|
| `detection_count` | Number of hotspot detections |
| `frp_sum` | Total Fire Radiative Power |
| `frp_mean` | Average FRP |
| `frp_max` | Maximum FRP |
| `day_count` | Number of daytime detections |
| `night_count` | Number of nighttime detections |
| `active_cells_1km` | Number of distinct 1 km grid cells containing detections |

`active_cells_1km` represents spatially distributed detected activity. It is not an observation-adjusted estimate of burned area or fire occurrence.

### 6.4 Aggregation Outputs

| Dataset | Rows |
|---|---:|
| Weekly cell-level | 717,006 |
| Weekly AOI-level | 1,712 |
| Monthly cell-level | 615,901 |
| Monthly AOI-level | 477 |

All aggregation datasets retain sensor identity.

---

## 7. Sensor Comparison and Diagnostics

Before calculating harmonized indicators, the project evaluates differences between the two sensors.

The diagnostic workflow includes:

- Comparing MODIS and VIIRS detection counts.
- Examining FRP distributions.
- Comparing weekly and monthly activity.
- Checking common-period coverage.
- Investigating changes in sensor processing versions.
- Verifying consistency between raw, clipped, and cleaned observations.

A MODIS processing-version transition around 2023 was identified during temporal stability analysis.

This is an important consideration when interpreting long-term trends. The transition alone does not establish the cause of any observed change.

The comparison is diagnostic. It does not establish a validated conversion between MODIS and VIIRS detection counts.

---

## 8. Implemented Harmonization Method

### 8.1 Method: Sensor-Specific Historical Percentile Ranking

Instead of directly combining raw hotspot counts, the project calculates historical percentile ranks separately for each sensor.

Each sensor is evaluated against its own historical distribution.

For a current observation, the percentile rank is calculated as:

\[
P(x) = 100 \times
\frac{\text{Number of historical values } \leq x}
{\text{Total number of historical values}}
\]

Where:

- \(x\) is the current observation.
- Historical values belong to the corresponding sensor and comparison group.
- The result is expressed as a percentile from 0 to 100.

For example:

If the current weekly VIIRS detection count is greater than 90% of its historical comparison values, its historical percentile rank is approximately 90.

The same process is performed independently for MODIS.

### 8.2 Why Sensor-Specific Percentiles?

Suppose MODIS records 100 detections while VIIRS records 180 detections.

Comparing these raw numbers directly may be misleading because the sensors have different detection characteristics.

Instead, we ask:

- Is 100 detections unusually high compared with MODIS historical activity?
- Is 180 detections unusually high compared with VIIRS historical activity?

This makes it possible to compare relative activity levels without assuming that both instruments detect the same number of hotspots under equivalent conditions.

### 8.3 What the Method Achieves

The implemented methodology provides:

1. A common geographic reference grid.
2. Consistent weekly and monthly aggregation.
3. Sensor-specific historical activity indicators.
4. Preservation of original sensor-specific measurements.
5. A comparable relative-activity framework.

### 8.4 What the Method Does Not Achieve

The current method does not:

- Convert MODIS counts into VIIRS-equivalent counts.
- Convert VIIRS counts into MODIS-equivalent counts.
- Establish a universal cross-sensor calibration multiplier.
- Prove that equal percentile ranks represent equal physical fire activity.
- Remove all differences in sensor sensitivity or observation coverage.

Therefore, the outputs should be interpreted as **sensor-specific relative activity indicators**, not physically calibrated equivalent hotspot counts.

---

## 9. Harmonization Outputs

The harmonization pipeline produces weekly and monthly datasets.

| Output | Description |
|---|---|
| Weekly harmonized dataset | Sensor-specific weekly relative activity indicators |
| Monthly harmonized dataset | Sensor-specific monthly relative activity indicators |
| Harmonization parameters | Parameters and configuration used by the process |
| Harmonization QA | Validation results and quality checks |

### Output Row Counts

| Dataset | Rows |
|---|---:|
| Weekly harmonized | 718,718 |
| Monthly harmonized | 616,378 |

The outputs preserve the sensor identity and underlying measurements alongside the relative indicators.

---

## 10. Quality Assurance

The harmonization pipeline includes checks for:

- Missing sensor identifiers.
- Invalid percentile values.
- Null or invalid spatial identifiers.
- Unexpected duplicate records.
- FRP calculation issues.
- Output row counts.
- Consistency of weekly and monthly aggregation.
- Correct sensor-specific processing.

The harmonization QA output is:

`outputs/sqh/harmonization_qa.json`

Additional configuration and parameter information is stored in:

`outputs/sqh/harmonization_parameters.csv`

---

## 11. Limitations

The current approach has several limitations.

### Sensor Differences

MODIS and VIIRS have different detection characteristics. A common grid and percentile ranking cannot eliminate these differences.

### Historical Coverage

VIIRS Suomi-NPP has a shorter historical record than MODIS Terra.

### Processing Changes

Changes in processing versions can influence long-term comparisons.

### Observation Coverage

The number of recorded hotspots does not directly measure observation effort or guarantee complete satellite coverage.

### Percentile Interpretation

A percentile describes the position of an observation within its historical distribution. It is not a fire probability, fire-risk score, or physical measurement of fire intensity.

### Calibration

A validated universal cross-sensor count conversion has not been established in this project.

Further work would be required to investigate calibration using matched observations, suitable overlap periods, spatial and temporal controls, and independent validation.

---

## 12. Reproducibility

The main harmonization scripts are located in:

`pipeline/sqh/`

Important scripts include:

| Script | Purpose |
|---|---|
| `create_sqh_grid.py` | Creates the common spatial grid |
| `prepare_sqh_detections.py` | Cleans and assigns detections to grid cells |
| `aggregate_sqh.py` | Produces weekly and monthly aggregates |
| `compare_sensors.py` | Compares sensor-specific observations |
| `temporal_stability.py` | Examines temporal consistency |
| `audit_sensor_consistency.py` | Checks consistency across processing stages |
| `harmonize_sqh.py` | Generates sensor-specific relative activity indicators |

The scripts and QA outputs are maintained in the project repository.

Large Parquet datasets are maintained separately from GitHub because of their file sizes.

---

## 13. Final Summary

The Punjab Fire Calendar project implements a sensor-aware harmonization framework for MODIS Terra Standard Processing and VIIRS Suomi-NPP Standard Processing.

The methodology consists of:

1. Selecting two standard satellite products.
2. Preserving sensor-specific observations.
3. Cleaning and validating hotspot records.
4. Assigning detections to a common Punjab 1 km grid.
5. Aggregating observations into weekly and monthly periods.
6. Comparing sensor-specific measurements.
7. Calculating sensor-specific historical percentile ranks.
8. Validating outputs through quality assurance checks.

**The central principle of our methodology is that MODIS and VIIRS should be compared using a consistent analytical framework without assuming that their raw hotspot counts are physically equivalent.**

This provides a more responsible basis for analysing historical relative fire activity across the two satellite products.
