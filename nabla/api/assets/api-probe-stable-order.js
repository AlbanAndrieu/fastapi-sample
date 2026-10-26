// Avoid self-triggered MutationObserver/rAF loops in service cards.
// DOM appendChild() on an already attached node is NOT a harmless render:
// it moves the node and emits childList mutations, even when order is stable.
export function reorderProbeNodesIfNeeded(strip, probes, order) {
  const desired = [...probes].sort(
    (left, right) =>
      (order.get(left.dataset.probeKind) ?? 99) -
      (order.get(right.dataset.probeKind) ?? 99),
  );
  if (desired.every((probe, index) => probe === probes[index])) return false;
  // One intentional batch. The next observer pass sees correct order and
  // performs no further DOM writes.
  for (const probe of desired) strip.appendChild(probe);
  return true;
}
