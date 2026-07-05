import React, { useEffect, useMemo, useState } from 'react'

type InvestmentParseResult = {
  status: 'known' | 'new'
  symbol: string | null
  investment: InvestmentData | null
}

type InvestmentData = {
  symbol: string
  name?: string | null
  category?: string | null
  nyse_ticker?: string | null
  ibkr_ticker?: string | null
  identifier?: string | null
  identifier_type?: string | null
  country?: string | null
  fund_type?: string | null
  fund_focus?: string | null
}

type ParseRow = {
  index: number
  source_row: Record<string, string>
  edited_row: Record<string, string>
  row_hash: string
  selected: boolean
  status: 'pending' | 'processing' | 'processed' | 'error'
  checks: string[]
  error?: string | null
  llm_error?: string | null
  interpretation?: ParseResult | null
  updated_at: string
}

type ParseResult = {
  summary: string
  confidence: number
  result: InvestmentParseResult | null
}

type InvestParseJob = {
  id: string
  filename: string
  created_at: string
  updated_at: string
  document_hash: string
  headers: string[]
  paused: boolean
  status: 'running' | 'paused' | 'completed' | 'error'
  rows: ParseRow[]
  temperature: number
  model: string
  base_url: string
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

type AccountInfo = {
  id: string
  name?: string | null
  type?: string | null
  institution?: string | null
}

type ModelInfo = {
  name: string
  size: number
  digest: string
}

function toJsonSafe(v: unknown): string {
  try { return JSON.stringify(v, null, 2) } catch { return String(v) }
}

function objectToCsv(data: Record<string, string>[]): string {
  if (data.length === 0) return ''
  const headers = Object.keys(data[0])
  const rows = data.map(row => headers.map(h => `"${String(row[h]).replace(/"/g, '""')}"`).join(','))
  return [headers.join(','), ...rows].join('\n')
}

export default function InvestParsePanel() {
  const [job, setJob] = useState<InvestParseJob | null>(null)
  const [accounts, setAccounts] = useState<AccountInfo[]>([])
  const [selectedAccountId, setSelectedAccountId] = useState<string>('')
  const [selectedRowIndex, setSelectedRowIndex] = useState<number | null>(null)
  const [fileName, setFileName] = useState<string>('')
  const [isUploading, setIsUploading] = useState<boolean>(false)
  const [isCommitting, setIsCommitting] = useState<boolean>(false)
  const [statusMessage, setStatusMessage] = useState<string>('Upload a CSV to start Investment Asset Parsing')
  const [errorMessage, setErrorMessage] = useState<string>('')
  const [commitResult, setCommitResult] = useState<CommitResponse | null>(null)
  const [existingSymbols, setExistingSymbols] = useState<string[]>([])
  const [availableModels, setAvailableModels] = useState<ModelInfo[]>([])
  const [selectedModel, setSelectedModel] = useState<string>('gemma4:31b')
  const [temperature, setTemperature] = useState<number>(0.6)
  const [batchProcessing, setBatchProcessing] = useState<boolean>(true)

  const selectedRow = useMemo(() => {
    if (!job || selectedRowIndex === null) return null
    return job.rows.find((row) => row.index === selectedRowIndex) ?? null
  }, [job, selectedRowIndex])

  const [investmentEditorText, setInvestmentEditorText] = useState<string>('{}')
  const [dbReady, setDbReady] = useState<boolean>(false)
  const [dbLoading, setDbLoading] = useState<boolean>(true)

  useEffect(() => {
    fetch('/api/health')
      .then(r => r.json())
      .then(() => {
        setDbReady(true)
        setDbLoading(false)
      })
      .catch(() => {
        setDbReady(false)
        setDbLoading(false)
      })
  }, [])

  useEffect(() => {
    if (!selectedRow?.interpretation?.result) {
      setInvestmentEditorText('{}')
      return
    }
    setInvestmentEditorText(toJsonSafe(selectedRow.interpretation.result))
  }, [selectedRowIndex, selectedRow?.interpretation])

  useEffect(() => {
    fetch('/api/invest-parse/symbols')
      .then((r) => (r.ok ? r.json() : Promise.reject(r.statusText)))
      .then((s: string[]) => setExistingSymbols(s))
      .catch((e) => setErrorMessage(String(e)))
  }, [])

  useEffect(() => {
    fetch('/api/accounts')
      .then((r) => r.json())
      .then((accounts: AccountInfo[]) => setAccounts(accounts))
      .catch(() => {})
  }, [])

  useEffect(() => {
    fetch('/api/models')
      .then((r) => r.json())
      .then((data: ModelInfo[]) => {
        setAvailableModels(data)
        if (data.length > 0) {
          setSelectedModel(data[0].name)
        }
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (!dbReady || !job) return
    const timer = window.setInterval(() => {
      fetch(`/api/invest-parse/jobs/${job.id}`)
        .then((response) => response.json())
        .then((data: InvestParseJob) => {
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
  }, [job?.id, dbReady])

  const uploadCsv = async (file: File): Promise<void> => {
    setIsUploading(true)
    setErrorMessage('')
    setCommitResult(null)
    try {
      const csvText = await file.text()
      const body: Record<string, unknown> = {
        filename: file.name,
        csv_text: csvText,
        temperature: temperature,
        model: selectedModel,
        base_url: 'http://localhost:11434/v1'
      }
      if (selectedAccountId) {
        body.account_id = selectedAccountId
      }
      const response = await fetch('/api/invest-parse/jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      })
      if (!response.ok) {
        throw new Error(await response.text())
      }
      const data = (await response.json()) as InvestParseJob
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

  const loadExampleFile = async (): Promise<void> => {
    setErrorMessage('')
    setCommitResult(null)
    try {
      const response = await fetch('/api/invest-parse/examples/load', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: 'fidelity_sales.csv' })
      })
      if (!response.ok) {
        throw new Error(await response.text())
      }
      const data = (await response.json()) as InvestParseJob
      setFileName(data.filename)
      setJob(data)
      setSelectedRowIndex(data.rows.length > 0 ? data.rows[0].index : null)
      setStatusMessage(`Debug: loaded "${data.filename}" with ${data.rows.length} rows (paused)`)
    } catch (error) {
      setErrorMessage(String(error))
    }
  }

  const postJobAction = async (action: 'pause' | 'resume' | 'rerun-all'): Promise<void> => {
    if (!job) return
    setErrorMessage('')
    try {
      const response = await fetch(`/api/invest-parse/jobs/${job.id}/${action}`, { method: 'POST' })
      if (!response.ok) throw new Error(await response.text())
      const data = (await response.json()) as InvestParseJob
      setJob(data)
    } catch (error) {
      setErrorMessage(String(error))
    }
  }

  const rerunSelectedRows = async (): Promise<void> => {
    if (!job) return
    const selectedIndices = job.rows.filter((row) => row.selected).map((row) => row.index)
    if (selectedIndices.length === 0) {
      setErrorMessage('Select at least one row to rerun')
      return
    }
    setErrorMessage('')
    try {
      const response = await fetch(`/api/invest-parse/jobs/${job.id}/rerun-rows`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ row_indices: selectedIndices })
      })
      if (!response.ok) throw new Error(await response.text())
      const data = (await response.json()) as InvestParseJob
      setJob(data)
    } catch (error) {
      setErrorMessage(String(error))
    }
  }

  const rerunSingleRow = async (rowIndex: number): Promise<void> => {
    if (!job) return
    setErrorMessage('')
    try {
      const response = await fetch(`/api/invest-parse/jobs/${job.id}/rerun-rows`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ row_indices: [rowIndex] })
      })
      if (!response.ok) throw new Error(await response.text())
      const data = (await response.json()) as InvestParseJob
      setJob(data)
    } catch (error) {
      setErrorMessage(String(error))
    }
  }

  const toggleSelectAll = async (selected: boolean): Promise<void> => {
    if (!job) return
    setErrorMessage('')
    for (const row of job.rows) {
      try {
        await patchRow(row.index, { selected })
      } catch (error) {
        setErrorMessage(String(error))
        break
      }
    }
  }

  const patchRow = async (
    rowIndex: number,
    payload: {
      edited_row?: Record<string, string>
      interpretation?: ParseResult
      selected?: boolean
    }
  ): Promise<void> => {
    if (!job) return
    const response = await fetch(`/api/invest-parse/jobs/${job.id}/rows/${rowIndex}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    if (!response.ok) throw new Error(await response.text())
    const updated = (await response.json()) as ParseRow
    setJob((previous) => {
      if (!previous) return previous
      return {
        ...previous,
        rows: previous.rows.map((row) => (row.index === updated.index ? updated : row))
      }
    })
  }

  const saveRowEdits = async (): Promise<void> => {
    if (!selectedRow) return
    setErrorMessage('')
    try {
      const parsed = JSON.parse(investmentEditorText) as InvestmentParseResult
      await patchRow(selectedRow.index, {
        interpretation: {
          summary: selectedRow.interpretation?.summary || '',
          confidence: selectedRow.interpretation?.confidence || 0,
          result: parsed
        }
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

  const commitSelectedRows = async (dryRun: boolean): Promise<void> => {
    if (!job) return
    setIsCommitting(true)
    setErrorMessage('')
    try {
      const selected = job.rows.filter((row) => row.selected).map((row) => row.index)
      const response = await fetch(`/api/invest-parse/jobs/${job.id}/commit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ row_indices: selected, dry_run: dryRun })
      })
      if (!response.ok) throw new Error(await response.text())
      const data = (await response.json()) as CommitResponse
      setCommitResult(data)
      setStatusMessage(dryRun ? 'Dry run completed' : 'Saved selected rows to database')
    } catch (error) {
      setErrorMessage(String(error))
    } finally {
      setIsCommitting(false)
    }
  }

  const downloadResults = (): void => {
    if (!job) return
    const selectedRows = job.rows.filter((row) => row.selected && row.interpretation?.result)
    if (selectedRows.length === 0) {
      setErrorMessage('No rows to download')
      return
    }
    const csvData = selectedRows.map((row) => {
      const result = row.interpretation!.result!
      const base: Record<string, string> = {
        row_index: String(row.index),
        source_hash: row.row_hash,
        status: result.status,
        symbol: result.symbol || '',
      }
      if (result.investment) {
        for (const [key, value] of Object.entries(result.investment)) {
          if (value !== null && value !== undefined) {
            base[key] = String(value)
          }
        }
      }
      return base
    })
    const csv = objectToCsv(csvData)
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `investment_parse_${Date.now()}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  const processedCount = job ? job.rows.filter((row) => row.status === 'processed').length : 0
  const failedCount = job ? job.rows.filter((row) => row.status === 'error').length : 0

  return (
    <main className="app-root">
      {dbLoading && (
        <section className="empty-state">
          <p>Checking database...</p>
        </section>
      )}
      {!dbLoading && !dbReady && (
        <section className="empty-state">
          <h2>No Database Loaded</h2>
          <p>Select an existing database or create a new one to begin.</p>
        </section>
      )}

      {dbReady && (
        <>
          <header className="topbar">
            <div>
              <div className="account-selector">
                <label htmlFor="model-select">Model:</label>
                <select
                  id="model-select"
                  value={selectedModel}
                  onChange={(event) => setSelectedModel(event.currentTarget.value)}
                >
                  {availableModels.length > 0 ? (
                    availableModels.map((model) => (
                      <option key={model.name} value={model.name}>
                        {model.name}
                      </option>
                    ))
                  ) : (
                    <option value="gemma4:31b">gemma4:31b</option>
                  )}
                </select>
              </div>
              <div className="account-selector">
                <label htmlFor="temperature">Temperature:</label>
                <input
                  id="temperature"
                  type="number"
                  step="0.1"
                  min="0"
                  max="1"
                  value={temperature}
                  onChange={(event) => setTemperature(parseFloat(event.currentTarget.value))}
                />
              </div>
              <label className="account-selector">
                <input
                  type="checkbox"
                  checked={batchProcessing}
                  onChange={(event) => setBatchProcessing(event.currentTarget.checked)}
                />
                <span>Batch Process</span>
              </label>
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
            <div>
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
              <button
                type="button"
                className="invest-load-example-btn"
                onClick={() => void loadExampleFile()}
              >
                Load Example
              </button>
            </div>
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
              <button type="button" disabled={isCommitting} onClick={downloadResults}>
                Download CSV
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
                        <th>Confidence</th>
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
                          <td>{row.interpretation?.confidence?.toFixed(2) || ''}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </article>

              <article className="row-editor">
                <h2>Input Row</h2>
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
                      value={toJsonSafe(selectedRow.edited_row)}
                      onChange={(event) => setInvestmentEditorText(event.currentTarget.value)}
                      spellCheck={false}
                    />
                    <button type="button" className="primary" onClick={() => {
                      if (selectedRow) {
                        void rerunSingleRow(selectedRow.index)
                      }
                    }}>
                      Rerun This Row
                    </button>
                  </>
                ) : (
                  <p>Select a row to edit input values.</p>
                )}
              </article>

              <article className="result-editor">
                <h2>Parsed Investment</h2>
                {selectedRow && selectedRow.interpretation?.result && (
                  <>
                    <p>
                      AI confidence: <strong>{selectedRow.interpretation.confidence.toFixed(2)}</strong>
                    </p>
                    <p>
                      Status: <strong>{selectedRow.interpretation.result.status}</strong>
                    </p>
                    {selectedRow.interpretation.result.status === 'known' && selectedRow.interpretation.result.symbol && (
                      <p>
                        Known symbol: <strong>{selectedRow.interpretation.result.symbol}</strong>
                      </p>
                    )}
                    {selectedRow.interpretation.result.status === 'new' && selectedRow.interpretation.result.investment && (
                      <div className="investment-editor-container">
                        <textarea
                          value={investmentEditorText}
                          onChange={(event) => setInvestmentEditorText(event.currentTarget.value)}
                          spellCheck={false}
                        />
                        <button type="button" className="primary" onClick={saveRowEdits}>
                          Save Investment Edits
                        </button>
                      </div>
                    )}
                  </>
                )}
                {!selectedRow || !selectedRow.interpretation?.result ? (
                  <p>Select a processed row to view investment results.</p>
                ) : null}
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

          {!job && dbReady && (
            <section className="empty-state">
              <h2>No Active Investment Parse Job</h2>
              <p>Upload one of your broker CSV files to start AI-assisted investment parsing.</p>
            </section>
          )}
        </>
      )}
    </main>
  )
}