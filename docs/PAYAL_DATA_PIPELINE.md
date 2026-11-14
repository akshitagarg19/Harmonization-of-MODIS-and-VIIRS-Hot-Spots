# Punjab Fire Calendar
### Processing, Comparing and Harmonizing MODIS and VIIRS Active Fire Observations

## 1. Project Overview

Punjab Fire Calendar is a satellite-based fire activity analysis project that processes historical active-fire observations from NASA's Fire Information for Resource Management System (FIRMS).

The project uses two satellite data products:

1. **MODIS Standard Processing (MODIS_SP)** — observations from the Terra satellite.
2. **VIIRS S-NPP Standard Processing (VIIRS_SNPP_SP)** — observations from the Suomi National Polar-orbiting Partnership satellite.

Our objective is to build a consistent spatial and temporal framework for analysing fire activity across Punjab, India.

The pipeline processes raw satellite observations into cleaned hotspot datasets, spatial aggregations, sensor comparison tables, harmonized activity indicators, historical baselines and anomaly classifications.

The final outputs help identify periods of unusually high recorded fire activity relative to the historical observations available for the same sensor and seasonal period.

---

## 2. Project Objectives

The main objectives are:

- Acquire historical MODIS and VIIRS active-fire observations from NASA FIRMS.
- Preserve original satellite observations and maintain a reproducible processing pipeline.
- Clean and validate hotspot records.
- Restrict observations to the Punjab Area of Interest (AOI).
- Assign observations to a common spatial grid.
- Aggregate hotspot activity into weekly and monthly time periods.
- Compare MODIS and VIIRS observations over their common operational period.
- Investigate differences between the two sensors.
- Develop sensor-aware harmonized activity indicators.
- Generate historical seasonal baselines.
- Identify elevated and extreme activity periods.
- Produce structured datasets and QA reports for the project's frontend and further analysis.

---

## 3. Data Sources and Satellite Products

All active-fire observations are obtained from NASA FIRMS.

Official source: https://firms.modaps.eosdis.nasa.gov/

### 3.1 Products Used

The current SQH (Spatial and Quantitative Harmonization) analysis uses two products.

| Product ID | Satellite | Instrument | Data type |
|---|---|---|---|
| MODIS_SP | Terra | MODIS | Standard Processing |
| VIIRS_SNPP_SP | Suomi NPP | VIIRS | Standard Processing |

We selected these products to establish a comparison between the MODIS Terra and VIIRS S-NPP active-fire observation systems.

**Scope exclusions:**

- MODIS Aqua is not included in the current SQH comparison.
- VIIRS NOAA-20 is excluded.
- VIIRS NOAA-21 is excluded.
- Near Real-Time (NRT) observations are not mixed into the main historical standard-product analysis.

This keeps the current comparison focused on two defined satellite products rather than combining observations from additional sensors with different characteristics.

### 3.2 Historical Availability

The FIRMS availability information checked for the products was:

| Product | Available period |
|---|---|
| MODIS_SP | 2000-11-01 to 2026-08-31 |
| VIIRS_SNPP_SP | 2012-01-20 to 2026-07-31 |

The direct comparison between the two products uses their common period, beginning on **2012-01-20**.

MODIS Terra observations before 2012 are retained for historical MODIS analysis, but are not used for direct MODIS–VIIRS comparison.

Availability dates indicate the product availability checked through FIRMS; they should not be interpreted as proof that every date has valid observations.

### 3.3 Acquisition Method

The acquisition workflow uses historical FIRMS archive downloads rather than relying on NRT data for the main analysis.

The general acquisition process is:

1. Select the required FIRMS product.
2. Request historical observations for the Punjab region.
3. Preserve the downloaded source files.
4. Keep product and satellite information identifiable.
5. Process the acquired observations through the cleaning and spatial preparation stages.

An initial geographic bounding box used for regional acquisition was:

- Latitude: 29.5°N to 32.5°N
- Longitude: 73.8°E to 77.0°E

The Punjab geographic boundary is used for the actual spatial clipping and AOI definition.

---

## 4. Geographic Area of Interest

The primary study region is Punjab, India.

The project uses a geographic boundary file to identify observations belonging to the study region.

### Spatial processing

The geographic workflow consists of:

1. Loading the Punjab boundary.
2. Validating geographic coordinates.
3. Restricting observations to the Punjab region.
4. Creating a consistent spatial grid.
5. Assigning hotspot observations to grid cells.

### SQH Grid

