const DEFAULT_API_BASE_URL =
  'https://harmonization-of-modis-and-viirs-hot-ccxf.onrender.com'

const API_BASE_URL = (
  import.meta.env.VITE_FIRELINE_API_BASE_URL ||
  (import.meta.env.DEV ? '/api' : DEFAULT_API_BASE_URL)
).replace(/\/+$/, '')

export class FireActivityApiError extends Error {
  constructor(message, status = null) {
    super(message)
    this.name = 'FireActivityApiError'
    this.status = status
  }
}

async function getJson(path, params, signal) {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null) {
      query.set(key, String(value))
    }
  })

  const url = `${API_BASE_URL}${path}?${query.toString()}`
  let response

  try {
    response = await fetch(url, {
      headers: { Accept: 'application/json' },
      signal,
    })
  } catch (error) {
    if (error.name === 'AbortError') throw error
    throw new FireActivityApiError(
      'Unable to reach the backend. Check network access and its CORS configuration.',
    )
  }

  const responseText = await response.text()
  let body = null

  if (responseText) {
    try {
      body = JSON.parse(responseText)
    } catch {
      if (response.ok) {
        throw new FireActivityApiError('The backend returned invalid JSON.')
      }
    }
  }

  if (!response.ok) {
    const detail = typeof body?.detail === 'string' ? `: ${body.detail}` : ''
    const message =
      response.status === 503
        ? `The backend dataset is temporarily unavailable (HTTP 503)${detail}`
        : `The backend request failed (HTTP ${response.status})${detail}`
    throw new FireActivityApiError(message, response.status)
  }

  if (!body || typeof body !== 'object') {
    throw new FireActivityApiError('The backend returned an empty or invalid response.')
  }

  return body
}

function requireDataRows(response, path) {
  if (!Array.isArray(response.data)) {
    throw new FireActivityApiError(
      `The ${path} response did not contain a data array.`,
    )
  }

  return response
}

export function hasValidHotspotCoordinates(record) {
  return (
    Number.isFinite(record?.latitude) &&
    record.latitude >= -90 &&
    record.latitude <= 90 &&
    Number.isFinite(record?.longitude) &&
    record.longitude >= -180 &&
    record.longitude <= 180
  )
}

export async function fetchHotspots({ limit = 100, signal } = {}) {
  const response = await getJson('/hotspots', { limit }, signal)
  requireDataRows(response, '/hotspots')
  if (typeof response.warning !== 'string') {
    throw new FireActivityApiError('The /hotspots response was missing its warning.')
  }
  return response
}

export async function fetchMeta({ signal } = {}) {
  const response = await getJson('/meta', {}, signal)
  if (typeof response.region !== 'string') {
    throw new FireActivityApiError('The /meta response was missing its region.')
  }
  return response
}

export async function fetchCalendar({ mode = 'raw', limit = 10000, signal } = {}) {
  const response = await getJson('/calendar', { mode, limit }, signal)
  return requireDataRows(response, '/calendar')
}

export async function fetchSeries({
  freq,
  mode,
  year,
  limit = 10000,
  signal,
}) {
  const response = await getJson(
    '/series',
    { freq, mode, year, limit },
    signal,
  )
  return requireDataRows(response, '/series')
}

export async function fetchHarmonizedSeries({
  freq = 'month',
  year,
  month,
  sensor,
  limit = 10000,
  signal,
} = {}) {
  const response = await getJson(
    '/harmonized/series',
    { freq, year, month, sensor, limit },
    signal,
  )
  return requireDataRows(response, '/harmonized/series')
}

export function createExportUrl({
  dataset = 'monthly_aoi',
  year,
  limit = 10000,
} = {}) {
  const query = new URLSearchParams({ dataset, limit: String(limit) })
  if (year !== undefined && year !== null) {
    query.set('year', String(year))
  }
  return `${API_BASE_URL}/export?${query.toString()}`
}
