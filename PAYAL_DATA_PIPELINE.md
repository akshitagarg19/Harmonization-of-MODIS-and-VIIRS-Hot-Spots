# Punjab Fire Calendar
### Harmonization of MODIS and VIIRS Active Fire Data

## Project Overview

Punjab Fire Calendar is a data-processing project focused on collecting, cleaning, analysing, and preparing historical active-fire observations from NASA's MODIS and VIIRS satellite instruments.

The project aims to build a consistent historical dataset of active-fire detections across Punjab, India. It combines observations from multiple satellite sensors and prepares them for temporal, spatial, and sensor-level analysis.

The processed data will support the development of a fire-calendar system that can help identify historical fire activity patterns and provide a foundation for future analysis.

## Objectives

- Collect historical MODIS and VIIRS active-fire observations.
- Prepare and clip hotspot data to the Punjab study region.
- Clean and standardise observations from different satellite sensors.
- Preserve sensor-specific information while creating common fields.
- Aggregate detections by grid cell, week, month, and district.
- Compare MODIS and VIIRS observations during overlapping periods.
- Prepare reliable datasets for future sensor harmonisation and analysis.

## Study Area

The current processing workflow focuses on **Punjab, India**.

The study region is configured using the project's geographic settings and Punjab boundary data.

The pipeline uses a globally aligned **0.25° × 0.25° grid** for spatial aggregation.

## Satellite Data Sources

The project uses active-fire observations from two NASA satellite instrument families.

| Sensor family | Satellites |
|---|---|
| MODIS | Terra and Aqua |
| VIIRS | Suomi-NPP, NOAA-20, NOAA-21 |

Data are collected through NASA FIRMS (Fire Information for Resource Management System).

Source: [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/)

MODIS and VIIRS observations have different sensor characteristics and detection capabilities. Their raw detection counts should therefore not be treated as directly equivalent.

## Data Processing Workflow

The processing pipeline follows these main stages:

1. **Data acquisition**  
   Collect historical MODIS and VIIRS active-fire observations for the study region.

2. **Geographic preparation**  
   Prepare the Punjab boundary and district polygons used for spatial processing.

3. **Clipping**  
   Retain hotspot observations located within the Punjab study region.

4. **Cleaning and standardisation**  
   Standardise important fields, handle confidence information, preserve sensor-specific attributes, and remove exact duplicate records.

5. **Spatial and temporal aggregation**  
   Aggregate observations into grid-cell, weekly, monthly, and district-level datasets.

6. **Sensor-family aggregation**  
   Prepare combined MODIS and VIIRS summaries while retaining the distinction between the two sensor families.

7. **Overlap-pair preparation**  
   Identify spatial and temporal overlaps between MODIS and VIIRS observations for future harmonisation analysis.

8. **Quality assurance**  
   Check missing values, duplicate records, row counts, district assignments, and aggregation consistency.

Detailed implementation and processing information is documented in [`PAYAL_DATA_PIPELINE.md`](PAYAL_DATA_PIPELINE.md).

## Corrected Clean Dataset

The latest corrected cleaning pipeline produced:

| Metric | Result |
|---|---:|
| Total cleaned observations | 1,876,200 |
| MODIS observations | 369,486 |
| VIIRS observations | 1,506,714 |
| Missing sensor values | 0 |
| Missing coordinates | 0 |
| Missing timestamps | 0 |
| Missing grid IDs | 0 |
| Exact duplicate full rows | 0 |

### Sensor-wise observations

| Sensor | Observations |
|---|---:|
| VIIRS Suomi-NPP | 936,691 |
| VIIRS NOAA-20 | 472,650 |
| MODIS Aqua | 294,548 |
| VIIRS NOAA-21 | 97,373 |
| MODIS Terra | 74,938 |
| **Total** | **1,876,200** |

### Confidence distribution

| Confidence category | Observations |
|---|---:|
| Nominal | 1,753,854 |
| High | 122,346 |
| **Total retained** | **1,876,200** |

Low-confidence detections were excluded from the corrected clean dataset.

The corrected pipeline removes exact duplicate records rather than applying the previous approximate spatial-and-time deduplication rule. This avoids unintentionally merging nearby detections that may represent distinct observations.

## Aggregated Datasets

The cleaned observations are aggregated at multiple spatial and temporal levels.

