import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('tcms_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('tcms_token')
      localStorage.removeItem('tcms_user')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export default api

export const auth = {
  register: (data) => api.post('/auth/register', data),
  login: (data) => api.post('/auth/login', data),
  apiKeys: () => api.get('/auth/api-keys'),
  createApiKey: (data) => api.post('/auth/api-keys', data),
  deleteApiKey: (id) => api.delete(`/auth/api-keys/${id}`),
}

export const projects = {
  list: () => api.get('/projects'),
  get: (id) => api.get(`/projects/${id}`),
  create: (data) => api.post('/projects', data),
  update: (id, data) => api.put(`/projects/${id}`, data),
  delete: (id) => api.delete(`/projects/${id}`),
  stats: (id) => api.get(`/projects/${id}/stats`),
  componentTagRules: (id) => api.get(`/projects/${id}/component-tag-rules`),
  createComponentTagRule: (id, data) => api.post(`/projects/${id}/component-tag-rules`, data),
  deleteComponentTagRule: (id, ruleId) => api.delete(`/projects/${id}/component-tag-rules/${ruleId}`),
}

export const testcases = {
  list: (projectId, params) => api.get(`/projects/${projectId}/testcases`, { params }),
  get: (projectId, id) => api.get(`/projects/${projectId}/testcases/${id}`),
  create: (projectId, data) => api.post(`/projects/${projectId}/testcases`, data),
  update: (projectId, id, data) => api.put(`/projects/${projectId}/testcases/${id}`, data),
  delete: (projectId, id) => api.delete(`/projects/${projectId}/testcases/${id}`),
  importCsv: (projectId, file) => {
    const form = new FormData()
    form.append('file', file)
    return api.post(`/projects/${projectId}/testcases/import-csv`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  importTemplate: (projectId, templateType) =>
    api.post(`/projects/${projectId}/testcases/import-template`, { template_type: templateType }),
}

export const runs = {
  list: (projectId) => api.get(`/projects/${projectId}/runs`),
  get: (projectId, id) => api.get(`/projects/${projectId}/runs/${id}`),
  create: (projectId, data) => api.post(`/projects/${projectId}/runs`, data),
  updateResult: (projectId, runId, resultId, data) =>
    api.put(`/projects/${projectId}/runs/${runId}/results/${resultId}`, data),
  complete: (projectId, runId) => api.put(`/projects/${projectId}/runs/${runId}/complete`),
  abandon: (projectId, runId) => api.put(`/projects/${projectId}/runs/${runId}/abandon`),
  shareLink: (projectId, runId) => api.post(`/projects/${projectId}/runs/${runId}/share`),
}

export const ai = {
  generate: (data) => api.post('/ai/generate', data),
  criticize: (data) => api.post('/ai/criticize', data),
}

export const templates = {
  list: () => api.get('/testcases/templates'),
}
