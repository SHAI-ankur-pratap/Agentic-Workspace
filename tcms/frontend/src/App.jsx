import { Routes, Route, Navigate, NavLink, Link, useNavigate, useParams } from 'react-router-dom'
import { useState, useEffect } from 'react'
import Dashboard from './components/Dashboard.jsx'
import TestEditor from './components/TestEditor.jsx'
import ExecutionRunner from './components/ExecutionRunner.jsx'

function LoginPage({ onLogin }) {
  const [form, setForm] = useState({ email: '', password: '' })
  const [err, setErr] = useState('')
  const [loading, setLoading] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setErr('')
    setLoading(true)
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Login failed')
      localStorage.setItem('tcms_token', data.access_token)
      localStorage.setItem('tcms_user', JSON.stringify(data.user))
      onLogin(data.user)
    } catch (ex) {
      setErr(ex.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <h1>TCMS</h1>
        <p className="subtitle">AI-Native Test Case Management · Shorthills AI</p>
        {err && <div className="error-msg">{err}</div>}
        <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
          <div className="form-group">
            <label className="form-label">Email</label>
            <input
              className="form-input"
              type="email"
              value={form.email}
              onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
              required
              autoFocus
            />
          </div>
          <div className="form-group">
            <label className="form-label">Password</label>
            <input
              className="form-input"
              type="password"
              value={form.password}
              onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
              required
            />
          </div>
          <button className="btn btn-primary btn-lg" type="submit" disabled={loading}>
            {loading ? <><span className="spinner" style={{ width: 16, height: 16 }} /> Signing in...</> : 'Sign in'}
          </button>
        </form>
      </div>
    </div>
  )
}

function TopNav({ user, onLogout }) {
  return (
    <nav className="topnav">
      <Link to="/" className="brand">
        TCMS <span className="label">· Shorthills AI</span>
      </Link>
      <div className="spacer" />
      <NavLink to="/" end className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
        Dashboard
      </NavLink>
      <span style={{ color: 'var(--shai-text-muted)', fontSize: '0.857rem' }}>{user?.email}</span>
      <button className="btn btn-ghost btn-sm" onClick={onLogout}>Sign out</button>
    </nav>
  )
}

function ProjectLayout({ user }) {
  const { projectId } = useParams()
  const navigate = useNavigate()
  const [tab, setTab] = useState('tests')

  const sidebarItems = [
    { key: 'tests', label: 'Test Cases', icon: '🧪' },
    { key: 'runs', label: 'Execution Runs', icon: '▶' },
    { key: 'settings', label: 'Settings', icon: '⚙' },
  ]

  return (
    <div className="app-layout">
      <aside className="sidebar">
        <div className="sidebar-label">Project</div>
        {sidebarItems.map((item) => (
          <button
            key={item.key}
            className={`sidebar-link${tab === item.key ? ' active' : ''}`}
            onClick={() => {
              if (item.key === 'runs') {
                navigate(`/projects/${projectId}/runs`)
              } else {
                setTab(item.key)
              }
            }}
          >
            <span>{item.icon}</span>
            {item.label}
          </button>
        ))}
        <div style={{ marginTop: 'var(--space-4)' }}>
          <button className="sidebar-link" onClick={() => navigate('/')}>
            ← Back to Dashboard
          </button>
        </div>
      </aside>
      <main className="main-content">
        {tab === 'tests' && <TestEditor projectId={projectId} user={user} />}
        {tab === 'settings' && <ProjectSettings projectId={projectId} />}
      </main>
    </div>
  )
}

function ProjectSettings({ projectId }) {
  return (
    <div className="page">
      <h2>Project Settings</h2>
      <p className="text-secondary" style={{ marginTop: 'var(--space-2)' }}>
        Configure GitHub integration and component tag rules.
      </p>
    </div>
  )
}

