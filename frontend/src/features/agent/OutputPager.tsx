export type OutputPage = 'lookup' | 'strategy' | 'recommendation'

interface Props {
  page: OutputPage
  lookupCount: number
  scenarioCount: number
  recommendationCount: number
  onChange: (page: OutputPage) => void
}

export function OutputPager({
  page,
  lookupCount,
  scenarioCount,
  recommendationCount,
  onChange,
}: Props) {
  const pages: Array<{ id: OutputPage; index: string; title: string; detail: string }> = [
    {
      id: 'lookup',
      index: '01',
      title: '일반조회',
      detail: lookupCount > 0 ? `조회 결과 ${lookupCount}개` : '순위·통계',
    },
    {
      id: 'strategy',
      index: '02',
      title: '창업맥락/전략가설',
      detail: scenarioCount > 0 ? `전략 ${scenarioCount}개` : '조건·가정·전략',
    },
    {
      id: 'recommendation',
      index: '03',
      title: '입지분석',
      detail: recommendationCount > 0
        ? `상권 ${recommendationCount}곳 · 점포 · 자금계획`
        : '상권분석 · 점포분석 · 자금계획',
    },
  ]

  return (
    <nav className="output-pager" aria-label="분석 결과 페이지">
      {pages.map((item) => (
        <button
          key={item.id}
          type="button"
          className={page === item.id ? 'active' : ''}
          aria-current={page === item.id ? 'page' : undefined}
          onClick={() => onChange(item.id)}
        >
          <b>{item.index}</b>
          <span><strong>{item.title}</strong><small>{item.detail}</small></span>
        </button>
      ))}
    </nav>
  )
}
