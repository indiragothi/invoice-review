import { useEffect, useState } from 'react'

/** Shows the chosen file before upload (image, or the PDF in the browser's own viewer). */
export function FilePreview({ file }: { file: File }) {
  const [source, setSource] = useState<{ file: File; url: string } | null>(null)

  useEffect(() => {
    let cancelled = false
    const reader = new FileReader()
    reader.onload = () => {
      if (!cancelled && typeof reader.result === 'string') {
        setSource({ file, url: reader.result })
      }
    }
    reader.readAsDataURL(file)
    return () => {
      cancelled = true
      reader.abort()
    }
  }, [file])

  // Until the new file has been read, show nothing rather than the previous file.
  if (source === null || source.file !== file) return null

  if (file.type === 'application/pdf') {
    return (
      <iframe
        src={source.url}
        title={`Preview of ${file.name}`}
        className="h-96 w-full rounded-md border border-zinc-200 bg-white"
      />
    )
  }
  return (
    <img
      src={source.url}
      alt={`Preview of ${file.name}`}
      className="max-h-96 w-full rounded-md border border-zinc-200 bg-white object-contain"
    />
  )
}
