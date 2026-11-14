\# Punjab MODIS–VIIRS Active Fire Data Pipeline



\*\*Contribution:\*\* Data Acquisition, Cleaning, Aggregation, Quality Assurance and Sensor Harmonisation Investigation  

\*\*Study Region:\*\* Punjab, India  

\*\*Data Source:\*\* NASA Fire Information for Resource Management System (FIRMS)  

\*\*Primary Tools:\*\* Python, Pandas, GeoPandas, NumPy, PyArrow, Shapely



\---



\## 1. Project Overview



This contribution develops a data-processing pipeline for analysing satellite-detected active-fire observations across Punjab, India, using historical MODIS and VIIRS data from NASA FIRMS.



The objective is to prepare clean, geographically organised and aggregated datasets that can support the team's fire-calendar application and further analysis.



The pipeline processes observations from five satellite sensors:



| Sensor | Satellite |

|---|---|

| MODIS Terra | Terra |

| MODIS Aqua | Aqua |

| VIIRS SNPP | Suomi-NPP |

| VIIRS NOAA-20 | NOAA-20 |

| VIIRS NOAA-21 | NOAA-21 |



The pipeline produces cleaned observations, spatial and temporal aggregations, district-level summaries, sensor-family datasets and exploratory sensor-overlap datasets.



\*\*Important:\*\* These records represent satellite-detected active-fire observations. They should not automatically be interpreted as unique fires, confirmed wildfires or verified agricultural burning events.



\---



\## 2. Study Region and Configuration



The current implementation focuses on Punjab, India.



Configuration is maintained in:



`config/punjab.py`



Current configuration:



| Parameter | Value |

|---|---|

| Study region | Punjab, India |

| Minimum latitude | 29.5 |

| Maximum latitude | 32.5 |

| Minimum longitude | 73.8 |

| Maximum longitude | 77.0 |

| Starting year | 2000 |

| Spatial grid resolution | 0.25° |

| Time zone | Asia/Kolkata |



The geographic preparation stage includes the Punjab state boundary and its 22 district boundaries.



The current pipeline is Punjab-focused. It should not yet be described as globally validated or ready for arbitrary user-selected AOIs.



\---



\## 3. Data Sources and Acquisition



Historical active-fire observations are obtained from NASA FIRMS.



Source: https://firms.modaps.eosdis.nasa.gov/



The pipeline uses historical archives for the five sensors listed above.



Raw downloads are maintained separately from the Git repository because of their size.



The acquisition and availability-checking code includes:



\- `pipeline/check\_availability.py`

\- `pipeline/download\_punjab\_boundary.py`



The FIRMS API key is loaded through an environment variable using `python-dotenv`.



API credentials must never be committed to GitHub. The `.env` file is excluded through `.gitignore`.



\---



\## 4. Processing Workflow



The data pipeline is organised into the following stages.



\### Stage A — Geographic Preparation



Relevant scripts:



\- `pipeline/download\_punjab\_boundary.py`

\- `pipeline/prepare\_punjab\_districts.py`



Tasks:



1\. Obtain the Punjab state boundary.

2\. Prepare the district boundary dataset.

3\. Validate geographic features.

4\. Prepare the spatial boundaries required for clipping and district aggregation.



Outputs include:



\- `data/boundaries/punjab\_state\_boundary.geojson`

\- `data/boundaries/punjab\_districts.geojson`



\### Stage B — Data Inspection, Clipping and Cleaning



Relevant scripts:



\- `pipeline/inspect\_raw\_data.py`

\- `pipeline/clip\_punjab\_data.py`

\- `pipeline/clean\_hotspots.py`



Tasks:



1\. Inspect the historical sensor datasets.

2\. Retain observations falling within the Punjab study region.

3\. Apply data-quality filtering.

4\. Handle duplicate observations.

5\. Standardise date and timestamp fields.

6\. Prepare UTC and Indian Standard Time representations.

