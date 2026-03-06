import { Link2, ExternalLink } from 'lucide-react'

interface SourcesPanelProps {
  sources: string[]
}

export function SourcesPanel({ sources }: SourcesPanelProps) {
  if (sources.length === 0) {
    return (
      <aside className="sources-panel">
        <div className="sources-header">
          <Link2 size={18} />
          <h3>Sources</h3>
        </div>
        <div className="sources-empty">
          <p>Sources will appear here when available</p>
        </div>
      </aside>
    )
  }

  return (
    <aside className="sources-panel">
      <div className="sources-header">
        <Link2 size={18} />
        <h3>Sources</h3>
        <span className="sources-count">{sources.length}</span>
      </div>
      
      <div className="sources-list">
        {sources.map((source, idx) => (
          <a
            key={idx}
            href={source}
            target="_blank"
            rel="noopener noreferrer"
            className="source-link"
          >
            <span className="source-number">{idx + 1}</span>
            <span className="source-url">{source}</span>
            <ExternalLink size={14} className="source-icon" />
          </a>
        ))}
      </div>
    </aside>
  )
}
