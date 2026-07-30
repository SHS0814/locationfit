import { describe, expect, it } from 'vitest'
import {
  DEMO_FLOW_QUERY_VALUE,
  createDemoLeaseCandidate,
  createDemoLeaseFinanceState,
  createAgentBriefing,
  createHongdaeCafeDemoSession,
  deriveAgentCommandStages,
  draftToRequest,
  emptyDraft,
  hongdaeCafeDemoDraft,
  isDraftReady,
  marketLookupToQuery,
  restoreSession,
  shouldRunDemoFlow,
} from './model'

describe('agent session model', () => {
  it('accepts an industry alone and treats omitted preferences as unrestricted', () => {
    expect(isDraftReady(emptyDraft)).toBe(false)
    expect(isDraftReady({ ...emptyDraft, industry_code: 'CS100001' })).toBe(true)
    expect(isDraftReady({
      ...emptyDraft,
      industry_code: 'CS100001',
      preferred_districts: ['강남구'],
    })).toBe(true)
  })

  it('restores a valid session and falls back from malformed JSON', () => {
    const draft = { ...emptyDraft, industry_code: 'CS100001', target_age_groups: ['20'] }
    const restored = restoreSession(JSON.stringify({
      schemaVersion: 7,
      history: [{ role: 'user', content: '카페를 열고 싶어요' }],
      draft,
      phase: 'ready_for_confirmation',
      items: [],
      comparison: [],
      activeRequest: draftToRequest(draft),
    }))
    expect(restored.draft.industry_code).toBe('CS100001')
    expect(restored.schemaVersion).toBe(9)
    expect(restored.recommendationReport).toBeNull()
    expect(restored.context.discovery_question_count).toBe(0)
    expect(restored.storeRelations).toEqual(['competitor', 'complementary', 'daily_life', 'other'])
    expect(restored.leaseCandidates).toEqual([])
    expect(restored.marketLookupHistory).toEqual([])
    expect(restored.marketLookupIndex).toBe(-1)
    expect(restored.phase).toBe('discovering')
    expect(restored.draft.performance_group_weights).toBeNull()
    expect(restoreSession('{broken').phase).toBe('discovering')
  })

  it('drops cached recommendation items that predate map boundaries', () => {
    const draft = { ...emptyDraft, industry_code: 'CS100001', target_age_groups: ['20'] }
    const restored = restoreSession(JSON.stringify({
      schemaVersion: 7,
      history: [{ role: 'user', content: '카페를 열고 싶어요' }],
      draft,
      phase: 'results',
      items: [{ area_code: '3110001', area_name: '오래된 결과' }],
      activeRequest: draftToRequest(draft),
    }))
    expect(restored.items).toEqual([])
    expect(restored.activeRequest).toBeNull()
  })

  it('restores v8 lease candidates and their finance state', () => {
    const draft = { ...emptyDraft, industry_code: 'CS100001' }
    const financeState = {
      additionalCosts: { interior_krw: 0, equipment_krw: 0, initial_inventory_krw: 0, working_capital_krw: 0, other_krw: 0 },
      eligibility: { own_capital_krw: 10_000_000, business_status: 'pre_startup', business_age_months: null, is_small_business: null, vulnerability: 'unknown', has_policy_excluded_industry: null },
      plan: null,
    }
    const restored = restoreSession(JSON.stringify({
      schemaVersion: 8,
      history: [{ role: 'user', content: '매물 후보' }],
      draft,
      phase: 'results',
      items: [],
      leaseCandidates: [{ id: 'listing-1', areaCode: 'A1', title: '테스트 매물' }],
      leaseFinanceById: { 'listing-1': financeState },
      selectedLeaseCandidateId: 'listing-1',
      financeAreaCode: 'A1',
    }))
    expect(restored.leaseCandidates).toHaveLength(1)
    expect(restored.leaseFinanceById['listing-1'].eligibility.own_capital_krw).toBe(10_000_000)
    expect(restored.leaseFinanceById['listing-1'].eligibility.has_miso_good_repayment_history).toBeNull()
    expect(restored.selectedLeaseCandidateId).toBe('listing-1')
    expect(restored.workspaceChats.stores[0].content).toContain('선택한 상권')
  })

  it('clears a restored lease selection that belongs to another area', () => {
    const restored = restoreSession(JSON.stringify({
      schemaVersion: 9,
      history: [{ role: 'user', content: '다른 상권으로 이동' }],
      draft: { ...emptyDraft, industry_code: 'CS100001' },
      phase: 'results',
      leaseCandidates: [{ id: 'listing-a', areaCode: 'A1', title: '이전 상권 매물' }],
      selectedLeaseCandidateId: 'listing-a',
      financeAreaCode: 'B1',
    }))
    expect(restored.financeAreaCode).toBe('B1')
    expect(restored.selectedLeaseCandidateId).toBeNull()
  })

  it('restores independent page agent conversations', () => {
    const restored = restoreSession(JSON.stringify({
      schemaVersion: 8,
      history: [{ role: 'assistant', content: '기존 상담' }],
      draft: emptyDraft,
      phase: 'results',
      workspaceChats: {
        stores: [{ role: 'user', content: '점포 질문' }],
        finance: [{ role: 'user', content: '자금 질문' }],
      },
    }))

    expect(restored.workspaceChats.stores[0].content).toBe('점포 질문')
    expect(restored.workspaceChats.finance[0].content).toBe('자금 질문')
  })

  it('clears only a legacy hardcoded finance plan while preserving its inputs', () => {
    const draft = { ...emptyDraft, industry_code: 'CS100001' }
    const restored = restoreSession(JSON.stringify({
      schemaVersion: 8,
      history: [{ role: 'user', content: '기존 금융계획' }],
      draft,
      phase: 'results',
      leaseCandidates: [],
      leaseFinanceById: {
        'listing-1': {
          additionalCosts: { interior_krw: 5_000_000 },
          eligibility: { own_capital_krw: 10_000_000, business_status: 'pre_startup' },
          plan: { policy_candidates: [{ program_id: 'legacy-hardcoded' }] },
        },
      },
    }))

    expect(restored.leaseFinanceById['listing-1'].plan).toBeNull()
    expect(restored.leaseFinanceById['listing-1'].additionalCosts.interior_krw).toBe(5_000_000)
    expect(restored.leaseFinanceById['listing-1'].eligibility.has_miso_good_repayment_history).toBeNull()
  })

  it('keeps an industry-only draft ready after strategy selection', () => {
    expect(isDraftReady({ ...emptyDraft, industry_code: 'CS100001', strategy: 'growth' })).toBe(true)
  })

  it('includes normalized custom performance weights in the API payload and blocks all-zero weights', () => {
    const weights = { scale_productivity: 0.2, growth: 0.4, stability: 0.2, competition: 0.05, closure_risk: 0.15 }
    const draft = { ...emptyDraft, industry_code: 'CS100001', performance_group_weights: weights }
    expect(draftToRequest(draft).performance_group_weights).toEqual(weights)
    expect(isDraftReady({
      ...draft,
      performance_group_weights: { scale_productivity: 0, growth: 0, stability: 0, competition: 0, closure_risk: 0 },
    })).toBe(false)
  })

  it('requires complete rent conditions only when a monthly cap is used', () => {
    const base = { ...emptyDraft, industry_code: 'CS100001', preferred_districts: ['강남구'] }
    expect(isDraftReady({ ...base, total_startup_budget_krw: 100_000_000 })).toBe(true)
    expect(isDraftReady({ ...base, monthly_converted_rent_limit_krw: 4_000_000 })).toBe(false)
    expect(isDraftReady({ ...base, rentable_area_sqm: 66 })).toBe(false)
    expect(isDraftReady({
      ...base,
      monthly_converted_rent_limit_krw: 4_000_000,
      rentable_area_sqm: 66,
      floor: 'f1',
    })).toBe(true)
  })

  it('provides a ready deterministic Hongdae cafe demo session', () => {
    const session = createHongdaeCafeDemoSession()

    expect(isDraftReady(hongdaeCafeDemoDraft)).toBe(true)
    expect(session.draft.industry_code).toBe('CS100010')
    expect(session.draft.preferred_districts).toEqual(['마포구'])
    expect(session.draft.strategy).toBe('growth')
    expect(session.selectedScenarioId).toBeNull()
    expect(shouldRunDemoFlow(`?demo=${DEMO_FLOW_QUERY_VALUE}`)).toBe(true)
    expect(shouldRunDemoFlow('?demo=other')).toBe(false)
  })

  it('keeps the deterministic market lookup parameters for follow-up questions', () => {
    const query = marketLookupToQuery({
      title: '최근 폐업률 기준 낮은 업종 Top 3',
      group_by: 'industry',
      metric: 'closing_rate',
      metric_label: '최근 폐업률',
      metric_unit: 'ratio',
      order: 'asc',
      filters: { district_name: '도봉구' },
      data_period: '2025Q1~2025Q4',
      distribution: { population_count: 63, mean: 0.02, mean_display: '2.0%', median: 0.018, median_display: '1.8%', standard_deviation: 0.01, standard_deviation_display: '1.0%p' },
      rows: [
        { rank: 1, entity_code: 'CS200007', entity_name: '치과의원', metric_value: 0.004, metric_display_value: '0.4%', difference_from_mean: -0.016, difference_from_mean_display: '-1.6%p', difference_from_median: -0.014, difference_from_median_display: '-1.4%p', standard_deviation_distance: -1.6, district_name: null, admin_dong_name: null, area_count: 10, observation_count: 10 },
      ],
      geographic_basis: '서울시 상권영역',
      disclosure: '관측 상권은 집계에 포함된 고유 서울시 상권입니다.',
    })

    expect(query).toEqual({
      group_by: 'industry',
      metric: 'closing_rate',
      top_n: 1,
      order: 'asc',
      district_name: '도봉구',
      admin_dong_name: null,
      industry_code: null,
    })
  })

  it('derives the AI command stages from the existing session state', () => {
    const initialStages = deriveAgentCommandStages(createHongdaeCafeDemoSession())
    expect(initialStages.map((stage) => stage.status)).toEqual([
      'complete', 'active', 'pending', 'pending', 'pending', 'pending',
    ])

    const session = createHongdaeCafeDemoSession()
    const recommendationStages = deriveAgentCommandStages({
      ...session,
      scenarios: [{}] as typeof session.scenarios,
      selectedScenarioId: 'growth',
      items: [{}] as typeof session.items,
      recommendationReport: {} as NonNullable<typeof session.recommendationReport>,
      leaseCandidates: [{}] as typeof session.leaseCandidates,
    })
    expect(recommendationStages.map((stage) => stage.status)).toEqual([
      'complete', 'complete', 'complete', 'complete', 'complete', 'active',
    ])
    expect(recommendationStages[5].detail).toContain('정책자금')
  })

  it('creates an AI briefing from deterministic recommendation evidence', () => {
    const session = createHongdaeCafeDemoSession()
    const briefing = createAgentBriefing({
      ...session,
      recommendationReport: {
        candidate_count: 27,
        benchmark_label: '후보 중앙값',
        data_period: {},
        competition_reference_period: '2025Q4',
        rental_estimate_basis: '입력 조건 기준',
        rental_estimate_uses_default: false,
        performance_group_weights: { scale_productivity: 0.35, growth: 0.27, stability: 0.18, competition: 0.08, closure_risk: 0.12 },
        performance_weights_source: 'strategy_default',
        benchmark: {} as NonNullable<typeof session.recommendationReport>['benchmark'],
        areas: [{
          area_code: 'A1',
          area_name: '홍대입구역(홍대)',
          rank: 1,
          district_name: '마포구',
          area_type: '발달상권',
          reliability_grade: 'A',
          base_final_score: 84,
          budget_fit_score: 90,
          rental_estimate: null,
          metrics: { final_score: 86, condition_fit_score: 91 } as NonNullable<typeof session.recommendationReport>['areas'][number]['metrics'],
          benchmark_delta: {} as NonNullable<typeof session.recommendationReport>['areas'][number]['benchmark_delta'],
          positive_reasons: [{ factor: '주말 유동', feature: 'weekend', fit_score: 94, weight: 0.8 }],
          negative_reasons: [],
          warnings: [],
          performance_breakdown: {} as NonNullable<typeof session.recommendationReport>['areas'][number]['performance_breakdown'],
        }],
      },
    })

    expect(briefing.title).toContain('홍대입구역(홍대)')
    expect(briefing.summary).toContain('세부 수치는 아래 보고서')
    expect(briefing.evidence).toContain('추천 이유 · 주말 유동')
    expect(briefing.evidence.join(' ')).not.toContain('94.0점')
  })

  it('creates a complete arbitrary lease candidate for the demo area', () => {
    const candidate = createDemoLeaseCandidate({
      rank: 1,
      area_code: 'A1',
      area_name: '홍대입구역(홍대)',
      district_name: '마포구',
      admin_dong_name: '서교동',
      area_type: '골목상권',
      industry_code: 'CS100010',
      industry_name: '커피-음료',
      latitude: 37.55,
      longitude: 126.92,
      area_size_sqm: 1000,
      boundary: { type: 'Polygon', coordinates: [] },
      final_score: 80,
      base_final_score: null,
      budget_fit_score: null,
      budget_adjusted: false,
      condition_fit_score: 80,
      raw_evidence_score: null,
      reliability_adjusted_evidence_score: null,
      data_reliability: 1,
      reliability_grade: 'A',
      positive_reasons: [],
      negative_reasons: [],
      evidence_summary: {},
      performance_breakdown: {} as Parameters<typeof createDemoLeaseCandidate>[0]['performance_breakdown'],
      warnings: [],
      rental_estimate: null,
    })
    const finance = createDemoLeaseFinanceState()

    expect(candidate.areaCode).toBe('A1')
    expect(candidate.managementFeeKrw).toBe(400_000)
    expect(candidate.keyMoneyKrw).toBe(20_000_000)
    expect(candidate.warnings[0]).toContain('데모용 임의 매물')
    expect(finance.additionalCosts.interior_krw).toBe(40_000_000)
    expect(finance.eligibility.is_small_business).toBe(true)
  })

  it('drops legacy property type and unsupported floor values during session migration', () => {
    const restored = restoreSession(JSON.stringify({
      schemaVersion: 5,
      history: [{ role: 'user', content: '기존 조건' }],
      draft: { ...emptyDraft, commercial_property_type: 'small_retail', floor: 'f2' },
      phase: 'results',
    }))
    expect(restored.schemaVersion).toBe(9)
    expect(restored.draft.floor).toBeNull()
    expect('commercial_property_type' in restored.draft).toBe(false)
    expect(restored.phase).toBe('discovering')
  })
})
