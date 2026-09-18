/**
 * EquipmentSelector.jsx
 *
 * Sidebar-style equipment selector for the detail view.
 * Equipment list is always fetched dynamically — never hard-coded.
 * Fires onSelect(equipment_id) when user clicks a unit.
 */
import { useEffect, useState, useCallback } from "react";
import { Server, ChevronRight } from "lucide-react";
import { fetchEquipmentList } from "../api";
import { SkeletonLine } from "./LoadingState";
import SeverityBadge from "./SeverityBadge";

export default function EquipmentSelector({
  selected,
  onSelect,
  healthMap = {},  // equipment_id → health object (optional, from parent)
}) {
  const [equipment, setEquipment] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await fetchEquipmentList();
      setEquipment(list);
      // Auto-select first if nothing selected
      if (!selected && list.length > 0) onSelect(list[0]);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);  // eslint-disable-line

  useEffect(() => { load(); }, [load]);

  if (loading) {
    return (
      <div style={{ padding: "12px 16px", display: "flex", flexDirection: "column", gap: 10 }}>
        {[1, 2, 3].map((k) => <SkeletonLine key={k} height="36px" />)}
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: "12px 16px", fontSize: 12, color: "var(--color-warning)" }}>
        Failed to load equipment list
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2, padding: "4px 0" }}>
      {equipment.map((id) => {
        const h = healthMap[id];
        const isSelected = selected === id;
        return (
          <div
            key={id}
            onClick={() => onSelect(id)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              padding: "9px 16px",
              cursor: "pointer",
              background: isSelected ? "var(--color-accent-dim)" : "transparent",
              borderLeft: `2px solid ${isSelected ? "var(--color-accent)" : "transparent"}`,
              transition: "background 0.12s, border-color 0.12s",
            }}
            onMouseEnter={(e) => {
              if (!isSelected) e.currentTarget.style.background = "var(--color-bg-hover)";
            }}
            onMouseLeave={(e) => {
              if (!isSelected) e.currentTarget.style.background = "transparent";
            }}
          >
            <Server size={13} style={{ color: isSelected ? "var(--color-accent)" : "var(--color-text-muted)", flexShrink: 0 }} />
            <span style={{
              fontSize: 13,
              fontWeight: 600,
              fontFamily: "var(--font-mono)",
              color: isSelected ? "var(--color-accent)" : "var(--color-text-secondary)",
              flex: 1,
              letterSpacing: "0.02em",
            }}>
              {id}
            </span>
            {h && <SeverityBadge severity={h.status} showDot={false} />}
            {isSelected && <ChevronRight size={12} style={{ color: "var(--color-accent)", flexShrink: 0 }} />}
          </div>
        );
      })}
    </div>
  );
}
