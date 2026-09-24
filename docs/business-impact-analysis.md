# Business Impact Analysis — fastapi-sample

Status: **provisional / to validate with operating evidence**

Assessment date: **2026-09-23**

Service: `fastapi-sample`

Canonical entity target: `component:default/fastapi-sample`

## 1. Purpose and business role

`fastapi-sample` is primarily a homelab **monitoring, exposure-control and security-assurance service**.

Its useful functions are:

- observe internal services and runtime dependencies;
- check selected internal/external HTTP, HTTPS and TCP paths;
- reconcile desired exposure intent with observed runtime/network state;
- identify unexpectedly exposed, unreachable or insufficiently protected endpoints;
- present security and operational evidence for TrueNAS, pfSense, Cloudflare and
  other homelab services.

The service is **not itself a critical business workload**. The underlying
security controls, firewalling, DNS, storage and administration paths must remain
usable without it.

This distinction is important: loss of `fastapi-sample` mainly reduces
visibility and automation. By contrast, an insecure or badly behaved
`fastapi-sample` instance can itself increase risk by exposing control paths,
holding privileged connectivity, or generating excessive probes against
TrueNAS/pfSense.

## 2. Initial BIA decision

| Measure | Initial value | Rationale |
| --- | --- | --- |
| Business criticality | **Low — provisional** | Service outage reduces monitoring and exposure assurance but does not stop the homelab or its core controls. |
| RTO | **7 days / `P7D` — owner-confirmed** | The homelab can be operated safely for seven days without FastAPI because important exposure checks can be performed manually. |
| MTPD / DIMA | **14 days / `P14D`** | More than two weeks without automated exposure/security drift visibility becomes an unacceptable blind spot. |
| Recovery margin | **7 days / 604800 s** | Difference between MTPD and RTO; preserves time for safe validation before the maximum tolerated disruption is reached. |
| RPO | **N/A / null — owner-confirmed** | No recovery of the runtime database is required. Runtime/cache/monitoring state is considered disposable and reconstructible. |
| MBCO / OMCA | **0% automated service is acceptable during recovery** | Manual checks of critical exposure/security controls are the fallback. The homelab must not depend on this service to continue operating safely. |
| BIA status | **Provisional** | RTO and no-database-backup assumptions are owner-confirmed; MTPD and safe probe-capacity thresholds still require operating evidence. |

The RTO remains deliberately lower than MTPD/DIMA. NIST contingency guidance
uses the same principle: recovery must be completed early enough that the
maximum tolerable downtime is not exceeded.


### Owner validation — 2026-09-23

The current operating assumptions have been reviewed with the service owner:

- **seven days without FastAPI is acceptable** because the important exposure
  checks can be performed manually;
- once the homelab is stabilized, **exposure changes are expected roughly once
  per week**, which is consistent with the current seven-day recovery target;
- the safe request capacity of **pfSense and TrueNAS is not yet known** and must
  not be inferred from the current protective rate limits;
- probe capacity must therefore be measured through Prometheus by correlating
  FastAPI origin-probe rate/latency/concurrency with TrueNAS and pfSense
  saturation/resource signals.

The BIA remains provisional because MTPD/DIMA and the safe probe envelope still
need measured operating evidence.

## 3. Data and backup position

### Runtime database

**No database backup is required for this service at present.**

The BIA therefore does not assign a conventional RPO to the runtime database.
A failed or corrupted runtime database may be discarded and rebuilt.

This assumption remains valid only while the database contains no
irreplaceable evidence, audit history or user-owned records.

If the service later becomes the system of record for historical security
evidence, incident records, approvals or configuration changes, the BIA must be
reopened and an explicit RPO/retention policy defined.

### Reconstructible sources

The following are expected to be recovered from declarative sources rather than
from a database backup:

- application source and deployment code from Git;
- declared service/catalog/topology intent from the canonical Nabla repository;
- deployment/runtime configuration from the approved configuration/secrets
  mechanisms;
- current service state by reprobe/reconciliation after recovery.

Secrets must not be reconstructed from application logs or historical runtime
state.

## 4. Impact of unavailability

### 0–24 hours

Expected impact: **low**.

- no automated health/exposure board;
- no automatic reconciliation between desired and observed exposure;
- manual checks are sufficient for important endpoints;
- underlying firewall, Cloudflare and TrueNAS controls continue independently.

