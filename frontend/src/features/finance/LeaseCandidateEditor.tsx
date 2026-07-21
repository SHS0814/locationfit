import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { RecommendationItem } from '../../types/api'
import {
  candidateFromDraft,
  draftFromCandidate,
  draftFromExtraction,
  emptyLeaseDraft,
  validateLeaseDraft,
  type LeaseCandidateDraft,
  type LeaseCandidateRecord,
  type LeaseMoneyField,
} from './model'


const leaseMoneyFields: Array<{ key: LeaseMoneyField; label: string; optional?: boolean }> = [
  { key: 'deposit', label: '보증금' },
  { key: 'monthlyRent', label: '월세' },
  { key: 'managementFee', label: '월 관리비', optional: true },
  { key: 'keyMoney', label: '권리금', optional: true },
]

export function LeaseCandidateEditor({ area, existing, onClose, onSave }: {
  area: RecommendationItem
  existing: LeaseCandidateRecord | null
  onClose: () => void
  onSave: (candidate: LeaseCandidateRecord) => string | null
}) {
  const [draft, setDraft] = useState<LeaseCandidateDraft>(() => existing ? draftFromCandidate(existing) : emptyLeaseDraft())
  const [extracting, setExtracting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setDraft(existing ? draftFromCandidate(existing) : emptyLeaseDraft())
    setError(null)
  }, [existing, area.area_code])

  const updateMoney = (key: LeaseMoneyField, value: string) => {
    setDraft((current) => ({
      ...current,
      money: { ...current.money, [key]: value.replace(/[^0-9.]/g, '') },
    }))
  }

  const extract = async () => {
    if (!draft.sourceUrl.trim() && !draft.sourceText.trim()) {
      setError('AI로 채우려면 매물 URL 또는 매물 설명을 입력해주세요.')
      return
    }
    setExtracting(true)
    setError(null)
    try {
      const response = await api.extractLeaseCandidate({
        source_url: draft.sourceUrl.trim() || null,
        source_text: draft.sourceText.trim() || null,
        selected_area_name: area.area_name,
      })
      setDraft((current) => draftFromExtraction(response, current))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '매물 정보를 추출하지 못했습니다.')
    } finally {
      setExtracting(false)
    }
  }

  const save = () => {
    const validationError = validateLeaseDraft(draft)
    if (validationError) return setError(validationError)
    const saveError = onSave(candidateFromDraft(draft, area, existing))
    if (saveError) return setError(saveError)
    onClose()
  }

  return (
    <div className="lease-editor-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose()
    }}>
      <aside className="lease-editor" role="dialog" aria-modal="true" aria-labelledby="lease-editor-title">
        <header>
          <div><span className="eyebrow">LEASE CANDIDATE</span><h2 id="lease-editor-title">{existing ? '임대매물 수정' : '임대매물 추가'}</h2><p>{area.area_name} · {area.industry_name}</p></div>
          <button type="button" onClick={onClose} aria-label="닫기">×</button>
        </header>
        <div className="lease-editor-body">
          <section className="lease-source-box">
            <h3>외부 매물에서 AI로 채우기 <small>선택</small></h3>
            <label><span>매물 URL</span><input type="url" value={draft.sourceUrl} onChange={(event) => setDraft({ ...draft, sourceUrl: event.target.value })} placeholder="https://..." /></label>
            <label><span>매물 설명</span><textarea rows={4} value={draft.sourceText} onChange={(event) => setDraft({ ...draft, sourceText: event.target.value })} placeholder="주소, 보증금/월세, 관리비, 권리금, 면적, 층 정보" /></label>
            <button type="button" onClick={extract} disabled={extracting}>{extracting ? 'AI가 읽는 중…' : 'AI로 아래 항목 채우기'}</button>
          </section>

          <section className="lease-manual-box">
            <h3>확인한 매물 정보 <small>직접 수정 가능</small></h3>
            <div className="lease-editor-fields two">
              <label><span>매물명</span><input value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} placeholder="선택 입력" /></label>
              <label><span>주소 *</span><input value={draft.address} onChange={(event) => setDraft({ ...draft, address: event.target.value })} /></label>
              <label><span>임대면적(㎡)</span><input type="number" min="0" value={draft.areaSqm} onChange={(event) => setDraft({ ...draft, areaSqm: event.target.value })} /></label>
              <label><span>층</span><input value={draft.floor} onChange={(event) => setDraft({ ...draft, floor: event.target.value })} /></label>
            </div>
            <div className="lease-editor-fields money">
              {leaseMoneyFields.map((field) => <label key={field.key}><span>{field.label}{field.optional ? ' · 빈칸=미확인' : ' *'}</span><div><input inputMode="numeric" value={draft.money[field.key]} onChange={(event) => updateMoney(field.key, event.target.value)} /><small>만원</small></div></label>)}
            </div>
            <p className="lease-zero-guide">관리비·권리금이 없다고 확인한 경우에는 빈칸 대신 0을 입력하세요.</p>
            <p className="lease-area-warning">이 주소가 선택한 {area.area_name} 검토 대상인지 직접 확인해주세요. 주변 영업 점포는 임대 가능 매물을 뜻하지 않습니다.</p>
            {draft.notes && <p className="finance-note">AI 메모: {draft.notes}</p>}
            {draft.warnings.length > 0 && <ul className="finance-disclosures">{draft.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>}
          </section>
          {error && <div className="finance-error" role="alert">{error}</div>}
        </div>
        <footer><button type="button" onClick={onClose}>취소</button><button type="button" className="save" onClick={save}>{existing ? '수정 저장' : '후보함에 추가'}</button></footer>
      </aside>
    </div>
  )
}