function RunsPage() {
  const { projectId } = useParams()
  const navigate = useNavigate()
  const [runs, setRuns] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const token = localStorage.getItem('tcms_token')
    fetch(`/api/projects/${projectId}/runs`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then((data) => { setRuns(data); setLoading(false) })
      .catch(() => setLoading(false))
  }, [projectId])

  async function createRun() {
    const token = localStorage.getItem('tcms_token')
    const name = prompt('Run name (e.g. Sprint 5 Regression):')
    if (!name) return
    const res = await fetch(`/api/projects/${projectId}/runs`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    })
    const data = await res.json()
    navigate(`/projects/${projectId}/runs/${data.run.id}`)
  }

  if (loading) return <div className="page-loader"><span className="spinner" /> Loading runs...</div>

  return (
    <div className="page">
      <div className="flex items-center justify-between" style={{ marginBottom: 'var(--space-6)' }}>
        <div>
          <h2>Execution Runs</h2>
          <p className="text-secondary text-sm" style={{ marginTop: 4 }}>Start a new run or review past executions</p>
        </div>
        <div className="flex gap-3">
          <button className="btn btn-ghost btn-sm" onClick={() => navigate('/')}>← Back</button>
          <button className="btn btn-primary" onClick={createRun}>+ New Run</button>
        </div>
      </div>

      {runs.length === 0 ? (
        <div className="empty-state">
          <h3>No runs yet</h3>
          <p>Create your first execution run to start testing.</p>
        </div>
      ) : (
        <div className="card">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Status</th>
                  <th>Progress</th>
                  <th>Coverage</th>
                  <th>Created</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => {
                  const pct = run.total ? Math.round(((run.passed || 0) / run.total) * 100) : 0
                  return (
                    <tr key={run.id}>
                      <td style={{ fontWeight: 500 }}>{run.name}</td>
                      <td>
                        <span className={`badge badge-${run.status === 'completed' ? 'pass' : run.status === 'abandoned' ? 'fail' : 'pending'}`}>
                          {run.status}
                        </span>
                      </td>
                      <td>
                        <div style={{ fontSize: '0.857rem', color: 'var(--shai-text-secondary)' }}>
                          {run.passed || 0}P / {run.failed || 0}F / {run.pending || 0} pending
                        </div>
                      </td>
                      <td>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 100 }}>
                          <div className={`coverage-bar ${pct >= 70 ? 'coverage-high' : pct >= 40 ? 'coverage-med' : 'coverage-low'}`} style={{ width: 60 }}>
                            <div className="coverage-bar-fill" style={{ width: `${pct}%` }} />
                          </div>
                          <span className="text-sm">{pct}%</span>
                        </div>
                      </td>
                      <td className="text-sm text-secondary">
                        {new Date(run.created_at).toLocaleDateString()}
                      </td>
                      <td>
                        {run.status === 'in_progress' && (
                          <button
                            className="btn btn-primary btn-sm"
                            onClick={() => navigate(`/projects/${projectId}/runs/${run.id}`)}
                          >
                            Continue
                          </button>
                        )}
                        {run.status === 'completed' && (
                          <button
                            className="btn btn-secondary btn-sm"
                            onClick={() => window.open(`/api/projects/${projectId}/runs/${run.id}/report.html`, '_blank')}
                          >
                            Report
                          </button>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

export default function App() {
  const [user, setUser] = useState(() => {
    const u = localStorage.getItem('tcms_user')
    return u ? JSON.parse(u) : null
  })

  function logout() {
    localStorage.removeItem('tcms_token')
    localStorage.removeItem('tcms_user')
    setUser(null)
  }

  if (!user) return <LoginPage onLogin={setUser} />

  return (
    <>
      <TopNav user={user} onLogout={logout} />
      <Routes>
        <Route path="/" element={<Dashboard user={user} />} />
        <Route path="/projects/:projectId" element={<ProjectLayout user={user} />} />
        <Route path="/projects/:projectId/runs" element={<RunsPage />} />
        <Route path="/projects/:projectId/runs/:runId" element={<ExecutionRunner />} />
        <Route path="/login" element={<Navigate to="/" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  )
}
