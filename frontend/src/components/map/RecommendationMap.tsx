import { useEffect, useRef } from 'react'
import { divIcon, geoJSON } from 'leaflet'
import type { Feature, FeatureCollection, Geometry } from 'geojson'
import { GeoJSON, MapContainer, Marker, Popup, TileLayer, useMap } from 'react-leaflet'
import type { RecommendationItem } from '../../types/api'

interface Props {
  items: RecommendationItem[]
  selected: RecommendationItem | null
  onSelect: (item: RecommendationItem) => void
  onExplore: (item: RecommendationItem) => void
}

const tileUrl = import.meta.env.VITE_MAP_TILE_URL || 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'
const attribution = import.meta.env.VITE_MAP_ATTRIBUTION || '&copy; OpenStreetMap contributors'

function asFeature(item: RecommendationItem): Feature {
  return {
    type: 'Feature',
    properties: { area_code: item.area_code },
    geometry: item.boundary as Geometry,
  }
}

function MapViewport({ items, selected }: { items: RecommendationItem[]; selected: RecommendationItem | null }) {
  const map = useMap()
  const previousItems = useRef<RecommendationItem[] | null>(null)
  const previousSelectedCode = useRef<string | null>(selected?.area_code ?? null)

  useEffect(() => {
    const itemsChanged = previousItems.current !== items
    const selectedCode = selected?.area_code ?? null
    const selectionChanged = previousSelectedCode.current !== selectedCode

    if (itemsChanged) {
      const collection: FeatureCollection = {
        type: 'FeatureCollection',
        features: items.map(asFeature),
      }
      const bounds = geoJSON(collection).getBounds()
      if (bounds.isValid()) map.fitBounds(bounds, { padding: [28, 28], maxZoom: 15 })
    } else if (selectionChanged && selected) {
      const bounds = geoJSON(asFeature(selected)).getBounds()
      if (bounds.isValid()) map.fitBounds(bounds, { padding: [48, 48], maxZoom: 16 })
    }

    previousItems.current = items
    previousSelectedCode.current = selectedCode
  }, [items, map, selected])
  return null
}

function rankIcon(rank: number, active: boolean) {
  return divIcon({
    className: 'rank-marker-wrapper',
    html: `<span class="rank-marker${active ? ' active' : ''}">${rank}</span>`,
    iconSize: [34, 42],
    iconAnchor: [17, 42],
  })
}

function formatArea(areaSizeSqm: number): string {
  if (areaSizeSqm >= 1_000_000) return `${(areaSizeSqm / 1_000_000).toFixed(2)}㎢`
  return `${Math.round(areaSizeSqm).toLocaleString('ko-KR')}㎡`
}

export function RecommendationMap({ items, selected, onSelect, onExplore }: Props) {
  return (
    <section className="map-panel" aria-label="추천 상권 지도">
      <MapContainer center={[37.5665, 126.978]} zoom={12} scrollWheelZoom className="map-container">
        <TileLayer url={tileUrl} attribution={attribution} />
        {items.map((item) => {
          const active = selected?.area_code === item.area_code
          return (
            <GeoJSON
              key={`boundary-${item.area_code}`}
              data={asFeature(item)}
              pathOptions={{
                color: active ? '#181d1a' : '#645300',
                weight: active ? 3 : 1.5,
                fillColor: '#ffcc00',
                fillOpacity: active ? 0.4 : 0.17,
              }}
              eventHandlers={{ click: () => onSelect(item) }}
            >
              <Popup>
                <strong>{item.area_name}</strong><br />
                실제 면적 {formatArea(item.area_size_sqm)}<br />
                종합점수 {item.final_score.toFixed(1)}
              </Popup>
            </GeoJSON>
          )
        })}
        {items.map((item) => (
          <Marker
            key={`marker-${item.area_code}`}
            position={[item.latitude, item.longitude]}
            icon={rankIcon(item.rank, selected?.area_code === item.area_code)}
            eventHandlers={{ click: () => onSelect(item) }}
          >
            <Popup>
              <strong>{item.area_name}</strong><br />
              실제 면적 {formatArea(item.area_size_sqm)}<br />
              종합점수 {item.final_score.toFixed(1)}
            </Popup>
          </Marker>
        ))}
        <MapViewport items={items} selected={selected} />
      </MapContainer>
      <div className="map-legend"><i /> 서울시 상권분석서비스 실제 경계</div>
      {selected && (
        <aside className="map-detail">
          <span className="detail-rank">추천 {selected.rank}위</span>
          <h3>{selected.area_name}</h3>
          <p>{selected.district_name} · {selected.area_type} · {formatArea(selected.area_size_sqm)}</p>
          <div className="score-bars">
            <span>조건 적합도 <strong>{selected.condition_fit_score.toFixed(1)}</strong></span>
            <span>성과 근거 <strong>{selected.reliability_adjusted_evidence_score?.toFixed(1) ?? '-'}</strong></span>
          </div>
          <small>노란 영역은 서울시가 제공한 상권 경계이며, 결과는 미래 매출 예측이 아닌 과거 관측 데이터 기반 추천입니다.</small>
          <button className="store-explore-button" type="button" onClick={() => onExplore(selected)}>
            이 상권 점포 분석
          </button>
        </aside>
      )}
    </section>
  )
}