A spatial grid was generated for the study region.

| Property | Value |
|---|---|
| Coordinate reference system | EPSG:32643 |
| Projection | WGS 84 / UTM zone 43N |
| Nominal grid resolution | 1 km |
| Number of grid cells | 51,410 |

The grid provides a common spatial reference for MODIS Terra and VIIRS S-NPP observations.

Both sensors are assigned to the same grid so their activity can be examined at corresponding spatial locations.

The grid is generated independently of the sensor observations, ensuring that the spatial framework is consistent.

---

## 5. Data Processing Pipeline

The project follows a staged processing architecture.

```text
NASA FIRMS
    |
    v
Historical Data Acquisition
    |
    v
Raw MODIS and VIIRS Files
    |
    v
Data Cleaning and Validation
    |
    v
Punjab AOI Filtering
    |
    v
SQH Grid Generation
    |
    v
Spatial Detection Assignment
    |
    v
Weekly and Monthly Aggregation
    |
    v
Sensor Comparison and Diagnostics
    |
    v
Sensor-Aware Harmonization
    |
    v
Historical Seasonal Baselines
    |
    v
Anomaly Classification
    |
    v
Final Analysis Tables and QA Reports
```

### 5.1 Data Cleaning

The raw satellite observations are prepared before spatial and temporal analysis.

The processing includes:

- Checking required columns.
- Validating latitude and longitude.
- Removing invalid geographic records.
- Standardizing relevant data fields.
- Preserving acquisition date and time.
- Retaining satellite and instrument identification.
- Checking missing values in important fields.
- Checking duplicate observations.
- Preparing consistent hotspot records for downstream processing.

The cleaned dataset retains relevant fire-observation attributes, including:

- Latitude
- Longitude
- Acquisition date
- Acquisition time
- Satellite
- Instrument
- Confidence
- Fire radiative power (FRP)
- Day/night information
- Brightness-related attributes where available

Invalid or unmatched spatial records are checked through QA reports rather than silently accepted.

### 5.2 Spatial Detection Assignment

Each cleaned hotspot observation is assigned to the common 1 km SQH grid.

This makes it possible to analyse:

- Hotspot detections within each grid cell.
- The number of distinct active grid cells.
- Spatial changes in recorded fire activity.
- MODIS and VIIRS activity at comparable locations.

The final spatially prepared dataset is:

`hotspots_sqh.parquet`

Validated dataset statistics:

| Metric | Result |
|---|---:|
| Total records | 1,011,629 |
| Invalid coordinates | 0 |
| Unmatched grid assignments | 0 |
| Null grid IDs | 0 |
| Duplicate records | 0 |
| Retained pre-2012 Terra records | 41,764 |

The dataset contains the two selected sensors: MODIS Terra and VIIRS S-NPP.

---

## 6. Weekly and Monthly Aggregation

After spatial assignment, hotspot observations are aggregated into weekly and monthly datasets.

The aggregation stage produces both grid-cell-level and AOI-level statistics.

### 6.1 Weekly Aggregation

Weekly aggregation uses Monday-start calendar weeks.

For each sensor and time period, the pipeline calculates:

- Detection count
- FRP sum
- FRP mean
- FRP maximum
- Daytime detection count
- Nighttime detection count
- Number of active 1 km grid cells

### 6.2 Monthly Aggregation

The same general metrics are calculated for monthly periods.

This supports longer-term seasonal and monthly analysis.

### 6.3 Aggregation Outputs

| Dataset | Rows |
|---|---:|
| weekly_cell_sqh.parquet | 717,006 |
| weekly_aoi_sqh.parquet | 1,712 |
| monthly_cell_sqh.parquet | 615,901 |
| monthly_aoi_sqh.parquet | 477 |

The distinction between cell-level and AOI-level datasets is important:

- **Cell-level datasets:** describe activity within individual 1 km grid cells.
- **AOI-level datasets:** describe aggregated activity across the entire Punjab study region.

### 6.4 Important Metric Definition

`active_cells_1km` represents the number of distinct 1 km grid cells containing at least one recorded hotspot detection during the aggregation period.

It is a measure of spatial detection extent, not an observation-adjusted estimate of fire activity.

---

## 7. MODIS–VIIRS Sensor Comparison

MODIS and VIIRS use different instruments and observation characteristics.

Therefore, their raw detection counts should not automatically be interpreted as equivalent measurements.

Before developing harmonized indicators, we conducted sensor comparison and consistency investigations.

