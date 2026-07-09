const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8765'

export type JobRow = {
  id: string
  publish_date: string
  company_name: string
  job_title: string
  announcement_url: string
  apply_url: string
  industry: string
  company_type: string
  batch: string
  location: string
  hot_score: number
  source_name: string
  source_type: string
  confidence: string
  status: string
  raw_summary: string
  last_updated: string
}

export type AgentStatus = {
  agent: string
  status: string
  latency_ms: number
  success_count: number
  failure_count: number
  last_message: string
  updated_at: string
}

export type AgentLog = {
  id: number
  agent: string
  level: string
  message: string
  latency_ms: number
  created_at: string
}

export type AgentEvent = {
  id: number
  agent: string
  source_name: string
  source_url: string
  status: string
  latency_ms: number
  message: string
  detail: string
  created_at: string
}

export type ApiSettings = {
  profile_name: string
  api_key_set: boolean
  api_key_preview: string
  base_url: string
  model: string
  active_profile: string
  profiles: Array<{
    name: string
    api_key_set: boolean
    api_key_preview: string
    base_url: string
    model: string
  }>
}

export type LlmStatus = {
  used_by: string[]
  api_key_set: boolean
  base_url: string
  model: string
  last_message: string
  last_time: string
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, options)
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`)
  }
  return response.json()
}

export function getJobs(params: Record<string, string>) {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value) query.set(key, value)
  })
  return request<JobRow[]>(`/api/jobs?${query.toString()}`)
}

export function getFilters() {
  return request<Record<string, string[]>>('/api/filters')
}

export function runAgents() {
  return request<{ ok: boolean; message: string }>('/api/run', { method: 'POST' })
}

export function stopAgents() {
  return request<{ ok: boolean; message: string }>('/api/stop', { method: 'POST' })
}

export function getStatus() {
  return request<{ running: boolean; stopping: boolean; agents: AgentStatus[] }>('/api/status')
}

export function getLogs() {
  return request<AgentLog[]>('/api/logs?limit=120')
}

export function getEvents(agent = '') {
  const query = agent ? `?agent=${encodeURIComponent(agent)}` : ''
  return request<AgentEvent[]>(`/api/events${query}`)
}

export function getSources() {
  return request<any[]>('/api/sources')
}

export function getSettings() {
  return request<ApiSettings>('/api/settings')
}

export function getLlmStatus() {
  return request<LlmStatus>('/api/llm/status')
}

export function testLlm() {
  return request<{ ok: boolean; message: string }>('/api/llm/test', { method: 'POST' })
}

export function saveSettings(payload: {
  profile_name: string
  original_name?: string
  api_key?: string
  base_url: string
  model: string
}) {
  return request<ApiSettings>('/api/settings', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function activateSettings(profile_name: string) {
  return request<ApiSettings>('/api/settings/active', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ profile_name }),
  })
}

export function deleteSettings(profile_name: string) {
  return request<ApiSettings>(`/api/settings/${encodeURIComponent(profile_name)}`, {
    method: 'DELETE',
  })
}
