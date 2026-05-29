import { useState, useEffect, useRef } from 'react'
import TemplateModal from './TemplateModal.jsx'

const PRIORITY_OPTIONS = ['P1', 'P2', 'P3', 'P4']

function PriorityBadge({ priority }) {
  return (
    <span className={`badge badge-${priority?.toLowerCase() || 'p4'}`}>
      {priority || 'P4'}
    </span>
  )
}

function AISuggestionsDrawer({ suggestions, onClose, onApply }) {
  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <div className="drawer">
        <div className="drawer-header">
          <div>
            <h3 style={{ fontSize: '1rem' }}>AI Critic Suggestions</h3>
            <p className="text-sm text-secondary">{suggestions.length} suggestion{suggestions.length !== 1 ? 's' : ''}</p>
          </div>
          <button className="btn btn-ghost btn-icon" onClick={onClose}>✕</button>
        </div>
        <div className="drawer-body" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
          {suggestions.map((s, i) => (
            <div key={i} className="ai-card stagger-in" style={{ animationDelay: `${i * 60}ms` }}>
              <span className="ai-type-badge">{s.type}</span>
              <p className="text-sm" style={{ marginBottom: s.rewrite ? 'var(--space-3)' : 0 }}>{s.description}</p>
              {s.rewrite && (
                <div style={{ marginTop: 'var(--space-3)', background: 'var(--shai-surface)', borderRadius: 'var(--radius-sm)', padding: 'var(--space-3)', border: '1px solid var(--shai-border)' }}>
                  <div className="text-xs text-muted" style={{ marginBottom: 'var(--space-1)' }}>SUGGESTED REWRITE</div>
                  <p className="text-sm font-mono">{s.rewrite}</p>
                  <button
                    className="btn btn-primary btn-sm"
                    style={{ marginTop: 'var(--space-2)' }}
                    onClick={() => onApply(s.rewrite)}
                  >
                    Apply
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </>
  )
}

function TestCaseForm({ tc, onSave, onCancel }) {
  const [form, setForm] = useState(
    tc
      ? { title: tc.title, steps: tc.steps, expected_result: tc.expected_result, priority: tc.priority || 'P3', component_tags: (tc.component_tags || []).join(', ') }
      : { title: '', steps: '', expected_result: '', priority: 'P3', component_tags: '' }
  )
  const [loading, setLoading] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setLoading(true)
    const payload = {
      ...form,
      component_tags: form.component_tags.split(',').map((t) => t.trim()).filter(Boolean),
    }
    await onSave(payload)
    setLoading(false)
  }

  return (
    <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
      <div className="form-group">
        <label className="form-label">Title *</label>
        <input
          className="form-input"
          value={form.title}
          onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
          required
          autoFocus
          placeholder="Verify login with valid credentials"
        />
      </div>

      <div className="flex gap-4">
        <div className="form-group" style={{ flex: 1 }}>
          <label className="form-label">Priority</label>
          <select
            className="form-select"
            value={form.priority}
            onChange={(e) => setForm((f) => ({ ...f, priority: e.target.value }))}
          >
            {PRIORITY_OPTIONS.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>
        <div className="form-group" style={{ flex: 2 }}>
          <label className="form-label">Component Tags</label>
          <input
            className="form-input"
            value={form.component_tags}
            onChange={(e) => setForm((f) => ({ ...f, component_tags: e.target.value }))}
            placeholder="auth, payments (comma-separated)"
          />
        </div>
      </div>

      <div className="form-group">
        <label className="form-label">Steps *</label>
        <textarea
          className="form-textarea"
          rows={5}
          value={form.steps}
          onChange={(e) => setForm((f) => ({ ...f, steps: e.target.value }))}
          required
          placeholder="1. Navigate to /login&#10;2. Enter valid email and password&#10;3. Click Sign In"
        />
      </div>

      <div className="form-group">
        <label className="form-label">Expected Result *</label>
        <textarea
          className="form-textarea"
          rows={3}
          value={form.expected_result}
          onChange={(e) => setForm((f) => ({ ...f, expected_result: e.target.value }))}
          required
          placeholder="User is redirected to dashboard and session token is set"
        />
      </div>

      <div className="flex gap-3" style={{ justifyContent: 'flex-end' }}>
        <button type="button" className="btn btn-secondary" onClick={onCancel}>Cancel</button>
        <button type="submit" className="btn btn-primary" disabled={loading}>
          {loading ? 'Saving...' : tc ? 'Update' : 'Create'}
        </button>
      </div>
    </form>
  )
}

function AIGenerateModal({ projectId, onClose, onGenerated }) {
  const [story, setStory] = useState('')
  const [count, setCount] = useState(5)
  const [loading, setLoading] = useState(false)
  const [generated, setGenerated] = useState([])

  async function generate() {
    if (!story.trim()) return
    setLoading(true)
    try {
      const token = localStorage.getItem('tcms_token')
      const res = await fetch('/api/ai/generate', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: projectId, user_story: story, count }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'AI generation failed')
      setGenerated(data.test_cases)
    } catch (ex) {
      alert(ex.message)
    } finally {
      setLoading(false)
    }
  }

  async function importAll() {
    onGenerated(generated)
    onClose()
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" style={{ maxWidth: 640 }} onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>AI Generate Test Cases</h3>
          <button className="btn btn-ghost btn-icon" onClick={onClose}>✕</button>
        </div>
        <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
          <div className="form-group">
            <label className="form-label">User Story / Feature Description</label>
            <textarea
              className="form-textarea"
              rows={4}
              value={story}
              onChange={(e) => setStory(e.target.value)}
              placeholder="As a logged-in user, I want to reset my password so that I can regain access if I forget it."
              autoFocus
            />
          </div>
          <div className="form-group" style={{ maxWidth: 120 }}>
            <label className="form-label">Count (1–20)</label>
            <input
              className="form-input"
              type="number"
              min={1}
              max={20}
              value={count}
              onChange={(e) => setCount(Number(e.target.value))}
            />
          </div>
          {generated.length === 0 ? (
            <button className="btn btn-primary" onClick={generate} disabled={loading || !story.trim()}>
              {loading ? <><span className="spinner" style={{ width: 16, height: 16 }} /> Generating...</> : '✨ Generate'}
            </button>
          ) : (
            <>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)', maxHeight: 360, overflowY: 'auto' }}>
                {generated.map((tc, i) => (
                  <div key={i} className="ai-card stagger-in" style={{ animationDelay: `${i * 50}ms` }}>
                    <div className="flex items-center gap-2" style={{ marginBottom: 'var(--space-2)' }}>
                      <PriorityBadge priority={tc.priority} />
                      <span style={{ fontWeight: 500, fontSize: '0.929rem' }}>{tc.title}</span>
                    </div>
                    <p className="text-sm text-secondary font-mono" style={{ whiteSpace: 'pre-line' }}>{tc.steps}</p>
                  </div>
                ))}
              </div>
              <div className="flex gap-3" style={{ justifyContent: 'flex-end' }}>
                <button className="btn btn-secondary" onClick={() => setGenerated([])}>Regenerate</button>
                <button className="btn btn-primary" onClick={importAll}>
                  Import {generated.length} cases
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

export default function TestEditor({ projectId, user }) {
  const [testCases, setTestCases] = useState([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState(null)
  const [editing, setEditing] = useState(false)
  const [creating, setCreating] = useState(false)
  const [showAI, setShowAI] = useState(false)
  const [showTemplate, setShowTemplate] = useState(false)
  const [suggestions, setSuggestions] = useState(null)
  const [criticizing, setCriticizing] = useState(false)
  const [search, setSearch] = useState('')
  const fileInputRef = useRef(null)

  useEffect(() => {
    loadTestCases()
  }, [projectId])

  async function loadTestCases() {
    try {
      const token = localStorage.getItem('tcms_token')
      const res = await fetch(`/api/projects/${projectId}/testcases`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      const data = await res.json()
      setTestCases(Array.isArray(data) ? data : [])
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  async function saveTestCase(payload) {
    const token = localStorage.getItem('tcms_token')
    if (editing && selected) {
      const res = await fetch(`/api/projects/${projectId}/testcases/${selected.id}`, {
        method: 'PUT',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const updated = await res.json()
      setTestCases((tcs) => tcs.map((t) => (t.id === updated.id ? updated : t)))
      setSelected(updated)
      setEditing(false)
    } else {
      const res = await fetch(`/api/projects/${projectId}/testcases`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const created = await res.json()
      setTestCases((tcs) => [created, ...tcs])
      setCreating(false)
      setSelected(created)
    }
  }

  async function deleteTestCase(id) {
    if (!confirm('Delete this test case?')) return
    const token = localStorage.getItem('tcms_token')
    await fetch(`/api/projects/${projectId}/testcases/${id}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${token}` },
    })
    setTestCases((tcs) => tcs.filter((t) => t.id !== id))
    if (selected?.id === id) { setSelected(null); setEditing(false) }
  }

  async function criticize() {
    if (!selected) return
    setCriticizing(true)
    try {
      const token = localStorage.getItem('tcms_token')
      const res = await fetch('/api/ai/criticize', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ test_case_id: selected.id }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'AI critic failed')
      setSuggestions(data.suggestions)
    } catch (ex) {
      alert(ex.message)
    } finally {
      setCriticizing(false)
    }
  }

  async function importCsv(e) {
    const file = e.target.files[0]
    if (!file) return
    const form = new FormData()
    form.append('file', file)
    const token = localStorage.getItem('tcms_token')
    try {
      const res = await fetch(`/api/projects/${projectId}/testcases/import-csv`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Import failed')
      alert(`Imported ${data.imported} test cases`)
      loadTestCases()
    } catch (ex) {
      alert(ex.message)
    }
    e.target.value = ''
  }

  async function handleGeneratedCases(cases) {
    const token = localStorage.getItem('tcms_token')
    for (const tc of cases) {
      await fetch(`/api/projects/${projectId}/testcases`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(tc),
      })
    }
    loadTestCases()
  }

  async function handleTemplateImport(templateType) {
    const token = localStorage.getItem('tcms_token')
    try {
      const res = await fetch(`/api/projects/${projectId}/testcases/import-template`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ template_type: templateType }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Template import failed')
      alert(`Imported ${data.imported} cases from ${templateType} template`)
      loadTestCases()
    } catch (ex) {
      alert(ex.message)
    }
  }

  const filtered = testCases.filter((tc) =>
    tc.title.toLowerCase().includes(search.toLowerCase()) ||
    tc.tc_id?.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div style={{ height: 'calc(100vh - 56px)', display: 'flex', flexDirection: 'column' }}>
      {/* Toolbar */}
      <div style={{ padding: 'var(--space-4) var(--space-6)', borderBottom: '1px solid var(--shai-border)', background: 'var(--shai-surface)', display: 'flex', alignItems: 'center', gap: 'var(--space-3)', flexShrink: 0 }}>
        <input
          className="form-input"
          style={{ maxWidth: 240 }}
          placeholder="Search test cases..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <div className="spacer" style={{ flex: 1 }} />
        <button className="btn btn-ghost btn-sm" onClick={() => showTemplate ? setShowTemplate(false) : setShowTemplate(true)}>
          📋 Template
        </button>
        <button className="btn btn-ghost btn-sm" onClick={() => fileInputRef.current?.click()}>
          ↑ CSV
        </button>
        <input ref={fileInputRef} type="file" accept=".csv" style={{ display: 'none' }} onChange={importCsv} />
        <button className="btn btn-secondary btn-sm" onClick={() => { setShowAI(true); setCreating(false); setEditing(false) }}>
          ✨ AI Generate
        </button>
        <button className="btn btn-primary btn-sm" onClick={() => { setCreating(true); setEditing(false); setSelected(null) }}>
          + New
        </button>
      </div>

      <div style={{ flex: 1, display: 'grid', gridTemplateColumns: '340px 1fr', overflow: 'hidden' }}>
        {/* List */}
        <div style={{ borderRight: '1px solid var(--shai-border)', overflowY: 'auto', background: 'var(--shai-surface)' }}>
          {loading ? (
            <div className="page-loader"><span className="spinner" /></div>
          ) : filtered.length === 0 ? (
            <div className="empty-state" style={{ padding: 'var(--space-8) var(--space-4)' }}>
              <p>{search ? 'No matches' : 'No test cases yet'}</p>
            </div>
          ) : filtered.map((tc) => (
            <div
              key={tc.id}
              className={`tc-list-item${selected?.id === tc.id ? ' active' : ''}`}
              onClick={() => { setSelected(tc); setEditing(false); setCreating(false) }}
            >
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="tc-id">{tc.tc_id}</div>
                <div className="truncate" style={{ fontWeight: 500, fontSize: '0.857rem', marginBottom: 4 }}>{tc.title}</div>
                <PriorityBadge priority={tc.priority} />
              </div>
            </div>
          ))}
        </div>

        {/* Detail */}
        <div style={{ overflowY: 'auto', padding: 'var(--space-6)' }}>
          {creating ? (
            <>
              <h3 style={{ marginBottom: 'var(--space-5)' }}>New Test Case</h3>
              <TestCaseForm onSave={saveTestCase} onCancel={() => setCreating(false)} />
            </>
          ) : editing && selected ? (
            <>
              <h3 style={{ marginBottom: 'var(--space-5)' }}>Edit {selected.tc_id}</h3>
              <TestCaseForm tc={selected} onSave={saveTestCase} onCancel={() => setEditing(false)} />
            </>
          ) : selected ? (
            <>
              <div className="flex items-center justify-between" style={{ marginBottom: 'var(--space-5)' }}>
                <div className="flex items-center gap-3">
                  <span className="tc-id" style={{ fontSize: '0.929rem' }}>{selected.tc_id}</span>
                  <PriorityBadge priority={selected.priority} />
                </div>
                <div className="flex gap-2">
                  <button className="btn btn-ghost btn-sm" onClick={criticize} disabled={criticizing}>
                    {criticizing ? <><span className="spinner" style={{ width: 14, height: 14 }} /> Analyzing...</> : '🤖 Critique'}
                  </button>
                  <button className="btn btn-secondary btn-sm" onClick={() => setEditing(true)}>Edit</button>
                  <button className="btn btn-danger btn-sm" onClick={() => deleteTestCase(selected.id)}>Delete</button>
                </div>
              </div>

              <h3 style={{ marginBottom: 'var(--space-4)' }}>{selected.title}</h3>

              {(selected.component_tags || []).length > 0 && (
                <div className="flex gap-2" style={{ marginBottom: 'var(--space-4)', flexWrap: 'wrap' }}>
                  {selected.component_tags.map((tag) => (
                    <span key={tag} className="badge badge-pending">{tag}</span>
                  ))}
                </div>
              )}

              <div style={{ marginBottom: 'var(--space-5)' }}>
                <div className="form-label" style={{ marginBottom: 'var(--space-2)' }}>STEPS</div>
                <div className="card-body" style={{ background: 'var(--shai-bg)', borderRadius: 'var(--radius-md)', padding: 'var(--space-4)' }}>
                  <pre className="text-sm font-mono" style={{ whiteSpace: 'pre-wrap', lineHeight: 1.6 }}>{selected.steps}</pre>
                </div>
              </div>

              <div>
                <div className="form-label" style={{ marginBottom: 'var(--space-2)' }}>EXPECTED RESULT</div>
                <div className="card-body" style={{ background: 'var(--shai-bg)', borderRadius: 'var(--radius-md)', padding: 'var(--space-4)' }}>
                  <pre className="text-sm font-mono" style={{ whiteSpace: 'pre-wrap', lineHeight: 1.6 }}>{selected.expected_result}</pre>
                </div>
              </div>
            </>
          ) : (
            <div className="empty-state">
              <p>Select a test case to view details, or create a new one.</p>
            </div>
          )}
        </div>
      </div>

      {showAI && (
        <AIGenerateModal
          projectId={projectId}
          onClose={() => setShowAI(false)}
          onGenerated={handleGeneratedCases}
        />
      )}

      {showTemplate && (
        <TemplateModal
          onClose={() => setShowTemplate(false)}
          onImport={handleTemplateImport}
        />
      )}

      {suggestions && (
        <AISuggestionsDrawer
          suggestions={suggestions}
          onClose={() => setSuggestions(null)}
          onApply={(rewrite) => {
            if (selected && editing) {
              // handled via form state, close drawer
            }
            setSuggestions(null)
          }}
        />
      )}
    </div>
  )
}
