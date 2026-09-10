# Kubernetes Zero Trust deployment hardening roadmap

Last updated: 2026-09-10.

Target: make `charts/generic-service` and the Kubernetes deployment examples
**PSS Restricted-compatible by default**, while keeping explicit documented
exceptions for infrastructure workloads that cannot satisfy Restricted.

Reference:

- <https://blog.stephane-robert.info/docs/securiser/kubernetes/>
- Kubernetes Pod Security Standards / Pod Security Admission documentation
- Talos default hardening and CIS guidance

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
