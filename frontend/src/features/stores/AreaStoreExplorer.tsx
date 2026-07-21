import { useEffect, useMemo, useState } from 'react'
import { divIcon, geoJSON } from 'leaflet'
import type { Feature, Geometry, Point } from 'geojson'
import Supercluster from 'supercluster'
import { CircleMarker, GeoJSON, MapContainer, Marker, Popup, TileLayer, useMap, useMapEvents } from 'react-leaflet'
import type { AreaStoresResponse, RecommendationItem, StorePoint, StoreRelation, WebResearchResponse } from '../../types/api'
import { filterStores } from './model'

const tileUrl = import.meta.env.VITE_MAP_TILE_URL || 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'
const attribution = import.meta.env.VITE_MAP_ATTRIBUTION || '&copy; OpenStreetMap contributors'

const relationLabels: Record<StoreRelation, string> = {
  competitor: '직접 경쟁점',
  complementary: '보완 업종',
  daily_life: '생활시설',
  other: '기타 업소',
}

const relationColors: Record<StoreRelation, string> = {
  competitor: '#d84a3a',
  complementary: '#167d68',
  daily_life: '#3766b1',
  other: '#77736c',
}

interface StoreProperties { store: StorePoint }

function boundaryFeature(area: RecommendationItem): Feature {
  return { type: 'Feature', properties: { area_code: area.area_code }, geometry: area.boundary as Geometry }
}

function StoreViewport({ area }: { area: RecommendationItem }) {
  const map = useMap()
  useEffect(() => {
    const bounds = geoJSON(boundaryFeature(area)).getBounds()
    if (bounds.isValid()) map.fitBounds(bounds, { padding: [32, 32], maxZoom: 17 })
  }, [area, map])
  return null
}

function clusterIcon(count: number) {
  return divIcon({
    className: 'store-cluster-wrapper',
    html: `<span class="store-cluster">${count.toLocaleString('ko-KR')}</span>`,
    iconSize: [42, 42],
    iconAnchor: [21, 21],
  })
}

function StoreClusters({ stores, selectedStoreId, onSelect }: {
  stores: StorePoint[]
  selectedStoreId: string | null
  onSelect: (store: StorePoint) => void
}) {
  const map = useMap()
  const [view, setView] = useState(() => ({
    bounds: map.getBounds(),
    zoom: map.getZoom(),
  }))
  useMapEvents({
    moveend: (event) => setView({ bounds: event.target.getBounds(), zoom: event.target.getZoom() }),
    zoomend: (event) => setView({ bounds: event.target.getBounds(), zoom: event.target.getZoom() }),
  })
  const index = useMemo(() => {
    const points: Array<Feature<Point, StoreProperties>> = stores.map((store) => ({
      type: 'Feature',
      properties: { store },
      geometry: { type: 'Point', coordinates: [store.longitude, store.latitude] },
    }))
    return new Supercluster<StoreProperties>({ radius: 55, maxZoom: 18 }).load(points)
  }, [stores])
  const clusters = useMemo(() => index.getClusters([
    view.bounds.getWest(), view.bounds.getSouth(), view.bounds.getEast(), view.bounds.getNorth(),
  ], Math.round(view.zoom)), [index, view])

  return clusters.map((feature) => {
    const [longitude, latitude] = feature.geometry.coordinates
    if ('cluster' in feature.properties && feature.properties.cluster) {
      const clusterId = feature.properties.cluster_id
      return (
        <Marker
          key={`cluster-${clusterId}`}
          position={[latitude, longitude]}
          icon={clusterIcon(feature.properties.point_count)}
          eventHandlers={{ click: () => map.setView([latitude, longitude], index.getClusterExpansionZoom(clusterId)) }}
        />
      )
    }
    const store = (feature.properties as StoreProperties).store
    const active = selectedStoreId === store.store_id
    return (
      <CircleMarker
        key={store.store_id}
        center={[latitude, longitude]}
        radius={active ? 9 : 6}
        pathOptions={{
          color: active ? '#171b18' : relationColors[store.relation],
          fillColor: relationColors[store.relation],
          fillOpacity: 0.86,
          weight: active ? 3 : 1,
        }}
        eventHandlers={{ click: () => onSelect(store) }}
      >
        <Popup><strong>{store.name}</strong><br />{relationLabels[store.relation]}<br />{store.industry_small_name || store.industry_middle_name || '-'}</Popup>
      </CircleMarker>
    )
  })
}

function ResearchCard({ result }: { result: WebResearchResponse }) {
  return (
    <section className="web-research-card">
      <div className="section-title"><span>{result.subject} 웹 정보</span><small>{new Date(result.searched_at).toLocaleString('ko-KR')}</small></div>
      <p className="research-summary">{result.summary}</p>
      <div className="research-sources">
        {result.sources.map((source) => (
          <a key={source.url} href={source.url} target="_blank" rel="noreferrer">{source.title}</a>
        ))}
      </div>
      {result.warnings.map((warning) => <small key={warning}>{warning}</small>)}
    </section>
  )
}

interface Props {
  area: RecommendationItem
  analysis: AreaStoresResponse
  relations: StoreRelation[]
  search: string
  selectedStoreId: string | null
  research: WebResearchResponse[]
  researchLoadingKey: string | null
  onBack: () => void
  onRelationsChange: (relations: StoreRelation[]) => void
  onSearchChange: (value: string) => void
  onSelectStore: (storeId: string | null) => void
  onResearch: (scope: 'area' | 'store', storeId?: string) => void
}

