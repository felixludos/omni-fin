import React, { useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
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
  const [selectedRowIndex, setSelectedRowIndex] = useState<number | null>(null)
  const [fileName, setFileName] = useState<string>('')
  const [isUploading, setIsUploading] = useState<boolean>(false)
  const [isCommitting, setIsCommitting] = useState<boolean>(false)
  const [statusMessage, setStatusMessage] = useState<string>('Upload a CSV to start AI ingestion')
  const [errorMessage, setErrorMessage] = useState<string>('')
  const [commitResult, setCommitResult] = useState<CommitResponse | null>(null)

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

  useEffect(() => {
    if (!job) {
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
      const response = await fetch('/api/ingest/jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: file.name, csv_text: csvText })
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

  return (
    <main className="app-root">
      <header className="topbar">
        <div>
          <h1>Omnifin AI Ingestion Studio</h1>
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

      {errorMessage && <p className="error-banner">{errorMessage}</p>}

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
    </main>
  )
}

createRoot(document.getElementById('root')!).render(<App />)
