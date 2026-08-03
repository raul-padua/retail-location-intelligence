/** Presentation palette for archetype ids. Not an analytical input. */

const PALETTE = [
  "#0f766e",
  "#b45309",
  "#1d4ed8",
  "#7c3aed",
  "#be123c",
  "#047857",
  "#c2410c",
  "#0369a1",
] as const;

export function colorForCluster(clusterId: string | null | undefined): string {
  if (!clusterId) return "#64748b";
  const digits = clusterId.replace(/\D/g, "");
  const index = Math.max(0, (Number.parseInt(digits, 10) || 1) - 1);
  return PALETTE[index % PALETTE.length];
}
