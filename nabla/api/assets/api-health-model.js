const HEALTH_MODEL_AXES = [
  ["service_state", "service"],
  ["transport_state", "transport"],
  ["authentication_state", "auth"],
  ["application_state", "app"],
  ["runtime_state", "runtime"],
  ["dependency_state", "deps"],
  ["effective_state", "effective"],
];

const HEALTH_STATES = new Set(["ok", "warn", "fail", "unknown"]);

function healthState(value) {
  const normalized = String(value || "").trim().toLowerCase();
  return HEALTH_STATES.has(normalized) ? normalized : "unknown";
}

function axisValue(source, field, { allowTopLevel = true } = {}) {
  const nested =
    source?.health_model && typeof source.health_model === "object"
      ? source.health_model[field]
      : null;
  if (nested != null) return healthState(nested);
  return allowTopLevel ? healthState(source?.[field]) : "unknown";
}

export function mergeHealthModelEvidence(check, evidence) {
  if (!check || !evidence) return;
  const merged = {};
  for (const [field] of HEALTH_MODEL_AXES) {
    const allowTopLevel = field !== "runtime_state";
    const current = axisValue(check, field, { allowTopLevel });
    const observed = axisValue(evidence, field, { allowTopLevel });
    const value = current !== "unknown" ? current : observed;
    merged[field] = value;
    // runtime_state already has a legacy raw provider meaning (RUNNING/STOPPED).
    if (field !== "runtime_state") check[field] = value;
  }
  check.health_model = merged;
}

export function healthModelDetailText(check) {
  const model =
    check?.health_model && typeof check.health_model === "object"
      ? check.health_model
      : null;
  if (!model) return "";

  const states = HEALTH_MODEL_AXES.map(([field, label]) => [
    label,
    healthState(model[field]),
  ]);
  const needsExplanation = states.some(
    ([label, state]) =>
      label !== "effective" && (state === "warn" || state === "fail"),
  );
  const effective = healthState(model.effective_state);
  if (!needsExplanation && effective === "ok") return "";

  return (
    "health: " +
    states.map(([label, state]) => label + "=" + state).join(" · ")
  );
}