### 1–7 days

Expected impact: **low to moderate**.

- increased chance of missing configuration drift or newly exposed endpoints;
- more manual effort to review pfSense, Cloudflare, TrueNAS and public services;
- reduced historical continuity of monitoring evidence.

This remains inside the target RTO.

### 7–14 days

Expected impact: **moderate**.

- the security visibility gap becomes material;
- exposure changes may remain unnoticed for too long;
- manual verification should be scheduled explicitly until recovery.

Recovery should normally complete during this period.

### Beyond 14 days

Expected impact: **unacceptable for the current operating model**.

The problem is not loss of application processing; it is the duration of the
security-assurance blind spot. At this point the service should either be safely
restored or formally replaced by another monitoring/exposure-assurance method.

## 5. Security and operational risk when the service is available

Business criticality and security risk are deliberately kept separate.

### Availability/business criticality

**Low.**

The service may remain unavailable for days without directly stopping the
homelab.

### Inherent security exposure risk

**High.**

Reasons include:

- it observes and reaches internal homelab services;
- it may test externally exposed administration or service endpoints;
- a vulnerability in the application or its authentication/exposure path could
  become a pivot toward internal infrastructure;
- a control endpoint exposed too broadly could provide unintended access to
  homelab operations;
- configuration or probe results may reveal sensitive topology, hostnames,
  ports or security posture.

### Resource-exhaustion / denial-of-service risk

**High until bounded by measured limits.**

The service has previously tended to generate enough activity to increase load
on **TrueNAS and pfSense**, including situations consistent with degraded
availability or denial of service.

Risk factors include:

- excessive fan-out across many probes;
- short probe intervals;
- multiple retries;
- concurrent HTTP/TCP/TLS checks;
- expensive pfSense API/webConfigurator requests;
- repeated external/security probes that trigger defensive tooling;
- duplicated checks from FastAPI Cloud, TrueNAS-local runtime and other
  monitoring systems.

An availability improvement to `fastapi-sample` must never be obtained by
making TrueNAS or pfSense less available.

## 6. Recovery strategy

Recovery is **safe-state first**, not speed first.

1. Keep `fastapi-sample` stopped or externally isolated if compromise,
   uncontrolled exposure or probe amplification is suspected.
2. Verify TrueNAS, pfSense, DNS and Cloudflare independently of
   `fastapi-sample`.
3. Rebuild/redeploy the application from trusted Git/IaC sources. Do not restore
   the runtime database.
4. Start in the least-privileged/read-only mode possible with:
   - control/mutation functions disabled unless explicitly required;
   - internal probe fan-out bounded;
   - conservative concurrency, retry and timeout settings;
   - pfSense API polling minimized;
   - no recurring disruptive SSH/banner/security scanning.
5. Validate resource consumption on TrueNAS and pfSense before enabling the full
   monitoring set.
6. Validate intended external exposure and authentication independently.
7. Re-enable public or privileged paths only after the service has demonstrated
   stable bounded behavior.

A recovery that reintroduces unsafe WAN exposure, privileged access or
resource-exhaustion behavior is **not a successful recovery**, even if the API
is technically reachable inside the seven-day RTO.

## 7. Minimum Business Continuity Objective (MBCO / OMCA)

During the recovery window, the acceptable minimum capability is:

> **No automated fastapi-sample service is required, provided critical exposure
> and administrative paths can be checked manually and the underlying homelab
> security controls remain independent and operational.**

Manual fallback should cover, at minimum:

- verify pfSense WAN/LAN policy and administration exposure;
- verify Cloudflare Tunnel/Access policy for intended public services;
- verify TrueNAS management exposure;
- verify that obviously sensitive SSH/API administration paths remain blocked
  from untrusted sources;
- review critical services directly when a security incident or configuration
  change occurs.

## 8. Dependencies and anti-dependencies

### Dependencies of fastapi-sample

Depending on deployment mode, the service may consume evidence from:

- TrueNAS;
- pfSense;
- Cloudflare;
- Prometheus/observability systems;
- DNS/network connectivity;
- the canonical Nabla service catalog/topology.

Failure of those dependencies may degrade monitoring evidence.

### Anti-dependency requirement

