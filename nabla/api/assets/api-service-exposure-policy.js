// A presentation contract, not a second network probe or policy engine.
// /sickz remains the sole origin for outside-in exposure policy evidence.
const STATES = new Set(["ok", "warn", "fail", "unknown"]);

export function exposurePolicyPresentation(exposure, { cloudflareConfirmed = false } = {}) {
  const unknown = {
    state: "unknown",
    tone: "unknown",
    label: "Exposure ?",
    summary: "Exposure policy not verified",
    detail: "No current /sickz policy evidence; service reachability is a separate signal.",
  };
  if (!exposure || exposure.skipped === true || exposure.stale === true) {
    return unknown;
  }

  const external = exposure.external;
  const mode = exposure.tunnel_secure;
  const policy = STATES.has(exposure.policy_status)
    ? exposure.policy_status : "unknown";
  const publicHttpObserved = exposure.reachable === true;
  const unexpectedTunnel = external === false &&
    exposure.cloudflare_tunnel_observed === true;
  const unexpectedAccess = external === false &&
    exposure.cloudflare_access_observed === true;

  // A private service reached from outside, even with HTTP 401/403,
  // is a policy violation. A Cloudflare edge/Access response does not
  // prove that the protected origin was reached.
  if (external === false && (publicHttpObserved || unexpectedTunnel || unexpectedAccess)) {
    const reason = publicHttpObserved
      ? "A public HTTP endpoint answered the external observer; HTTP 401/403 does not make an internal-only endpoint private."
      : "A public Cloudflare route or Access application was observed for an internal-only service.";
    return {
      state: "fail", tone: "fail", label: "Exposure !",
      summary: "Unexpected public exposure", detail: reason,
    };
  }

  if (policy === "fail") {
    return {
      state: "fail", tone: "fail", label: "Exposure !",
      summary: "Exposure policy failed",
      detail: "The existing /sickz policy reported a failure. Check the separate HTTP, TLS, runtime and edge evidence for its cause.",
    };
  }

  // Internal services may only claim compliant privacy when an actual
  // outside-in probe supports it. A policy declaration is not evidence.
  if (external === false) {
    if (policy === "ok" && exposure.reachable === false) {
      return {
        state: "ok", tone: "ok", label: "Private OK",
        summary: "Internal-only policy observed compliant",
        detail: "external=false; the outside-in probe did not reach the declared endpoint. Other undeclared routes have not been scanned.",
      };
    }
    if (policy === "warn") {
      return {
        state: "warn", tone: "warn", label: "Privacy risk",
        summary: "Internal-only exposure needs review",
        detail: "The existing /sickz policy reported a warning; no confirmed public ingress was inferred.",
      };
    }
    return {
      ...unknown,
      summary: "Internal-only exposure not verified",
      detail: "external=false is a declaration, not proof that every public ingress path is closed.",
    };
  }

  if (external === true && mode === false) {
    return {
      state: "warn", tone: "warn", label: "Direct · Risk",
      summary: "Direct public exposure explicitly declared",
      detail: "tunnelSecure=false allows a direct Internet entry point. It is an acknowledged security debt, even when the service is available.",
    };
  }

  if (external === true && mode === true) {
    if (policy === "ok" && cloudflareConfirmed) {
      return {
        state: "ok", tone: "ok", label: "Protected",
        summary: "Cloudflare ingress policy verified",
        detail: "External exposure is declared behind a Tunnel and the existing /sickz policy verified its Access requirements. Not proof of application health.",
      };
    }
    if (policy === "warn") {
      return {
        state: "warn", tone: "warn", label: "Access review",
        summary: "Protected public exposure needs review",
        detail: "The /sickz policy reports a warning for the declared Cloudflare protected service.",
      };
    }
    return {
      ...unknown,
      summary: "Cloudflare policy verification incomplete",
      detail: "A declared Tunnel alone does not prove Access protection; Cloudflare control-plane evidence is incomplete or absent.",
    };
  }

  return {
    ...unknown,
    summary: "Public exposure security mode undeclared",
    detail: "The catalogue must explicitly declare whether external access uses Cloudflare Tunnel/Access or an approved direct exception.",
  };
}
