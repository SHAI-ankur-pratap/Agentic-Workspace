import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'

const STATUS_OPTIONS = [
  { key: 'pass', label: 'Pass', shortcut: 'P' },
  { key: 'fail', label: 'Fail', shortcut: 'F' },
  { key: 'skip', label: 'Skip', shortcut: 'S' },
  { key: 'blocked', label: 'Blocked', shortcut: 'B' },
]

function KbdHelp({ onClose }) {
  return (
    <div className="kbd-help" onClick={onClose}>
      <div className="kbd-help-panel" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between" style={{ marginBottom: 'var(--space-5)' }}>
          <h3>Keyboard Shortcuts</h3>
          <button className="btn btn-ghost btn-icon" onClick={onClose}>✕</button>
        </div>
        {[
          ['J / ↓', 'Next test case'],
          ['K / ↑', 'Previous test case'],
          ['P', 'Mark Pass'],
          ['F', 'Mark Fail'],
          ['S', 'Mark Skip'],
          ['B', 'Mark Blocked'],
          ['?', 'Toggle this help'],
        ].map(([key, desc]) => (
          <div key={key} className="kbd-row">
            <span className="text-secondary text-sm">{desc}</span>
            <kbd className="kbd">{key}</kbd>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function ExecutionRunner() {
  const { projectId, runId } = useParams()
  const navigate = useNavigate()
  const [run, setRun] = useState(null)
  const [results, setResults] = useState([])
  const [currentIdx, setCurrentIdx] = useState(0)
  const [notes, setNotes] = useState('')
  const [actualResult, setActualResult] = useState('')
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [showHelp, setShowHelp] = useState(false)
  const [shareUrl, setShareUrl] = useState(null)

  useEffect(() => {
    loadRun()
  }, [runId])

  async function loadRun() {
    const token = localStorage.getItem('tcms_token')
    try {
      const res = await fetch(`/api/projects/${projectId}/runs/${runId}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      const data = await res.json()
      setRun(data)
      setResults(data.results || [])
      const firstPending = (data.results || []).findIndex((r) => r.status === 'pending')
      setCurrentIdx(firstPending >= 0 ? firstPending : 0)
    } finally {
      setLoading(false)
    }
  }

  const current = results[currentIdx]

  async function markResult(status) {
    if (!current || submitting) return
    setSubmitting(true)
    const token = localStorage.getItem('tcms_token')
    try {
      const res = await fetch(`/api/projects/${projectId}/runs/${runId}/results/${current.id}`, {
        method: 'PUT',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ status, notes, actual_result: actualResult }),
      })
      const updated = await res.json()
      setResults((prev) => prev.map((r) => (r.id === updated.id ? updated : r)))
      setNotes('')
      setActualResult('')
      // Auto-advance to next pending
      const nextPending = results.findIndex((r, i) => i > currentIdx && r.status === 'pending')
      if (nextPending >= 0) setCurrentIdx(nextPending)
      else if (currentIdx < results.length - 1) setCurrentIdx(currentIdx + 1)
    } finally {
      setSubmitting(false)
    }
  }

  async function completeRun() {
    if (!confirm('Mark this run as completed?')) return
    const token = localStorage.getItem('tcms_token')
    await fetch(`/api/projects/${projectId}/runs/${runId}/complete`, {
      method: 'PUT',
      headers: { Authorization: `Bearer ${token}` },
    })
    navigate(`/projects/${projectId}/runs`)
  }

  async function createShareLink() {
    const token = localStorage.getItem('tcms_token')
    const res = await fetch(`/api/projects/${projectId}/runs/${runId}/share`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    })
    const data = await res.json()
    setShareUrl(data.url)
    navigator.clipboard?.writeText(data.url).catch(() => {})
  }

  const handleKey = useCallback((e) => {
    if (e.target.tagName === 'TEXTAREA' || e.target.tagName === 'INPUT') return
    switch (e.key.toLowerCase()) {
      case 'j': case 'arrowdown':
        setCurrentIdx((i) => Math.min(i + 1, results.length - 1)); break
      case 'k': case 'arrowup':
        setCurrentIdx((i) => Math.max(i - 1, 0)); break
      case 'p': markResult('pass'); break
      case 'f': markResult('fail'); break
      case 's': markResult('skip'); break
      case 'b': markResult('blocked'); break
      case '?': setShowHelp((v) => !v); break
    }
  }, [results, currentIdx, notes, actualResult, submitting])

  useEffect(() => {
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [handleKey])

  if (loading) {
    return <div className="page-loader"><span className="spinner" /> Loading run...</div>
  }

  const total = results.length
  const passed = results.filter((r) => r.status === 'pass').length
  const failed = results.filter((r) => r.status === 'fail').length
  const pending = results.filter((r) => r.status === 'pending').length
  const pct = total ? Math.round((passed / total) * 100) : 0

  return (
    <>
      {showHelp && <KbdHelp onClose={() => setShowHelp(false)} />}

      {/* Header bar */}
      <div style={{ background: 'var(--shai-surface)', borderBottom: '1px solid var(--shai-border)', padding: 'var(--space-3) var(--space-6)', display: 'flex', alignItems: 'center', gap: 'var(--space-4)' }}>
        <button className="btn btn-ghost btn-sm" onClick={() => navigate(`/projects/${projectId}/runs`)}>← Runs</button>
        <span style={{ fontWeight: 600 }}>{run?.run?.name}</span>
        <div style={{ flex: 1 }}>
          <div className="progress-bar" style={{ maxWidth: 200 }}>
            <div className="progress-fill" style={{ width: `${pct}%` }} />
          </div>
        </div>
        <span className="text-sm text-secondary">{passed}P {failed}F {pending} pending</span>
        <button className="btn btn-ghost btn-sm" onClick={() => setShowHelp(true)}>?</button>
        <button className="btn btn-ghost btn-sm" onClick={createShareLink}>Share</button>
        <button className="btn btn-ghost btn-sm" onClick={() => window.open(`/api/projects/${projectId}/runs/${runId}/report.html`, '_blank')}>Report</button>
        <button className="btn btn-primary btn-sm" onClick={completeRun}>Complete Run</button>
      </div>

      {shareUrl && (
        <div style={{ background: 'var(--shai-blue-light)', padding: 'var(--space-3) var(--space-6)', display: 'flex', alignItems: 'center', gap: 'var(--space-3)', borderBottom: '1px solid var(--shai-border)' }}>
          <span className="text-sm">Share link: </span>
          <code className="font-mono text-sm">{shareUrl}</code>
          <span className="text-sm text-muted">(copied to clipboard)</span>
          <button className="btn btn-ghost btn-icon btn-sm" onClick={() => setShareUrl(null)}>✕</button>
        </div>
      )}

      <div className="exec-layout">
        {/* TC List */}
        <div className="exec-sidebar">
          {results.map((r, i) => (
            <div
              key={r.id}
              className={`tc-list-item${i === currentIdx ? ' active' : ''}`}
              onClick={() => setCurrentIdx(i)}
            >
              <span className={`dot dot-${r.status}`} style={{ marginTop: 4, flexShrink: 0 }} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="tc-id">{r.test_case?.tc_id}</div>
                <div className="truncate" style={{ fontSize: '0.857rem', fontWeight: 500 }}>
                  {r.test_case?.title}
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Main panel */}
        <div className="exec-main">
          {current ? (
            <>
              <div className="flex items-center gap-3" style={{ marginBottom: 'var(--space-5)' }}>
                <span className="tc-id" style={{ fontSize: '1rem' }}>{current.test_case?.tc_id}</span>
                <span className={`badge badge-${current.status}`}>{current.status}</span>
                <span className={`badge badge-${current.test_case?.priority?.toLowerCase() || 'p4'}`}>
                  {current.test_case?.priority || 'P4'}
                </span>
                <span className="text-muted text-sm">{currentIdx + 1} of {total}</span>
              </div>

              <h2 style={{ marginBottom: 'var(--space-6)' }}>{current.test_case?.title}</h2>

              <div style={{ marginBottom: 'var(--space-5)' }}>
                <div className="form-label" style={{ marginBottom: 'var(--space-2)' }}>STEPS</div>
                <div style={{ background: 'var(--shai-bg)', borderRadius: 'var(--radius-md)', padding: 'var(--space-4)' }}>
                  <pre className="text-sm font-mono" style={{ whiteSpace: 'pre-wrap', lineHeight: 1.7 }}>
                    {current.test_case?.steps}
                  </pre>
                </div>
              </div>

              <div style={{ marginBottom: 'var(--space-6)' }}>
                <div className="form-label" style={{ marginBottom: 'var(--space-2)' }}>EXPECTED RESULT</div>
                <div style={{ background: 'var(--shai-bg)', borderRadius: 'var(--radius-md)', padding: 'var(--space-4)' }}>
                  <pre className="text-sm font-mono" style={{ whiteSpace: 'pre-wrap', lineHeight: 1.7 }}>
                    {current.test_case?.expected_result}
                  </pre>
                </div>
              </div>

              <div className="result-btn-group" style={{ marginBottom: 'var(--space-5)' }}>
                {STATUS_OPTIONS.map((opt) => (
                  <button
                    key={opt.key}
                    className={`result-btn result-btn-${opt.key}${current.status === opt.key ? ' active' : ''}`}
                    onClick={() => markResult(opt.key)}
                    disabled={submitting}
                  >
                    <kbd className="kbd" style={{ background: 'rgba(255,255,255,0.3)', color: 'inherit' }}>{opt.shortcut}</kbd>
                    {opt.label}
                  </button>
                ))}
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
                <div className="form-group">
                  <label className="form-label">Actual Result</label>
                  <textarea
                    className="form-textarea"
                    rows={2}
                    value={actualResult}
                    onChange={(e) => setActualResult(e.target.value)}
                    placeholder="What actually happened..."
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Notes</label>
                  <textarea
                    className="form-textarea"
                    rows={2}
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    placeholder="Bug ref, observations..."
                  />
                </div>
              </div>
            </>
          ) : (
            <div className="empty-state">
              <p>No test cases in this run.</p>
            </div>
          )}
        </div>
      </div>
    </>
  )
}
