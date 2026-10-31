import { Component, type ErrorInfo, type ReactNode } from "react";

/** Last line of defence: a rendering bug shows a recoverable message, not a blank page. */
export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Unhandled UI error", error, info.componentStack);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <main className="fatal" role="alert">
        <h1>Something went wrong</h1>
        <p>The console hit an unexpected error. Reloading usually fixes it.</p>
        <button type="button" className="btn btn-primary" onClick={() => window.location.reload()}>
          Reload
        </button>
      </main>
    );
  }
}
