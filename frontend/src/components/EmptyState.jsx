/**
 * EmptyState.jsx - Clean empty state display
 * Palette: Blueberry (#6B7A8F), Apricot (#F7882F), Citrus (#F7C331), Apple Core (#DCC7AA)
 */
import { Inbox, RotateCcw } from "lucide-react";

export default function EmptyState({ icon: Icon, title, body, actionLabel, onAction, fullHeight = false }) {
  const Ic = Icon || Inbox;
  return (
    <div
      className="state-center"
      style={fullHeight ? { flex: 1, minHeight: 260 } : {}}
    >
      <Ic size={36} className="state-icon" style={{ color: "var(--blueberry)" }} />
      <span className="state-title">{title || "No data recorded"}</span>
      {body && <span className="state-body">{body}</span>}
      {actionLabel && onAction && (
        <button
          type="button"
          className="btn-soft"
          onClick={onAction}
          style={{ marginTop: 8, color: "var(--citrus)" }}
        >
          <RotateCcw size={14} />
          <span>{actionLabel}</span>
        </button>
      )}
    </div>
  );
}
