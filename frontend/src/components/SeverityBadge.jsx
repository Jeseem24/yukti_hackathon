/**
 * SeverityBadge.jsx
 * Renders a consistent severity badge using the design system.
 * severity prop: "Normal" | "Watch" | "Warning" | "Critical"
 * Or pass a numeric score and let this component derive the label.
 */

const SEVERITY_THRESHOLDS = [
  { min: 0.75, label: "Critical" },
  { min: 0.55, label: "Warning" },
  { min: 0.35, label: "Watch" },
  { min: 0,    label: "Normal" },
];

export function scoreToSeverity(score) {
  for (const t of SEVERITY_THRESHOLDS) {
    if (score >= t.min) return t.label;
  }
  return "Normal";
}

export function severityClass(label) {
  switch (label) {
    case "Critical": return "severity-critical";
    case "Warning":  return "severity-warning";
    case "Watch":    return "severity-watch";
    default:         return "severity-normal";
  }
}

export function severityDotClass(label) {
  switch (label) {
    case "Critical": return "critical";
    case "Warning":  return "warning";
    case "Watch":    return "watch";
    default:         return "normal";
  }
}

export function severityColor(label) {
  switch (label) {
    case "Critical": return "var(--color-critical)";
    case "Warning":  return "var(--color-warning)";
    case "Watch":    return "var(--color-watch)";
    default:         return "var(--color-normal)";
  }
}

export default function SeverityBadge({ severity, score, showDot = true }) {
  const label = severity ?? (score !== undefined ? scoreToSeverity(score) : "Normal");
  return (
    <span className={`severity-badge ${severityClass(label)}`}>
      {showDot && <span className={`sev-dot ${severityDotClass(label)}`} />}
      {label}
    </span>
  );
}
