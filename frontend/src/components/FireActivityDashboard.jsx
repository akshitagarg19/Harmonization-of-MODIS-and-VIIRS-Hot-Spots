import { useEffect, useMemo, useState } from 'react'
import {
  createExportUrl,
  fetchCalendar,
  fetchHarmonizedSeries,
  fetchMeta,
  fetchSeries,
} from '../services/fireActivityApi'

const MONTHS = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
]

function getSeriesRequests(dataView) {
  const modes = dataView === 'comparison' ? ['modis', 'viirs'] : [dataView]
  return ['week', 'month'].flatMap((frequency) =>
    modes.map((mode) => ({ frequency, mode })),
  )
}

function getAvailableYears(rows) {
  return [
    ...new Set(
      rows
        .map((row) => String(row.month_start ?? '').slice(0, 4))
        .filter((year) => /^\d{4}$/.test(year)),
    ),
  ].sort()
}

function getMonthlySensorCounts(rows) {
  const months = new Map()

  rows.forEach((row) => {
    const monthKey = String(row.month_start ?? '').slice(0, 7)
    const family = row.sensor_family
    if (row.n_detections === null || row.n_detections === undefined) return
    const count = Number(row.n_detections)

    if (
      !/^\d{4}-\d{2}$/.test(monthKey) ||
      !['MODIS', 'VIIRS'].includes(family) ||
      !Number.isFinite(count)
    ) {
      return
    }

    const current = months.get(monthKey) ?? {}
    current[family] = (current[family] ?? 0) + count
    months.set(monthKey, current)
  })

  return months
}

function formatCount(value) {
  return value === null || value === undefined
    ? '—'
    : new Intl.NumberFormat().format(value)
}

function getPeriodLabel(period, frequency) {
  const [, month, day] = String(period).slice(0, 10).split('-').map(Number)
  if (!month || month > 12) return String(period).slice(0, 10)
  const monthLabel = MONTHS[month - 1].slice(0, 3)
  return frequency === 'month' ? monthLabel : `${monthLabel} ${day}`
}

function getSeriesRows(resources, frequency, dataView) {
  const periodField = frequency === 'week' ? 'week_start' : 'month_start'
  const periods = new Map()
  const seriesKeys = new Set()
  const modes = dataView === 'comparison' ? ['modis', 'viirs'] : [dataView]

  modes.forEach((mode) => {
    const resource = resources?.[mode]
    if (resource?.status !== 'success') return

    resource.data.forEach((row) => {
      const period = row[periodField]
      const rawValue =
        mode === 'harmonized' ? row.activity_index : row.n_detections
      if (rawValue === null || rawValue === undefined) return
      const value = Number(rawValue)
      const seriesKey = mode === 'harmonized' ? row.sensor : mode
      if (
        typeof period !== 'string' ||
        typeof seriesKey !== 'string' ||
        !seriesKey ||
        !Number.isFinite(value)
      ) {
        return
      }

      const values = periods.get(period) ?? { period }
      values[seriesKey] = value
      periods.set(period, values)
      seriesKeys.add(seriesKey)
    })
  })

  const keys =
    dataView === 'comparison'
      ? ['modis', 'viirs']
      : dataView === 'harmonized'
        ? [...seriesKeys].sort()
        : [dataView]

  return {
    rows: [...periods.values()].sort((first, second) =>
      first.period.localeCompare(second.period),
    ),
    seriesKeys: keys,
  }
}

function formatSeriesValue(value, isHarmonized) {
  return isHarmonized
    ? Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 })
    : formatCount(value)
}

function getSeriesLabel(key) {
  if (key === 'modis') return 'MODIS'
  if (key === 'viirs') return 'VIIRS'
  return key
}

function getSeriesColor(key) {
  return key.toLowerCase().includes('viirs') ? 'viirs' : 'modis'
}

