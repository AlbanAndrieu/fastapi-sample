// An unresponsive, skipped or unconfigured probe is not retirement evidence.
// An explicit lifecycle declaration or the Freebox cutover marks retirement.
export function isRetiredCheck(key, check) {
  const lifecycle = String(
    check?.lifecycle_state || check?.operational_state || "",
  )
    .trim()
    .toLowerCase();
  if (lifecycle === "retired") return true;
  return (
    key === "pfsense" &&
    check?.skipped === true &&
    /pfsense retired; freebox is the active network edge/i.test(
      String(check?.reason || ""),
    )
  );
}
