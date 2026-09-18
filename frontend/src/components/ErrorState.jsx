/**
 * ErrorState.jsx - Error display with retry button
 * Palette: Blueberry (#6B7A8F), Apricot (#F7882F), Citrus (#F7C331), Apple Core (#DCC7AA)
 */
import { AlertTriangle, RefreshCw } from "lucide-react";

export default function ErrorState({ message, onRetry, fullHeight = false }) {
  return (
    <div
      className="state-center"
      style={fullHeight ? { flex: 1, minHeight: 280 } : {}}
    >
      <AlertTriangle
        size={36}
        style={{ color: "var(--apricot)" }}
      />
      <span className="state-title">Something went wrong</span>
      <span className="state-body">
        {message || "Failed to load telemetry. Please verify that the backend server is reachable."}
      </span>
      {onRetry && (
        <button
          type="button"
          className="btn-soft"
          onClick={onRetry}
          style={{ marginTop: 8, color: "var(--citrus)", borderColor: "var(--c-highlight-border)" }}
        >
          <RefreshCw size={14} />
          <span>Retry Connection</span>
        </button>
      )}
    </div>
  );
}
