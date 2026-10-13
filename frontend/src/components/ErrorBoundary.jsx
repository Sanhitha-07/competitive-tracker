import { Component } from "react";

// If a tab fails while drawing, show a message instead of a blank page.
// The rest of the app (header, workspace picker, tabs) keeps working.
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error("Tab failed to render:", error, info?.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <section className="panel">
        <div className="empty" role="alert">
          <b>This page couldn't be shown</b>
          <span>
            Usually the API is running an older version. Close the API window, double-click backend\run_api.bat again,
            then click Try again.
          </span>
          <span className="muted small">Details: {String(this.state.error.message || this.state.error)}</span>
          <div className="center">
            <button className="btn primary small-btn" onClick={() => this.setState({ error: null })}>Try again</button>
          </div>
        </div>
      </section>
    );
  }
}
