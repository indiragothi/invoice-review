export interface HealthResponse {
  status: 'ok'
  llm_provider: 'gemini' | 'nvidia'
  model: string
}
