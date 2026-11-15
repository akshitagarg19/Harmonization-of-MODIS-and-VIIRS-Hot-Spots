import { useCallback, useEffect, useState } from 'react'
import EarthGlobe from './components/EarthGlobe'
import FireActivityDashboard from './components/FireActivityDashboard'
import { fetchHotspots, hasValidHotspotCoordinates } from './services/fireActivityApi'
import './App.css'

export default function App() {
  const [mode, setMode] = useState('landing')
  const [drawingEnabled, setDrawingEnabled] = useState(false)
  const [drawingPoints, setDrawingPoints] = useState([])
  const [coordinateMode, setCoordinateMode] = useState(false)
  const [coordinatePoints, setCoordinatePoints] = useState([])
  const [latitudeInput, setLatitudeInput] = useState('')
  const [longitudeInput, setLongitudeInput] = useState('')
  const [selectedAreaPoints, setSelectedAreaPoints] = useState([])
  const [drawingCommand, setDrawingCommand] = useState(null)
  const [mapAction, setMapAction] = useState(null)
  const [journeyError, setJourneyError] = useState('')
  const [polygonStatus, setPolygonStatus] = useState('')
  const [selectionError, setSelectionError] = useState('')
  const [showDashboard, setShowDashboard] = useState(false)
  const [areaSidebarOpen, setAreaSidebarOpen] = useState(false)
  const [hotspots, setHotspots] = useState([])
  const [hotspotLoading, setHotspotLoading] = useState(false)
  const [hotspotError, setHotspotError] = useState('')
  const [skippedHotspotCount, setSkippedHotspotCount] = useState(0)

  useEffect(() => {
    if (mode !== 'explorer') return undefined

    const controller = new AbortController()
    let isActive = true
    setHotspots([])
    setHotspotError('')
    setSkippedHotspotCount(0)
    setHotspotLoading(true)

    fetchHotspots({ limit: 100, signal: controller.signal })
      .then((response) => {
        if (!isActive) return
        const validRecords = response.data.filter(hasValidHotspotCoordinates)
        setHotspots(validRecords)
        setSkippedHotspotCount(response.data.length - validRecords.length)
      })
      .catch((error) => {
        if (!isActive || error?.name === 'AbortError') return
        setHotspotError(
          error instanceof Error ? error.message : 'Unable to load hotspot records.',
        )
      })
      .finally(() => {
        if (isActive) setHotspotLoading(false)
      })

    return () => {
      isActive = false
      controller.abort()
    }
  }, [mode])

  const handleExploreClick = () => {
    setJourneyError('')
    setMode('journey')
  }

  const handleJourneyComplete = useCallback(() => {
    setMode('explorer')
  }, [])

  const handleJourneyError = useCallback((message) => {
    setJourneyError(message)
    setMode('landing')
  }, [])

  const handleDrawingPointsChange = useCallback((points) => {
    setDrawingPoints(points)
    setPolygonStatus(
      points.length === 1
        ? '1 vertex added. Add at least two more to finish.'
        : `${points.length} vertices added.`,
    )
  }, [])

  const handleSelectionError = useCallback((message) => {
    setSelectionError(message)
  }, [])

  const handlePolygonComplete = useCallback((points, method = 'draw') => {
    if (points.length < 3) {
      setSelectionError('Add at least three points to complete an area.')
      return
    }

    setSelectedAreaPoints(points)
    setDrawingEnabled(false)
    setDrawingPoints([])
    setCoordinateMode(method === 'coordinates')
    setCoordinatePoints([])
    setSelectionError('')
    setPolygonStatus(`Area selected (${points.length} points).`)
  }, [])

  const handleDrawClick = () => {
    if (drawingEnabled) {
      setDrawingEnabled(false)
      setDrawingPoints([])
      setSelectionError('')
      setPolygonStatus('Drawing cancelled.')
      return
    }

    setCoordinateMode(false)
    setCoordinatePoints([])
    setLatitudeInput('')
    setLongitudeInput('')
    setSelectionError('')
    setDrawingPoints([])
    setPolygonStatus('Click the map to add points.')
    setDrawingEnabled(true)
  }

  const handleDrawingCancel = () => {
    setDrawingEnabled(false)
    setDrawingPoints([])
    setSelectionError('')
    setPolygonStatus('Drawing cancelled.')
  }

  const handleSelectionMethodChange = (method) => {
    const useCoordinates = method === 'coordinates'
    if (useCoordinates === coordinateMode && selectedAreaPoints.length < 3) return

    setDrawingEnabled(false)
    setDrawingPoints([])
    setSelectedAreaPoints([])
    setCoordinateMode(useCoordinates)
    setCoordinatePoints([])
    setLatitudeInput('')
    setLongitudeInput('')
    setSelectionError('')
    setPolygonStatus('')
  }

  const handleAddCoordinate = (event) => {
    event.preventDefault()

    const latitudeText = latitudeInput.trim()
    const longitudeText = longitudeInput.trim()

    if (!latitudeText || !longitudeText) {
      setSelectionError('Enter both a latitude and a longitude.')
      return
    }

    const latitude = Number(latitudeText)
    const longitude = Number(longitudeText)

    if (!Number.isFinite(latitude) || latitude < -90 || latitude > 90) {
      setSelectionError('Latitude must be a number from -90 to 90.')
      return
    }

    if (!Number.isFinite(longitude) || longitude < -180 || longitude > 180) {
      setSelectionError('Longitude must be a number from -180 to 180.')
      return
    }

    if (
      coordinatePoints.some(
        ([existingLongitude, existingLatitude]) =>
          existingLongitude === longitude && existingLatitude === latitude,
      )
    ) {
      setSelectionError('That point has already been added.')
      return
    }

    setCoordinatePoints([...coordinatePoints, [longitude, latitude]])
    setLatitudeInput('')
    setLongitudeInput('')
    setSelectionError('')
  }

  const handleCompleteCoordinates = () => {
    if (coordinatePoints.length < 3) {
      setSelectionError('Add at least three valid points to complete an area.')
      return
    }

    handlePolygonComplete(coordinatePoints, 'coordinates')
  }

  const handleCoordinateCancel = () => {
    setCoordinateMode(false)
    setCoordinatePoints([])
    setLatitudeInput('')
    setLongitudeInput('')
    setSelectionError('')
    setPolygonStatus('Coordinate entry cancelled.')
  }

  const handleClearArea = () => {
    setSelectedAreaPoints([])
    setDrawingPoints([])
    setCoordinatePoints([])
    setLatitudeInput('')
    setLongitudeInput('')
    setSelectionError('')
    setPolygonStatus('')
  }

  const handleAnalyzeClick = () => {
    setShowDashboard(true)
  }

  const requestDrawingCommand = (type) => {
    setDrawingCommand((previous) => ({
      type,
      id: (previous?.id ?? 0) + 1,
    }))
  }

  const requestMapAction = (type) => {
    setMapAction((previous) => ({
      type,
      id: (previous?.id ?? 0) + 1,
    }))
  }

  const areaSelected = selectedAreaPoints.length >= 3
  const hasModisHotspots = hotspots.some(
    (record) =>
      typeof record.sensor === 'string' &&
      record.sensor.toUpperCase().includes('MODIS'),
  )
  const hasViirsHotspots = hotspots.some(
    (record) =>
      typeof record.sensor === 'string' &&
      record.sensor.toUpperCase().includes('VIIRS'),
  )

  return (
    <div className={`landing-page landing-page-${mode}`}>
      <div className="stars-layer stars-1" />
      <div className="stars-layer stars-2" />
      <div className="stars-layer stars-3" />

      <div className="globe-canvas-layer">
        <EarthGlobe
          mode={mode}
          hotspots={hotspots}
          drawingEnabled={drawingEnabled}
          coordinateMode={coordinateMode}
          coordinatePoints={coordinatePoints}
          selectedAreaPoints={selectedAreaPoints}
          drawingCommand={drawingCommand}
          mapAction={mapAction}
          onJourneyComplete={handleJourneyComplete}
          onJourneyError={handleJourneyError}
          onDrawingPointsChange={handleDrawingPointsChange}
          onPolygonComplete={handlePolygonComplete}
          onSelectionError={handleSelectionError}
        />
      </div>

      <header className="telemetry-header">
        <div className="telemetry-badge">
          <span className="telemetry-dot" />
          <span className="telemetry-label">ORBITAL OBSERVATION PLATFORM</span>
        </div>
        <div className="telemetry-system-info">
          <span className="telemetry-status">STATUS: ONLINE</span>
        </div>
      </header>

      <main
        className={`hero-overlay${showDashboard ? ' hero-overlay-dashboard' : ''}`}
      >
        {mode !== 'explorer' ? (
          <div className="hero-content">
            <h1 className="hero-title">FIRELINE</h1>
            <p className="hero-subtitle">Explore Earth&apos;s Fire Patterns</p>

            {mode === 'landing' ? (
              <div className="hero-action-group">
                <button
                  type="button"
                  className="explore-btn"
                  onClick={handleExploreClick}
                  aria-label="Explore Fire Activity"
                >
                  <span className="btn-glow" />
                  <span className="btn-text">EXPLORE FIRE ACTIVITY</span>
                  <svg
                    className="btn-icon"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    aria-hidden="true"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" d="M13 7l5 5m0 0l-5 5m5-5H6" />
                  </svg>
                </button>
              </div>
            ) : (
              <p className="journey-status" role="status">ROUTING TO PUNJAB</p>
            )}

            {journeyError && <p className="journey-error" role="alert">{journeyError}</p>}
          </div>
        ) : showDashboard ? (
          <FireActivityDashboard onClose={() => setShowDashboard(false)} />
        ) : (
          <>
            <button
              type="button"
              className={`area-sidebar-toggle${areaSidebarOpen ? ' is-open' : ''}`}
              onClick={() => setAreaSidebarOpen((open) => !open)}
              aria-expanded={areaSidebarOpen}
              aria-controls="area-selection-sidebar"
              aria-label={areaSidebarOpen ? 'Close area selection panel' : 'Open area selection panel'}
            >
              <span className="area-sidebar-toggle-icon" aria-hidden="true">
                {areaSidebarOpen ? '×' : '+'}
              </span>
              {areaSidebarOpen ? 'CLOSE PANEL' : 'SELECT AREA'}
            </button>
            <aside
              id="area-selection-sidebar"
              className={`area-selection-sidebar${areaSidebarOpen ? ' is-open' : ''}`}
              aria-label="Punjab area selection"
              aria-hidden={!areaSidebarOpen}
              inert={!areaSidebarOpen}
            >
              <section className="map-controls">
            <p className="map-location">PUNJAB, INDIA</p>
            <h1 className="map-title">SELECT YOUR AREA</h1>
            <div className="selection-method-switch" role="group" aria-label="Area selection method">
              <button
                type="button"
                className={`selection-method-btn${!coordinateMode ? ' is-active' : ''}`}
                onClick={() => handleSelectionMethodChange('draw')}
                aria-pressed={!coordinateMode}
                aria-label="Draw polygon on map"
              >
                DRAW POLYGON
              </button>
              <button
                type="button"
                className={`selection-method-btn${coordinateMode ? ' is-active' : ''}`}
                onClick={() => handleSelectionMethodChange('coordinates')}
                aria-pressed={coordinateMode}
              >
                ENTER COORDINATES
              </button>
            </div>

            {areaSelected ? (
              <div className="selected-area-details">
                <p className="selected-area-status" role="status">
                  Area selected ({selectedAreaPoints.length} points).
                </p>
                <button
                  className="clear-area-btn"
                  type="button"
                  onClick={handleClearArea}
                >
                  CLEAR AREA
                </button>
              </div>
            ) : coordinateMode ? (
              <form className="coordinate-entry-panel" onSubmit={handleAddCoordinate}>
                <p className="tool-hint">
                  Add latitude/longitude pairs in polygon order.
                </p>
                <div className="coordinate-input-row">
                  <label>
                    <span>LATITUDE</span>
                    <input
                      type="number"
                      step="any"
                      value={latitudeInput}
                      onChange={(event) => setLatitudeInput(event.target.value)}
                      aria-label="Latitude"
                    />
                  </label>
                  <label>
                    <span>LONGITUDE</span>
                    <input
                      type="number"
                      step="any"
                      value={longitudeInput}
                      onChange={(event) => setLongitudeInput(event.target.value)}
                      aria-label="Longitude"
                    />
                  </label>
                  <button className="secondary-map-btn" type="submit">
                    ADD POINT
                  </button>
                </div>

                {coordinatePoints.length > 0 && (
                  <ol className="coordinate-point-list">
                    {coordinatePoints.map(([longitude, latitude], index) => (
                      <li key={`${longitude},${latitude}`}>
                        <span>
                          {index + 1}. {latitude}, {longitude}
                        </span>
                        <button
                          type="button"
                          onClick={() => {
                            setCoordinatePoints(
                              coordinatePoints.filter((_, itemIndex) => itemIndex !== index),
                            )
                            setSelectionError('')
                          }}
                          aria-label={`Remove point ${index + 1}`}
                        >
                          REMOVE
                        </button>
                      </li>
                    ))}
                  </ol>
                )}

                <div className="selection-tool-buttons">
                  <button
                    className="secondary-map-btn"
                    type="button"
                    onClick={handleCompleteCoordinates}
                    disabled={coordinatePoints.length < 3}
                  >
                    COMPLETE AREA
                  </button>
                  <button
                    className="secondary-map-btn secondary-map-btn--quiet"
                    type="button"
                    onClick={handleCoordinateCancel}
                  >
                    CANCEL
                  </button>
                </div>
                <p className="selection-count">
                  {coordinatePoints.length} point
                  {coordinatePoints.length === 1 ? '' : 's'} added
                </p>
              </form>
            ) : (
              <div className="draw-area-panel">
                {drawingEnabled ? (
                  <div className="selection-tools">
                    <p className="tool-hint" aria-live="polite">
                      Click the map to add vertices. At least three are required.
                    </p>
                    <div className="selection-tool-buttons">
                      <button
                        className="secondary-map-btn"
                        type="button"
                        onClick={() => requestDrawingCommand('undo')}
                        disabled={drawingPoints.length === 0}
                      >
                        UNDO
                      </button>
                      <button
                        className="secondary-map-btn"
                        type="button"
                        onClick={() => requestDrawingCommand('finish')}
                        disabled={drawingPoints.length < 3}
                      >
                        FINISH
                      </button>
                      <button
                        className="secondary-map-btn secondary-map-btn--quiet"
                        type="button"
                        onClick={handleDrawingCancel}
                      >
                        CANCEL
                      </button>
                    </div>
                    <p className="selection-count" aria-live="polite">
                      {drawingPoints.length} point{drawingPoints.length === 1 ? '' : 's'} added
                    </p>
                  </div>
                ) : (
                  <button
                    type="button"
                    className="explore-btn draw-area-btn"
                    onClick={handleDrawClick}
                  >
                    <span className="btn-glow" />
                    <span className="btn-text">DRAW YOUR AREA</span>
                    <svg
                      className="btn-icon"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      aria-hidden="true"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" d="M13 7l5 5m0 0l-5 5m5-5H6" />
                    </svg>
                  </button>
                )}
              </div>
            )}

            {selectionError && (
              <p className="error-message" role="alert">
                {selectionError}
              </p>
            )}
            {polygonStatus && !areaSelected && !drawingEnabled && !coordinateMode && (
              <p className="drawing-status" role="status">{polygonStatus}</p>
            )}

            <button
              type="button"
              className={`analyze-area-btn${areaSelected ? ' is-available' : ''}`}
              onClick={handleAnalyzeClick}
              disabled={!areaSelected}
              aria-label="Analyze Data"
            >
              ANALYZE SELECTED AREA
              <span aria-hidden="true">→</span>
            </button>
              </section>
            </aside>
          </>
        )}
      </main>

      {mode === 'explorer' && !showDashboard && (
        <>
          <div className="hotspot-map-legend" aria-label="Hotspot sensor legend">
            {hotspotLoading && (
              <span className="hotspot-map-legend-status" role="status">
                Loading…
              </span>
            )}
            {hotspotError && (
              <span className="hotspot-map-legend-error" role="alert">
                Hotspots unavailable
              </span>
            )}
            {hasModisHotspots && (
              <span className="hotspot-map-legend-item">
                <i className="hotspot-map-legend-dot hotspot-map-legend-dot-modis" />
                MODIS
              </span>
            )}
            {hasViirsHotspots && (
              <span className="hotspot-map-legend-item">
                <i className="hotspot-map-legend-dot hotspot-map-legend-dot-viirs" />
                VIIRS
              </span>
            )}
            {skippedHotspotCount > 0 && (
              <span
                className="hotspot-map-legend-status"
                title="Some records had invalid coordinates and were not plotted."
              >
                {skippedHotspotCount} skipped
              </span>
            )}
          </div>
          <div className="map-zoom-controls" role="group" aria-label="Map zoom controls">
            <button
              type="button"
              onClick={() => requestMapAction('zoomIn')}
              aria-label="Zoom in"
              title="Zoom in"
            >
              +
            </button>
            <button
              type="button"
              onClick={() => requestMapAction('zoomOut')}
              aria-label="Zoom out"
              title="Zoom out"
            >
              −
            </button>
            <button
              type="button"
              className="fit-punjab-btn"
              onClick={() => requestMapAction('fitPunjab')}
              aria-label="Reset or fit Punjab"
              title="Reset / fit Punjab"
            >
              RESET / FIT PUNJAB
            </button>
          </div>
        </>
      )}

      <footer className="telemetry-footer">
        <span className="footer-val">NASA GIBS imagery</span>
      </footer>
    </div>
  )
}
