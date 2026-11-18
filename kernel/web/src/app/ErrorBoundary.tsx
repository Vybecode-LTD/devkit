/**
 * Catches a part that fails to draw, so the rest of the page stays. Each
 * slot entry has its own (K4 contract §2); the router has `RouteError` for a
 * whole page.
 */
import { Component, type ErrorInfo, type ReactNode } from "react";

type Props = {
  children: ReactNode;
  /** What failed, for the console: "blog's part of site.footer". */
  where: string;
  /** What shows instead; a short line with a way to try again by default. */
  fallback?: (retry: () => void) => ReactNode;
  /** Called on Try again, before drawing the part again: a parent that made it may make it anew. */
  onRetry?: () => void;
};

type State = { failed: boolean };

export class ErrorBoundary extends Component<Props, State> {
  override state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  override componentDidCatch(error: unknown, info: ErrorInfo): void {
    console.error(`${this.props.where} failed to show.`, error, info.componentStack);
  }

  retry = (): void => {
    this.props.onRetry?.();
    this.setState({ failed: false });
  };

  override render(): ReactNode {
    if (!this.state.failed) return this.props.children;
    if (this.props.fallback) return this.props.fallback(this.retry);
    return (
      <div role="status" className="mf-part-failed">
        This part didn't load.{" "}
        <button type="button" onClick={this.retry}>
          Try again
        </button>
      </div>
    );
  }
}
