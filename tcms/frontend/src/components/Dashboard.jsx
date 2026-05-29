import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'

function CoverageBar({ pct }) {
  const level = pct >= 70 ? 'coverage-high' : pct >= 40 ? 'coverage-med' : 'coverage-low'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div className={`coverage-bar ${level}`} style={{ flex: 1 }}>
        <div className="coverage-bar-fill" style={{ width: `${pct}%` }} />
      </div>
      <span className="text-sm" style={{ minWidth: 36, textAlign: 'right' }}>{pct}%</span>
    </div>
  )
}

function ProjectCard({ project, onClick }) {
  const needsAttention = project.stats?.needs_attention
  const pct = project.stats?.coverage_pct ?? 0
  const totalCases = project.stats?.total_cases ?? 0
  const daysSince = project.stats?.days_since_last_run

  return (
    <div
      className="card"
      style={{ cursor: 'pointer', transition: 'box-shadow 150ms ease' }}
      onClick={onClick}
      onMouseEnter={(e) => (e.currentTarget.style.boxShadow = 'var(--shadow-md)')}
      onMouseLeave={(e) => (e.currentTarget.style.boxShadow = '')}
    >
      {needsAttention && (
        <div className="attention-banner" style={{ borderRadius: 'var(--radius-lg) var(--radius-lg) 0 0', borderBottom: 'none' }}>
          ⚠ Needs attention
        </div>
      )}
      <div className="card-body">
        <div className="flex items-center justify-between" style={{ marginBottom: 'var(--space-3)' }}>
          <h3 style={{ fontSize: '1rem' }}>{project.name}</h3>
          <span className="badge badge-pending">{totalCases} cases</span>
        </div>

        {project.description && (
          <p className="text-sm text-secondary" style={{ marginBottom: 'var(--space-4)' }}>
            {project.description}
          </p>
        )}

        <CoverageBar pct={pct} />

        <div className="flex items-center justify-between" style={{ marginTop: 'var(--space-3)' }}>
          <span className="text-xs text-muted">
            {daysSince != null ? `Last run ${daysSince}d ago` : 'No runs yet'}
          </span>
          {project.github_repo && (
            <span className="text-xs text-muted font-mono">{project.github_repo}</span>
          )}
        </div>
      </div>
    </div>
  )
}

function CreateProjectModal({ onClose, onCreate }) {
  const [form, setForm] = useState({ name: '', description: '', github_repo: '' })
  const [loading, setLoading] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setLoading(true)
    try {
      const token = localStorage.getItem('tcms_token')
      const res = await fetch('/api/projects', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Failed to create project')
      onCreate(data)
      onClose()
    } catch (ex) {
      alert(ex.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>New Project</h3>
          <button className="btn btn-ghost btn-icon" onClick={onClose}>✕</button>
        </div>
        <form onSubmit={submit}>
          <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
            <div className="form-group">
              <label className="form-label">Project Name *</label>
              <input
                className="form-input"
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                required
                autoFocus
                placeholder="e.g. Agentic Hiring Platform"
              />
            </div>
            <div className="form-group">
              <label className="form-label">Description</label>
              <input
                className="form-input"
                value={form.description}
                onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
                placeholder="Optional project description"
              />
            </div>
            <div className="form-group">
              <label className="form-label">GitHub Repo</label>
              <input
                className="form-input"
                value={form.github_repo}
                onChange={(e) => setForm((f) => ({ ...f, github_repo: e.target.value }))}
                placeholder="e.g. org/repo-name"
              />
            </div>
          </div>
          <div className="modal-footer">
            <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-primary" disabled={loading}>
              {loading ? 'Creating...' : 'Create Project'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default function Dashboard({ user }) {
  const navigate = useNavigate()
  const [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [search, setSearch] = useState('')

  useEffect(() => {
    loadProjects()
  }, [])

  async function loadProjects() {
    try {
      const token = localStorage.getItem('tcms_token')
      const res = await fetch('/api/projects', {
        headers: { Authorization: `Bearer ${token}` },
      })
      const data = await res.json()
      setProjects(Array.isArray(data) ? data : [])
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const filtered = projects.filter((p) =>
    p.name.toLowerCase().includes(search.toLowerCase())
  )

  const attention = filtered.filter((p) => p.stats?.needs_attention)
  const normal = filtered.filter((p) => !p.stats?.needs_attention)
  const sorted = [...attention, ...normal]

  return (
    <div className="page">
      <div className="flex items-center justify-between" style={{ marginBottom: 'var(--space-6)' }}>
        <div>
          <h1>Projects</h1>
          <p className="text-secondary text-sm" style={{ marginTop: 4 }}>
            Welcome back, {user?.full_name || user?.email}
          </p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowCreate(true)}>
          + New Project
        </button>
      </div>

      <div style={{ marginBottom: 'var(--space-6)' }}>
        <input
          className="form-input"
          style={{ maxWidth: 320 }}
          placeholder="Search projects..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {loading ? (
        <div className="page-loader">
          <span className="spinner" /> Loading projects...
        </div>
      ) : sorted.length === 0 ? (
        <div className="empty-state">
          <div style={{ fontSize: '2rem', marginBottom: 'var(--space-4)' }}>🧪</div>
          <h3>{search ? 'No projects match your search' : 'No projects yet'}</h3>
          <p style={{ marginBottom: 'var(--space-4)' }}>
            {search ? 'Try a different search term.' : 'Create your first project to start managing test cases.'}
          </p>
          {!search && (
            <button className="btn btn-primary" onClick={() => setShowCreate(true)}>
              Create Project
            </button>
          )}
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 'var(--space-5)' }}>
          {sorted.map((project) => (
            <ProjectCard
              key={project.id}
              project={project}
              onClick={() => navigate(`/projects/${project.id}`)}
            />
          ))}
        </div>
      )}

      {showCreate && (
        <CreateProjectModal
          onClose={() => setShowCreate(false)}
          onCreate={(p) => setProjects((prev) => [p, ...prev])}
        />
      )}
    </div>
  )
}
