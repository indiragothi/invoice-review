import { Component } from 'react'
import type { ErrorInfo, ReactNode } from 'react'

interface State {
  error: Error | null
}

/** Last resort: a render bug shows a message and a reload button, not a blank page. */
export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Screen crashed', error, info.componentStack)
  }

  render() {
    if (this.state.error === null) return this.props.children
    return (
      <main className="mx-auto max-w-xl p-8">
        <div role="alert" className="space-y-3 rounded-lg border border-red-200 bg-red-50 p-5">
          <h1 className="text-lg font-semibold text-red-800">Something went wrong on this screen</h1>
          <p className="text-sm text-zinc-700">{this.state.error.message}</p>
          <p className="text-sm text-zinc-600">
            Your saved reviews are safe on the server. Reload to continue.
          </p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="rounded-md bg-indigo-600 px-3.5 py-2 text-sm font-medium text-white hover:bg-indigo-700"
          >
            Reload
          </button>
        </div>
      </main>
    )
  }
}