7\. Add day/night information and spatial grid identifiers.

8\. Generate cleaning and clipping quality reports.



The cleaning stage applies the project's confidence and data-quality rules. Records removed during cleaning are not included in the final cleaned dataset.



\*\*Main cleaned dataset:\*\*



`data/processed/hotspots\_clean.parquet`



The cleaned dataset contains approximately \*\*1,595,863 retained observations\*\*.



The larger cleaned and pre-cleaning datasets are maintained separately from the Git repository.



\### Stage C — Temporal and Spatial Aggregation



Relevant scripts:



\- `pipeline/aggregate\_hotspots.py`

\- `pipeline/aggregate\_districts.py`

\- `pipeline/aggregate\_sensor\_families.py`



The cleaned observations are aggregated at weekly and monthly intervals.



Three spatial levels are supported:



1\. AOI-level summaries — overall Punjab activity.

2\. Grid-cell summaries — spatial distribution using a 0.25° grid.

3\. District-level summaries — activity across Punjab's districts.



Separate MODIS and VIIRS family aggregations are also generated.



This preserves sensor-family information instead of combining measurements into a single supposedly equivalent series.



\### Stage D — Sensor Overlap Analysis



Relevant script:



`pipeline/build\_overlap\_pairs.py`



This stage constructs matched MODIS–VIIRS datasets for exploratory comparison.



The pipeline creates pair datasets for:



\- MODIS Aqua and VIIRS SNPP

\- MODIS Aqua and VIIRS NOAA-20

\- MODIS Aqua and VIIRS NOAA-21

\- MODIS Terra and VIIRS SNPP

\- MODIS Terra and VIIRS NOAA-20

\- MODIS Terra and VIIRS NOAA-21



The comparison uses:



\- Weekly time intervals.

\- Spatial grid identifiers.

\- Day/night categories.

\- Outer joins between sensor observations.

\- Zero-filling for missing sensor detections in matched combinations.



\*\*Interpretation:\*\* A zero indicates that no detection was recorded for that sensor in the corresponding matched combination. It does not prove that no fire occurred.



\### Stage E — Calibration Investigation



Relevant scripts:



\- `pipeline/fit\_calibration.py`

\- `pipeline/test\_regional\_calibration.py`

\- `pipeline/validate\_calibration\_stability.py`

\- `pipeline/diagnose\_monthly\_ratio.py`



The calibration investigation evaluates whether MODIS and VIIRS observations can be related through statistical models.



The evaluation includes:



1\. Grid-cell-level calibration.

2\. Regional calibration.

3\. Training and validation across different time periods.

4\. Yearly validation.

5\. Weekly prediction analysis.

6\. Monthly sensor-ratio diagnostics.



The models are evaluated using training data through 2024-12-30 and validation data from 2025 onward.



The current results do not establish a sufficiently reliable and temporally stable universal MODIS-to-VIIRS conversion.



Therefore, no final calibration has been applied to the main datasets.



\---



\## 5. Current Processing Results



\### Cleaning



| Metric | Result |

|---|---:|

| Total records across sensors | 2,887,859 |

| Punjab-clipped records | 2,104,042 |

| Retained cleaned observations | 1,595,863 |

| Removed during cleaning | 508,179 |



\### Retained observations by sensor



| Sensor | Observations |

|---|---:|

| VIIRS SNPP | 760,755 |

| VIIRS NOAA-20 | 390,072 |

| MODIS Aqua | 289,192 |

| VIIRS NOAA-21 | 82,250 |

| MODIS Terra | 73,594 |

| \*\*Total\*\* | \*\*1,595,863\*\* |



\### Temporal and spatial aggregation



The pipeline generated:



\- Weekly AOI summaries.

\- Monthly AOI summaries.

\- Weekly grid-cell summaries.

\- Monthly grid-cell summaries.

\- Weekly district summaries.

\- Monthly district summaries.

\- Separate MODIS and VIIRS family summaries.



