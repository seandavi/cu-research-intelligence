import { Component, type ErrorInfo, type ReactNode } from "react";

// Isolates a subtree that may throw during render (e.g. a canvas/WebGL
// visualization that fails under a headless renderer, an old browser, or
// assistive tech). Without this, one throwing child unmounts the whole page —
// which is exactly why /networks rendered blank: react-force-graph crashed and
// took the accessible bridge-investigators table down with it. The fallback
// keeps the surrounding text content readable.
export class ErrorBoundary extends Component<
  { children: ReactNode; fallback?: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Non-fatal: the page still shows its text view. Log for diagnostics.
    console.error("Visualization failed to render:", error, info.componentStack);
  }

  render() {
    if (this.state.failed) {
      return (
        this.props.fallback ?? (
          <div className="error">The interactive view couldn’t be displayed.</div>
        )
      );
    }
    return this.props.children;
  }
}
