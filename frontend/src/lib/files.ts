// Quick checks before upload. The server repeats them and decides; these only save a round trip.

export const MAX_UPLOAD_BYTES = 5 * 1024 * 1024
export const ACCEPT = 'application/pdf,image/png,image/jpeg'
const ALLOWED_TYPES = new Set(ACCEPT.split(','))

/** Why the file cannot be uploaded, or null when it looks fine. */
export function fileProblem(file: File): string | null {
  if (!ALLOWED_TYPES.has(file.type)) return 'Choose a PDF, PNG or JPG file.'
  if (file.size === 0) return 'The file is empty.'
  if (file.size > MAX_UPLOAD_BYTES) {
    return `The file is ${formatSize(file.size)}; the limit is ${formatSize(MAX_UPLOAD_BYTES)}.`
  }
  return null
}

export function formatSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