All 22 Punjab districts are represented in the district aggregation outputs.



All cleaned detections were assigned to districts. The nearest-district fallback was used for 125 assignments, with a maximum reported distance of 26.5 metres.



\### Sensor-family totals



| Sensor family | Observations |

|---|---:|

| MODIS | 362,786 |

| VIIRS | 1,233,077 |

| \*\*Total\*\* | \*\*1,595,863\*\* |



These totals describe the processed sensor observations, not the number of unique physical fires.



\---



\## 6. Generated Datasets



\### Main processed datasets



| File | Description |

|---|---|

| `hotspots\_clean.parquet` | Cleaned individual observations |

| `hotspots\_punjab\_clipped.parquet` | Punjab-clipped observations before final cleaning |

| `weekly\_aoi.parquet` | Weekly Punjab-level summaries |

| `monthly\_aoi.parquet` | Monthly Punjab-level summaries |

| `weekly\_cell.parquet` | Weekly spatial grid-cell summaries |

| `monthly\_cell.parquet` | Monthly spatial grid-cell summaries |

| `weekly\_district.parquet` | Weekly district summaries |

| `monthly\_district.parquet` | Monthly district summaries |



\### Sensor-family datasets



| File | Description |

|---|---|

| `weekly\_aoi\_family.parquet` | Weekly MODIS and VIIRS AOI summaries |

| `monthly\_aoi\_family.parquet` | Monthly MODIS and VIIRS AOI summaries |

| `weekly\_cell\_family.parquet` | Weekly MODIS and VIIRS grid-cell summaries |

| `monthly\_cell\_family.parquet` | Monthly MODIS and VIIRS grid-cell summaries |

| `weekly\_district\_family.parquet` | Weekly MODIS and VIIRS district summaries |

| `monthly\_district\_family.parquet` | Monthly MODIS and VIIRS district summaries |



\### Calibration investigation datasets



Stored in:



`data/processed/calibration/`



These include six sensor-pair Parquet datasets and:



`calibration\_parameters.csv`



The pair datasets are exploratory comparison inputs, not calibrated replacements for the original observations.



\---



\## 7. Quality Assurance and Reports



Quality assurance reports are stored in `outputs/`.



| Report | Purpose |

|---|---|

| `raw\_spatial\_qa.csv` | Raw data spatial checks |

| `raw\_yearly\_counts.csv` | Raw yearly observation counts |

| `data\_availability.csv` | Sensor data availability |

| `clipping\_qa\_report.csv` | Geographic clipping checks |

| `cleaning\_qa\_report.csv` | Cleaning statistics |

| `aggregation\_qa\_report.csv` | Aggregation checks |

| `district\_aggregation\_qa.csv` | District assignment checks |

| `sensor\_family\_aggregation\_qa.csv` | MODIS/VIIRS family aggregation checks |

| `overlap\_pair\_qa.csv` | Sensor-pair construction checks |

| `calibration\_metrics.csv` | Calibration model evaluation |

| `regional\_calibration\_metrics.csv` | Regional model evaluation |

| `calibration\_yearly\_validation.csv` | Year-wise validation |

| `calibration\_overall\_validation.csv` | Overall validation |

| `calibration\_weekly\_predictions.csv` | Weekly model predictions |

| `aqua\_snpp\_monthly\_ratio.csv` | Monthly Aqua–SNPP ratio diagnostics |



These reports should be consulted before using the datasets for downstream analysis.



\---



\## 8. Sensor Harmonisation: Current Status



Sensor harmonisation remains an investigation rather than a completed calibration stage.



MODIS and VIIRS differ in their characteristics, including spatial resolution, observation geometry, overpass timing, detection algorithms and sensitivity.



The current exploratory models have not demonstrated sufficiently reliable and stable performance to support a universal MODIS-to-VIIRS conversion.



For this reason:



\- Original sensor observations are preserved.

\- MODIS and VIIRS family summaries remain separate.

