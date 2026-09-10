# helm-sample

A Helm sample chart for Kubernetes.

## Security-first defaults

The default workload template is intended to render under Kubernetes Pod
Security Standards **Restricted** without a workload-specific exception.

Default controls include:

- non-root UID/GID;
- `seccompProfile: RuntimeDefault`;
- `privileged=false`;
- `allowPrivilegeEscalation=false`;
- read-only root filesystem;
- capability drop `ALL`;
- no host network/PID/IPC namespaces;
- no automatic ServiceAccount token mount;
- Kubernetes Service environment-link injection disabled;
- bounded writable `/tmp` through `emptyDir`;
- `ClusterIP` service and no Ingress by default.

When `podSecurityStandards.enforceRestricted=true`, Helm deliberately fails to
render if key Restricted/security-first invariants are weakened. Infrastructure
workloads that need privileged access should use a different purpose-built
chart/namespace rather than weakening this generic application profile.

### Namespace PSA labels

Namespace security policy is a platform concern and must be established before
the application release. The chart therefore does **not** create or mutate its
own release namespace.

A bootstrap example is provided at:

```text
charts/generic-service/examples/namespace-restricted.yaml
```

Apply or manage the equivalent policy through Terraform/GitOps before Helm:

```bash
kubectl apply -f charts/generic-service/examples/namespace-restricted.yaml

helm upgrade --install fastapi-sample charts/generic-service \
  --namespace fastapi-sample
```

The example labels the namespace with `enforce/audit/warn=restricted`. In a
controlled cluster, pin the PSS minor version and review it during Kubernetes
upgrades rather than leaving `latest` indefinitely.

### NetworkPolicy

`networkPolicy.enabled=false` by default until the target CNI is proven to
enforce Kubernetes NetworkPolicy and the workload's required flows have been
specified. When enabled with the default empty ingress/egress lists, the chart
creates a **true default-deny ingress+egress** policy.

Define only required allows for DNS, ingress-controller traffic, observability,
databases and external APIs before enabling it in an environment.

### Admission test

Do not stop at `helm template`. Render and test through the actual API
server/admission chain using server-side dry-run:

```bash
helm template fastapi-sample charts/generic-service \
  --namespace fastapi-sample > /tmp/fastapi-sample.yaml

kubectl apply --dry-run=server \
  --namespace fastapi-sample \
  -f /tmp/fastapi-sample.yaml
```

This validates the effective PSA/PSS and any Kyverno/Gatekeeper policies rather
than only local YAML syntax.

See `docs/kubernetes-zero-trust-hardening.md` for the wider Zero Trust roadmap.

## SOPS encrypted secrets

To inject SOPS-decrypted secrets from `secrets-enc.yaml` into the application:

1. Install [helm-secrets](https://github.com/jkroepke/helm-secrets).
2. Set `sopsSecrets.enabled: true` and adjust `sopsSecrets.keys`.
3. Install/upgrade with the encrypted file:
    `helm secrets upgrade --install <release> . -f values.yaml -f secrets-enc.yaml`.

The chart creates a Secret from those values and the Deployment loads it via
`envFrom`.

## Important security values

| Key | Default | Purpose |
| --- | --- | --- |
| `podSecurityStandards.enforceRestricted` | `true` | Fail rendering when core Restricted invariants are weakened |
| `podSecurityStandards.namespace.enforce` | `restricted` | Desired platform namespace enforcement posture |
| `serviceAccount.automount` | `false` | Avoid API credentials on the ServiceAccount |
| `pod.automountServiceAccountToken` | `false` | Avoid API credentials in the Pod |
| `pod.enableServiceLinks` | `false` | Reduce automatically injected service environment variables |
| `pod.hostNetwork` / `hostPID` / `hostIPC` | `false` | Prevent normal app access to host namespaces |
| `securityContext.allowPrivilegeEscalation` | `false` | PSS Restricted control |
| `securityContext.readOnlyRootFilesystem` | `true` | Minimize writable container surface |
| `securityContext.capabilities.drop` | `[ALL]` | Remove Linux capabilities |
| `service.type` | `ClusterIP` | Avoid node-level exposure by default |
| `ingress.enabled` | `false` | Require explicit external exposure |
| `networkPolicy.enabled` | `false` | Enable explicit default-deny policy after CNI/allow rules are proven |
