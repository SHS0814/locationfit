import { useEffect, useState } from 'react'
import { api } from './api/client'
import { RecommendationMap } from './components/map/RecommendationMap'
import { RecommendationForm } from './features/recommendation/RecommendationForm'
import { emptyRecommendationRequest, hasPreference } from './features/recommendation/model'
import { RecommendationResults } from './features/recommendation/RecommendationResults'
import type { MetadataResponse, RecommendationItem, RecommendationRequest } from './types/api'

export default function App() {
  const [metadata, setMetadata] = useState<MetadataResponse | null>(null)
  const [form, setForm] = useState<RecommendationRequest>(emptyRecommendationRequest)
  const [items, setItems] = useState<RecommendationItem[]>([])
  const [selected, setSelected] = useState<RecommendationItem | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.metadata().then(setMetadata).catch((reason: Error) => setError(reason.message))
  }, [])

  const submit = async () => {
    if (!form.industry_code) return setError('업종을 선택해주세요.')
    if (!hasPreference(form)) return setError('업종 외에 원하는 조건을 하나 이상 선택해주세요.')
    setLoading(true)
    setError(null)
    try {
      const response = await api.recommend(form)
      setItems(response.recommendations)
      setSelected(response.recommendations[0] || null)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '추천 요청에 실패했습니다.')
    } finally {
      setLoading(false)
    }
  }

  if (!metadata) {
    return <main className="boot-screen"><div className="loader" /><p>{error || '상권 데이터를 불러오는 중입니다.'}</p></main>
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top"><span>KB</span> 상권 나침반</a>
        <div className="data-badge"><i /> 데이터 {metadata.data_period.profile || '2025Q4'} · {metadata.artifact_version}</div>
      </header>
      <main id="top">
        <section className="hero">
          <div>
            <span className="hero-kicker">SEOUL COMMERCIAL AREA RECOMMENDER</span>
            <h1>감이 아닌 데이터로,<br /><em>내 가게의 자리</em>를 찾다</h1>
            <p>서울 1,650개 상권의 유동인구와 경쟁 환경, 과거 업종 성과를 분석합니다.</p>
          </div>
          <div className="hero-stat"><strong>1,650</strong><span>분석 상권</span><strong>63</strong><span>지원 업종</span></div>
        </section>

        <section className="workspace">
          <RecommendationForm metadata={metadata} value={form} loading={loading} onChange={setForm} onSubmit={submit} />
          <div className="output-area">
            {error && <div className="error-banner" role="alert">{error}</div>}
            {items.length ? (
              <>
                <RecommendationMap items={items} selected={selected} onSelect={setSelected} />
                <RecommendationResults items={items} selectedCode={selected?.area_code || null} onSelect={setSelected} />
              </>
            ) : (
              <div className="empty-state">
                <div className="compass">⌖</div>
                <h2>조건을 선택하면 추천 지도가 열립니다</h2>
                <p>왼쪽에서 업종과 고객 특성을 설정해보세요.</p>
              </div>
            )}
          </div>
        </section>
      </main>
      <footer>KB AI Challenge · 서울 열린데이터광장 기반 분석 · 미래 매출을 보장하지 않습니다.</footer>
    </div>
  )
}
