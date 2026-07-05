import React, { useCallback, useEffect, useMemo, useState } from 'react'

type RunTuningResponse = {
  content: string
  reasoning?: string | null
  parsed?: Record<string, unknown> | null
  validation_notes: string[]
}

type SchemaMap = Record<string, Record<string, unknown>>
type ContextData = { accounts: { name: string; type: string; institution: string }[]; assets: { symbol: string; name: string; category: string }[] }

const DEFAULT_TEMPLATE = `# Omnifin Ingestion Prompt

You are converting one CSV row into Omnifin database objects.

## Input
{{input_json}}

## Database Context
{{context_accounts}}
{{context_assets}}
{{source_account}}

## Object Schemas
{{schema_Transfer}}
{{schema_Statement}}
{{schema_Event}}
{{schema_InvestmentSale}}
{{schema_Asset}}
{{schema_Account}}

## Output Requirements
Return only valid JSON with this schema shape:
- summary: string (1 line summary)
- confidence: string (one of low, medium, high)
- products: array of {rationale: string, product: object}

Each product must adhere to the schema of its object_type.
Do not include markdown fences or explanatory prose.`

const SCHEMA_PLACEHOLDER_NAMES = [
  'Report', 'Asset', 'Investment', 'Account', 'Statement', 'Transfer',
  'Location', 'Event', 'InvestmentSale', 'Tag', 'Comment',
  'Portfolio', 'Trade', 'Sale', 'ParsingRowResult',
]

function toJsonSafe(v: unknown): string {
  try { return JSON.stringify(v, null, 2) } catch { return String(v) }
}

function tryParseJson(text: string): unknown {
  try { return JSON.parse(text) } catch { return null }
}

// ── Panel wrapper with mode toggle ────────────────────────────────────────
type ModeSwitchProps = {
  mode: 'form' | 'json'
  onToggle: () => void
  label: string
  children: React.ReactNode
}

function Panel({ mode, onToggle, label, children }: ModeSwitchProps) {
  return (
    <section className="tuning-panel">
      <header className="tuning-panel-header">
        <span className="tuning-panel-title">{label}</span>
        <button
          type="button"
          className="tuning-mode-btn"
          onClick={onToggle}
          title={mode === 'form' ? 'Switch to JSON mode' : 'Switch to form mode'}
        >
          {mode === 'form' ? '⚙ Form' : '📄 JSON'}
        </button>
      </header>
      <div className="tuning-panel-body">
        {children}
      </div>
    </section>
  )
}

// ── Key-value entry editor (for Input JSON form mode) ────────────────────
type Entry = { key: string; value: string }

function EntryEditor({ entries, onChange }: { entries: Entry[]; onChange: (e: Entry[]) => void }) {
  const update = (idx: number, field: 'key' | 'value', val: string) => {
    const next = entries.map((e, i) => (i === idx ? { ...e, [field]: val } : e))
    onChange(next)
  }
  const add = () => onChange([...entries, { key: '', value: '' }])
  const remove = (idx: number) => onChange(entries.filter((_, i) => i !== idx))

  return (
    <div className="tuning-entry-editor">
      {entries.map((e, i) => (
        <div key={i} className="tuning-entry-row">
          <input className="tuning-entry-input" placeholder="Field name" value={e.key} onChange={(ev) => update(i, 'key', ev.currentTarget.value)} />
          <span className="tuning-entry-sep">:</span>
          <input className="tuning-entry-input" placeholder="Value" value={e.value} onChange={(ev) => update(i, 'value', ev.currentTarget.value)} />
          <button type="button" className="tuning-entry-del" onClick={() => remove(i)} disabled={entries.length <= 1}>✕</button>
        </div>
      ))}
      <button type="button" className="tuning-entry-add" onClick={add}>+ Add field</button>
    </div>
  )
}

function entriesToObject(entries: Entry[]): Record<string, string> {
  const obj: Record<string, string> = {}
  for (const e of entries) {
    if (e.key.trim()) obj[e.key.trim()] = e.value
  }
  return obj
}

