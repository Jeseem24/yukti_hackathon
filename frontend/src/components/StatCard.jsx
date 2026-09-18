/**
 * StatCard.jsx — Fleet summary stat card
 */
export default function StatCard({ label, value, sub, accentColor, icon: Icon }) {
  return (
    <div className="card stat-card">
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
        <span className="stat-label">{label}</span>
        {Icon && (
          <Icon
            size={18}
            style={{ color: accentColor || "var(--color-text-muted)", opacity: 0.7 }}
          />
        )}
      </div>
      <span
        className="stat-value"
        style={accentColor ? { color: accentColor } : undefined}
      >
        {value}
      </span>
      {sub && <span className="stat-sub">{sub}</span>}
    </div>
  );
}
