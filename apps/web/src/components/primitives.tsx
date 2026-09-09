import type { ButtonHTMLAttributes, ReactNode } from "react";
import { SIMULATION_BANNER_LABEL } from "../fixtures/golden.js";

export function Text({
  role = "body",
  as: Tag = "p",
  children,
}: {
  role?: "display" | "heading" | "body" | "label" | "meta" | "fact";
  as?: "p" | "h1" | "h2" | "h3" | "span" | "legend";
  children: ReactNode;
}) {
  return <Tag className={`itaa-text itaa-text--${role}`}>{children}</Tag>;
}

export function Surface({
  children,
  padding = "lg",
  raised = false,
}: {
  children: ReactNode;
  padding?: "sm" | "md" | "lg" | "xl";
  raised?: boolean;
}) {
  const elevation = raised ? " itaa-surface--raised" : "";
  return (
    <section className={`itaa-surface itaa-surface--pad-${padding}${elevation}`}>
      {children}
    </section>
  );
}

export function Button({
  variant = "primary",
  busy = false,
  disabledReason,
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "consent" | "ghost" | "destructive";
  busy?: boolean;
  disabledReason?: string | undefined;
}) {
  const disabled = props.disabled === true || busy;
  if (disabledReason !== undefined && props.id === undefined) {
    throw new Error("Button disabledReason requires id");
  }
  if (disabledReason !== undefined && !disabled) {
    throw new Error("Button disabledReason may be supplied only when disabled or busy");
  }
  const reasonId =
    disabledReason !== undefined && props.id !== undefined ? `${props.id}-reason` : undefined;
  return (
    <>
      <button
        {...props}
        type={props.type ?? "button"}
        className={`itaa-button itaa-button--${variant} itaa-focus-ring`}
        disabled={disabled}
        aria-disabled={disabled}
        aria-busy={busy || undefined}
        aria-describedby={reasonId}
        data-variant={variant}
        data-state={busy ? "busy" : disabled ? "disabled" : "default"}
      >
        <span className="itaa-button__label">{children}</span>
        {busy ? <span className="itaa-visually-hidden">Working</span> : null}
      </button>
      {disabledReason !== undefined && reasonId !== undefined ? (
        <span id={reasonId} className="itaa-visually-hidden">
          {disabledReason}
        </span>
      ) : null}
    </>
  );
}

export function StatusIndicator({
  variant,
  label,
}: {
  variant: "neutral" | "working" | "attention" | "confidence" | "denial" | "offline";
  label: string;
}) {
  return (
    <span className={`itaa-status itaa-status--${variant}`} role="status" data-variant={variant}>
      <span className="itaa-status__swatch" aria-hidden="true" />
      <span className="itaa-status__label">{label}</span>
    </span>
  );
}

export function SimulationBanner({
  placement = "demo-shell",
  density = "wide",
}: {
  placement?: "offers" | "authorization" | "receipt" | "demo-shell";
  density?: "compact" | "wide";
}) {
  return (
    <div
      className={`itaa-simulation-banner itaa-simulation-banner--${density}`}
      role="status"
      data-itaa-simulation="true"
      data-placement={placement}
      aria-label={SIMULATION_BANNER_LABEL}
    >
      <p className="itaa-simulation-banner__label">{SIMULATION_BANNER_LABEL}</p>
    </div>
  );
}

export function LiveRegion({
  message,
  politeness = "polite",
}: {
  message: string;
  politeness?: "polite" | "assertive";
}) {
  return (
    <div
      className="itaa-live-region itaa-visually-hidden"
      role="status"
      aria-live={politeness}
      aria-atomic="true"
    >
      {message}
    </div>
  );
}

export function VisuallyHidden({ children, id }: { children: ReactNode; id?: string }) {
  return (
    <span id={id} className="itaa-visually-hidden">
      {children}
    </span>
  );
}
