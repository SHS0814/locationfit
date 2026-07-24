import { useEffect, useMemo, useRef, useState } from 'react'
import { divIcon, geoJSON } from 'leaflet'
import type { Feature, FeatureCollection, Geometry } from 'geojson'
import { GeoJSON, MapContainer, Marker, Popup, TileLayer, useMap } from 'react-leaflet'
import { api } from '../../api/client'
import type { MarketGeographyFeature, MarketGeographyResponse, MarketLookupResult } from '../../types/api'
import { isMappableLookup, marketLookupEntityKey, marketLookupMapCacheKey } from './marketLookupMapModel'

interface Props {
  result: MarketLookupResult
  selectedKey: string | null
  onSelect: (key: string) => void
}

const tileUrl = import.meta.env.VITE_MAP_TILE_URL || 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'
const attribution = import.meta.env.VITE_MAP_ATTRIBUTION || '&copy; OpenStreetMap contributors'
const geographyCache = new Map<string, MarketGeographyResponse>()

function asFeature(feature: MarketGeographyFeature): Feature {
  return {
    type: 'Feature',
    properties: { entity_key: feature.entity_key },
    geometry: feature.boundary as Geometry,
  }
}

function MapViewport({ features, selectedKey }: {
  features: MarketGeographyFeature[]
  selectedKey: string | null
}) {
  const map = useMap()
  const previousFeatures = useRef<MarketGeographyFeature[] | null>(null)
  const previousSelectedKey = useRef<string | null>(selectedKey)

  useEffect(() => {
    map.invalidateSize({ animate: false })
    const featuresChanged = previousFeatures.current !== features
    const selectionChanged = previousSelectedKey.current !== selectedKey
    if (featuresChanged && features.length > 0) {
      const collection: FeatureCollection = {
        type: 'FeatureCollection',
        features: features.map(asFeature),
      }
      const bounds = geoJSON(collection).getBounds()
      if (bounds.isValid()) map.fitBounds(bounds, { padding: [24, 24], maxZoom: 15 })
    } else if (selectionChanged && selectedKey) {
      const selected = features.find((feature) => feature.entity_key === selectedKey)
      if (selected) {
        const bounds = geoJSON(asFeature(selected)).getBounds()
        if (bounds.isValid()) map.fitBounds(bounds, { padding: [40, 40], maxZoom: 15 })
      }
    }
    previousFeatures.current = features
    previousSelectedKey.current = selectedKey
  }, [features, map, selectedKey])
  return null
}

function rankIcon(rank: number, active: boolean) {
  return divIcon({
    className: 'lookup-rank-marker-wrapper',
    html: `<span class="lookup-rank-marker${active ? ' active' : ''}">${rank}</span>`,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  })
}

export function MarketLookupMap({ result, selectedKey, onSelect }: Props) {
  const cacheKey = marketLookupMapCacheKey(result)
  const entityKeys = useMemo(
    () => result.rows.map((row) => marketLookupEntityKey(result, row)).filter((key): key is string => Boolean(key)),
    [result],
  )
  const [response, setResponse] = useState<MarketGeographyResponse | null>(
    cacheKey ? geographyCache.get(cacheKey) || null : null,
  )
  const [loading, setLoading] = useState(Boolean(cacheKey && !geographyCache.has(cacheKey)))
  const [error, setError] = useState<string | null>(null)
  const [retryToken, setRetryToken] = useState(0)

  useEffect(() => {
    if (!cacheKey || !isMappableLookup(result)) return
    const cached = geographyCache.get(cacheKey)
    if (cached) {
      setResponse(cached)
      setLoading(false)
      setError(null)
      return
    }
    const controller = new AbortController()
    setResponse(null)
    setLoading(true)
    setError(null)
    api.marketGeographies({ group_by: result.group_by, entity_keys: entityKeys }, controller.signal)
      .then((nextResponse) => {
        geographyCache.set(cacheKey, nextResponse)
        setResponse(nextResponse)
      })
      .catch((reason: Error) => {
        if (reason.name !== 'AbortError') setError(reason.message)
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [cacheKey, entityKeys, result, retryToken])

  if (!cacheKey) return null
  if (loading) return <div className="lookup-map-state"><div className="loader" /><p>조회 경계를 불러오는 중입니다.</p></div>
  if (error || !response) {
    return (
      <div className="lookup-map-state error" role="alert">
        <p>{error || '조회 지도를 불러오지 못했습니다.'}</p>
        <button type="button" onClick={() => setRetryToken((value) => value + 1)}>지도 다시 시도</button>
      </div>
    )
  }

  const rowByKey = new Map(
    result.rows.map((row) => [marketLookupEntityKey(result, row), row]),
  )
  const selectedRow = result.rows.find((row) => marketLookupEntityKey(result, row) === selectedKey) || null

  return (
    <section className="lookup-map-panel" aria-label="단순조회 결과 지도">
      <MapContainer center={[37.5665, 126.978]} zoom={11} scrollWheelZoom className="lookup-map-container">
        <TileLayer url={tileUrl} attribution={attribution} />
        {response.features.map((feature) => {
          const row = rowByKey.get(feature.entity_key)
          const active = selectedKey === feature.entity_key
          return (
            <GeoJSON
              key={`lookup-boundary-${feature.entity_key}`}
              data={asFeature(feature)}
              pathOptions={{
                color: active ? '#181d1a' : '#645300',
                weight: active ? 3 : 1.5,
                fillColor: '#ffcc00',
                fillOpacity: active ? 0.42 : 0.18,
              }}
              eventHandlers={{ click: () => onSelect(feature.entity_key) }}
            >
              <Popup><strong>{feature.entity_name}</strong><br />{row?.metric_display_value || '-'}</Popup>
            </GeoJSON>
          )
        })}
        {response.features.map((feature) => {
          const bounds = geoJSON(asFeature(feature)).getBounds()
          const row = rowByKey.get(feature.entity_key)
          if (!bounds.isValid() || !row) return null
          return (
            <Marker
              key={`lookup-marker-${feature.entity_key}`}
              position={bounds.getCenter()}
              icon={rankIcon(row.rank, selectedKey === feature.entity_key)}
              eventHandlers={{ click: () => onSelect(feature.entity_key) }}
            />
          )
        })}
        <MapViewport features={response.features} selectedKey={selectedKey} />
      </MapContainer>
      <div className="lookup-map-legend"><i /> {result.group_by === 'district' ? '자치구 행정경계' : '서울시 상권 경계'}</div>
      {selectedRow && (
        <aside className="lookup-map-detail">
          <span>{selectedRow.rank}위 · {result.metric_label}</span>
          <h4>{selectedRow.entity_name}</h4>
          <strong>{selectedRow.metric_display_value}</strong>
          <p>평균 대비 {selectedRow.difference_from_mean_display} · 중앙값 대비 {selectedRow.difference_from_median_display}</p>
          <small>평균에서 {selectedRow.standard_deviation_distance > 0 ? '+' : ''}{selectedRow.standard_deviation_distance.toFixed(2)}σ · 관측 상권 {selectedRow.area_count.toLocaleString('ko-KR')}곳 · {result.data_period}</small>
        </aside>
      )}
    </section>
  )
}
