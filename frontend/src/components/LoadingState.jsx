/**
 * LoadingState.jsx - Loading animation & skeleton
 * Palette: Blueberry (#6B7A8F), Apricot (#F7882F), Citrus (#F7C331), Apple Core (#DCC7AA)
 */
export function SkeletonLine({ width = "100%", height = "14px", style }) {
  return (
    <div
      className="loading-skeleton"
      style={{ width, height, borderRadius: 4, ...style }}
    />
  );
}

export function SkeletonCard({ height = 120 }) {
  return (
    <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: "var(--radius-md)", padding: 16, height, display: "flex", flexDirection: "column", gap: 10 }}>
      <SkeletonLine width="40%" height="12px" />
      <SkeletonLine width="60%" height="24px" />
      <SkeletonLine width="80%" height="12px" />
    </div>
  );
}

export function LoadingSpinner({ size = 26 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      style={{ animation: "spin 0.8s linear infinite" }}
    >
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      <circle
        cx="12" cy="12" r="10"
        stroke="rgba(220, 199, 170, 0.15)"
        strokeWidth="3"
      />
      <path
        d="M12 2a10 10 0 0 1 10 10"
        stroke="var(--citrus)"
        strokeWidth="3"
        strokeLinecap="round"
      />
    </svg>
  );
}

export default function LoadingState({ message = "Loading...", fullHeight = false }) {
  return (
    <div
      className="state-center"
      style={fullHeight ? { flex: 1, minHeight: 280 } : {}}
    >
      <LoadingSpinner size={32} />
      <span className="state-title">{message}</span>
    </div>
  );
}
