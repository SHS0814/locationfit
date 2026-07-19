import { useEffect } from 'react'
import { divIcon } from 'leaflet'
import { MapContainer, Marker, Popup, TileLayer, useMap } from 'react-leaflet'
import type { RecommendationItem } from '../../types/api'

interface Props {
  items: RecommendationItem[]
  selected: RecommendationItem | null
  onSelect: (item: RecommendationItem) => void
}

const tileUrl = import.meta.env.VITE_MAP_TILE_URL || 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'
const attribution = import.meta.env.VITE_MAP_ATTRIBUTION || '&copy; OpenStreetMap contributors'

function MapFocus({ selected }: { selected: RecommendationItem | null }) {
  const map = useMap()
  useEffect(() => {
    if (selected) map.flyTo([selected.latitude, selected.longitude], 15, { duration: 0.7 })
  }, [map, selected])
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

export function RecommendationMap({ items, selected, onSelect }: Props) {
  return (
    <section className="map-panel" aria-label="추천 상권 지도">
      <MapContainer center={[37.5665, 126.978]} zoom={12} scrollWheelZoom className="map-container">
        <TileLayer url={tileUrl} attribution={attribution} />
        {items.map((item) => (
          <Marker key={item.area_code} position={[item.latitude, item.longitude]}
            icon={rankIcon(item.rank, selected?.area_code === item.area_code)} eventHandlers={{ click: () => onSelect(item) }}>
            <Popup><strong>{item.area_name}</strong><br />종합점수 {item.final_score.toFixed(1)}</Popup>
          </Marker>
        ))}
        <MapFocus selected={selected} />
      </MapContainer>
      {selected && (
        <aside className="map-detail">
          <span className="detail-rank">추천 {selected.rank}위</span>
          <h3>{selected.area_name}</h3>
          <p>{selected.district_name} · {selected.area_type}</p>
          <div className="score-bars">
            <span>조건 적합도 <strong>{selected.condition_fit_score.toFixed(1)}</strong></span>
            <span>성과 근거 <strong>{selected.reliability_adjusted_evidence_score?.toFixed(1) ?? '-'}</strong></span>
          </div>
          <small>본 결과는 미래 매출 예측이 아닌 과거 관측 데이터 기반 추천입니다.</small>
        </aside>
      )}
    </section>
  )
}