The comparison stage examines:

- Differences in hotspot detection counts.
- Differences in FRP distributions.
- Differences in active grid cells.
- Weekly and monthly temporal patterns.
- Spatial differences between sensor detections.
- Sensor-specific historical behaviour.
- Changes in temporal stability.

### Common Comparison Period

Direct comparison starts on 2012-01-20, when both selected products are available.

MODIS Terra records before this date are retained separately for MODIS historical analysis.

### Temporal Stability Analysis

The pipeline also examines sensor behaviour over time.

A MODIS product/version transition around 2023 was identified during the investigation.

This is treated as a potential factor affecting temporal consistency. The analysis does not claim that the transition alone explains observed changes in detection counts.

### Sensor Consistency Audit

A separate audit checks consistency between:

- Raw observations.
- Geographic clipping.
- Cleaned observations.
- Spatially assigned detections.

The audit helps identify processing-related differences before interpreting sensor comparisons scientifically.

---

## 8. Sensor Harmonization

### 8.1 Why Harmonization Is Needed

MODIS and VIIRS are different satellite observation systems.

They differ in:

- Spatial resolution.
- Instrument characteristics.
- Observation geometry.
- Detection sensitivity.
- Overpass characteristics.
- Fire detection behaviour.

Consequently, the same real-world fire event may not produce the same number of hotspot detections in both products.

Directly combining raw MODIS and VIIRS detection counts can therefore introduce misleading comparisons.

Our approach is to preserve sensor identity and develop comparable spatial and temporal activity indicators without assuming that the raw observations are interchangeable.

### 8.2 Common Spatial and Temporal Framework

The first step in harmonization is to place both sensors into a shared analysis framework.

We use:

- The same Punjab AOI.
- The same EPSG:32643 spatial reference system.
- The same nominal 1 km grid.
- Consistent weekly and monthly aggregation periods.
- Consistent metric definitions.

This allows both sensors to be analysed at matching spatial and temporal scales.

### 8.3 Sensor-Specific Historical Percentiles

The harmonization stage calculates retrospective historical percentile ranks separately for each sensor.

The purpose is to describe how unusual a particular observation period is relative to that sensor's own historical behaviour.

For a metric value \(x\), the empirical percentile rank is calculated as:

\[
P(x) = 100 \times
\frac{\text{Number of historical values } \leq x}
{\text{Number of historical values}}
\]

The calculation is performed separately for the relevant sensor and analysis level.

Metrics include:

- Detection count.
- FRP sum.
- FRP mean and maximum in the aggregation datasets.
- Active 1 km grid cells.

The sensor-specific historical percentile approach helps compare relative activity patterns without assuming that identical raw counts represent identical fire conditions.

### 8.4 What This Harmonization Does and Does Not Mean

The current implementation provides a common spatial-temporal framework and sensor-specific relative activity indicators.

It does not establish a universal conversion factor between MODIS and VIIRS raw hotspot counts.

It does not claim that every VIIRS detection has an equivalent MODIS detection or vice versa.

The sensor comparison and calibration investigations are retained as diagnostic work. A fully validated universal cross-sensor count calibration has not been established.

### 8.5 Harmonization Outputs

The main harmonization outputs are:

- `weekly_aoi_harmonized.parquet`
- `monthly_aoi_harmonized.parquet`
- Corresponding harmonized cell-level datasets.
- `harmonization_parameters.csv`
- `harmonization_qa.json`

Validated output sizes:

| Dataset | Rows |
|---|---:|
| Weekly harmonized output | 718,718 |
| Monthly harmonized output | 616,378 |

The harmonized datasets preserve sensor-specific information and relative historical activity indicators.

---

## 9. Historical Baselines and Anomaly Detection

After harmonization, the project generates historical seasonal baselines and identifies periods with elevated activity.

The implementation is available in:

`pipeline/anomalies/build_baselines.py`

### 9.1 Baseline Methodology

Baselines are calculated separately for each sensor and seasonal period.

Two temporal frequencies are supported:

**Weekly baselines**
- Grouped by ISO calendar week.
- Compare observations with previous years' observations for the same seasonal week.

**Monthly baselines**
- Grouped by calendar month.
- Compare observations with previous years' observations for the same calendar month.

Only previous-year observations are used when calculating the historical reference for a current period.

This avoids using future observations to establish a past period's baseline.

### 9.2 Baseline Metrics

Three main metrics are used:

1. `detection_count`
2. `frp_sum`
3. `active_cells_1km`