function objectToEntries(obj: Record<string, string>): Entry[] {
  const keys = Object.keys(obj)
  return keys.length > 0 ? keys.map((k) => ({ key: k, value: obj[k] })) : [{ key: '', value: '' }]
}

// ── Main component ────────────────────────────────────────────────────────
export default function AiTuningPanel() {
  // Data fetched on mount
  const [schemas, setSchemas] = useState<SchemaMap>({})
  const [contextData, setContextData] = useState<ContextData>({ accounts: [], assets: [] })
  const [loadError, setLoadError] = useState('')

  // ── Input JSON panel ─────────────────────────────────────────────────────
  const [inputMode, setInputMode] = useState<'form' | 'json'>('form')
  const [inputEntries, setInputEntries] = useState<Entry[]>([{ key: '', value: '' }])
  const [inputJsonText, setInputJsonText] = useState('{}')

  // ── DB Context panel ─────────────────────────────────────────────────────
  const [contextMode, setContextMode] = useState<'form' | 'json'>('form')
  const [includeAccounts, setIncludeAccounts] = useState(true)
  const [includeAssets, setIncludeAssets] = useState(true)
  const [includeSourceAccount, setIncludeSourceAccount] = useState(false)
  const [selectedSourceId, setSelectedSourceId] = useState('')
  const [contextJsonText, setContextJsonText] = useState('{}')

  // ── Schema Selector panel ────────────────────────────────────────────────
  const [schemaMode, setSchemaMode] = useState<'form' | 'json'>('form')
  const [selectedSchemaNames, setSelectedSchemaNames] = useState<Set<string>>(() => new Set(['Transfer', 'Statement', 'Event', 'InvestmentSale', 'Asset', 'Account', 'ParsingRowResult']))
  const [expandedSchemaNames, setExpandedSchemaNames] = useState<Set<string>>(new Set())
  const [schemaJsonText, setSchemaJsonText] = useState('{}')

  // ── Template panel ───────────────────────────────────────────────────────
  const [activeTab, setActiveTab] = useState<'template' | 'rendered'>('template')
  const [templateText, setTemplateText] = useState(DEFAULT_TEMPLATE)
  const [renderedPrompt, setRenderedPrompt] = useState('')

  // ── Hyperparams panel ───────────────────────────────────────────────────
  const [hyperMode, setHyperMode] = useState<'form' | 'json'>('form')
  const [hyperModel, setHyperModel] = useState('gemma4:31b')
  const [hyperBaseUrl, setHyperBaseUrl] = useState('http://localhost:11434/v1')
  const [hyperTemperature, setHyperTemperature] = useState('0.0')
  const [hyperMaxTokens, setHyperMaxTokens] = useState('5000')
  const [structuredOutput, setStructuredOutput] = useState(true)
  const [responseSchema, setResponseSchema] = useState('ParsingRowResult')
  const [hyperJsonText, setHyperJsonText] = useState('')

  // ── Output ──────────────────────────────────────────────────────────────
  const [runResult, setRunResult] = useState<RunTuningResponse | null>(null)
  const [isRunning, setIsRunning] = useState(false)
  const [runError, setRunError] = useState('')

  // Fetch schemas + context on mount
  useEffect(() => {
    Promise.all([
      fetch('/api/ingest/tuning/schemas').then((r) => (r.ok ? r.json() : Promise.reject(r.statusText))),
      fetch('/api/ingest/tuning/context').then((r) => (r.ok ? r.json() : Promise.reject(r.statusText))),
    ])
      .then(([s, c]) => {
        setSchemas(s as SchemaMap)
        setContextData(c as ContextData)
      })
      .catch((e) => setLoadError(String(e)))
  }, [])

  // ── Fill placeholders ────────────────────────────────────────────────────
  const fillPlaceholders = useCallback(() => {
    const inputObj = inputMode === 'json'
      ? tryParseJson(inputJsonText)
      : entriesToObject(inputEntries)
    const inputJson = toJsonSafe(inputObj)

    let contextAccounts = ''
    let contextAssets = ''
    let sourceAccount = ''
    if (contextMode === 'json') {
      const parsed = tryParseJson(contextJsonText) as Record<string, unknown> | null
      if (parsed) {
        contextAccounts = toJsonSafe(parsed.accounts ?? [])
        contextAssets = toJsonSafe(parsed.assets ?? [])
        sourceAccount = toJsonSafe(parsed.source_account ?? null)
      }
    } else {
      if (includeAccounts) contextAccounts = toJsonSafe(contextData.accounts)
      if (includeAssets) contextAssets = toJsonSafe(contextData.assets)
      if (includeSourceAccount && selectedSourceId) {
        const acct = contextData.accounts.find((a) => a.name === selectedSourceId)
        sourceAccount = toJsonSafe(acct ?? null)
      }
    }

    const selSchemas = schemaMode === 'json'
      ? (tryParseJson(schemaJsonText) as SchemaMap | null) ?? {}
      : Object.fromEntries(
          [...selectedSchemaNames]
            .filter((name) => schemas[name])
            .map((name) => [name, schemas[name]])
        )

    let result = templateText
    result = result.replace(/\{\{input_json\}\}/g, inputJson)
    result = result.replace(/\{\{context_accounts\}\}/g, contextAccounts)
    result = result.replace(/\{\{context_assets\}\}/g, contextAssets)
    result = result.replace(/\{\{source_account\}\}/g, sourceAccount)

    for (const name of SCHEMA_PLACEHOLDER_NAMES) {
      const placeholder = `{{schema_${name}}}`
      if (result.includes(placeholder)) {
        const schema = selSchemas[name as keyof typeof selSchemas]
        result = result.replace(new RegExp(placeholder.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g'), schema ? toJsonSafe(schema) : '')
      }
    }

    setRenderedPrompt(result)
    setActiveTab('rendered')
  }, [inputMode, inputJsonText, inputEntries, contextMode, contextJsonText, includeAccounts, includeAssets, includeSourceAccount, selectedSourceId, contextData, schemaMode, schemaJsonText, selectedSchemaNames, schemas, templateText])

  // ── Run AI call ──────────────────────────────────────────────────────────
  const runAiCall = useCallback(async () => {
    setIsRunning(true)
    setRunError('')
    setRunResult(null)
    try {
      let prompt = renderedPrompt
      if (!prompt) {
        fillPlaceholders()
        prompt = renderedPrompt
      }
      if (!prompt) {
        setRunError('Fill in placeholders first.')
        setIsRunning(false)
        return
      }

      let model = hyperModel
      let baseUrl = hyperBaseUrl
      let temperature = 0.0
      let maxTokens = 5000
      let useStructured = structuredOutput
      let respSchema = responseSchema

      if (hyperMode === 'json') {
        const parsed = tryParseJson(hyperJsonText) as Record<string, unknown> | null
        if (parsed) {
          model = String(parsed.model ?? model)
          baseUrl = String(parsed.base_url ?? baseUrl)
          temperature = Number(parsed.temperature ?? temperature)
          maxTokens = Number(parsed.max_tokens ?? maxTokens)
          useStructured = parsed.structured_output !== false
          respSchema = String(parsed.response_schema ?? respSchema)
        }
      } else {
        temperature = Number(hyperTemperature) || 0.0
        maxTokens = Number(hyperMaxTokens) || 5000
      }

      const body: Record<string, unknown> = {
        prompt,
        model,
        base_url: baseUrl,
        temperature,
        max_tokens: maxTokens,
      }
      if (useStructured) {
        body.response_schema = respSchema
      }

      const response = await fetch('/api/ingest/tuning/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!response.ok) {
        throw new Error(await response.text())
      }
      const data = (await response.json()) as RunTuningResponse
      setRunResult(data)
    } catch (e) {
      setRunError(String(e))
    } finally {
      setIsRunning(false)
    }
  }, [renderedPrompt, hyperMode, hyperJsonText, hyperModel, hyperBaseUrl, hyperTemperature, hyperMaxTokens, structuredOutput, responseSchema, fillPlaceholders])

  // ── Input JSON: sync form ↔ JSON ────────────────────────────────────────
  const handleInputToggle = () => {
    if (inputMode === 'form') {
      setInputJsonText(toJsonSafe(entriesToObject(inputEntries)))
      setInputMode('json')
    } else {
      const parsed = tryParseJson(inputJsonText) as Record<string, string> | null
      if (parsed) setInputEntries(objectToEntries(parsed))
      setInputMode('form')
    }
  }

  // ── Context: sync form ↔ JSON ───────────────────────────────────────────
  const handleContextToggle = () => {
    if (contextMode === 'form') {
      const ctx: Record<string, unknown> = {}
      if (includeAccounts && contextData.accounts.length > 0) ctx.accounts = contextData.accounts
      if (includeAssets && contextData.assets.length > 0) ctx.assets = contextData.assets
      if (includeSourceAccount && selectedSourceId) {
        const acct = contextData.accounts.find((a) => a.name === selectedSourceId)
        if (acct) ctx.source_account = acct
      }
      setContextJsonText(toJsonSafe(ctx))
      setContextMode('json')
    } else {
      setContextMode('form')
    }
  }

  // ── Schema: sync form ↔ JSON ────────────────────────────────────────────
  const handleSchemaToggle = () => {
    if (schemaMode === 'form') {
      const sel: Record<string, unknown> = {}
      for (const name of selectedSchemaNames) {
        if (schemas[name]) sel[name] = schemas[name]
      }
      setSchemaJsonText(toJsonSafe(sel))
      setSchemaMode('json')
    } else {
      setSchemaMode('form')
    }
  }

  // ── Hyperparams: sync form ↔ JSON ───────────────────────────────────────
  const hyperFormState = useMemo(() => ({
    model: hyperModel,
    base_url: hyperBaseUrl,
    temperature: Number(hyperTemperature) || 0.0,
    max_tokens: Number(hyperMaxTokens) || 5000,
    structured_output: structuredOutput,
    response_schema: responseSchema,
  }), [hyperModel, hyperBaseUrl, hyperTemperature, hyperMaxTokens, structuredOutput, responseSchema])

  const handleHyperToggle = () => {
    if (hyperMode === 'form') {
      setHyperJsonText(toJsonSafe(hyperFormState))
      setHyperMode('json')
    } else {
      setHyperMode('form')
    }
  }

  const toggleSchema = (name: string) => {
    setSelectedSchemaNames((prev) => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  const toggleExpanded = (name: string) => {
    setExpandedSchemaNames((prev) => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  if (loadError) {
    return <div className="tuning-error">Failed to load tuning data: {loadError}</div>
  }

  const schemaNames = Object.keys(schemas).sort()

  return (
    <div className="tuning-layout">
      {/* ── LEFT COLUMN ─────────────────────────────────────────────── */}
      <div className="tuning-col tuning-col-left">
        {/* Input JSON */}
        <Panel mode={inputMode} onToggle={handleInputToggle} label="Input JSON">
          {inputMode === 'form' ? (
            <EntryEditor entries={inputEntries} onChange={setInputEntries} />
          ) : (
            <textarea
              className="tuning-textarea"
              value={inputJsonText}
              onChange={(e) => setInputJsonText(e.currentTarget.value)}
              spellCheck={false}
              placeholder='{"Date": "01/15/2025", "Description": "...", "Amount": 500.00}'
            />
          )}
        </Panel>

        {/* DB Context */}
        <Panel mode={contextMode} onToggle={handleContextToggle} label="DB Context">
          {contextMode === 'form' ? (
            <div className="tuning-context-form">
              <label className="tuning-check-row">
                <input type="checkbox" checked={includeAccounts} onChange={(e) => setIncludeAccounts(e.currentTarget.checked)} />
                <span>Include accounts ({contextData.accounts.length})</span>
              </label>
              <label className="tuning-check-row">
                <input type="checkbox" checked={includeAssets} onChange={(e) => setIncludeAssets(e.currentTarget.checked)} />
                <span>Include assets ({contextData.assets.length})</span>
              </label>
              <label className="tuning-check-row">
                <input type="checkbox" checked={includeSourceAccount} onChange={(e) => setIncludeSourceAccount(e.currentTarget.checked)} />
                <span>Include source account</span>
              </label>
              {includeSourceAccount && (
                <select
                  className="tuning-select"
                  value={selectedSourceId}
                  onChange={(e) => setSelectedSourceId(e.currentTarget.value)}
                >
                  <option value="">— Select account —</option>
                  {contextData.accounts.map((a) => (
                    <option key={a.name} value={a.name}>{a.name} ({a.type})</option>
                  ))}
                </select>
              )}
            </div>
          ) : (
            <textarea
              className="tuning-textarea"
              value={contextJsonText}
              onChange={(e) => setContextJsonText(e.currentTarget.value)}
              spellCheck={false}
              placeholder='{"accounts": [...], "assets": [...], "source_account": {...}}'
            />
          )}
        </Panel>

        {/* Schema Selector */}
        <Panel mode={schemaMode} onToggle={handleSchemaToggle} label="Schema Selector">
          {schemaMode === 'form' ? (
            <div className="tuning-schema-list">
              {schemaNames.map((name) => (
                <div key={name} className="tuning-schema-item">
                  <div className="tuning-schema-header-row">
                    <label className="tuning-check-row">
                      <input type="checkbox" checked={selectedSchemaNames.has(name)} onChange={() => toggleSchema(name)} />
                      <span className="tuning-schema-name">{name}</span>
                    </label>
                    <button
                      type="button"
                      className="tuning-expand-btn"
                      onClick={() => toggleExpanded(name)}
                    >
                      {expandedSchemaNames.has(name) ? '▾' : '▸'}
                    </button>
                  </div>
                  {expandedSchemaNames.has(name) && (
                    <pre className="tuning-schema-preview">{toJsonSafe(schemas[name])}</pre>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <textarea
              className="tuning-textarea"
              value={schemaJsonText}
              onChange={(e) => setSchemaJsonText(e.currentTarget.value)}
              spellCheck={false}
              placeholder='{"Transfer": {...}, "Statement": {...}}'
            />
          )}
        </Panel>
      </div>

      {/* ── MIDDLE COLUMN ───────────────────────────────────────────── */}
      <div className="tuning-col tuning-col-middle">
        <section className="tuning-panel tuning-panel-grow">
          <header className="tuning-panel-header">
            <span className="tuning-panel-title">Prompt Template</span>
          </header>
          <div className="tuning-tab-bar">
            <button
              type="button"
              className={`tuning-tab ${activeTab === 'template' ? 'active' : ''}`}
              onClick={() => setActiveTab('template')}
            >
              Template
            </button>
            <button
              type="button"
              className={`tuning-tab ${activeTab === 'rendered' ? 'active' : ''}`}
              onClick={() => setActiveTab('rendered')}
            >
              Rendered
            </button>
          </div>
          <div className="tuning-panel-body-text tuning-panel-grow">
            {activeTab === 'template' ? (
              <textarea
                className="tuning-textarea tuning-textarea-grow"
                value={templateText}
                onChange={(e) => setTemplateText(e.currentTarget.value)}
                spellCheck={false}
              />
            ) : (
              <textarea
                className="tuning-textarea tuning-textarea-grow"
                value={renderedPrompt}
                readOnly
                spellCheck={false}
                placeholder="Click 'Fill Placeholders' to render the prompt."
              />
            )}
          </div>
          <div className="tuning-panel-footer">
            <button type="button" className="tuning-btn primary" onClick={fillPlaceholders}>
              Fill Placeholders
            </button>
          </div>
        </section>
      </div>

      {/* ── RIGHT COLUMN ────────────────────────────────────────────── */}
      <div className="tuning-col tuning-col-right">
        {/* Hyperparameters */}
        <Panel mode={hyperMode} onToggle={handleHyperToggle} label="Hyperparameters">
          {hyperMode === 'form' ? (
            <div className="tuning-hyper-form">
              <label className="tuning-field">
                <span>Model</span>
                <input className="tuning-input" value={hyperModel} onChange={(e) => setHyperModel(e.currentTarget.value)} />
              </label>
              <label className="tuning-field">
                <span>Base URL</span>
                <input className="tuning-input" value={hyperBaseUrl} onChange={(e) => setHyperBaseUrl(e.currentTarget.value)} />
              </label>
              <label className="tuning-field">
                <span>Temperature</span>
                <input className="tuning-input" type="number" step="0.1" min="0" max="2" value={hyperTemperature} onChange={(e) => setHyperTemperature(e.currentTarget.value)} />
              </label>
              <label className="tuning-field">
                <span>Max tokens</span>
                <input className="tuning-input" type="number" step="100" min="1" value={hyperMaxTokens} onChange={(e) => setHyperMaxTokens(e.currentTarget.value)} />
              </label>
              <label className="tuning-check-row">
                <input type="checkbox" checked={structuredOutput} onChange={(e) => setStructuredOutput(e.currentTarget.checked)} />
                <span>Structured output</span>
              </label>
              {structuredOutput && (
                <label className="tuning-field">
                  <span>Response schema</span>
                  <select className="tuning-select" value={responseSchema} onChange={(e) => setResponseSchema(e.currentTarget.value)}>
                    {Object.keys(schemas).sort().map((name) => (
                      <option key={name} value={name}>{name}</option>
                    ))}
                  </select>
                </label>
              )}
            </div>
          ) : (
            <textarea
              className="tuning-textarea"
              value={hyperJsonText}
              onChange={(e) => setHyperJsonText(e.currentTarget.value)}
              spellCheck={false}
              placeholder='{"model": "gemma4:31b", "temperature": 0.0, ...}'
            />
          )}
        </Panel>

        {/* Run button */}
        <button
          type="button"
          className="tuning-btn primary tuning-run-btn"
          disabled={isRunning}
          onClick={() => void runAiCall()}
        >
          {isRunning ? 'Running…' : 'Run AI Call'}
        </button>

        {runError && <p className="tuning-error">{runError}</p>}

        {/* Output */}
        {runResult && (
          <section className="tuning-panel tuning-panel-grow">
            <header className="tuning-panel-header">
              <span className="tuning-panel-title">Output</span>
            </header>
            <div className="tuning-panel-body tuning-panel-grow tuning-output">
              {/* Validation notes */}
              {runResult.validation_notes.length > 0 && (
                <div className="tuning-output-section">
                  <strong>Validation:</strong>
                  <ul className="tuning-validation-list">
                    {runResult.validation_notes.map((note, i) => (
                      <li key={i} className={note.includes('failed') || note.includes('not') ? 'tuning-validation-warn' : 'tuning-validation-ok'}>{note}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Reasoning / thoughts */}
              {runResult.reasoning && (
                <div className="tuning-output-section">
                  <strong>Thoughts:</strong>
                  <pre className="tuning-output-pre">{runResult.reasoning}</pre>
                </div>
              )}

              {/* Raw content */}
              <div className="tuning-output-section">
                <strong>Raw response:</strong>
                <pre className="tuning-output-pre">{runResult.content}</pre>
              </div>

              {/* Parsed JSON */}
              {runResult.parsed && (
                <div className="tuning-output-section">
                  <strong>Parsed:</strong>
                  <pre className="tuning-output-pre">{toJsonSafe(runResult.parsed)}</pre>
                </div>
              )}
            </div>
          </section>
        )}
      </div>
    </div>
  )
}
