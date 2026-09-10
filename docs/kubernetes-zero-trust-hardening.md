# Kubernetes Zero Trust deployment hardening roadmap

Last updated: 2026-09-10.

Target: make `charts/generic-service` and the Kubernetes deployment examples
**PSS Restricted-compatible by default**, while keeping explicit documented
exceptions for infrastructure workloads that cannot satisfy Restricted.

Publication acceptance follows `scripts/agent-quality-gate.sh`; formatter or
linter rewrites must be committed and the gate rerun until a clean pass.

Reference:

- <https://blog.stephane-robert.info/docs/securiser/kubernetes/>
- Kubernetes Pod Security Standards / Pod Security Admission documentation
- Talos default hardening and CIS guidance

## Hardening strategy

The design principle is **deny implicit privilege, make every trust transition
explicit, and preserve a functional recovery path**. `generic-service` models a
normal application workload, not a privileged infrastructure component. It must
therefore remain compatible with PSS `Restricted` without per-workload
exceptions. CSI, CNI, eBPF/runtime-security agents or other node-level workloads
that genuinely require privilege belong in dedicated infrastructure namespaces
with their own purpose-built manifests, RBAC and documented exception.

Hardening is applied in layers so a failure in one control does not silently
become a full-cluster compromise:

1. **Reduce the starting attack surface** — run as non-root, remove Linux
   capabilities, deny privilege escalation, use `RuntimeDefault` seccomp, make
   the root filesystem read-only, bound writable scratch space, and prevent host
   namespace access.
2. **Reduce identity exposure** — do not mount a ServiceAccount token unless the
   application actually calls the Kubernetes API; separate human, CI/CD,
   observer and workload identities rather than sharing broad credentials.
3. **Reduce network reachability** — expose only a `ClusterIP` by default and
   make Ingress an explicit environment decision. Once CNI enforcement is
   proven, move application namespaces to default-deny ingress/egress and allow
   only DNS plus required ingress, storage, observability, database and external
   API flows.
4. **Make unsafe manifests fail before deployment** — keep Helm security
   invariants fail-closed and exercise rendered manifests through server-side
   dry-run so the real API-server PSA and policy-as-code admission chain is
   tested, not just YAML syntax.
5. **Control what is allowed to enter the cluster** — introduce Kyverno first
   in audit/report mode, or Gatekeeper where Rego reuse is justified, then move
   proven policies to enforcement. Add immutable-image, resource, PSS,
   NetworkPolicy and later signature/provenance controls.
6. **Protect the software supply chain** — prefer digest-pinned production
   images, generate SBOMs, scan code/dependencies/images/IaC, and sign/verify
   artifacts with Sigstore/Cosign before admission-time provenance becomes a
   blocking control.
7. **Assume prevention can fail** — use Kubernetes audit/admission evidence and
   runtime detection such as Falco. If a later Cilium migration is justified,
   use Hubble for network-flow evidence and evaluate Tetragon for eBPF runtime
   visibility/selective enforcement.
8. **Continuously prove the posture** — keep Restricted rendering, admission,
   network isolation, runtime signals and rollback/recovery paths in automated
   regression tests. A control is not considered effective merely because its
   object exists; for example, a NetworkPolicy is only a security boundary once
   the selected CNI has been proven to enforce it.

The intended defense model is:

```text
Prevent / minimize
  Talos + RBAC + PSS/PSA + NetworkPolicy + Kyverno/Gatekeeper + supply chain
                                |
                                v
Detect
  Kubernetes audit/admission + Falco (+ Tetragon if Cilium is adopted)
                                |
                                v
Observe / respond / recover
  Prometheus/Grafana + network-flow evidence + SIEM + tested rollback
```

This sequencing deliberately avoids installing many security products before
basic isolation is proven. Every additional component must close a documented
capability gap and produce actionable evidence rather than only increasing tool
count or cluster privilege.

## Security-first deployment contract

- [x] default application containers to non-root execution;
- [x] `allowPrivilegeEscalation=false`;
- [x] `privileged=false`;
- [x] read-only root filesystem with bounded writable `/tmp`;
- [x] `seccompProfile: RuntimeDefault`;
- [x] capability drop `ALL`;
- [x] disable host network/PID/IPC namespaces;
- [x] disable unnecessary ServiceAccount token automounting;
- [x] disable automatic Kubernetes Service environment-link injection;
- [x] default Service exposure to internal-only `ClusterIP` and keep Ingress
  disabled until explicitly enabled by an environment;
