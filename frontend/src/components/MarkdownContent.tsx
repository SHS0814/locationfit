import ReactMarkdown from 'react-markdown'

interface Props {
  content: string
  className?: string
}

export function MarkdownContent({ content, className }: Props) {
  const classes = ['markdown-content', className].filter(Boolean).join(' ')

  return (
    <div className={classes}>
      <ReactMarkdown
        components={{
          a: ({ node, ...props }) => {
            void node
            return <a {...props} target="_blank" rel="noopener noreferrer" />
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}