\- Calibration outputs are retained for investigation.

\- No universal correction factor is applied.

\- Model evaluation results are not treated as proof of successful harmonisation.



A relative anomaly or seasonal percentile approach may be investigated as an alternative for the application. However, such an approach must not be presented as making the physical measurements of different sensors equivalent.



\---



\## 9. Repository Structure



```text

.

├── config/

│   └── punjab.py

│

├── data/

│   ├── boundaries/

│   │   ├── punjab\_state\_boundary.geojson

│   │   └── punjab\_districts.geojson

│   │

│   └── processed/

│       ├── weekly\_aoi.parquet

│       ├── monthly\_aoi.parquet

│       ├── weekly\_cell.parquet

│       ├── monthly\_cell.parquet

│       ├── weekly\_district.parquet

│       ├── monthly\_district.parquet

│       └── calibration/

│

├── docs/

│   └── cleaning\_rules.md

│

├── outputs/

│   └── QA and calibration reports

│

├── pipeline/

│   ├── check\_availability.py

│   ├── inspect\_raw\_data.py

│   ├── clip\_punjab\_data.py

│   ├── clean\_hotspots.py

│   ├── aggregate\_hotspots.py

│   ├── aggregate\_districts.py

│   ├── aggregate\_sensor\_families.py

│   ├── build\_overlap\_pairs.py

│   ├── fit\_calibration.py

│   ├── test\_regional\_calibration.py

│   ├── validate\_calibration\_stability.py

│   └── diagnose\_monthly\_ratio.py

│

├── requirements.txt

├── .gitignore

└── PAYAL\_DATA\_PIPELINE.md

```



Large raw archives and the largest cleaned observation files are maintained separately from this Git repository.



\---



\## 10. Installation and Dependencies



The development environment used Python 3.14.



Install the dependencies using:



```bash

pip install -r requirements.txt

```



The main dependencies are:



\- GeoPandas

\- Pandas

\- NumPy

\- PyArrow

\- Shapely

\- Requests

\- Matplotlib

\- python-dotenv



The environment file containing the NASA FIRMS API key must remain local and must never be committed.



\---



\## 11. Using Processed Data



The Parquet files can be read using Pandas:



```python

import pandas as pd



weekly\_data = pd.read\_parquet(

&#x20;   "data/processed/weekly\_aoi.parquet"

)



print(weekly\_data.head())

```



For the application, the aggregated datasets are suitable inputs for backend processing and API development.



The frontend should consume structured backend responses rather than downloading raw historical archives or processing millions of observations in the browser.



Potential backend endpoints include:



\- `/api/summary`

\- `/api/weekly`

\- `/api/monthly`

\- `/api/districts`

\- `/api/hotspots`

\- `/api/sensors`



These are proposed integration endpoints, not an assertion that the API has already been implemented.



\---



\## 12. Limitations and Interpretation



1\. The current implementation focuses on Punjab, India.

2\. The pipeline has not yet been validated for arbitrary global AOIs.

3\. Satellite detections are not equivalent to unique fire events.

4\. A missing detection does not prove the absence of fire.

5\. MODIS and VIIRS measurements are not directly interchangeable.

6\. The calibration investigation has not produced a validated universal conversion.

7\. Raw historical archives and large observation-level datasets are maintained separately from GitHub.



\---



\## 13. Contribution Summary



This contribution provides the team's data-processing foundation for the Punjab Fire Calendar:



\- Historical MODIS and VIIRS data preparation.

\- Geographic clipping and cleaning.

\- Spatial and temporal aggregation.

\- District-level summaries.

\- Separate MODIS and VIIRS family datasets.

\- Sensor-overlap analysis.

\- Calibration investigation and validation.

\- Quality assurance reports.

\- Processed Parquet datasets for backend integration.



The resulting datasets and reports are intended to support further backend development, visualisation and fire-activity analysis while preserving the limitations of the underlying satellite observations.