| Dataset | Rows | Total detections |
|---|---:|---:|
| Weekly grid-cell | 82,456 | 1,876,200 |
| Monthly grid-cell | 35,490 | 1,876,200 |
| Weekly Punjab AOI | 3,363 | 1,876,200 |
| Monthly Punjab AOI | 905 | 1,876,200 |

The aggregated datasets retain detection counts and corresponding fire radiative power (FRP) summaries.

## District-Level Processing

Hotspots are assigned to Punjab districts using:

- Strict point-within-polygon spatial assignment.
- Nearest-district fallback for detections not assigned by the strict spatial join.
- A maximum permitted fallback distance of 30 metres.

Latest district assignment results:

| Metric | Result |
|---|---:|
| Punjab districts represented | 22 |
| Missing district assignments | 0 |
| Fallback assignments | 144 |
| Maximum fallback distance | 26.502 metres |

District-level aggregation totals reconcile with the cleaned observation count of **1,876,200**.

## MODIS–VIIRS Overlap Preparation

The project prepares six pairwise overlap datasets:

- MODIS Aqua – VIIRS Suomi-NPP
- MODIS Aqua – VIIRS NOAA-20
- MODIS Aqua – VIIRS NOAA-21
- MODIS Terra – VIIRS Suomi-NPP
- MODIS Terra – VIIRS NOAA-20
- MODIS Terra – VIIRS NOAA-21

The current overlap analysis identifies shared-positive cell-week observations.

| Sensor pair | Day | Night |
|---|---:|---:|
| Aqua – Suomi-NPP | 11,919 | 179 |
| Aqua – NOAA-20 | 6,614 | 120 |
| Aqua – NOAA-21 | 2,403 | 61 |
| Terra – Suomi-NPP | 7,272 | 434 |
| Terra – NOAA-20 | 3,799 | 236 |
| Terra – NOAA-21 | 1,138 | 122 |

These datasets are intended for further sensor-comparison and harmonisation work.

The overlap counts are not calibration results. In particular, the available shared-positive night observations are limited and require further investigation before reliable night-time calibration can be attempted.

## Quality Assurance

The corrected pipeline includes checks for:

- Missing sensor identifiers.
- Missing coordinates and timestamps.
- Missing grid-cell identifiers.
- Exact duplicate records.
- District assignment completeness.
- Aggregation row counts and detection totals.
- MODIS and VIIRS family-level reconciliation.
- Pairwise overlap dataset consistency.

QA reports are available in the `outputs/` directory.

These checks establish processing consistency. They do not, by themselves, prove that every satellite detection corresponds to a unique real-world fire or that observations from different sensors are equivalent.

## Important Limitations

- The current processed study region is Punjab, India.
- MODIS and VIIRS have different detection characteristics.
- Raw detection counts from different sensors are not directly interchangeable.
- Shared-positive overlap counts are not validated calibration coefficients.
- Night-time overlap support is limited.
- Industrial heat sources and other non-vegetation thermal sources may remain in the dataset because land-cover-based filtering has not yet been applied.
- Further validation is required before producing final harmonised datasets or drawing conclusions about sensor equivalence.

## Repository Structure

```text
.
├── config/
├── data/
│   ├── raw/
│   └── processed/
├── pipeline/
│   ├── clean_hotspots.py
│   ├── aggregate_hotspots.py
│   ├── aggregate_districts.py
│   ├── build_overlap_pairs.py
│   └── audit_processed_data.py
├── outputs/
├── docs/
│   └── cleaning_rules.md
├── PAYAL_DATA_PIPELINE.md
└── README.md
```

This is a high-level representation of the project structure. Refer to the repository for the complete file inventory.

## Project Status

| Component | Status |
|---|---|
| Punjab hotspot data preparation | Completed |
| Corrected hotspot cleaning | Completed |
| Weekly and monthly aggregation | Completed |
| District-level assignment and aggregation | Completed |
| MODIS and VIIRS family aggregation | Completed |
| MODIS–VIIRS overlap-pair preparation | Completed |
| Processing quality checks | Completed |
| Sensor harmonisation validation | Pending further analysis |
| Final harmonised dataset | Pending |

## Documentation

- [`PAYAL_DATA_PIPELINE.md`](PAYAL_DATA_PIPELINE.md) — Detailed data pipeline and processing documentation.
- [`docs/cleaning_rules.md`](docs/cleaning_rules.md) — Cleaning and standardisation rules.

## Acknowledgements

This project uses active-fire data provided by NASA FIRMS and satellite observations from the MODIS and VIIRS instruments.