For each metric, the baseline calculation produces:

- 25th percentile (P25)
- Median (P50)
- 75th percentile (P75)
- 90th percentile (P90)
- Historical percentile rank
- Number of historical observations (`history_count`)

### 9.3 Anomaly Classification

Metric-level activity is classified using historical percentile thresholds.

| Condition | Classification |
|---|---|
| At or below P75 | Normal |
| Above P75 and at or below P90 | Elevated |
| Above P90 | Extreme |
| Fewer than 3 previous observations | Insufficient history |

The overall activity score is calculated as the mean of the three metric percentile ranks when all required metric ranks are available.

Overall classification:

| Activity score | Classification |
|---|---|
| At or below 75 | Normal |
| Above 75 and at or below 90 | Elevated |
| Above 90 | Extreme |
| Not available | Insufficient history |

The overall score is a descriptive activity indicator, not a statistically validated anomaly probability or fire-risk probability.

### 9.4 Important Missing-Period Limitation

The current baseline implementation uses periods with recorded hotspot detections.

A period absent from the input dataset is not automatically interpreted as zero fire activity.

Without reliable observation-coverage information, missing records cannot be treated as proof of no fire.

Therefore, the baseline results should be interpreted as:

**Historical seasonal baselines among recorded hotspot periods.**

They are not yet a complete calendar-based anomaly system with observation-adjusted zero-activity periods.

### 9.5 Anomaly Outputs

The pipeline generates:

- `weekly_aoi_anomalies.parquet`
- `monthly_aoi_anomalies.parquet`
- `weekly_critical_periods.csv`
- `monthly_critical_periods.csv`
- `weekly_baseline_qa.json`
- `monthly_baseline_qa.json`

### 9.6 Final Anomaly Results

**Weekly results**

| Classification | Number of records |
|---|---:|
| Normal | 1,035 |
| Insufficient history | 317 |
| Extreme | 197 |
| Elevated | 163 |
| Total | 1,712 |

Total weekly critical periods (elevated + extreme): **360**.

**Monthly results**

| Classification | Number of records |
|---|---:|
| Normal | 303 |
| Insufficient history | 72 |
| Elevated | 58 |
| Extreme | 44 |
| Total | 477 |

Total monthly critical periods (elevated + extreme): **102**.

These counts describe the classifications produced by the current dataset and methodology. They are not counts of confirmed emergencies or independently verified fire events.

---

## 10. Quality Assurance and Validation

Quality assurance is performed at multiple stages.

The project includes checks for:

- Invalid coordinates.
- Missing or null spatial grid assignments.
- Duplicate hotspot records.
- Spatial assignment consistency.
- Weekly and monthly aggregation integrity.
- Sensor-specific processing consistency.
- Harmonization output consistency.
- Historical baseline calculations.
- Previous-year-only baseline usage.
- Missing historical observations.

### Baseline Validation

The final baseline validation produced:

| Check | Weekly | Monthly |
|---|---:|---:|
| Input/output records | 1,712 | 477 |
| History-count mismatches | 0 | 0 |
| Previous-year-only history check | Passed | Passed |

The baseline stage also correctly identifies periods with insufficient historical data.

QA reports are stored in `outputs/sqh/`.

---

## 11. Project Directory Structure

The repository contains the processing code, documentation and lightweight analysis outputs.

```text
project/
│
├── pipeline/
│   │
│   ├── anomalies/
│   │   ├── build_baselines.py
│   │   └── __init__.py
│   │
│   └── sqh/
│       ├── create_sqh_grid.py
│       ├── prepare_sqh_detections.py
│       ├── aggregate_sqh.py
│       ├── compare_sensors.py
│       ├── audit_sensor_consistency.py
│       ├── temporal_stability.py
│       ├── harmonize_sqh.py
│       ├── settings.py
│       └── __init__.py
│
├── data/
│   ├── raw/
│   ├── boundaries/
│   └── processed/
│       └── sqh/
│
├── outputs/
│   └── sqh/
│       ├── anomalies/
│       ├── baselines/
│       ├── aggregation_qa.json
│       ├── detection_assignment_qa.json
│       ├── grid_qa.json
│       ├── harmonization_parameters.csv
│       ├── harmonization_qa.json
│       ├── sensor_comparison_qa.json
│       ├── sensor_consistency_qa.json
│       └── temporal_stability_qa.json
│
├── docs/
│   ├── sqh/
│   │   └── data_dictionary.md
│   └── PAYAL_DATA_PIPELINE.md
│
├── requirements.txt
├── .gitignore
└── README.md
```

