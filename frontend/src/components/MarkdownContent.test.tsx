import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { MarkdownContent } from './MarkdownContent'

describe('MarkdownContent', () => {
  it('renders emphasis, paragraphs, and lists as Markdown', () => {
    const html = renderToStaticMarkup(
      <MarkdownContent content={'**핵심 정보**\n\n- 첫 번째\n- 두 번째'} />,
    )

    expect(html).toContain('<strong>핵심 정보</strong>')
    expect(html).toContain('<ul>')
    expect(html).toContain('<li>첫 번째</li>')
  })

  it('opens links safely in a new tab', () => {
    const html = renderToStaticMarkup(
      <MarkdownContent content="[출처](https://example.com/source)" />,
    )

    expect(html).toContain('href="https://example.com/source"')
    expect(html).toContain('target="_blank"')
    expect(html).toContain('rel="noopener noreferrer"')
  })

  it('removes unsafe link protocols', () => {
    const html = renderToStaticMarkup(
      <MarkdownContent content="[실행](javascript:alert('unsafe'))" />,
    )

    expect(html).not.toContain('javascript:')
  })

  it('does not execute raw HTML', () => {
    const html = renderToStaticMarkup(
      <MarkdownContent content={'<script>alert("unsafe")</script>'} />,
    )

    expect(html).not.toContain('<script>')
    expect(html).toContain('&lt;script&gt;')
  })
})
