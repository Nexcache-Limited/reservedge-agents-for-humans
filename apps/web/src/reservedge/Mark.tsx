export function ReservedgeMark({ size = 28, label }: { size?: number; label?: string }) {
  const radius = size >= 32 ? 10 : size >= 28 ? 9 : 10;
  return (
    <span
      className="re-mark"
      style={{ width: size, height: size, borderRadius: radius }}
      aria-hidden={label ? undefined : true}
      aria-label={label}
    >
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <path d="M11 3.2H5.6v9.6H11" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" />
        <circle cx="12.7" cy="8" r="1.5" fill="#fff" />
      </svg>
    </span>
  );
}

export function SimChip({ tone = "rail" }: { tone?: "rail" | "light" }) {
  return (
    <span className={`re-sim re-sim--${tone}`} title="Simulation mode">
      SIM
    </span>
  );
}
