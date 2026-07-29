import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { WorkspaceAgentPanel } from './WorkspaceAgentPanel'

describe('WorkspaceAgentPanel tool evidence', () => {
  it('renders deterministic finance evidence and assumptions', () => {
    const html = renderToStaticMarkup(
      <WorkspaceAgentPanel
        workspace="finance"
        history={[{ role: 'assistant', content: '계산했습니다.' }]}
        loading={false}
        error={null}
        toolOutputs={[{
          kind: 'finance_scenario',
          status: 'succeeded',
          title: '가정 시나리오',
          payload: {
            funding: {
              total_first_year_cash_need_krw: 53_200_000,
              funding_gap_krw: 28_200_000,
              own_capital_ratio: 0.47,
            },
          },
          as_of: null,
          assumptions: ['인테리어비=20000000'],
          warnings: ['저장값을 변경하지 않습니다.'],
        }]}
        onSend={() => undefined}
        onClear={() => undefined}
      />,
    )

    expect(html).toContain('도구 실행 근거')
    expect(html).toContain('53,200,000원')
    expect(html).toContain('인테리어비=20000000')
    expect(html).toContain('저장값을 변경하지 않습니다.')
  })

  it('renders web research sources as safe external links', () => {
    const html = renderToStaticMarkup(
      <WorkspaceAgentPanel
        workspace="stores"
        history={[]}
        loading={false}
        error={null}
        toolOutputs={[{
          kind: 'web_research', status: 'succeeded', title: '최신 정보',
          payload: {
            summary: '최근 정보를 확인했습니다.',
            sources: [{ title: '공식 출처', url: 'https://example.com/source' }],
          },
          as_of: '2026-07-29', assumptions: [], warnings: [],
        }]}
        onSend={() => undefined}
        onClear={() => undefined}
      />,
    )

    expect(html).toContain('href="https://example.com/source"')
    expect(html).toContain('target="_blank"')
    expect(html).toContain('rel="noreferrer"')
  })
})