function SeriesPanel({ title, frequency, year, state, dataView }) {
  const resources = state.data?.[frequency]
  const { rows, seriesKeys } = getSeriesRows(resources, frequency, dataView)
  const isHarmonized = dataView === 'harmonized'
  const maxCount = Math.max(
    0,
    ...rows.flatMap((row) => seriesKeys.map((key) => row[key] ?? 0)),
  )
  const labelInterval = Math.max(1, Math.ceil(rows.length / 12))
  const requestedModes =
    dataView === 'comparison' ? ['modis', 'viirs'] : [dataView]

  return (
    <section className="activity-series-panel">
      <header className="activity-series-heading">
        <div>
          <h3>{title}</h3>
          <p>
            {isHarmonized
              ? `Sensor-specific activity index (not detection/fire counts) · ${year}`
              : `Satellite detection counts (not unique fires) · ${year}`}
          </p>
        </div>
        <div className="activity-series-legend" aria-label="Sensor legend">
          {seriesKeys.map((key) => (
            <span key={key}>
              <i className={`series-color-${getSeriesColor(key)}`} />
              {getSeriesLabel(key)}
            </span>
          ))}
        </div>
      </header>

      {state.status === 'loading' ? (
        <p className="dashboard-loading" role="status">
          Loading {title.toLowerCase()} data…
        </p>
      ) : (
        <>
          {requestedModes.map((mode) =>
            resources?.[mode]?.status === 'error' ? (
              <p className="dashboard-inline-error" role="alert" key={mode}>
                {mode === 'harmonized' ? 'HARMONIZED' : mode.toUpperCase()}:{' '}
                {resources[mode].error}
              </p>
            ) : null,
          )}

          {rows.length === 0 ? (
            <p className="dashboard-empty" role="status">
              {requestedModes.every((mode) => resources?.[mode]?.status === 'error')
                ? 'No data could be loaded for this period.'
                : `No ${isHarmonized ? 'harmonized values' : 'observations'} were returned for ${year}.`}
            </p>
          ) : (
            <div
              className="activity-series-scroll"
              role="region"
              aria-label={`${title} ${isHarmonized ? 'harmonized activity index' : 'satellite detection comparison'}`}
              tabIndex={0}
            >
              <div
                className="activity-series-chart"
                style={{
                  gridTemplateColumns: `repeat(${rows.length}, minmax(24px, 1fr))`,
                  minWidth: `${Math.max(360, rows.length * 30)}px`,
                }}
              >
                {rows.map((row, index) => (
                  <div
                    className="activity-series-period"
                    key={row.period}
                    title={`${getPeriodLabel(row.period, frequency)} ${year}`}
                  >
                    <div className="activity-series-bars">
                      {seriesKeys.map((key) => {
                        const value = row[key] ?? null
                        const color = getSeriesColor(key)
                        const height =
                          value === null || maxCount === 0
                            ? 0
                            : (value / maxCount) * 100

                        return (
                          <span
                            className={`activity-series-bar series-color-${color}`}
                            key={key}
                            style={{ height: `${height}%` }}
                            title={
                              value === null
                                ? `${getSeriesLabel(key)}: no data`
                                : isHarmonized
                                  ? `${getSeriesLabel(key)}: ${formatSeriesValue(value, true)} activity index`
                                  : `${getSeriesLabel(key)}: ${formatCount(value)} detection records`
                            }
                          />
                        )
                      })}
                    </div>
                    <span className="activity-series-date">
                      {index % labelInterval === 0 || index === rows.length - 1
                        ? getPeriodLabel(row.period, frequency)
                        : ''}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </section>
  )
}

function getCalendarYearComparison(rows, selectedMonth, dataView) {
  const keys =
    dataView === 'comparison'
      ? ['MODIS', 'VIIRS']
      : [dataView.toUpperCase()]
  const years = new Map()
  const monthNumber = String(selectedMonth).padStart(2, '0')

  rows.forEach((row) => {
    const monthStart = String(row.month_start ?? '')
    const year = monthStart.slice(0, 4)
    const family = row.sensor_family
    if (row.n_detections === null || row.n_detections === undefined) return
    const count = Number(row.n_detections)
    if (
      !/^\d{4}-\d{2}/.test(monthStart) ||
      monthStart.slice(5, 7) !== monthNumber ||
      !keys.includes(family) ||
      !Number.isFinite(count)
    ) {
      return
    }

    const values = years.get(year) ?? {}
    values[family] = (values[family] ?? 0) + count
    years.set(year, values)
  })

  return {
    seriesKeys: keys,
    rows: [...years.entries()]
      .map(([year, values]) => ({ year, values }))
      .sort((first, second) => first.year.localeCompare(second.year)),
  }
}

function getHarmonizedYearComparison(rows, selectedMonth) {
  const years = new Map()
  const monthNumber = String(selectedMonth).padStart(2, '0')
  const seriesKeys = new Set()

  rows.forEach((row) => {
    const monthStart = String(row.month_start ?? '')
    const sensor = row.sensor
    const rawValue = row.activity_index
    if (
      !/^\d{4}-\d{2}/.test(monthStart) ||
      monthStart.slice(5, 7) !== monthNumber ||
      typeof sensor !== 'string' ||
      rawValue === null ||
      rawValue === undefined
    ) {
      return
    }

    const value = Number(rawValue)
    if (!Number.isFinite(value)) return

    const year = monthStart.slice(0, 4)
    const values = years.get(year) ?? {}
    values[sensor] = value
    years.set(year, values)
    seriesKeys.add(sensor)
  })

  return {
    seriesKeys: [...seriesKeys].sort(),
    rows: [...years.entries()]
      .map(([year, values]) => ({ year, values }))
      .sort((first, second) => first.year.localeCompare(second.year)),
  }
}

function YearOverYearPanel({
  calendarState,
  harmonizedState,
  selectedMonth,
  dataView,
}) {
  const isHarmonized = dataView === 'harmonized'
  const sourceState = isHarmonized ? harmonizedState : calendarState
  const comparison = isHarmonized
    ? getHarmonizedYearComparison(harmonizedState.rows, selectedMonth)
    : getCalendarYearComparison(calendarState.rows, selectedMonth, dataView)
  const maxValue = Math.max(
    0,
    ...comparison.rows.flatMap((row) =>
      comparison.seriesKeys.map((key) => row.values[key] ?? 0),
    ),
  )
  const monthLabel = MONTHS[Number(selectedMonth) - 1]

  return (
    <section className="activity-yoy-section" aria-labelledby="activity-yoy-title">
      <div className="activity-section-heading">
        <div>
          <h3 id="activity-yoy-title">SAME-MONTH YEAR-OVER-YEAR</h3>
          <p>
            {isHarmonized
              ? 'Harmonized activity indices; not detection or fire counts'
              : 'Monthly detection counts returned by the API; observations are not unique fires'}
          </p>
        </div>
      </div>

      {sourceState.status === 'loading' ? (
        <p className="dashboard-loading" role="status">
          Loading {monthLabel} year-over-year data…
        </p>
      ) : sourceState.status === 'error' ? (
        <p className="dashboard-inline-error" role="alert">
          {sourceState.error}
        </p>
      ) : comparison.rows.length === 0 ? (
        <p className="dashboard-empty" role="status">
          No {isHarmonized ? 'harmonized values' : 'calendar observations'} were
          returned for {monthLabel}.
        </p>
      ) : (
        <div className="activity-yoy-panel">
          <div className="activity-yoy-legend">
            {comparison.seriesKeys.map((key) => {
              const color = getSeriesColor(key)
              return (
                <span key={key}>
                  <i className={`series-color-${color}`} />
                  {getSeriesLabel(key)}
                </span>
              )
            })}
          </div>
          <div className="activity-yoy-scroll" role="region" aria-label={`${monthLabel} year-over-year comparison`} tabIndex={0}>
            <div
              className="activity-yoy-chart"
              style={{
                gridTemplateColumns: `repeat(${comparison.rows.length}, minmax(54px, 1fr))`,
                minWidth: `${Math.max(360, comparison.rows.length * 58)}px`,
              }}
            >
              {comparison.rows.map((row) => (
                <div className="activity-yoy-year" key={row.year}>
                  <div className="activity-yoy-bars">
                    {comparison.seriesKeys.map((key) => {
                      const value = row.values[key] ?? null
                      const color = getSeriesColor(key)
                      const height =
                        value === null || maxValue === 0
                          ? 0
                          : (value / maxValue) * 100
                      const formatted =
                        value === null
                          ? 'No data'
                          : formatSeriesValue(value, isHarmonized)

                      return (
                        <div
                          className="activity-yoy-series"
                          key={key}
                          title={`${row.year} ${monthLabel} · ${getSeriesLabel(key)}: ${formatted}${isHarmonized ? ' activity index' : ' observations'}`}
                        >
                          <span className="activity-yoy-value">
                            {value === null ? '—' : formatSeriesValue(value, isHarmonized)}
                          </span>
                          {value === null ? (
                            <span className="activity-yoy-no-data" aria-hidden="true" />
                          ) : (
                            <span
                              className={`activity-yoy-bar series-color-${color}`}
                              style={{ height: `${height}%` }}
                            />
                          )}
                        </div>
                      )
                    })}
                  </div>
                  <span className="activity-yoy-year-label">{row.year}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </section>
  )
}

export default function FireActivityDashboard({ onClose }) {
  const [calendarState, setCalendarState] = useState({
    status: 'loading',
    rows: [],
    error: '',
  })
  const [metadataState, setMetadataState] = useState({
    status: 'loading',
    data: null,
    error: '',
  })
  const [selectedYear, setSelectedYear] = useState('')
  const [selectedDataView, setSelectedDataView] = useState('comparison')
  const [selectedMonth, setSelectedMonth] = useState('4')
  const [seriesState, setSeriesState] = useState({
    status: 'idle',
    data: null,
  })
  const [harmonizedYearState, setHarmonizedYearState] = useState({
    status: 'idle',
    rows: [],
    error: '',
    validationStatus: '',
  })

  useEffect(() => {
    const controller = new AbortController()
    let active = true

    Promise.allSettled([
      fetchCalendar({ mode: 'raw', limit: 10000, signal: controller.signal }),
      fetchMeta({ signal: controller.signal }),
    ]).then(([calendarResult, metadataResult]) => {
      if (!active) return

      if (calendarResult.status === 'fulfilled') {
        const rows = calendarResult.value.data
        const years = getAvailableYears(rows)
        setCalendarState({ status: 'success', rows, error: '' })
        setSelectedYear((currentYear) =>
          years.includes(currentYear) ? currentYear : years.at(-1) ?? '',
        )
      } else if (calendarResult.reason?.name !== 'AbortError') {
        setCalendarState({
          status: 'error',
          rows: [],
          error: calendarResult.reason.message,
        })
      }

      if (metadataResult.status === 'fulfilled') {
        setMetadataState({
          status: 'success',
          data: metadataResult.value,
          error: '',
        })
      } else if (metadataResult.reason?.name !== 'AbortError') {
        setMetadataState({
          status: 'error',
          data: null,
          error: metadataResult.reason.message,
        })
      }
    })

    return () => {
      active = false
      controller.abort()
    }
  }, [])

  useEffect(() => {
    if (!selectedYear) {
      setSeriesState({ status: 'idle', data: null })
      return undefined
    }

    const controller = new AbortController()
    let active = true
    setSeriesState({ status: 'loading', data: null })
    const requests = getSeriesRequests(selectedDataView)

    Promise.allSettled(
      requests.map(({ frequency, mode }) =>
        mode === 'harmonized'
          ? fetchHarmonizedSeries({
              freq: frequency,
              year: Number(selectedYear),
              limit: 10000,
              signal: controller.signal,
            })
          : fetchSeries({
              freq: frequency,
              mode,
              year: Number(selectedYear),
              limit: 10000,
              signal: controller.signal,
            }),
      ),
    ).then((results) => {
      if (!active) return

      const data = { week: {}, month: {} }
      results.forEach((result, index) => {
        const { frequency, mode } = requests[index]
        data[frequency][mode] =
          result.status === 'fulfilled'
            ? { status: 'success', data: result.value.data }
            : {
                status: 'error',
                error: result.reason.message,
              }
      })
      setSeriesState({ status: 'ready', data })
    })

    return () => {
      active = false
      controller.abort()
    }
  }, [selectedYear, selectedDataView])

  useEffect(() => {
    if (selectedDataView !== 'harmonized') {
      setHarmonizedYearState({
        status: 'idle',
        rows: [],
        error: '',
        validationStatus: '',
      })
      return undefined
    }

    const controller = new AbortController()
    let active = true
    setHarmonizedYearState({
      status: 'loading',
      rows: [],
      error: '',
      validationStatus: '',
    })

    fetchHarmonizedSeries({
      freq: 'month',
      month: Number(selectedMonth),
      limit: 10000,
      signal: controller.signal,
    }).then((response) => {
      if (!active) return
      setHarmonizedYearState({
        status: 'success',
        rows: response.data,
        error: '',
        validationStatus:
          typeof response.validation_status === 'string'
            ? response.validation_status
            : '',
      })
    }).catch((error) => {
      if (!active || error.name === 'AbortError') return
      setHarmonizedYearState({
        status: 'error',
        rows: [],
        error: error.message,
        validationStatus: '',
      })
    })

    return () => {
      active = false
      controller.abort()
    }
  }, [selectedDataView, selectedMonth])

  const years = useMemo(
    () => getAvailableYears(calendarState.rows),
    [calendarState.rows],
  )
  const calendarMonths = useMemo(
    () => getMonthlySensorCounts(calendarState.rows),
    [calendarState.rows],
  )
  const maxMonthlyDetections = useMemo(
    () =>
      Math.max(
        0,
        ...[...calendarMonths.values()].map(
          (counts) => (counts.MODIS ?? 0) + (counts.VIIRS ?? 0),
        ),
      ),
    [calendarMonths],
  )
  const seriesHasResults =
    seriesState.status === 'ready' &&
    Object.values(seriesState.data ?? {}).some((frequency) =>
      Object.values(frequency).some((resource) => resource.status === 'success'),
    )
  const backendConnected =
    metadataState.status === 'success' ||
    calendarState.status === 'success' ||
    seriesHasResults
  const connectionLabel = backendConnected
    ? 'BACKEND CONNECTED'
    : metadataState.status === 'loading' || calendarState.status === 'loading'
      ? 'CONNECTING TO BACKEND'
      : 'BACKEND UNAVAILABLE'

  return (
    <section className="activity-dashboard" aria-labelledby="activity-dashboard-title">
      <header className="activity-dashboard-header">
        <div>
          <span
            className={`activity-api-status${backendConnected ? ' is-connected' : ''}`}
            role="status"
          >
            <i />
            {connectionLabel}
          </span>
          <h2 id="activity-dashboard-title">PUNJAB FIRE ACTIVITY</h2>
          <p>{metadataState.data?.region ?? 'Punjab, India'}</p>
        </div>
        <button
          type="button"
          className="activity-dashboard-close"
          onClick={onClose}
        >
          BACK TO MAP
        </button>
      </header>

      {metadataState.status === 'error' && (
        <p className="dashboard-inline-error" role="alert">
          Backend status: {metadataState.error}
        </p>
      )}

      <div className="activity-dashboard-filter">
        <label className="activity-filter-field" htmlFor="activity-data-view">
          <span>DATA VIEW</span>
          <select
            id="activity-data-view"
            value={selectedDataView}
            onChange={(event) => setSelectedDataView(event.target.value)}
          >
            <option value="comparison">MODIS vs VIIRS counts</option>
            <option value="modis">MODIS</option>
            <option value="viirs">VIIRS</option>
            <option value="harmonized">Harmonized activity index</option>
          </select>
        </label>
        <label className="activity-filter-field" htmlFor="activity-year">
          <span>DATA YEAR</span>
          <select
            id="activity-year"
            value={selectedYear}
            disabled={calendarState.status !== 'success' || years.length === 0}
            onChange={(event) => setSelectedYear(event.target.value)}
          >
            {years.length === 0 ? (
              <option value="">No years available</option>
            ) : (
              years.slice().reverse().map((year) => (
                <option value={year} key={year}>{year}</option>
              ))
            )}
          </select>
        </label>
        <label className="activity-filter-field" htmlFor="activity-yoy-month">
          <span>COMPARE MONTH</span>
          <select
            id="activity-yoy-month"
            value={selectedMonth}
            onChange={(event) => setSelectedMonth(event.target.value)}
          >
            {MONTHS.map((month, index) => (
              <option value={index + 1} key={month}>{month}</option>
            ))}
          </select>
        </label>
        <a
          className={`activity-export-btn${selectedYear ? '' : ' is-disabled'}`}
          href={selectedYear
            ? createExportUrl({
                dataset:
                  selectedDataView === 'harmonized'
                    ? 'monthly_harmonized'
                    : 'monthly_aoi',
                year: Number(selectedYear),
                limit: 10000,
              })
            : undefined}
          aria-disabled={!selectedYear}
          title="Download the selected year's Punjab-wide monthly CSV; this is not filtered to the selected polygon or sensor."
        >
          DOWNLOAD CSV
          <span aria-hidden="true">↓</span>
        </a>
      </div>
      {selectedDataView === 'harmonized' && (
        <p
          className="activity-validation-status"
          role={harmonizedYearState.status === 'error' ? 'alert' : 'status'}
        >
          <span>Harmonized scientific validation:</span>{' '}
          <strong>
            {harmonizedYearState.status === 'loading'
              ? 'Loading from backend…'
              : harmonizedYearState.status === 'error'
                ? 'Unavailable'
                : harmonizedYearState.validationStatus || 'Not returned by API'}
          </strong>
        </p>
      )}
      <p className="activity-export-note">
        CSVs are Punjab-wide and are not filtered by the selected polygon,
        chart sensor, or comparison month. Exports are capped at 10,000 rows.
        Harmonized exports include AOI and cell rows and remain scientifically
        unvalidated.
      </p>

      <section className="activity-calendar-section" aria-labelledby="activity-calendar-title">
        <div className="activity-section-heading">
          <div>
            <h3 id="activity-calendar-title">MONTHLY ACTIVITY CALENDAR</h3>
            <p>
              MODIS and VIIRS detection counts; observations are not unique fires
            </p>
          </div>
        </div>

        {calendarState.status === 'loading' ? (
          <p className="dashboard-loading" role="status">
            Loading monthly calendar…
          </p>
        ) : calendarState.status === 'error' ? (
          <p className="dashboard-inline-error" role="alert">
            {calendarState.error}
          </p>
        ) : years.length === 0 ? (
          <p className="dashboard-empty" role="status">
            The backend returned no calendar observations.
          </p>
        ) : (
          <div className="activity-calendar-grid">
            {MONTHS.map((month, index) => {
              const monthKey = `${selectedYear}-${String(index + 1).padStart(2, '0')}`
              const counts = calendarMonths.get(monthKey)
              const total = counts
                ? (counts.MODIS ?? 0) + (counts.VIIRS ?? 0)
                : null
              const intensity =
                total === null || maxMonthlyDetections === 0
                  ? 0.06
                  : 0.06 + (total / maxMonthlyDetections) * 0.2

              return (
                <article
                  className="activity-calendar-month"
                  key={monthKey}
                  style={{
                    backgroundColor: `rgba(14, 116, 164, ${intensity})`,
                  }}
                >
                  <h4>{month}</h4>
                  <p><span>MODIS</span><strong>{formatCount(counts?.MODIS)}</strong></p>
                  <p><span>VIIRS</span><strong>{formatCount(counts?.VIIRS)}</strong></p>
                </article>
              )
            })}
          </div>
        )}
      </section>

      <section className="activity-series-section" aria-labelledby="activity-series-title">
        <div className="activity-section-heading">
          <div>
            <h3 id="activity-series-title">WEEKLY &amp; MONTHLY COMPARISONS</h3>
            <p>
              {selectedDataView === 'harmonized'
                ? 'Activity indices from /harmonized/series; not detection or fire counts'
                : 'Detection counts from /series; observations are not unique fires'}
            </p>
          </div>
        </div>

        {seriesState.status === 'idle' ? (
          <p className="dashboard-empty" role="status">
            Time series are unavailable because the calendar returned no years.
          </p>
        ) : (
          <div className="activity-series-grid">
            <SeriesPanel
              title={selectedDataView === 'harmonized' ? 'Weekly activity index' : 'Weekly detections'}
              frequency="week"
              year={selectedYear}
              state={seriesState}
              dataView={selectedDataView}
            />
            <SeriesPanel
              title={selectedDataView === 'harmonized' ? 'Monthly activity index' : 'Monthly detections'}
              frequency="month"
              year={selectedYear}
              state={seriesState}
              dataView={selectedDataView}
            />
          </div>
        )}
      </section>

      <YearOverYearPanel
        calendarState={calendarState}
        harmonizedState={harmonizedYearState}
        selectedMonth={selectedMonth}
        dataView={selectedDataView}
      />
    </section>
  )
}
