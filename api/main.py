from pathlib import Path
from typing import Literal
import csv
import io
import os

import duckdb
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

ROOT = Path(os.getenv('FIRE_DATA_DIR', 'data/processed'))

app = FastAPI(
    title='Punjab Fire Calendar API',
    version='0.2.0',
    description=(
        'Raw MODIS/VIIRS observations, historical anomaly baselines, and '
        'sensor-specific normalized activity indices. Scientific validation is pending.'
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv('CORS_ORIGINS', 'http://localhost:5173').split(','),
    allow_methods=['GET'],
    allow_headers=['*'],
)

TABLES = [
    'monthly_aoi', 'weekly_aoi',
    'monthly_aoi_family', 'weekly_aoi_family',
    'monthly_district', 'weekly_district',
    'monthly_cell', 'weekly_cell',
    'hotspots_clean',
    'monthly_aoi_anomalies', 'weekly_aoi_anomalies',
    'monthly_harmonized', 'weekly_harmonized',
]


def load(name: str) -> Path:
    if name not in TABLES:
        raise HTTPException(status_code=400, detail='Unsupported dataset')
    path = ROOT / f'{name}.parquet'
    if not path.is_file():
        raise HTTPException(
            status_code=503,
            detail=f'Missing dataset: {path}. Check FIRE_DATA_DIR and downloaded files.',
        )
    return path


def schema(name: str) -> list[dict]:
    path = load(name)
    with duckdb.connect() as db:
        description = db.execute(
            'DESCRIBE SELECT * FROM read_parquet(?)', [str(path)]
        ).fetchall()
    return [{'name': row[0], 'type': row[1]} for row in description]


def filter_rows(
    name: str,
    year: int | None = None,
    month: int | None = None,
    district: str | None = None,
    sensor_family: str | None = None,
    sensor: str | None = None,
    level: str | None = None,
    sqh_cell_id: str | None = None,
    limit: int = 10000,
) -> list[dict]:
    path = load(name)
    columns = {column['name'] for column in schema(name)}
    date_column = next(
        (col for col in ('month_start', 'week_start', 'acq_date') if col in columns),
        None,
    )
    conditions = []
    params = [str(path)]

    if year is not None:
        if date_column is None:
            raise HTTPException(422, f'Year filtering unavailable in {name}')
        conditions.append(f'EXTRACT(YEAR FROM CAST("{date_column}" AS DATE)) = ?')
        params.append(year)

    if month is not None:
        if date_column is None:
            raise HTTPException(422, f'Month filtering unavailable in {name}')
        conditions.append(f'EXTRACT(MONTH FROM CAST("{date_column}" AS DATE)) = ?')
        params.append(month)

    for column, value in (
        ('district', district),
        ('sensor_family', sensor_family),
        ('sensor', sensor),
        ('level', level),
        ('sqh_cell_id', sqh_cell_id),
    ):
        if value is not None:
            if column not in columns:
                raise HTTPException(422, f'{column} filtering unavailable in {name}')
            conditions.append(f'"{column}" = ?')
            params.append(value)

    sql = 'SELECT * FROM read_parquet(?)'
    if conditions:
        sql += ' WHERE ' + ' AND '.join(conditions)
    order_columns = [col for col in (date_column, 'sensor', 'district', 'sqh_cell_id') if col and col in columns]
    if order_columns:
        sql += ' ORDER BY ' + ', '.join(f'"{col}"' for col in order_columns)
    sql += ' LIMIT ?'
    params.append(limit)

    with duckdb.connect() as db:
        result = db.execute(sql, params)
        names = [col[0] for col in result.description]
        return [dict(zip(names, record)) for record in result.fetchall()]


@app.get('/health')
def health():
    return {'status': 'ok'}


@app.get('/meta')
def meta():
    available = {}
    for name in TABLES:
        if (ROOT / f'{name}.parquet').is_file():
            available[name] = schema(name)
    return {
        'region': 'Punjab, India',
        'harmonization_status': 'scientific validation pending',
        'datasets': available,
    }


@app.get('/series')
def series(
    freq: Literal['week', 'month'] = 'month',
    mode: Literal['raw', 'modis', 'viirs'] = 'raw',
    year: int | None = None,
    limit: int = Query(5000, ge=1, le=10000),
):
    prefix = 'weekly' if freq == 'week' else 'monthly'
    name = f'{prefix}_aoi' + ('_family' if mode != 'raw' else '')
    return {
        'mode': mode,
        'harmonized': False,
        'data': filter_rows(
            name, year=year,
            sensor_family=mode.upper() if mode != 'raw' else None,
            limit=limit,
        ),
    }


@app.get('/calendar')
def calendar(
    mode: Literal['raw', 'modis', 'viirs'] = 'raw',
    limit: int = Query(5000, ge=1, le=10000),
):
    name = 'monthly_aoi_family' if mode != 'raw' else 'monthly_aoi'
    return {
        'harmonized': False,
        'data': filter_rows(
            name,
            sensor_family=mode.upper() if mode != 'raw' else None,
            limit=limit,
        ),
    }


@app.get('/districts')
def districts(
    freq: Literal['week', 'month'] = 'month',
    year: int | None = None,
    month: int | None = Query(None, ge=1, le=12),
    limit: int = Query(10000, ge=1, le=10000),
):
    name = ('weekly' if freq == 'week' else 'monthly') + '_district'
    return {
        'data': filter_rows(
            name, year=year, month=month if freq == 'month' else None,
            limit=limit,
        )
    }


@app.get('/hotspots')
def hotspots(
    limit: int = Query(1000, ge=1, le=5000),
    sensor: str | None = None,
    sensor_family: Literal['MODIS', 'VIIRS'] | None = None,
    year: int | None = Query(None, ge=2000, le=2100),
    month: int | None = Query(None, ge=1, le=12),
):
    """Return individual detections, sampled across sensors by default.

    Without a sensor filter, select detections round-robin across available
    sensors rather than returning the first (usually MODIS-only) records.
    This is a capped sample, not a complete inventory of detections.
    """
    path = load('hotspots_clean')
    columns = {column['name'] for column in schema('hotspots_clean')}
    if 'sensor' not in columns or 'acq_date' not in columns:
        raise HTTPException(503, 'Hotspot dataset requires sensor and acq_date columns')

    conditions = []
    params = [str(path)]
    if sensor is not None:
        conditions.append('sensor = ?')
        params.append(sensor)
    if sensor_family is not None:
        conditions.append('sensor LIKE ?')
        params.append(sensor_family + '_%')
    if year is not None:
        conditions.append('EXTRACT(YEAR FROM CAST(acq_date AS DATE)) = ?')
        params.append(year)
    if month is not None:
        conditions.append('EXTRACT(MONTH FROM CAST(acq_date AS DATE)) = ?')
        params.append(month)

    where_clause = ' WHERE ' + ' AND '.join(conditions) if conditions else ''
    # Partitioning prevents early MODIS records from monopolizing the sample.
    # The order is deterministic; clients can request a particular year/month.
    sql = f"""
        WITH numbered AS (
            SELECT *, ROW_NUMBER() OVER (
                PARTITION BY sensor
                ORDER BY acq_date, latitude, longitude
            ) AS sample_rank
            FROM read_parquet(?)
            {where_clause}
        )
        SELECT * EXCLUDE (sample_rank)
        FROM numbered
        ORDER BY sample_rank, sensor
        LIMIT ?
    """
    params.append(limit)
    with duckdb.connect() as db:
        result = db.execute(sql, params)
        names = [column[0] for column in result.description]
        rows = [dict(zip(names, record)) for record in result.fetchall()]

    return {
        'warning': 'Individual satellite detections are not unique fires',
        'data': rows,
    }


@app.get('/anomalies')
def anomalies(
    freq: Literal['week', 'month'] = 'month',
    year: int | None = None,
    month: int | None = Query(None, ge=1, le=12),
    sensor: str | None = None,
    limit: int = Query(5000, ge=1, le=10000),
):
    name = ('weekly' if freq == 'week' else 'monthly') + '_aoi_anomalies'
    return {
        'frequency': freq,
        'method': 'previous_years_same_season_sensor_specific',
        'validation_status': 'pending research review',
        'note': 'insufficient_history and null percentile values are valid outcomes',
        'data': filter_rows(name, year=year, month=month, sensor=sensor, limit=limit),
    }


@app.get('/harmonized/series')
def harmonized_series(
    freq: Literal['week', 'month'] = 'month',
    year: int | None = None,
    month: int | None = Query(None, ge=1, le=12),
    sensor: str | None = None,
    limit: int = Query(5000, ge=1, le=10000),
):
    name = ('weekly' if freq == 'week' else 'monthly') + '_harmonized'
    return {
        'frequency': freq,
        'level': 'aoi',
        'metric': 'sensor-specific normalized activity index',
        'validation_status': 'pending research review',
        'warning': 'Activity index is not a count of unique fires or VIIRS-equivalent fires',
        'data': filter_rows(
            name, year=year, month=month, sensor=sensor, level='aoi', limit=limit
        ),
    }


@app.get('/harmonized/cells')
def harmonized_cells(
    freq: Literal['week', 'month'] = 'month',
    year: int | None = None,
    month: int | None = Query(None, ge=1, le=12),
    sensor: str | None = None,
    sqh_cell_id: str | None = None,
    limit: int = Query(1000, ge=1, le=5000),
):
    name = ('weekly' if freq == 'week' else 'monthly') + '_harmonized'
    return {
        'frequency': freq,
        'level': 'cell',
        'validation_status': 'pending research review',
        'warning': 'Cell IDs are not coordinates; use the matching 1 km grid geometry for mapping',
        'data': filter_rows(
            name, year=year, month=month, sensor=sensor,
            level='cell', sqh_cell_id=sqh_cell_id, limit=limit,
        ),
    }


@app.get('/harmonized/map')
def harmonized_map(
    freq: Literal['week', 'month'] = 'month',
    year: int | None = None,
    month: int | None = Query(None, ge=1, le=12),
    sensor: str | None = None,
    limit: int = Query(100, ge=1, le=5000),
):
    """Map-ready cell centroids; strongest activity first, not polygons."""
    name = ('weekly' if freq == 'week' else 'monthly') + '_harmonized'
    activity_path = load(name)
    grid_path = ROOT / 'punjab_1km_grid.parquet'
    if not grid_path.is_file():
        raise HTTPException(503, f'Missing grid dataset: {grid_path}')

    date_col = 'week_start' if freq == 'week' else 'month_start'
    conditions = ["h.level = 'cell'", 'g.centroid_lat IS NOT NULL',
                  'g.centroid_lon IS NOT NULL']
    params = [str(activity_path), str(grid_path)]
    if year is not None:
        conditions.append(f'EXTRACT(YEAR FROM h.{date_col}) = ?')
        params.append(year)
    if month is not None:
        conditions.append(f'EXTRACT(MONTH FROM h.{date_col}) = ?')
        params.append(month)
    if sensor is not None:
        conditions.append('h.sensor = ?')
        params.append(sensor)
    params.append(limit)

    sql = f"""
        SELECT h.{date_col}, h.sensor, h.sqh_cell_id,
               h.detection_count, h.frp_sum, h.activity_index,
               h.detection_percentile, h.frp_sum_percentile,
               g.centroid_lat AS latitude, g.centroid_lon AS longitude,
               g.cell_area_km2
        FROM read_parquet(?) AS h
        INNER JOIN read_parquet(?) AS g
            ON h.sqh_cell_id = g.sqh_cell_id
        WHERE {' AND '.join(conditions)}
        ORDER BY h.activity_index DESC NULLS LAST,
                 h.sqh_cell_id, h.sensor, h.{date_col}
        LIMIT ?
    """
    with duckdb.connect() as db:
        result = db.execute(sql, params)
        fields = [col[0] for col in result.description]
        rows = [dict(zip(fields, row)) for row in result.fetchall()]
    return {
        'frequency': freq,
        'level': 'cell',
        'geometry_type': 'centroid_points',
        'coordinate_system': 'EPSG:4326',
        'selection': 'highest activity_index first; limited sample, not all cells',
        'validation_status': 'pending research review',
        'warning': 'Sensor-specific index, not unique fire counts; map points are cell centroids',
        'data': rows,
    }


@app.get('/export')
def export(
    dataset: Literal[
        'monthly_aoi', 'weekly_aoi', 'monthly_district', 'weekly_district',
        'monthly_aoi_anomalies', 'weekly_aoi_anomalies',
        'monthly_harmonized', 'weekly_harmonized',
    ] = 'monthly_aoi',
    year: int | None = None,
    limit: int = Query(10000, ge=1, le=10000),
):
    # Harmonized tables include AOI and cell rows. Export remains capped at 10,000 rows.
    data = filter_rows(dataset, year=year, limit=limit)
    if not data:
        raise HTTPException(404, 'No rows matched')
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=list(data[0]))
    writer.writeheader()
    writer.writerows(data)
    return StreamingResponse(
        iter([stream.getvalue()]),
        media_type='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{dataset}.csv"'},
    )
