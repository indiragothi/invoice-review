import { BackendStatus } from './BackendStatus.tsx'
import { Button } from './ui/Button.tsx'
import { Card } from './ui/Card.tsx'

export function WelcomeScreen({ onStart, onInbox }: { onStart: () => void; onInbox: () => void }) {
  return (
    <div className="mx-auto flex min-h-[70vh] max-w-2xl flex-col justify-center gap-6">
      <header>
        <p className="text-sm font-medium text-indigo-600">Mehta &amp; Associates</p>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight">Invoice Review</h1>
        <p className="mt-2 text-zinc-600">
          Upload a client&apos;s GST invoice or receipt. The app reads it, checks it, suggests a
          ledger and flags what needs a human look. You decide.
        </p>
      </header>
      <Card>
        <ol className="list-decimal space-y-1 pl-5 text-sm text-zinc-700">
          <li>Pick the client and upload the file (PDF, PNG or JPG, up to 5 MB, 5 pages).</li>
          <li>Wait while it is read and checked.</li>
          <li>Review the fields against the page, fix anything wrong, choose the ledger.</li>
          <li>Approve or reject. Approved records can be exported.</li>
        </ol>
      </Card>
      <div className="flex gap-2">
        <Button onClick={onStart}>Upload a document</Button>
        <Button variant="secondary" onClick={onInbox}>
          Open inbox
        </Button>
      </div>
      <BackendStatus />
    </div>
  )
}
