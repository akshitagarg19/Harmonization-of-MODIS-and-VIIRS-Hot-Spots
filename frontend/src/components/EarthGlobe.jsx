import { useEffect, useRef, useState } from 'react'
import * as Cesium from 'cesium'
import punjabBoundaryUrl from '../../../data/boundaries/punjab_state_boundary.geojson?url'
import { hasValidHotspotCoordinates } from '../services/fireActivityApi'

// Configure Cesium static assets base URL
window.CESIUM_BASE_URL = '/cesium/'
window.__cesiumLog = []
window.__cesiumErr = null

export default function EarthGlobe({
  mode,
  hotspots = [],
  drawingEnabled,
  coordinateMode,
  coordinatePoints,
  selectedAreaPoints,
  drawingCommand,
  mapAction,
  onJourneyComplete,
  onJourneyError,
  onDrawingPointsChange,
  onPolygonComplete,
  onSelectionError,
}) {
  if (typeof window !== 'undefined' && window.__cesiumLog) {
    window.__cesiumLog.push('EarthGlobe component rendered')
  }
  const containerRef = useRef(null)
  const viewerRef = useRef(null)
  const creditContainerRef = useRef(null)
  const boundaryDataSourceRef = useRef(null)
  const hotspotDataSourceRef = useRef(null)
  const isRotatingRef = useRef(true)
  const selectedPolygonRef = useRef(null)
  const coordinatePreviewRef = useRef(null)
  const drawingActionsRef = useRef({})
  const lastDrawingCommandIdRef = useRef(0)
  const lastMapActionIdRef = useRef(0)
  const [isInitializing, setIsInitializing] = useState(true)
  const [loadError, setLoadError] = useState(null)

  useEffect(() => {
    let viewer = null
    let tickListener = null
    let resizeObserver = null
    let isMounted = true

    async function initCesium() {
      window.__cesiumLog.push('initCesium started. container: ' + !!containerRef.current)
      if (!containerRef.current) return

      try {
        window.__cesiumLog.push('1. Disabling ion token')
        Cesium.Ion.defaultAccessToken = ''

        window.__cesiumLog.push('2. Creating Blue Marble provider')
        const blueMarbleProvider = new Cesium.WebMapTileServiceImageryProvider({
          url: 'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/wmts.cgi',
          layer: 'BlueMarble_ShadedRelief_Bathymetry',
          style: 'default',
          format: 'image/jpeg',
          tileMatrixSetID: 'GoogleMapsCompatible_Level8',
          maximumLevel: 8,
          credit: new Cesium.Credit('Imagery courtesy of NASA GIBS / Earthdata (Blue Marble)', true),
        })

        window.__cesiumLog.push('3. Initializing Viewer')
        viewer = new Cesium.Viewer(containerRef.current, {
          baseLayer: false,
          terrainProvider: new Cesium.EllipsoidTerrainProvider(),
          geocoder: false,
          baseLayerPicker: false,
          animation: false,
          timeline: false,
          fullscreenButton: false,
          vrButton: false,
          homeButton: false,
          infoBox: false,
          selectionIndicator: false,
          navigationHelpButton: false,
          navigationInstructionsInitiallyVisible: false,
          sceneModePicker: false,
          projectionPicker: false,
          creditContainer: creditContainerRef.current || document.createElement('div'),
          showRenderLoopErrors: false,
          skyAtmosphere: new Cesium.SkyAtmosphere(),
        })

        window.__cesiumLog.push('4. Viewer created successfully')
        viewerRef.current = viewer
        window.__viewer = viewer
        const hotspotDataSource = new Cesium.CustomDataSource('FIRELINE hotspot observations')
        await viewer.dataSources.add(hotspotDataSource)
        if (!isMounted || viewer.isDestroyed()) return
        hotspotDataSourceRef.current = hotspotDataSource

        // Add base Blue Marble layer (active above 800 km and visible underneath MODIS)
        viewer.imageryLayers.addImageryProvider(blueMarbleProvider)

        // 4. NASA GIBS WMTS MODIS Terra Corrected Reflectance TrueColor Layer
        // Layer: MODIS_Terra_CorrectedReflectance_TrueColor, TileMatrixSet: GoogleMapsCompatible_Level9, Date: 2024-02-15
        const modisProvider = new Cesium.WebMapTileServiceImageryProvider({
          url: 'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/wmts.cgi',
          layer: 'MODIS_Terra_CorrectedReflectance_TrueColor',
          style: 'default',
          format: 'image/jpeg',
          tileMatrixSetID: 'GoogleMapsCompatible_Level9',
          maximumLevel: 9,
          dimensions: {
            TIME: '2024-02-15',
          },
          credit: new Cesium.Credit('NASA GIBS / MODIS Terra Corrected Reflectance (2024-02-15)', true),
        })

        // Add MODIS layer on top of Blue Marble (active below 800 km)
        const modisLayer = viewer.imageryLayers.addImageryProvider(modisProvider)
        modisLayer.show = false // Enabled dynamically when camera height is below 800,000m

        // 5. Camera Height Monitoring & Layer Zoom-Switching Logic:
        // Enable MODIS when camera height is below 800,000 metres
        const checkCameraHeight = () => {
          if (!viewer || viewer.isDestroyed()) return
          try {
            const cameraHeight = viewer.camera.positionCartographic.height
            const shouldShowModis = cameraHeight < 800000
            if (modisLayer.show !== shouldShowModis) {
              modisLayer.show = shouldShowModis
            }
          } catch {
            // Cartographic conversion can occasionally be undefined during edge re-renders
          }
        }

        viewer.camera.percentageChanged = 0.01
        viewer.camera.changed.addEventListener(checkCameraHeight)

        // 6. Visual Design: Atmospheric glow & realistic lighting
        const scene = viewer.scene
        const globe = scene.globe
        globe.enableLighting = true
        globe.showGroundAtmosphere = true
        globe.baseColor = Cesium.Color.fromCssColorString('#020617')

        if (scene.skyAtmosphere) {
          scene.skyAtmosphere.show = true
          scene.skyAtmosphere.hueShift = -0.05
          scene.skyAtmosphere.saturationShift = 0.25
          scene.skyAtmosphere.brightnessShift = 0.15
        }

        // Set realistic solar illumination aligned with the MODIS test date (2024-02-15)
        viewer.clock.currentTime = Cesium.JulianDate.fromDate(new Date('2024-02-15T10:30:00Z'))
        viewer.clock.shouldAnimate = true
        viewer.clock.multiplier = 1

        // Center 3D Earth prominently in the viewport
        viewer.camera.setView({
          destination: Cesium.Cartesian3.fromDegrees(20, 15, 21000000),
          orientation: {
            heading: Cesium.Math.toRadians(0),
            pitch: Cesium.Math.toRadians(-90),
            roll: 0.0,
          },
        })

        // 7. Slow, continuous rotation around Earth's Z-axis (North/South pole)
        tickListener = viewer.clock.onTick.addEventListener(() => {
          if (!viewer || viewer.isDestroyed()) return
          if (isRotatingRef.current) {
            viewer.scene.camera.rotate(Cesium.Cartesian3.UNIT_Z, 0.0006)
          }
          checkCameraHeight()
        })

        // 8. 2-3 Decorative animated satellites around Earth (MODIS & VIIRS platforms)
        const satellites = [
          {
            name: 'MODIS • Aqua',
            color: Cesium.Color.fromCssColorString('#38bdf8'),
            radius: 7150000,
            speed: 0.08,
            inclination: Cesium.Math.toRadians(82),
            raan: Cesium.Math.toRadians(30),
            phase: 0.0,
          },
          {
            name: 'VIIRS • Suomi-NPP',
            color: Cesium.Color.fromCssColorString('#f59e0b'),
            radius: 7400000,
            speed: 0.065,
            inclination: Cesium.Math.toRadians(70),
            raan: Cesium.Math.toRadians(150),
            phase: 2.1,
          },
          {
            name: 'MODIS • Terra',
            color: Cesium.Color.fromCssColorString('#34d399'),
            radius: 7250000,
            speed: 0.075,
            inclination: Cesium.Math.toRadians(98),
            raan: Cesium.Math.toRadians(270),
            phase: 4.2,
          },
        ]

        const startTime = Cesium.JulianDate.now()

        const computeOrbitPosition = (sat, time) => {
          const seconds = Cesium.JulianDate.secondsDifference(time, startTime)
          const angle = (seconds * sat.speed + sat.phase) % (Math.PI * 2)

          const xOrb = sat.radius * Math.cos(angle)
          const yOrb = sat.radius * Math.sin(angle)

          const xInc = xOrb
          const yInc = yOrb * Math.cos(sat.inclination)
          const zInc = yOrb * Math.sin(sat.inclination)

          const x = xInc * Math.cos(sat.raan) - yInc * Math.sin(sat.raan)
          const y = xInc * Math.sin(sat.raan) + yInc * Math.cos(sat.raan)
          const z = zInc

          return new Cesium.Cartesian3(x, y, z)
        }

        satellites.forEach((sat) => {
          // Render orbital trail path ring
          const ringPoints = []
          const segments = 90
          for (let i = 0; i <= segments; i++) {
            const angle = (i / segments) * Math.PI * 2
            const xOrb = sat.radius * Math.cos(angle)
            const yOrb = sat.radius * Math.sin(angle)
            const xInc = xOrb
            const yInc = yOrb * Math.cos(sat.inclination)
            const zInc = yOrb * Math.sin(sat.inclination)
            const x = xInc * Math.cos(sat.raan) - yInc * Math.sin(sat.raan)
            const y = xInc * Math.sin(sat.raan) + yInc * Math.cos(sat.raan)
            const z = zInc
            ringPoints.push(new Cesium.Cartesian3(x, y, z))
          }

          viewer.entities.add({
            polyline: {
              positions: ringPoints,
              width: 1.2,
              material: new Cesium.PolylineGlowMaterialProperty({
                glowPower: 0.15,
                taperPower: 1.0,
                color: sat.color.withAlpha(0.25),
              }),
            },
          })

          // Render moving satellite beacon with label
          viewer.entities.add({
            name: sat.name,
            position: new Cesium.CallbackProperty((time) => {
              return computeOrbitPosition(sat, time)
            }, false),
            point: {
              pixelSize: 6,
              color: sat.color,
              outlineColor: Cesium.Color.WHITE,
              outlineWidth: 1.5,
              disableDepthTestDistance: Number.POSITIVE_INFINITY,
            },
            label: {
              text: sat.name,
              font: '10px "Space Grotesk", "Courier New", monospace',
              fillColor: sat.color,
              outlineColor: Cesium.Color.fromCssColorString('#020617'),
              outlineWidth: 2,
              style: Cesium.LabelStyle.FILL_AND_OUTLINE,
              verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
              pixelOffset: new Cesium.Cartesian2(0, -9),
              distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 45000000),
            },
          })
        })

        // 9. ResizeObserver to ensure globe dynamically resizes with container
        resizeObserver = new ResizeObserver(() => {
          if (viewer && !viewer.isDestroyed()) {
            viewer.resize()
          }
        })
        resizeObserver.observe(containerRef.current)

        if (isMounted) {
          setIsInitializing(false)
        }
      } catch (err) {
        window.__cesiumErr = err.toString() + '\n' + (err.stack || '')
        window.__cesiumLog.push('ERROR: ' + err.message)
        console.error('Cesium globe initialization failed:', err)
        if (isMounted) {
          setLoadError(err.message || 'NASA GIBS imagery failed to load.')
          setIsInitializing(false)
        }
      }
    }

    initCesium()

    // 10. Clean up Cesium viewer and listeners on React unmount
    return () => {
      isMounted = false
      if (resizeObserver) {
        resizeObserver.disconnect()
      }
      if (tickListener) {
        tickListener()
      }
      if (viewer && !viewer.isDestroyed()) {
        viewer.destroy()
        viewer = null
        viewerRef.current = null
        boundaryDataSourceRef.current = null
        hotspotDataSourceRef.current = null
      }
    }
  }, [])

  useEffect(() => {
    isRotatingRef.current = mode === 'landing'
  }, [mode])

  useEffect(() => {
    const viewer = viewerRef.current
    if (
      !mapAction ||
      mapAction.id === lastMapActionIdRef.current ||
      mode !== 'explorer' ||
      !viewer ||
      viewer.isDestroyed()
    ) {
      return
    }

    lastMapActionIdRef.current = mapAction.id
    const height = viewer.camera.positionCartographic.height
    const distance = Math.max(1000, height * 0.25)

    if (mapAction.type === 'zoomIn') viewer.camera.zoomIn(distance)
    if (mapAction.type === 'zoomOut') viewer.camera.zoomOut(distance)
    if (mapAction.type === 'fitPunjab') {
      if (boundaryDataSourceRef.current) {
        viewer.flyTo(boundaryDataSourceRef.current, { duration: 1.2 })
      } else {
        viewer.camera.flyTo({
          destination: Cesium.Cartesian3.fromDegrees(75.41, 31.03, 650000),
          orientation: {
            heading: Cesium.Math.toRadians(0),
            pitch: Cesium.Math.toRadians(-90),
            roll: 0,
          },
          duration: 1.2,
        })
      }
    }
  }, [mapAction, mode])

  useEffect(() => {
    if (mode !== 'journey') return undefined

    const viewer = viewerRef.current
    if (!viewer || viewer.isDestroyed()) return undefined

    let cancelled = false
    isRotatingRef.current = false

    const waypoints = [
      { longitude: 92, latitude: 28, height: 17000000, duration: 2.4 },
      { longitude: 79, latitude: 25, height: 7200000, duration: 2.7 },
      { longitude: 75.41, latitude: 31.03, height: 650000, duration: 3.2 },
    ]

    const flyTo = (waypoint) =>
      new Promise((resolve) => {
        viewer.camera.flyTo({
          destination: Cesium.Cartesian3.fromDegrees(
            waypoint.longitude,
            waypoint.latitude,
            waypoint.height,
          ),
          orientation: {
            heading: Cesium.Math.toRadians(0),
            pitch: Cesium.Math.toRadians(-90),
            roll: 0,
          },
          duration: waypoint.duration,
          easingFunction: Cesium.EasingFunction.QUADRATIC_IN_OUT,
          complete: () => resolve(true),
          cancel: () => resolve(false),
        })
      })

    async function travelToPunjab() {
      try {
        for (const waypoint of waypoints) {
          const completed = await flyTo(waypoint)
          if (cancelled) return
          if (!completed) {
            throw new Error('The flight was interrupted. Please try again.')
          }
        }

        const boundaryDataSource = await Cesium.GeoJsonDataSource.load(
          punjabBoundaryUrl,
          {
            clampToGround: false,
            stroke: Cesium.Color.fromCssColorString('#fbbf24'),
            strokeWidth: 3,
            fill: Cesium.Color.fromCssColorString('#fbbf24').withAlpha(0.035),
          },
        )
        if (cancelled) return

        boundaryDataSourceRef.current = await viewer.dataSources.add(boundaryDataSource)
        if (!cancelled) onJourneyComplete()
      } catch (error) {
        if (!cancelled) {
          onJourneyError(error instanceof Error ? error.message : String(error))
        }
      }
    }

    travelToPunjab()

    return () => {
      cancelled = true
      if (!viewer.isDestroyed()) viewer.camera.cancelFlight()
    }
  }, [mode, onJourneyComplete, onJourneyError])

  useEffect(() => {
    const viewer = viewerRef.current
    if (mode !== 'explorer' || !drawingEnabled || !viewer || viewer.isDestroyed()) {
      drawingActionsRef.current = {}
      return undefined
    }

    const positions = []
    let previewLine = null
    let previewPolygon = null
    const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas)
    const viewerHandler = viewer.screenSpaceEventHandler
    const cameraController = viewer.scene.screenSpaceCameraController
    const originalEnableInputs = cameraController.enableInputs
    const originalClickAction = viewerHandler.getInputAction(
      Cesium.ScreenSpaceEventType.LEFT_CLICK,
    )
    const originalDoubleClickAction = viewerHandler.getInputAction(
      Cesium.ScreenSpaceEventType.LEFT_DOUBLE_CLICK,
    )
    cameraController.enableInputs = false
    viewerHandler.removeInputAction(Cesium.ScreenSpaceEventType.LEFT_CLICK)
    viewerHandler.removeInputAction(Cesium.ScreenSpaceEventType.LEFT_DOUBLE_CLICK)

    const toCoordinates = (cartesianPositions) =>
      cartesianPositions.map((position) => {
        const cartographic = Cesium.Cartographic.fromCartesian(position)
        return [
          Cesium.Math.toDegrees(cartographic.longitude),
          Cesium.Math.toDegrees(cartographic.latitude),
        ]
      })

    const syncPreview = () => {
      if (positions.length >= 2 && !previewLine) {
        previewLine = viewer.entities.add({
          polyline: {
            positions: new Cesium.CallbackProperty(() => positions.slice(), false),
            width: 3,
            material: Cesium.Color.fromCssColorString('#38bdf8'),
            clampToGround: true,
          },
        })
      } else if (positions.length < 2 && previewLine) {
        viewer.entities.remove(previewLine)
        previewLine = null
      }

      if (positions.length >= 3 && !previewPolygon) {
        previewPolygon = viewer.entities.add({
          polygon: {
            hierarchy: new Cesium.CallbackProperty(
              () => new Cesium.PolygonHierarchy(positions.slice()),
              false,
            ),
            height: 0,
            material: Cesium.Color.fromCssColorString('#38bdf8').withAlpha(0.22),
            outline: true,
            outlineColor: Cesium.Color.fromCssColorString('#7dd3fc'),
            outlineWidth: 2,
          },
        })
      } else if (positions.length < 3 && previewPolygon) {
        viewer.entities.remove(previewPolygon)
        previewPolygon = null
      }

      viewer.scene.requestRender()
    }

    const notifyPointsChanged = () => {
      onDrawingPointsChange(toCoordinates(positions))
    }

    const finishDrawing = () => {
      if (positions.length < 3) {
        onSelectionError('Add at least three points before finishing the area.')
        return
      }
      onPolygonComplete(toCoordinates(positions))
    }

    drawingActionsRef.current = {
      undo: () => {
        if (positions.length === 0) return
        positions.pop()
        syncPreview()
        notifyPointsChanged()
        onSelectionError('')
      },
      finish: finishDrawing,
    }

    handler.setInputAction(({ position }) => {
      const point = viewer.camera.pickEllipsoid(position, viewer.scene.globe.ellipsoid)
      if (!Cesium.defined(point)) return

      if (
        positions.length > 0 &&
        Cesium.Cartesian3.distance(positions[positions.length - 1], point) < 1
      ) {
        return
      }

      positions.push(point)
      syncPreview()
      notifyPointsChanged()
      onSelectionError('')
    }, Cesium.ScreenSpaceEventType.LEFT_CLICK)

    return () => {
      handler.destroy()
      if (!viewer.isDestroyed()) {
        cameraController.enableInputs = originalEnableInputs
        if (originalClickAction) {
          viewerHandler.setInputAction(
            originalClickAction,
            Cesium.ScreenSpaceEventType.LEFT_CLICK,
          )
        }
        if (originalDoubleClickAction) {
          viewerHandler.setInputAction(
            originalDoubleClickAction,
            Cesium.ScreenSpaceEventType.LEFT_DOUBLE_CLICK,
          )
        }
        if (previewLine) viewer.entities.remove(previewLine)
        if (previewPolygon) viewer.entities.remove(previewPolygon)
      }
      drawingActionsRef.current = {}
    }
  }, [
    drawingEnabled,
    mode,
    onDrawingPointsChange,
    onPolygonComplete,
    onSelectionError,
  ])

  useEffect(() => {
    if (!drawingCommand || drawingCommand.id === lastDrawingCommandIdRef.current) return
    lastDrawingCommandIdRef.current = drawingCommand.id
    drawingActionsRef.current[drawingCommand.type]?.()
  }, [drawingCommand])

  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer || viewer.isDestroyed()) return undefined

    if (coordinatePreviewRef.current) {
      viewer.entities.remove(coordinatePreviewRef.current)
      coordinatePreviewRef.current = null
    }

    if (mode !== 'explorer' || !coordinateMode || coordinatePoints.length === 0) {
      return undefined
    }

    const positions = coordinatePoints.map(([longitude, latitude]) =>
      Cesium.Cartesian3.fromDegrees(longitude, latitude),
    )
    const preview = {}

    if (positions.length === 1) {
      preview.position = positions[0]
      preview.point = {
        pixelSize: 8,
        color: Cesium.Color.fromCssColorString('#38bdf8'),
        outlineColor: Cesium.Color.WHITE,
        outlineWidth: 2,
      }
    } else {
      preview.polyline = {
        positions,
        width: 3,
        material: Cesium.Color.fromCssColorString('#38bdf8'),
        clampToGround: true,
      }
    }

    if (positions.length >= 3) {
      preview.polygon = {
        hierarchy: new Cesium.PolygonHierarchy(positions),
        height: 0,
        material: Cesium.Color.fromCssColorString('#38bdf8').withAlpha(0.22),
        outline: true,
        outlineColor: Cesium.Color.fromCssColorString('#7dd3fc'),
        outlineWidth: 2,
      }
    }

    coordinatePreviewRef.current = viewer.entities.add(preview)
    viewer.scene.requestRender()

    return () => {
      if (!viewer.isDestroyed() && coordinatePreviewRef.current) {
        viewer.entities.remove(coordinatePreviewRef.current)
        coordinatePreviewRef.current = null
      }
    }
  }, [coordinateMode, coordinatePoints, mode])

  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer || viewer.isDestroyed() || mode !== 'explorer' || selectedAreaPoints.length < 3) {
      return undefined
    }

    const positions = selectedAreaPoints.map(([longitude, latitude]) =>
      Cesium.Cartesian3.fromDegrees(longitude, latitude),
    )
    const polygon = viewer.entities.add({
      polygon: {
        hierarchy: new Cesium.PolygonHierarchy(positions),
        height: 0,
        material: Cesium.Color.fromCssColorString('#38bdf8').withAlpha(0.22),
        outline: true,
        outlineColor: Cesium.Color.fromCssColorString('#7dd3fc'),
        outlineWidth: 2,
      },
    })
    selectedPolygonRef.current = polygon
    viewer.scene.requestRender()

    return () => {
      if (!viewer.isDestroyed()) viewer.entities.remove(polygon)
      if (selectedPolygonRef.current === polygon) selectedPolygonRef.current = null
    }
  }, [mode, selectedAreaPoints])

  useEffect(() => {
    const viewer = viewerRef.current
    const dataSource = hotspotDataSourceRef.current
    if (!viewer || viewer.isDestroyed() || !dataSource) return undefined

    dataSource.entities.removeAll()
    hotspots.forEach((record, index) => {
      if (!hasValidHotspotCoordinates(record)) return

      const sensor =
        typeof record.sensor === 'string' ? record.sensor.trim() : ''
      const normalizedSensor = sensor.toUpperCase()
      const color = normalizedSensor.includes('MODIS')
        ? Cesium.Color.fromCssColorString('#f97316')
        : normalizedSensor.includes('VIIRS')
          ? Cesium.Color.fromCssColorString('#38bdf8')
          : Cesium.Color.fromCssColorString('#94a3b8')

      dataSource.entities.add({
        id: `hotspot-${index}`,
        position: Cesium.Cartesian3.fromDegrees(record.longitude, record.latitude),
        point: {
          pixelSize: 7,
          color,
          outlineColor: Cesium.Color.fromCssColorString('#020617'),
          outlineWidth: 1,
        },
      })
    })
    viewer.scene.requestRender()

    return () => {
      if (!viewer.isDestroyed() && hotspotDataSourceRef.current === dataSource) {
        dataSource.entities.removeAll()
        viewer.scene.requestRender()
      }
    }
  }, [hotspots, isInitializing])

  if (loadError) {
    return (
      <div className="globe-error-banner">
        <h3>Imagery Initialization Notice</h3>
        <p>{loadError}</p>
      </div>
    )
  }

  return (
    <div className="cesium-wrapper">
      <div ref={containerRef} className="cesium-container" />
      {/* Hidden credit container styled cleanly */}
      <div ref={creditContainerRef} className="cesium-credit-container" />
      {isInitializing && (
        <div className="globe-loader">
          <div className="spinner"></div>
          <span>INITIALIZING NASA GIBS 3D EARTH...</span>
        </div>
      )}
    </div>
  )
}
