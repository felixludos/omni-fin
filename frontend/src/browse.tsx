import { useEffect, useMemo, useState } from 'react'

// ── Types matching backend API ───────────────────────────────────────────────

type BrowseRow = {
  id: string
  low: Record<string, unknown>
  high: Record<string, unknown>
}

type BrowseResponse = {
  total: number
  limit: number
  offset: number
  low_columns: string[]
  high_columns: string[]
  rows: BrowseRow[]
  column_hints?: Record<string, string[]>
}

type TagInfo = {
  id: string
  name: string
  category: string | null
}

type CommentInfo = {
  id: string
  content: string
  type: string | null
  created_at: string
}

type DetailResponse = {
  low: Record<string, unknown>
  high: Record<string, unknown>
  tags: TagInfo[]
  comments: CommentInfo[]
  related: Record<string, unknown>
}

const MODELS = ['assets', 'accounts', 'transfers', 'statements', 'events', 'reports'] as const
type ModelType = typeof MODELS[number]

const MODEL_LABELS: Record<ModelType, string> = {
  assets: 'Assets',
  accounts: 'Accounts',
  transfers: 'Transfers',
  statements: 'Statements',
  events: 'Events',
  reports: 'Reports',
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function formatCellValue(val: unknown): string {
  if (val === null || val === undefined) return ''
  if (typeof val === 'number') {
    if (Number.isInteger(val)) return val.toLocaleString()
    return val.toFixed(2)
  }
  if (typeof val === 'boolean') return val ? 'true' : 'false'
  return String(val)
}

function formatColHeader(col: string): string {
  return col
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

// ── ObjectDetailPanel ────────────────────────────────────────────────────────

function ObjectDetailPanel({
  detail,
  viewMode,
  onClose,
}: {
  detail: DetailResponse
  viewMode: 'low' | 'high'
  onClose: () => void
}) {
  const fields = viewMode === 'low' ? detail.low : detail.high

  return (
    <div className="detail-overlay" onClick={onClose}>
      <div className="detail-panel" onClick={(e) => e.stopPropagation()}>
        <div className="detail-header">
          <h3>Details</h3>
          <button className="detail-close" onClick={onClose}>
            ✕
          </button>
        </div>

        {/* Core fields */}
        <section className="detail-section">
          <h4>Fields</h4>
          <table className="detail-fields">
            <tbody>
              {Object.entries(fields).map(([key, value]) => (
                <tr key={key}>
                  <td className="detail-key">{formatColHeader(key)}</td>
                  <td className="detail-value">{formatCellValue(value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        {/* Related objects */}
        {Object.keys(detail.related).length > 0 && (
          <section className="detail-section">
            <h4>Related</h4>
            {Object.entries(detail.related).map(([relKey, relValue]) => {
              const items = Array.isArray(relValue) ? relValue : [relValue]
              if (items.length === 0) return null
              return (
                <div key={relKey} className="detail-related-block">
                  <h5>{formatColHeader(relKey)}</h5>
                  {items.map((item: Record<string, unknown>, idx: number) => (
                    <table key={idx} className="detail-fields detail-sub">
                      <tbody>
                        {Object.entries(item).map(([k, v]) => (
                          <tr key={k}>
                            <td className="detail-key">{formatColHeader(k)}</td>
                            <td className="detail-value">{formatCellValue(v)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ))}
                </div>
              )
            })}
          </section>
        )}

        {/* Tags */}
        {detail.tags.length > 0 && (
          <section className="detail-section">
            <h4>Tags</h4>
            <div className="detail-tags">
              {detail.tags.map((tag) => (
                <span key={tag.id} className="tag-pill" title={tag.category ?? ''}>
                  {tag.name}
                </span>
              ))}
            </div>
          </section>
        )}

        {/* Comments */}
        {detail.comments.length > 0 && (
          <section className="detail-section">
            <h4>Comments</h4>
            {detail.comments.map((c) => (
              <div key={c.id} className="detail-comment">
                <p>{c.content}</p>
                <span className="comment-meta">
                  {c.type && <span>{c.type} · </span>}
                  {new Date(c.created_at).toLocaleString()}
                </span>
              </div>
            ))}
          </section>
        )}
      </div>
    </div>
  )
}

// ── BrowsePanel ──────────────────────────────────────────────────────────────

export default function BrowsePanel({ dbPath }: { dbPath: string | undefined }) {
  const [activeTab, setActiveTab] = useState<ModelType>('accounts')
  const [viewMode, setViewMode] = useState<'low' | 'high'>('high')
  const [searchQuery, setSearchQuery] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')
  const [browseData, setBrowseData] = useState<BrowseResponse | null>(null)
  const [columnHints, setColumnHints] = useState<Record<string, string[]>>({})
  const [loading, setLoading] = useState(false)
  const [detailData, setDetailData] = useState<DetailResponse | null>(null)
  const [loadingDetail, setLoadingDetail] = useState(false)

  // Debounce search
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQuery(searchQuery), 250)
    return () => clearTimeout(timer)
  }, [searchQuery])

  // Fetch list when tab, search, or dbPath changes
  useEffect(() => {
    setLoading(true)
    setDetailData(null)
    const params = new URLSearchParams({
      view: viewMode,
      limit: '200',
      offset: '0',
    })
    if (debouncedQuery) params.set('q', debouncedQuery)

    fetch(`/api/browse/${activeTab}?${params}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(r)))
      .then((data: BrowseResponse) => {
        setBrowseData(data)
        setColumnHints(data.column_hints ?? {})
      })
      .catch(() => { setBrowseData(null); setColumnHints({}) })
      .finally(() => setLoading(false))
  }, [activeTab, debouncedQuery, dbPath])

  // Fetch detail when a row is clicked
  const openDetail = (id: string) => {
    setLoadingDetail(true)
    fetch(`/api/browse/${activeTab}/${encodeURIComponent(id)}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(r)))
      .then((data: DetailResponse) => setDetailData(data))
      .catch(() => setDetailData(null))
      .finally(() => setLoadingDetail(false))
  }

  const columns = browseData
    ? viewMode === 'low'
      ? browseData.low_columns
      : browseData.high_columns
    : []

  return (
    <div className="browse-panel">
      {/* Toolbar */}
      <div className="browse-toolbar">
        <input
          className="browse-search"
          type="text"
          placeholder="Search…"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.currentTarget.value)}
        />
        <div className="view-toggle">
          <button
            type="button"
            className={viewMode === 'low' ? 'active' : ''}
            onClick={() => setViewMode('low')}
          >
            Low-level
          </button>
          <button
            type="button"
            className={viewMode === 'high' ? 'active' : ''}
            onClick={() => setViewMode('high')}
          >
            High-level
          </button>
        </div>
      </div>

      {/* Tabs */}
      <nav className="browse-tabs">
        {MODELS.map((m) => (
          <button
            key={m}
            type="button"
            className={activeTab === m ? 'active' : ''}
            onClick={() => setActiveTab(m)}
          >
            {MODEL_LABELS[m]}
            {browseData && activeTab === m && (
              <span className="browse-count">{browseData.total}</span>
            )}
          </button>
        ))}
      </nav>

      {/* Loading indicator */}
      {loading && (
        <div className="browse-loading">
          <span>Loading…</span>
        </div>
      )}

      {/* Table */}
      {!loading && browseData && (
        <div className="browse-table-wrapper">
          {browseData.rows.length === 0 ? (
            <div className="browse-empty">
              {debouncedQuery
                ? `No ${MODEL_LABELS[activeTab].toLowerCase()} matching "${debouncedQuery}"`
                : `No ${MODEL_LABELS[activeTab].toLowerCase()} yet`}
            </div>
          ) : (
            <table className="browse-table">
              <thead>
                <tr>
                  {columns.map((col) => (
                    <th key={col}>{formatColHeader(col)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                  {browseData.rows.map((row) => {
                  const data = viewMode === 'low' ? row.low : row.high
                  return (
                    <tr
                      key={row.id}
                      className="browse-row"
                      onClick={() => openDetail(row.id)}
                    >
                      {columns.map((col) => {
                        const val = data[col]
                        const hints = columnHints[col]
                        if (hints && val != null && val !== '') {
                          return (
                            <td key={col}>
                              <span
                                className="tag-pill"
                                title={`Possible values: ${hints.join(', ')}`}
                              >
                                {formatCellValue(val)}
                              </span>
                            </td>
                          )
                        }
                        return <td key={col}>{formatCellValue(val)}</td>
                      })}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Detail modal */}
      {loadingDetail && (
        <div className="detail-overlay">
          <div className="detail-panel detail-loading">
            <p>Loading details…</p>
          </div>
        </div>
      )}
      {detailData && !loadingDetail && (
        <ObjectDetailPanel
          detail={detailData}
          viewMode={viewMode}
          onClose={() => setDetailData(null)}
        />
      )}
    </div>
  )
}