**TrueNAS, pfSense, DNS, firewalling and core homelab administration must not
depend on fastapi-sample to remain available.**

The monitoring service must therefore avoid becoming:

- a required DNS resolver;
- a required reverse proxy for core administration;
- a mandatory control plane for TrueNAS/pfSense;
- a component whose probe load is necessary for normal platform operation.

## 9. Recovery acceptance criteria

The service is considered recovered only when all of the following are true:

- application starts from a trusted immutable source;
- no database restore is required;
- authentication/exposure policy matches the intended architecture;
- internal and external probes are bounded and fail safely;
- pfSense and TrueNAS resource consumption remains within their normal operating
  range during observation;
- failed/timeout probes do not create uncontrolled retries or fan-out;
- the service cannot turn loss of telemetry into a false-green security result;
- control operations, if any, are explicitly authenticated and least-privileged;
- stopping fastapi-sample does not remove core homelab connectivity or security
  controls.

## 10. How to validate the current BIA values

### RTO — 7 days, owner-confirmed

The service owner confirms that the homelab can be operated safely for seven
days without this dashboard because important exposure checks can be performed
manually. Exposure changes are expected approximately weekly once the homelab
is stabilized.

Reassess this RTO if the exposure-change cadence increases, manual verification
becomes materially harder, or fastapi-sample becomes the only source of a
critical security signal.

### MTPD / DIMA — proposed 14 days

Ask:

- After how many days without automatic exposure checks would the visibility
  gap become unacceptable?
- Would a fortnight without this service require compensating manual controls?
- Is there another independent tool that provides equivalent coverage?

If independent monitoring already provides equivalent assurance, MTPD may be
increased. If this service becomes the only reliable exposure monitor, MTPD
should decrease.

### RPO — currently N/A

Reassess only when answering **yes** to one of these:

- Does the database contain evidence that cannot be reproduced?
- Does it hold security incident history needed for investigations?
- Does it become the authoritative source of configuration or approvals?
- Would losing all database contents create a business/security impact?

Until then, database restore adds complexity without improving the stated
recovery objective.

### MBCO

Validate that the manual fallback is genuinely possible. A useful exercise is to
stop `fastapi-sample` for a planned maintenance window and verify the critical
exposure posture using pfSense, Cloudflare and TrueNAS directly.

## 11. Metrics to collect before the next BIA review

Record these for several weeks:

- time needed to redeploy a clean instance from Git;
- time needed to perform the manual exposure checklist;
- number of meaningful security/exposure findings produced by the service;
- maximum period between meaningful exposure/configuration changes;
- provider-specific origin-probe rate and concurrency generated toward TrueNAS
  and pfSense;
- provider-specific origin-probe duration distribution and p95/p99 latency;
- provider rate-budget utilization and rejection count;
- timeout/retry counts;
- TrueNAS CPU/memory/load change attributable to probes;
- pfSense CPU/PHP-FPM/request pressure attributable to probes;
- correlation between FastAPI probe volume/latency and TrueNAS/pfSense
  saturation, with Prometheus used to determine the safe operating envelope;
- number of false-positive or redundant probes;
- number of external/public endpoints whose posture is only visible through this
  service.

These measurements should drive the next RTO/MTPD review rather than an
availability target chosen only from intuition.

## 12. Initial risk/continuity conclusion

The current target is intentionally asymmetric:

- **restore availability within 7 days**;
- **do not tolerate more than 14 days without equivalent security-assurance
  coverage**;
- **do not back up/restore the runtime database**;
- **accept 0% automated service during recovery** when manual checks remain
  available;
- treat **compromise, excessive exposure and probe-induced DoS as higher risks
  than the temporary loss of fastapi-sample itself**.

This BIA should be migrated into the authoritative `nabla-compose` BIA/catalog
model during the planned direct catalog cutover. `fastapi-sample` should then
consume the authoritative business-criticality projection rather than calculate
its own score.

## References

- NIST SP 800-34 Rev. 1, *Contingency Planning Guide for Federal Information
  Systems*. NIST defines Maximum Tolerable Downtime, Recovery Time Objective and
  Recovery Point Objective and explains that RTO should normally remain below
  MTD.
- NIST contingency-planning guidance recommends using the BIA to identify
  supported business processes, dependencies, impacts and recovery priorities.
