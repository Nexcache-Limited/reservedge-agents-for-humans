import { attr, escapeHtml } from "../html.js";

export const SIMULATION_BANNER_LABEL = "SIMULATED - NO REAL CHARGES OR RESERVATIONS";

export const SIMULATION_BANNER_PLACEMENTS = [
  "offers",
  "authorization",
  "receipt",
  "demo-shell",
] as const;
export type SimulationBannerPlacement = (typeof SIMULATION_BANNER_PLACEMENTS)[number];

export const SIMULATION_BANNER_DENSITIES = ["compact", "wide"] as const;
export type SimulationBannerDensity = (typeof SIMULATION_BANNER_DENSITIES)[number];

export interface SimulationBannerProps {
  label?: string;
  placement?: SimulationBannerPlacement;
  density?: SimulationBannerDensity;
}

export function simulationBannerHtml(props: SimulationBannerProps = {}): string {
  const label = props.label ?? SIMULATION_BANNER_LABEL;
  const placement = props.placement ?? "demo-shell";
  const density = props.density ?? "wide";

  return `<div class="itaa-simulation-banner itaa-simulation-banner--${density}" role="status"${attr("data-itaa-simulation", "true")}${attr("data-placement", placement)}${attr("data-density", density)}${attr("aria-label", label)}><p class="itaa-simulation-banner__label">${escapeHtml(label)}</p></div>`;
}
