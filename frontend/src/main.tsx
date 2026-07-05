import React, { useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import BrowsePanel from './browse'
import AiTuningPanel from './tuning'
import './style.css'

type ProposedObjectType =
  | 'asset'
  | 'account'
  | 'transfer'
  | 'event'
  | 'investment_sale'
  | 'statement'

type ProposedObject = {
  object_type: ProposedObjectType
  data: Record<string, unknown>
  note?: string | null
}

type RowInterpretation = {
  summary: string
  confidence: number
  objects: ProposedObject[]
}

type IngestRow = {
  index: number
  source_row: Record<string, string>
  edited_row: Record<string, string>
  row_hash: string
  selected: boolean
  status: 'pending' | 'processing' | 'processed' | 'error'
  checks: string[]
  error?: string | null
  llm_error?: string | null
  interpretation?: RowInterpretation | null
  updated_at: string
}

type AccountInfo = {
  id: string
  name?: string | null
  type?: string | null
  institution?: string | null
}

type IngestJob = {
  id: string
  filename: string
  created_at: string
  updated_at: string
  document_hash: string
  headers: string[]
  paused: boolean
  status: 'running' | 'paused' | 'completed' | 'error'
  rows: IngestRow[]
}

type CommitResponse = {
  report_id: string
  selected_rows: number
  plan_valid: boolean
  inserts: Record<string, number>
  updates: Record<string, number>
  unchanged: Record<string, number>
  errors: string[]
}

type DbInfo = {
  path: string
  filename: string
  exists: boolean
  size_bytes: number
  dir: string
}

type DbFileInfo = {
  path: string
  filename: string
  size_bytes: number
}

const SAMPLE_OBJECTS: ProposedObjectType[] = [
  'transfer',
  'statement',
  'asset',
  'account',
  'event',
  'investment_sale'
]

function parseJsonObject(text: string): Record<string, string> {
  const parsed = JSON.parse(text)
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('Expected a JSON object')
  }
  const out: Record<string, string> = {}
  Object.entries(parsed).forEach(([key, value]) => {
    out[String(key)] = value === null ? '' : String(value)
  })
  return out
}

function parseInterpretation(text: string): RowInterpretation {
  const parsed = JSON.parse(text)
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('Interpretation must be a JSON object')
  }

  const summary = typeof parsed.summary === 'string' ? parsed.summary : ''
  const confidence = typeof parsed.confidence === 'number' ? parsed.confidence : 0
  const rawObjects: unknown[] = Array.isArray(parsed.objects) ? parsed.objects : []
  const objects: ProposedObject[] = rawObjects
    .filter((obj: unknown): obj is { object_type: ProposedObjectType; data: Record<string, unknown>; note?: string } => {
      return (
        obj !== null &&
        typeof obj === 'object' &&
        !Array.isArray(obj) &&
        typeof (obj as { object_type?: unknown }).object_type === 'string' &&
        typeof (obj as { data?: unknown }).data === 'object' &&
        (obj as { data?: unknown }).data !== null
      )
    })
    .map((obj: { object_type: ProposedObjectType; data: Record<string, unknown>; note?: string }) => ({
      object_type: obj.object_type,
      data: obj.data,
      note: obj.note
    }))

  return { summary, confidence, objects }
}

