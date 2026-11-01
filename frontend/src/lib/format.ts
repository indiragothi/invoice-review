/** "01 Nov 2026, 5:04 pm" in the reviewer's locale (India). */
export function formatDateTime(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })
}
