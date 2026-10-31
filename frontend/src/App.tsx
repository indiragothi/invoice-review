import { BackendStatus } from './components/BackendStatus.tsx'

export default function App() {
  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center gap-6 p-8">
      <header>
        <p className="text-sm font-medium text-indigo-600">Mehta &amp; Associates</p>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight">Invoice Review</h1>
        <p className="mt-2 text-zinc-600">
          Upload a client&apos;s GST invoice or receipt and get a prepared review.
        </p>
      </header>
      <BackendStatus />
    </main>
  )
}
