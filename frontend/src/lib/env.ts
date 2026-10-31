// The only module that reads import.meta.env.

function readApiBaseUrl(): string {
  const value: unknown = import.meta.env.VITE_API_BASE_URL
  if (typeof value !== 'string' || value.trim() === '') {
    throw new Error('VITE_API_BASE_URL is missing. Copy frontend/.env.example to frontend/.env.')
  }
  return value.replace(/\/+$/, '')
}

export const env = {
  apiBaseUrl: readApiBaseUrl(),
} as const