export function AreaStoreExplorer({
  area, analysis, relations, search, selectedStoreId, research, researchLoadingKey,
  onBack, onRelationsChange, onSearchChange, onSelectStore, onResearch,
}: Props) {
  const selectedStore = analysis.stores.find((store) => store.store_id === selectedStoreId) || null
  const filteredStores = filterStores(analysis.stores, relations, search)
  const areaResearch = research.find((item) => item.scope === 'area' && item.area_code === area.area_code)
  const storeResearch = selectedStore
    ? research.find((item) => item.scope === 'store' && item.store_id === selectedStore.store_id)
    : null

  const toggleRelation = (relation: StoreRelation) => {
    onRelationsChange(relations.includes(relation)
      ? relations.filter((item) => item !== relation)
      : [...relations, relation])
  }

  return (
    <div className="store-explorer">
      <header className="store-explorer-header">
        <button type="button" className="back-button" onClick={onBack}>← 추천 결과</button>
        <div><span>추천 {area.rank}위 상권 상세</span><h2>{area.area_name}</h2><p>{area.district_name} · {area.industry_name}</p></div>
        <button type="button" className="research-button" disabled={researchLoadingKey !== null} onClick={() => onResearch('area')}>
          {researchLoadingKey === 'area' ? '최신 정보 검색 중…' : '상권 최신 정보 검색'}
        </button>
      </header>

      <section className="store-summary-grid">
        <div><small>영업 업소</small><strong>{analysis.summary.total_count.toLocaleString('ko-KR')}</strong><span>{analysis.summary.total_density_per_sqkm.toLocaleString('ko-KR')}개/㎢</span></div>
        <div><small>직접 경쟁점</small><strong>{analysis.summary.competitor_count.toLocaleString('ko-KR')}</strong><span>{analysis.summary.competitor_density_per_sqkm.toLocaleString('ko-KR')}개/㎢</span></div>
        <div className="top-categories"><small>상위 업종</small><p>{analysis.summary.top_categories.map((item) => `${item.name} ${item.count}`).join(' · ') || '-'}</p></div>
        <div><small>데이터 기준</small><strong>{analysis.reference_month || '-'}</strong><span>{analysis.cache_status === 'stale' ? '이전 조회 결과' : '최신 조회'}</span></div>
      </section>

      <section className="store-controls">
        <input value={search} onChange={(event) => onSearchChange(event.target.value)} placeholder="상호·업종·주소 검색" aria-label="점포 검색" />
        <div className="store-relation-filters">
          {(Object.keys(relationLabels) as StoreRelation[]).map((relation) => {
            const count = analysis.summary.relation_counts.find((item) => item.relation === relation)?.count || 0
            return <button key={relation} type="button" className={relations.includes(relation) ? 'active' : ''} onClick={() => toggleRelation(relation)}><i style={{ background: relationColors[relation] }} />{relationLabels[relation]} {count}</button>
          })}
        </div>
        <small>필터 결과 {filteredStores.length.toLocaleString('ko-KR')}개</small>
      </section>

      <section className="store-map-layout">
        <div className="store-map-panel">
          <MapContainer center={[area.latitude, area.longitude]} zoom={16} scrollWheelZoom preferCanvas className="map-container">
            <TileLayer url={tileUrl} attribution={attribution} />
            <GeoJSON data={boundaryFeature(area)} pathOptions={{ color: '#645300', weight: 2, fillColor: '#ffcc00', fillOpacity: 0.08 }} />
            <StoreClusters stores={filteredStores} selectedStoreId={selectedStoreId} onSelect={(store) => onSelectStore(store.store_id)} />
            <StoreViewport area={area} />
          </MapContainer>
          <div className="map-legend">{(Object.keys(relationLabels) as StoreRelation[]).map((relation) => <span key={relation}><i style={{ background: relationColors[relation] }} />{relationLabels[relation]}</span>)}</div>
        </div>

        <aside className="store-detail-panel">
          {selectedStore ? (
            <>
              <span className={`relation-badge ${selectedStore.relation}`}>{relationLabels[selectedStore.relation]}</span>
              <h3>{selectedStore.name}{selectedStore.branch_name ? ` ${selectedStore.branch_name}` : ''}</h3>
              <p>{selectedStore.industry_large_name || '-'} › {selectedStore.industry_middle_name || '-'} › {selectedStore.industry_small_name || '-'}</p>
              <dl>
                <dt>주소</dt><dd>{selectedStore.road_address || selectedStore.lot_address || '-'}</dd>
                {selectedStore.building_name && <><dt>건물</dt><dd>{selectedStore.building_name}</dd></>}
                {(selectedStore.floor || selectedStore.unit) && <><dt>위치</dt><dd>{selectedStore.floor ? `${selectedStore.floor}층` : ''} {selectedStore.unit || ''}</dd></>}
              </dl>
              <button type="button" className="research-button" disabled={researchLoadingKey !== null} onClick={() => onResearch('store', selectedStore.store_id)}>
                {researchLoadingKey === selectedStore.store_id ? '업소 정보 검색 중…' : '이 업소 웹 정보 검색'}
              </button>
              <small>{analysis.disclosure}</small>
            </>
          ) : <div className="store-detail-empty"><strong>지도에서 업소를 선택하세요</strong><p>상호, 공식 업종, 주소와 건물·층 정보를 확인할 수 있습니다.</p></div>}
        </aside>
      </section>

      {analysis.warnings.map((warning) => <div className="store-warning" key={warning}>{warning}</div>)}
      {areaResearch && <ResearchCard result={areaResearch} />}
      {storeResearch && <ResearchCard result={storeResearch} />}
      <footer className="store-source">출처: {analysis.source} · 조회 {new Date(analysis.fetched_at).toLocaleString('ko-KR')}<br />{analysis.disclosure}</footer>
    </div>
  )
}
