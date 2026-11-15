# Harmonization of MODIS and VIIRS Hotspots

**Punjab Fire Calendar — Satellite Fire Activity Monitoring and Harmonization**

This project brings together satellite-derived fire hotspot detections from **MODIS** and **VIIRS** to support the exploration of fire activity in Punjab, India. It includes data-processing outputs, harmonized weekly and monthly datasets, and a **FastAPI** backend for frontend visualizations such as fire calendars, historical trends, anomalies, district comparisons, and maps.

> **Project status:** The backend is deployed on Render. The existing 11 API endpoints have been tested by the project team. Frontend integration is proceeding with the existing endpoints; a proposed new `hotspots_sqh.parquet` dataset is **not** currently required.

## Live API

- **Base URL:** https://harmonization-of-modis-and-viirs-hot-ccxf.onrender.com
- **Interactive API documentation:** https://harmonization-of-modis-and-viirs-hot-ccxf.onrender.com/docs
- **OpenAPI schema:** https://harmonization-of-modis-and-viirs-hot-ccxf.onrender.com/openapi.json
- **Health check:** https://harmonization-of-modis-and-viirs-hot-ccxf.onrender.com/health

The Swagger UI at `/docs` shows the current parameters and response schemas. Use **Try it out → Execute** to inspect actual JSON returned by each endpoint. The OpenAPI specification is the source of truth for integration; examples below are illustrative requests, not verified response payloads.

## Features

- Access individual MODIS/VIIRS hotspot detections.
- Explore historical fire activity through time-series and calendar views.
- Examine district-level summaries and anomalies.
- Query harmonized weekly/monthly activity and grid-cell data.
- Retrieve map-oriented harmonized data for geospatial visualization.
- Export supported datasets through the API.

## API endpoints

| Method | Endpoint | Purpose | Typical frontend use |
|---|---|---|---|
| GET | `/health` | Service health | Connectivity/status |
| GET | `/meta` | Available dataset metadata | Filters and UI configuration |
| GET | `/series` | Historical activity time-series | Trend charts |
| GET | `/calendar` | Calendar-oriented activity | Fire calendar |
| GET | `/districts` | District-level summaries | District comparison |
| GET | `/hotspots` | Individual hotspot detections | Hotspot point layer |
| GET | `/anomalies` | Anomaly data | Anomaly charts/highlights |
| GET | `/harmonized/series` | Harmonized activity over time | Harmonized trend charts |
| GET | `/harmonized/cells` | Harmonized grid-cell data | Grid analysis |
| GET | `/harmonized/map` | Map-oriented harmonized data | Harmonized map layer |
| GET | `/export` | Data export | Download feature |

**Frontend data mapping**

1. **Individual detections:** `/hotspots`
2. **MODIS and VIIRS:** `/hotspots`, `/series`, and any additional endpoints exposing sensor-related filters (confirm supported filters in `/docs`).
3. **Historical time-series:** `/series` and `/harmonized/series`
4. **Harmonized grid cells:** `/harmonized/cells`
5. **Map data:** `/harmonized/map` for harmonized activity; `/hotspots` for individual detections

### Example requests

```bash
curl https://harmonization-of-modis-and-viirs-hot-ccxf.onrender.com/health
curl https://harmonization-of-modis-and-viirs-hot-ccxf.onrender.com/meta
```

A previously verified health response was:

```json
{"status":"ok"}
```

Other endpoints may require query parameters. Refer to `/docs` rather than assuming parameter names or date formats.

### JavaScript frontend example

```js
const API_BASE = "https://harmonization-of-modis-and-viirs-hot-ccxf.onrender.com";

async function fetchHealth() {
  const response = await fetch(`${API_BASE}/health`);
  if (!response.ok) throw new Error(`API error: ${response.status}`);
  return response.json();
}

fetchHealth().then(console.log).catch(console.error);
```

For endpoints with required query parameters, use `URLSearchParams` with the exact parameter names listed in Swagger.

## Technology stack

