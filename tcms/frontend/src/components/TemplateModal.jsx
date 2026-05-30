import { useState } from 'react'

const TEMPLATES = [
  {
    type: 'react-crud',
    name: 'React CRUD',
    icon: '⚛',
    description: 'Create, Read, Update, Delete flows for React apps',
    count: 34,
  },
  {
    type: 'rest-api',
    name: 'REST API',
    icon: '🔌',
    description: 'Endpoint testing, auth, status codes, error handling',
    count: 28,
  },
  {
    type: 'mobile',
    name: 'Mobile App',
    icon: '📱',
    description: 'iOS/Android navigation, gestures, offline behavior',
    count: 22,
  },
]

export default function TemplateModal({ onClose, onImport }) {
  const [selected, setSelected] = useState(null)
  const [importing, setImporting] = useState(false)

  async function doImport() {
    if (!selected) return
    setImporting(true)
    await onImport(selected)
    setImporting(false)
    onClose()
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <h3>Import Template</h3>
            <p className="text-sm text-secondary">Add a curated test suite to your project</p>
          </div>
          <button className="btn btn-ghost btn-icon" onClick={onClose}>✕</button>
        </div>
        <div className="modal-body">
          <div className="template-grid">
            {TEMPLATES.map((t) => (
              <div
                key={t.type}
                className={`template-card${selected === t.type ? ' selected' : ''}`}
                onClick={() => setSelected(t.type)}
              >
                <div className="template-icon">{t.icon}</div>
                <div style={{ fontWeight: 600, marginBottom: 4 }}>{t.name}</div>
                <div className="text-sm text-secondary" style={{ marginBottom: 8 }}>{t.description}</div>
                <span className="badge badge-pending">{t.count} cases</span>
              </div>
            ))}
          </div>
        </div>
        <div className="modal-footer">
          <button className="btn btn-secondary" onClick={onClose}>Cancel</button>
          <button
            className="btn btn-primary"
            disabled={!selected || importing}
            onClick={doImport}
          >
            {importing ? 'Importing...' : `Import ${selected ? TEMPLATES.find((t) => t.type === selected)?.count : ''} cases`}
          </button>
        </div>
      </div>
    </div>
  )
}