function App() {
  const [job, setJob] = useState<IngestJob | null>(null)
  const [accounts, setAccounts] = useState<AccountInfo[]>([])
  const [selectedAccountId, setSelectedAccountId] = useState<string>('')
  const [selectedRowIndex, setSelectedRowIndex] = useState<number | null>(null)
  const [fileName, setFileName] = useState<string>('')
  const [isUploading, setIsUploading] = useState<boolean>(false)
  const [isCommitting, setIsCommitting] = useState<boolean>(false)
  const [statusMessage, setStatusMessage] = useState<string>('Upload a CSV to start AI ingestion')
  const [errorMessage, setErrorMessage] = useState<string>('')
  const [commitResult, setCommitResult] = useState<CommitResponse | null>(null)

  // Database management state
  const [currentDb, setCurrentDb] = useState<DbInfo | null>(null)
  const [availableDbs, setAvailableDbs] = useState<DbFileInfo[]>([])
  const [dbMode, setDbMode] = useState<'browse' | 'create'>('browse')
  const [dbInput, setDbInput] = useState('')
  const [selectedDbPath, setSelectedDbPath] = useState('')
  const [isLoadingDb, setIsLoadingDb] = useState(true)
  const [dbMessage, setDbMessage] = useState('')
  const [hasDb, setHasDb] = useState(false)
  const [seedWithData, setSeedWithData] = useState(true)
  const [debugMode, setDebugMode] = useState<boolean>(false)
  const [activeView, setActiveView] = useState<'ingestion' | 'tuning'>('ingestion')

  const selectedRow = useMemo(() => {
    if (!job || selectedRowIndex === null) {
      return null
    }
    return job.rows.find((row) => row.index === selectedRowIndex) ?? null
  }, [job, selectedRowIndex])

  const [rowEditorText, setRowEditorText] = useState<string>('{}')
  const [resultEditorText, setResultEditorText] = useState<string>(
    JSON.stringify({ summary: '', confidence: 0, objects: [] }, null, 2)
  )

  useEffect(() => {
    if (!selectedRow) {
      setRowEditorText('{}')
      setResultEditorText(JSON.stringify({ summary: '', confidence: 0, objects: [] }, null, 2))
      return
    }

    setRowEditorText(JSON.stringify(selectedRow.edited_row, null, 2))
    setResultEditorText(
      JSON.stringify(
        selectedRow.interpretation ?? { summary: '', confidence: 0, objects: [] },
        null,
        2
      )
    )
  }, [selectedRowIndex, selectedRow?.updated_at])

  // Auto-load previous database on mount, then scan for available DBs
  useEffect(() => {
    const lastDb = localStorage.getItem('omnifin_last_db')

    const loadDb = lastDb
      ? fetch('/api/db/open', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path: lastDb }),
        }).then((r) => (r.ok ? r.json() : Promise.reject()))
      : fetch('/api/db').then((r) => r.json())

    const onDbLoaded = (data: DbInfo) => {
      setCurrentDb(data)
      if (data.exists) {
        setHasDb(true)
        setDbMessage(lastDb ? `Loaded previous database: ${data.filename}` : `Loaded database: ${data.filename}`)
        fetch('/api/accounts')
          .then((r) => r.json())
          .then((accounts: AccountInfo[]) => setAccounts(accounts))
          .catch(() => {})
      }
    }

    loadDb.then(onDbLoaded).catch(() => {
      fetch('/api/db')
        .then((r) => r.json())
        .then(onDbLoaded)
        .catch(() => {})
    }).finally(() => setIsLoadingDb(false))

    fetch('/api/db/scan')
      .then((r) => r.json())
      .then((data: DbFileInfo[]) => {
        setAvailableDbs(data)
        if (data.length > 0) {
          setSelectedDbPath(data[0].path)
          setDbInput(data[0].filename)
        }
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (debugMode && hasDb && !job) {
      void loadExampleFile()
    }
  }, [debugMode])

  useEffect(() => {
    if (!hasDb || !job) {
      return
    }
    const timer = window.setInterval(() => {
      fetch(`/api/ingest/jobs/${job.id}`)
        .then((response) => response.json())
        .then((data: IngestJob) => {
          setJob(data)
          const done = data.rows.filter((row) => row.status === 'processed').length
          const failed = data.rows.filter((row) => row.status === 'error').length
          const running = data.rows.filter((row) => row.status === 'processing').length
          setStatusMessage(
            `Job ${data.status}. Processed ${done}/${data.rows.length}, running ${running}, errors ${failed}`
          )
          if (selectedRowIndex === null && data.rows.length > 0) {
            setSelectedRowIndex(data.rows[0].index)
          }
        })
        .catch((error: unknown) => {
          setErrorMessage(String(error))
        })
    }, 800)
    return () => window.clearInterval(timer)
  }, [job?.id])

  const uploadCsv = async (file: File): Promise<void> => {
    setIsUploading(true)
    setErrorMessage('')
    setCommitResult(null)
    try {
      const csvText = await file.text()
      let body: Record<string, string> = { filename: file.name, csv_text: csvText }
      if (selectedAccountId) {
        body.account_id = selectedAccountId
      }
      const response = await fetch('/api/ingest/jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      })
      if (!response.ok) {
        throw new Error(await response.text())
      }
      const data = (await response.json()) as IngestJob
      setFileName(file.name)
      setJob(data)
      setSelectedRowIndex(data.rows.length > 0 ? data.rows[0].index : null)
      setStatusMessage(`Created job with ${data.rows.length} rows`)
    } catch (error) {
      setErrorMessage(String(error))
    } finally {
      setIsUploading(false)
    }
  }

  const postJobAction = async (action: 'pause' | 'resume' | 'rerun-all'): Promise<void> => {
    if (!job) {
      return
    }
    setErrorMessage('')
    try {
      const response = await fetch(`/api/ingest/jobs/${job.id}/${action}`, { method: 'POST' })
      if (!response.ok) {
        throw new Error(await response.text())
      }
      const data = (await response.json()) as IngestJob
      setJob(data)
    } catch (error) {
      setErrorMessage(String(error))
    }
  }

  const loadExampleFile = async (): Promise<void> => {
    setErrorMessage('')
    setCommitResult(null)
    try {
      const response = await fetch('/api/ingest/examples/load', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: 'fidelity_sales.csv', account_id: selectedAccountId || undefined })
      })
      if (!response.ok) {
        throw new Error(await response.text())
      }
      const data = (await response.json()) as IngestJob
      setFileName(data.filename)
      setJob(data)
      setSelectedRowIndex(data.rows.length > 0 ? data.rows[0].index : null)
      setStatusMessage(`Debug: loaded "${data.filename}" with ${data.rows.length} rows (paused)`)
    } catch (error) {
      setErrorMessage(String(error))
    }
  }

  const rerunSelectedRows = async (): Promise<void> => {
    if (!job) {
      return
    }
    const selectedIndices = job.rows.filter((row) => row.selected).map((row) => row.index)
    if (selectedIndices.length === 0) {
      setErrorMessage('Select at least one row to rerun')
      return
    }
    setErrorMessage('')
    try {
      const response = await fetch(`/api/ingest/jobs/${job.id}/rerun-rows`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ row_indices: selectedIndices })
      })
      if (!response.ok) {
        throw new Error(await response.text())
      }
      const data = (await response.json()) as IngestJob
      setJob(data)
    } catch (error) {
      setErrorMessage(String(error))
    }
  }

  const patchRow = async (
    rowIndex: number,
    payload: {
      edited_row?: Record<string, string>
      interpretation?: RowInterpretation
      selected?: boolean
    }
  ): Promise<void> => {
    if (!job) {
      return
    }
    const response = await fetch(`/api/ingest/jobs/${job.id}/rows/${rowIndex}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    if (!response.ok) {
      throw new Error(await response.text())
    }
    const updated = (await response.json()) as IngestRow
    setJob((previous) => {
      if (!previous) {
        return previous
      }
      return {
        ...previous,
        rows: previous.rows.map((row) => (row.index === updated.index ? updated : row))
      }
    })
  }

  const toggleSelectAll = async (selected: boolean): Promise<void> => {
    if (!job) {
      return
    }
    setErrorMessage('')
    for (const row of job.rows) {
      try {
        // Intentional sequential writes to keep row state updates deterministic.
        await patchRow(row.index, { selected })
      } catch (error) {
        setErrorMessage(String(error))
        break
      }
    }
  }

  const saveRowEdits = async (): Promise<void> => {
    if (!selectedRow) {
      return
    }
    setErrorMessage('')
    try {
      await patchRow(selectedRow.index, {
        edited_row: parseJsonObject(rowEditorText),
        interpretation: parseInterpretation(resultEditorText)
      })
      setStatusMessage(`Saved edits for row ${selectedRow.index}`)
    } catch (error) {
      setErrorMessage(String(error))
    }
  }

  const toggleRowSelection = async (rowIndex: number, selected: boolean): Promise<void> => {
    setErrorMessage('')
    try {
      await patchRow(rowIndex, { selected })
    } catch (error) {
      setErrorMessage(String(error))
    }
  }

  const addObjectToSelectedRow = (objectType: ProposedObjectType): void => {
    try {
      const interpretation = parseInterpretation(resultEditorText)
      interpretation.objects.push({
        object_type: objectType,
        data: {},
        note: 'manually added'
      })
      setResultEditorText(JSON.stringify(interpretation, null, 2))
    } catch {
      setErrorMessage('Fix result JSON before adding object templates')
    }
  }

  const commitSelectedRows = async (dryRun: boolean): Promise<void> => {
    if (!job) {
      return
    }
    setIsCommitting(true)
    setErrorMessage('')
    try {
      const selected = job.rows.filter((row) => row.selected).map((row) => row.index)
      const response = await fetch(`/api/ingest/jobs/${job.id}/commit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ row_indices: selected, dry_run: dryRun })
      })
      if (!response.ok) {
        throw new Error(await response.text())
      }
      const data = (await response.json()) as CommitResponse
      setCommitResult(data)
      setStatusMessage(dryRun ? 'Dry run completed' : 'Saved selected rows to database')
    } catch (error) {
      setErrorMessage(String(error))
    } finally {
      setIsCommitting(false)
    }
  }

  const processedCount = job ? job.rows.filter((row) => row.status === 'processed').length : 0
  const failedCount = job ? job.rows.filter((row) => row.status === 'error').length : 0

  const handleLoadCreateDb = async (): Promise<void> => {
    setErrorMessage('')
    setIsLoadingDb(true)
    try {
      let response: Response
      if (dbMode === 'browse') {
        if (!selectedDbPath) {
          setErrorMessage('No database selected')
          setIsLoadingDb(false)
          return
        }
        response = await fetch('/api/db/open', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path: selectedDbPath }),
        })
      } else {
        const name = dbInput.trim()
        if (!name) {
          setErrorMessage('Enter a filename')
          setIsLoadingDb(false)
          return
        }
        let overwrite = false
        response = await fetch('/api/db/create', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ filename: name, seed: seedWithData, overwrite }),
        })
        if (response.status === 409 && window.confirm(`Database "${name}" already exists. Overwrite it?`)) {
          overwrite = true
          response = await fetch('/api/db/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filename: name, seed: seedWithData, overwrite }),
          })
        }
      }
      if (!response.ok) {
        const text = await response.text()
        throw new Error(text.length < 200 ? text : `Request failed (${response.status})`)
      }
      const data = (await response.json()) as DbInfo
      localStorage.setItem('omnifin_last_db', data.path)
      setCurrentDb(data)
      setHasDb(true)
      setDbMessage(`Loaded database: ${data.filename}`)
      setJob(null)
      setCommitResult(null)
      setStatusMessage('Upload a CSV to start AI ingestion')
      fetch('/api/accounts')
        .then((r) => r.json())
        .then((accounts: AccountInfo[]) => setAccounts(accounts))
        .catch(() => {})
    } catch (error) {
      setErrorMessage(String(error))
    } finally {
      setIsLoadingDb(false)
    }
  }

  return (
    <main className="app-root">
      {/* ── Database Header ─────────────────────────────────────────── */}
      <header className="db-header">
        <div className="db-header-main">
          <span className="db-label">Database</span>
          {isLoadingDb ? (
            <span className="db-loading">Loading…</span>
          ) : currentDb ? (
            <span className="db-path-text" title={currentDb.path}>
              {currentDb.filename}{' '}
              <span className="db-size">
                ({(currentDb.size_bytes / 1024).toFixed(1)} KB)
              </span>
            </span>
          ) : (
            <span className="db-path-text muted">No database loaded</span>
          )}
        </div>

        {!isLoadingDb && (
          <div className="db-controls">
            <div className="db-mode-toggle">
              <button
                type="button"
                className={dbMode === 'browse' ? 'active' : ''}
                onClick={() => setDbMode('browse')}
              >
                Browse existing
              </button>
              <button
                type="button"
                className={dbMode === 'create' ? 'active' : ''}
                onClick={() => setDbMode('create')}
              >
                Create new
              </button>
            </div>

            <div className="db-input-row">
              {dbMode === 'browse' ? (
                <select
                  className="db-select"
                  value={selectedDbPath}
                  onChange={(e) => {
                    setSelectedDbPath(e.currentTarget.value)
                    const match = availableDbs.find((d) => d.path === e.currentTarget.value)
                    if (match) setDbInput(match.filename)
                  }}
                >
                  {availableDbs.length === 0 && (
                    <option value="">No databases found</option>
                  )}
                  {availableDbs.map((dbf) => (
                    <option key={dbf.path} value={dbf.path}>
                      {dbf.filename}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  className="db-input"
                  type="text"
                  placeholder="e.g. my_finance.db"
                  value={dbInput}
                  onChange={(e) => setDbInput(e.currentTarget.value)}
                />
              )}
              <button
                type="button"
                className="db-load-btn"
                disabled={
                  isLoadingDb ||
                  (dbMode === 'browse' && (!selectedDbPath || availableDbs.length === 0)) ||
                  (dbMode === 'create' && !dbInput.trim())
                }
                onClick={() => void handleLoadCreateDb()}
              >
                {isLoadingDb ? 'Loading…' : 'Load / Create'}
              </button>
            </div>

            {dbMode === 'create' && (
              <label className="db-seed-checkbox">
                <input
                  type="checkbox"
                  checked={seedWithData}
                  onChange={(e) => setSeedWithData(e.currentTarget.checked)}
                />
                Populate with seed data
              </label>
            )}

            {dbMessage && <p className="db-message">{dbMessage}</p>}
          </div>
        )}
      </header>

      <nav className="app-nav">
        <button
          type="button"
          className={`app-nav-btn ${activeView === 'ingestion' ? 'active' : ''}`}
          onClick={() => setActiveView('ingestion')}
        >
          ⚡ Ingestion
        </button>
        <button
          type="button"
          className={`app-nav-btn ${activeView === 'tuning' ? 'active' : ''}`}
          onClick={() => setActiveView('tuning')}
        >
          🎛 AI Tuning
        </button>
      </nav>

      {activeView === 'ingestion' && <h1 className="app-title">Omnifin AI Ingestion Studio</h1>}

      {errorMessage && <p className="error-banner">{errorMessage}</p>}

      {activeView === 'tuning' && <AiTuningPanel />}

      {activeView === 'ingestion' && hasDb && <BrowsePanel dbPath={currentDb?.path} />}

      {activeView === 'ingestion' && hasDb && (
        <>
          <header className="topbar">
            <div>
              {accounts.length > 0 && (
                <div className="account-selector">
                  <label htmlFor="source-account">Source Account:</label>
                  <select
                    id="source-account"
                    value={selectedAccountId}
                    onChange={(event) => setSelectedAccountId(event.currentTarget.value)}
                  >
                    <option value="">— No source account —</option>
                    {accounts.map((account) => (
                      <option key={account.id} value={account.id}>
                        {account.name || 'Unnamed'} ({account.type ? account.type : ''}){account.institution ? ` — ${account.institution}` : ''}
                      </option>
                    ))}
                  </select>
                </div>
              )}
              <p>{statusMessage}</p>
              {job && (
                <p>
                  File: <strong>{job.filename || fileName}</strong> | Rows: <strong>{job.rows.length}</strong> |
                  Processed: <strong>{processedCount}</strong> | Errors: <strong>{failedCount}</strong>
                </p>
              )}
            </div>
            <label className="upload-button">
              <input
                type="file"
                accept=".csv,text/csv"
                disabled={isUploading}
                onChange={(event) => {
                  const file = event.currentTarget.files?.[0]
                  if (file) {
                    void uploadCsv(file)
                  }
                }}
              />
              {isUploading ? 'Uploading...' : 'Upload CSV'}
            </label>
          </header>

          {job && (
            <section className="control-panel">
              <button type="button" onClick={() => void postJobAction('pause')} disabled={job.paused || job.status === 'completed'}>
                Pause
              </button>
              <button type="button" onClick={() => void postJobAction('resume')} disabled={!job.paused}>
                Resume
              </button>
              <button type="button" onClick={() => void postJobAction('rerun-all')}>
                Rerun All
              </button>
              <button type="button" onClick={() => void rerunSelectedRows()}>
                Rerun Selected
              </button>
              <button type="button" onClick={() => void toggleSelectAll(true)}>
                Select All
              </button>
              <button type="button" onClick={() => void toggleSelectAll(false)}>
                Clear Selection
              </button>
              <button type="button" disabled={isCommitting} onClick={() => void commitSelectedRows(true)}>
                Dry Run Save
              </button>
              <button type="button" disabled={isCommitting} className="primary" onClick={() => void commitSelectedRows(false)}>
                Save Selected Rows
              </button>
            </section>
          )}

          {job && (
            <section className="workspace-grid">
              <article className="row-list">
                <h2>Rows</h2>
                <div className="row-table-wrapper">
                  <table>
                    <thead>
                      <tr>
                        <th>Use</th>
                        <th>Row</th>
                        <th>Status</th>
                        <th>Summary</th>
                      </tr>
                    </thead>
                    <tbody>
                      {job.rows.map((row) => (
                        <tr
                          key={row.index}
                          className={row.index === selectedRowIndex ? 'selected-row' : ''}
                          onClick={() => setSelectedRowIndex(row.index)}
                        >
                          <td>
                            <input
                              type="checkbox"
                              checked={row.selected}
                              onChange={(event) => {
                                event.stopPropagation()
                                void toggleRowSelection(row.index, event.currentTarget.checked)
                              }}
                            />
                          </td>
                          <td>{row.index}</td>
                          <td>
                            <span className={`status-pill ${row.status}`}>{row.status}</span>
                          </td>
                          <td>{row.error || row.llm_error || row.interpretation?.summary || ''}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </article>

              <article className="row-editor">
                <h2>Input Row (Left)</h2>
                {selectedRow ? (
                  <>
                    <p>
                      Row <strong>{selectedRow.index}</strong> hash <code>{selectedRow.row_hash}</code>
                    </p>
                    <p>
                      Checks: {selectedRow.checks.length === 0 ? 'none' : selectedRow.checks.join(' | ')}
                    </p>
                    {selectedRow.llm_error && (
                      <p className="error-banner">LLM error: {selectedRow.llm_error}</p>
                    )}
                    <textarea
                      value={rowEditorText}
                      onChange={(event) => setRowEditorText(event.currentTarget.value)}
                      spellCheck={false}
                    />
                  </>
                ) : (
                  <p>Select a row to edit input values.</p>
                )}
              </article>

              <article className="result-editor">
                <h2>Proposed Objects (Right)</h2>
                {selectedRow ? (
                  <>
                    <p>
                      AI confidence: <strong>{selectedRow.interpretation?.confidence ?? 0}</strong>
                    </p>
                    <div className="object-buttons">
                      {SAMPLE_OBJECTS.map((objectType) => (
                        <button key={objectType} type="button" onClick={() => addObjectToSelectedRow(objectType)}>
                          + {objectType}
                        </button>
                      ))}
                    </div>
                    <textarea
                      value={resultEditorText}
                      onChange={(event) => setResultEditorText(event.currentTarget.value)}
                      spellCheck={false}
                    />
                    <div className="editor-actions">
                      <button type="button" className="primary" onClick={() => void saveRowEdits()}>
                        Save Row Edits
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          if (job) {
                            void fetch(`/api/ingest/jobs/${job.id}/rerun-rows`, {
                              method: 'POST',
                              headers: { 'Content-Type': 'application/json' },
                              body: JSON.stringify({ row_indices: [selectedRow.index] })
                            })
                              .then((response) => response.json())
                              .then((data: IngestJob) => setJob(data))
                              .catch((error: unknown) => setErrorMessage(String(error)))
                          }
                        }}
                      >
                        Rerun This Row
                      </button>
                    </div>
                  </>
                ) : (
                  <p>Select a row to inspect AI results.</p>
                )}
              </article>
            </section>
          )}

          {commitResult && (
            <section className="commit-result">
              <h2>Commit Result</h2>
              <p>
                Report ID: <strong>{commitResult.report_id}</strong> | Selected rows: <strong>{commitResult.selected_rows}</strong>
              </p>
              <p>Plan valid: <strong>{String(commitResult.plan_valid)}</strong></p>
              <pre>{JSON.stringify(commitResult, null, 2)}</pre>
            </section>
          )}

          {!job && (
            <section className="empty-state">
              <h2>No Active Ingestion Job</h2>
              <p>Upload one of your broker CSV files to start async row interpretation with Ollama.</p>
            </section>
          )}
        </>
      )}

      {activeView === 'ingestion' && !hasDb && !isLoadingDb && (
        <section className="empty-state">
          <h2>No Database Loaded</h2>
          <p>Select an existing database above or create a new one to begin.</p>
        </section>
      )}
      <div
        className="debug-toggle"
        role="switch"
        aria-checked={debugMode}
        tabIndex={0}
        onClick={() => setDebugMode((prev) => !prev)}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') setDebugMode((prev) => !prev) }}
      >
        Debug: {debugMode ? 'ON' : 'OFF'}
      </div>
    </main>
  )
}

createRoot(document.getElementById('root')!).render(<App />)
