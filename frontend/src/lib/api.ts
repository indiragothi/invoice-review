import { env } from './env.ts'
import type { HealthResponse } from './types.ts'

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${env.apiBaseUrl}${path}`, { credentials: 'include' })
  if (!response.ok) {
    throw new Error(`${path} returned ${response.status}`)
  }
  return (await response.json()) as T
}

export const api = {
  health: () => getJson<HealthResponse>('/health'),
}