- **Backend:** Python, FastAPI, Uvicorn
- **Data querying:** DuckDB
- **Data format:** Parquet
- **Deployment:** Render
- **Data sources:** MODIS and VIIRS satellite hotspot detections

## Data and harmonization

MODIS and VIIRS have different observation characteristics. The project uses **Stratified Quantile Harmonization (SQH)** to support more consistent analysis across satellite products. Harmonized outputs are exposed as time-series and grid-oriented datasets.

Known processed data artifacts used or discussed in the project include:

| File | Role |
|---|---|
| `hotspots_clean.parquet` | Individual cleaned hotspot detections |
| `weekly_harmonized.parquet` | Weekly harmonized activity |
| `monthly_harmonized.parquet` | Monthly harmonized activity |
| `weekly_aoi_anomalies.parquet` | Weekly area-of-interest anomalies |
| `monthly_aoi_anomalies.parquet` | Monthly area-of-interest anomalies |
| `punjab_1km_grid.parquet` | Spatial grid data |

**Note:** `hotspots_sqh.parquet` has not been located in the shared processed-data folder and is **not part of the current frontend integration plan**. Do not assume that `hotspots_clean.parquet` has SQH-specific fields such as `sqh_cell_id` without checking its schema.

Some larger datasets may be distributed through the team's shared data storage rather than included in every local checkout. Check the actual file paths expected by `api/main.py` before running the server.

## Run locally

### Prerequisites

- Python 3.10+ (verify compatibility with the project's dependencies)
- Git
- Required Parquet files available at the paths configured by the backend

### Setup

```bash
git clone https://github.com/akshitagarg19/Harmonization-of-MODIS-and-VIIRS-Hot-Spots.git
cd Harmonization-of-MODIS-and-VIIRS-Hot-Spots
python -m venv .venv
```

Activate the environment:

**Windows PowerShell**

```powershell
.\.venv\Scripts\Activate.ps1
```

**macOS/Linux**

```bash
source .venv/bin/activate
```

Install dependencies and start the API:

```bash
pip install -r requirements.txt
uvicorn api.main:app --reload
```

Open http://127.0.0.1:8000/docs to inspect the local API.

If a route reports missing Parquet files, verify the data files and configured paths. A successful Python dependency installation does not automatically provide the processed datasets.

## Deployment

The existing backend is hosted on **Render** from the `main` branch.

**Build command**

```bash
pip install -r requirements.txt
```

**Start command**

```bash
uvicorn api.main:app --host 0.0.0.0 --port $PORT
```

If the frontend is hosted on a different origin, configure the backend's allowed CORS origins as appropriate. Check the current backend configuration before changing environment variables.

## Repository structure

The confirmed backend entry point is `api/main.py`. Other directories and files depend on the current repository checkout. The following is a **conceptual** layout rather than a verified full directory listing:

```text
Harmonization-of-MODIS-and-VIIRS-Hot-Spots/
├── api/
│   └── main.py              # FastAPI application
├── data/                    # Source and processed data (as available)
├── requirements.txt         # Python dependencies
└── README.md
```

## Frontend integration notes

- Use the deployed **base URL** for production frontend requests.
- Inspect `/docs` or `/openapi.json` for exact query parameters and response schemas.
- Use `/hotspots` for individual detections and `/harmonized/map` for the harmonized map layer.
- Use `/series` and `/harmonized/series` for historical charts.
- Avoid hardcoding assumptions about sensor identifiers, date formats, null values, or SQH fields without checking the API response.
- Render free-tier services may take time to respond after inactivity.

## Repository

https://github.com/akshitagarg19/Harmonization-of-MODIS-and-VIIRS-Hot-Spots

## Project status and next steps

- [x] FastAPI backend deployed
- [x] Eleven existing endpoints tested by the team
- [x] Harmonized series and map endpoints available
- [ ] Complete frontend integration
- [ ] Add verified endpoint-specific request/response examples to this README if needed

---

*This README describes the known working backend and integration plan. For exact live endpoint contracts, consult the generated OpenAPI documentation.*