- [x] fail Helm rendering when the Restricted defaults are weakened while
  `podSecurityStandards.enforceRestricted=true`;
- [x] provide an explicit pre-Helm Namespace bootstrap manifest with
  `enforce/audit/warn=restricted` rather than mutating the release namespace
  from the application chart;
- [x] provide configurable NetworkPolicy rendering with real default-deny
  semantics when enabled;
- [x] add static contract tests for the Restricted defaults, bootstrap manifest
  and fail-closed NetworkPolicy template;
- [ ] run Helm lint/rendering plus `kubectl apply --dry-run=server` against the
  Talos cluster and require zero PSS Restricted violations before using the
  chart for the Kubernetes FastAPI smoke workload;
- [ ] enable NetworkPolicy only after the cluster CNI enforcement path is proven
  and explicit DNS/ingress/observability/database/API egress allows are defined;
- [ ] pin critical/production images by digest and retain semantic version
  metadata for operators;
- [ ] generate SBOMs, scan with Trivy/Grype, sign with Sigstore/Cosign and later
  evaluate admission-time signature/provenance verification.

## Cluster hardening roadmap

- [ ] keep Talos' immutable/minimal OS security posture and continuously prove
  API server, etcd mTLS, Secret encryption-at-rest, kubelet authentication,
  certificate rotation, audit logging and seccomp defaults;
- [ ] converge normal application namespaces from Talos' default
  `enforce=baseline` to **`enforce=restricted`** where functional;
- [ ] inventory and document every privileged namespace; CSI/CNI/runtime
  security exceptions must remain namespace-scoped with tightly restricted RBAC;
- [ ] audit cluster-admin bindings and separate human, CI/CD, observer and
  workload identities;
- [ ] evaluate Kubescape/kube-bench for CIS/posture assurance with Talos-aware
  interpretation;
- [ ] evaluate **Kyverno first** for Kubernetes-native policy-as-code,
  PolicyReports, mutation/generation and image verification;
- [ ] keep **OPA Gatekeeper** as the alternative when Rego/OPA reuse is a
  stronger requirement; do not run both admission engines without a concrete
  need;
- [ ] introduce the selected engine in Audit/report-only mode before Enforce;
- [ ] require policies for immutable image references, resource limits,
  Restricted securityContext, no unnecessary SA token, forbidden host access
  and mandatory NetworkPolicy where appropriate.

## Network and runtime security

Falco is a runtime security/detection component, not a replacement for
NetworkPolicy.

- [ ] prove Kubernetes NetworkPolicy enforcement on the current Talos/Flannel
  cluster, then apply default-deny ingress/egress to representative application
  namespaces;
- [ ] explicitly allow DNS, ingress controller, storage, Prometheus/telemetry and
  required application dependencies;
- [ ] evaluate Cilium only after current CSI/network acceptance is stable; use
  the evaluation to decide whether identity-aware/L7 policy justifies a CNI
  migration;
- [ ] evaluate Hubble with Cilium for network-flow observability;
- [ ] evaluate **Falco** for portable syscall/container runtime detection and
  forward high-signal events into the existing SIEM/observability path;
- [ ] if Cilium is selected, evaluate **Tetragon** for eBPF runtime visibility
  and selective enforcement;
- [ ] compare NeuVector only if PSA/PSS + NetworkPolicy + the selected admission
  engine + Falco/Tetragon leave a justified capability gap.

## Zero Trust implementation order

1. Talos/Kubernetes trust root and control-plane hardening.
2. Identity/RBAC and ServiceAccount minimization.
3. PSS/PSA Restricted-by-default application posture.
4. NetworkPolicy default-deny with tested allow paths.
5. Secrets/workload identity and rotation.
6. Kyverno (preferred first candidate) or Gatekeeper policy-as-code.
7. Supply-chain controls: SBOM, scanning, digest pinning, signatures/provenance.
8. Falco runtime detection; Hubble/Tetragon if Cilium is adopted.
9. Continuous assurance through audit events, Prometheus/Grafana, SIEM and
   recurring admission/network/security regression tests.