Large raw and processed datasets are maintained separately from the GitHub source repository.

They should be distributed through the team's shared data storage.

---

## 12. Main Pipeline Scripts

| Script | Purpose |
|---|---|
| `create_sqh_grid.py` | Creates the Punjab 1 km spatial grid |
| `prepare_sqh_detections.py` | Prepares and assigns cleaned detections to grid cells |
| `aggregate_sqh.py` | Generates weekly and monthly cell/AOI aggregations |
| `compare_sensors.py` | Compares MODIS and VIIRS activity |
| `audit_sensor_consistency.py` | Checks processing consistency |
| `temporal_stability.py` | Investigates changes in sensor behaviour over time |
| `harmonize_sqh.py` | Generates sensor-aware harmonized activity indicators |
| `build_baselines.py` | Calculates historical baselines and anomaly classifications |

Additional scripts in the repository support the earlier data acquisition, cleaning, clipping and calibration investigations.

---

## 13. Technologies Used

- Python
- NumPy
- Pandas
- GeoPandas
- Shapely
- PyArrow
- Matplotlib
- NASA FIRMS

### Data Formats

| Format | Usage |
|---|---|
| CSV | Raw downloads, critical-period exports and analysis tables |
| Parquet | Large processed datasets and aggregated observations |
| GeoJSON | Geographic boundaries |
| JSON | QA reports and processing metadata |

---

## 14. Scientific Limitations and Interpretation

The results must be interpreted within the limits of satellite active-fire observations.

1. A hotspot detection is not necessarily a unique fire event.
2. MODIS and VIIRS have different observation and detection characteristics.
3. Raw detection counts should not be treated as directly equivalent across sensors.
4. Missing observations do not establish that no fire occurred.
5. Active grid cells measure the spatial extent of recorded detections, not observation-adjusted fire activity.
6. Historical percentile ranks are calculated separately for each sensor.
7. Baseline classifications are based on recorded hotspot periods and available historical observations.
8. The composite activity score is descriptive and is not a validated fire-risk or emergency probability.
9. Sensor version transitions and other temporal changes may affect long-term consistency.
10. Further validation against independent fire and ground-observation datasets would be needed before making operational fire-risk claims.

The system is intended for historical fire-activity analysis and identification of unusually active recorded periods.

---

## 15. Current Project Status

| Stage | Status |
|---|---|
| FIRMS product selection | Completed |
| Historical acquisition workflow | Developed |
| Punjab geographic preparation | Completed |
| SQH grid generation | Completed |
| Hotspot preparation and spatial assignment | Completed |
| Weekly/monthly aggregation | Completed |
| Sensor comparison | Completed |
| Sensor consistency audit | Completed |
| Temporal stability investigation | Completed |
| Sensor-aware harmonization | Completed |
| Historical seasonal baselines | Completed |
| Weekly/monthly anomaly classification | Completed |
| Baseline validation | Passed |
| Frontend/API integration | Separate development stage |
| Independent operational validation | Future work |

---

## 16. Future Work

Potential future improvements include:

- Integrating observation coverage information into the baseline methodology.
- Supporting explicit zero-activity periods only where coverage is established.
- Further investigating MODIS and VIIRS sensor differences.
- Developing and independently validating cross-sensor calibration.
- Expanding the framework to additional regions.
- Integrating the processed datasets into the interactive Fire Calendar.
- Developing API endpoints for weekly series, monthly summaries, anomaly periods, hotspot maps and data exports.
- Validating results against independent fire datasets and ground observations.

---

## 17. Acknowledgements and Data Source

This project uses active-fire observations distributed through NASA's Fire Information for Resource Management System (FIRMS).

NASA FIRMS:
https://firms.modaps.eosdis.nasa.gov/

The project processes satellite observations for research and analytical purposes. Its outputs should not be interpreted as a replacement for official fire monitoring, emergency services or ground-based verification.

---

**Project:** Punjab Fire Calendar  
**Core data products:** MODIS Terra Standard Processing and VIIRS S-NPP Standard Processing  
**Spatial framework:** Punjab, India — EPSG:32643, nominal 1 km grid  
**Analysis frequencies:** Weekly and monthly  
**Core processing:** Acquisition → Cleaning → Spatial Assignment → Aggregation → Sensor Comparison → Harmonization → Historical Baselines → Anomaly Classification
