# API diagnostics UI architecture

## Scope

The `/api` page remains the health-first operator view. It must not embed a network
or dependency graph. Interactive topology is a separate concern exposed through
`/api/topology`, with `/api/homelab-topology` remaining the machine-readable
contract.

The canonical declared topology still comes from `nabla-compose`. FastAPI may
classify, observe and present that topology, but presentation code must not become
a second source of infrastructure truth.

## Global service filter

`/api` has one page-wide service filter. Its visual scope must match its functional
scope: health results, exposure-policy rows and technical service drill-downs such
as TrueNAS are filtered through the same operator control.

The filter presentation follows the same interaction model as the homelab view on
`albanandrieu.com`: health-state summary buttons, explicit search/facets, reset and
expand/collapse controls, and a visible match count. FastAPI-specific probe and
exposure facets remain available because they represent evidence that the site
projection does not currently expose at the same depth.

The global filter is sticky while the operator scrolls. Secondary explanatory
content such as the probe legend must remain collapsible so the sticky surface does
not obscure the diagnostic results it controls, especially on mobile displays.

Filtering remains a single engine. Presentation helpers may synchronize controls,
move the filter shell or expose shortcuts, but they must not independently hide or
show service rows.

## Topology screen

The standalone topology screen uses Cytoscape.js because it provides a purpose-built
graph model, selectors, layouts, viewport interactions and graph algorithms without
introducing React.

Current constraints:

- load Cytoscape only on `/api/topology`;
- pin the external version and require Subresource Integrity;
- keep a visible link to the JSON topology if the optional renderer cannot load;
- reuse `analyzeTopology()` for role, criticality, dependency and blast-radius
  semantics instead of duplicating them in the renderer;
- reuse the same topology loader/fallback in the health grouping and topology
  screen;
- keep live health separate from declared topology until the declared view is
  stable;
- start with the **Dependencies** preset so functional dependencies are not mixed
  with routing/ingress edges by default;
- provide **Network paths** for canonical `routesTo` and `exposedBy` relations and
  **All relations** for structural, observability and automation edges as well;
- let an explicit relation filter override the preset rather than silently creating
  contradictory filters;
- expose canonical `runtime.provider`, `runtime.appId`,
  `runtime.containerService`, `lifecycle.phase` and `lifecycle.priority` as
  declared node context only. A lifecycle phase filter may select those declared
  nodes, but FastAPI must not derive or claim the operational TrueNAS start order;
  that ordering remains owned by the `nabla-compose` lifecycle planner, where
  required topology relations are authoritative over phase/priority;
- keep topology controls shareable through URL state (`q`, `view`, `relation`,
  `strength`, `phase`, `layout`) without storing operator state server-side;
- preserve unrelated query parameters and the URL hash while updating topology
  state;
- never infer trust/network zones from hostnames, URLs, service display names or
  categories. Add zones only after the canonical topology contract exposes
  reviewed zone metadata.

## Controlling frontend code growth

The current browser UI is deliberately framework-light, but repeated
`document.createElement()`, attribute mutation and append operations are becoming
a maintenance cost. Refactoring must remove maintained code or reduce measurable
complexity rather than only move boilerplate between modules.

### Candidate: standalone `lit-html`

`lit-html` is a credible candidate, but it is not yet an architectural decision.
The official Lit documentation explicitly supports using the template renderer
standalone, outside LitElement, with the small `html` and `render` API. That matches
this application better than introducing a component framework because the health
screen already has explicit JSON contracts and imperative data-fetching logic.

Research baseline as of 2026-09-11:

- current npm `lit-html` is 3.3.3, BSD-3-Clause, maintained in the `lit/lit`
  repository and widely depended upon;
- official standalone documentation supports installing `lit-html` separately and
  rendering into ordinary DOM containers without LitElement;
- Lit templates treat ordinary interpolated strings as text rather than parsing
  them as HTML, which provides a useful XSS-resistant default;
- Lit has supported Trusted Types integration since the 1.3 line;
- `unsafeHTML` and equivalent unsafe/static directives remain explicit trust
  boundaries and must never receive query strings, runtime service metadata or any
  other untrusted value;
- official production guidance recommends normal module bundling/minification and
  asset hashing. Rollup is the documented recommendation, although Lit does not
  require a specific bundler;
- the current `/api/assets` path has no frontend bundle step, so bare npm imports
  cannot simply be introduced into production browser modules without resolving
  or bundling them first.

Primary references:

- <https://lit.dev/docs/libraries/standalone-templates/>
- <https://lit.dev/docs/tools/production/>
- <https://lit.dev/docs/templates/directives/>
- <https://lit.dev/docs/v2/releases/release-notes/1.3.0/>
- <https://www.npmjs.com/package/lit-html>

### Pilot constraints and acceptance criteria

Do not add a public-CDN availability dependency to the `/api` health view. A pilot
must pin the npm dependency and produce a deterministic local asset at build time,
or use an equivalently reviewable vendoring mechanism. The optional Cytoscape
renderer is a different risk boundary because failure of `/api/topology` does not
remove the primary health operator screen.

A `lit-html` pilot should target exactly one high-churn renderer first, preferably
the probe-evidence strip or service-group summary. Accept it only when all of these
conditions hold:

- reduce maintained imperative DOM/rendering lines in the selected module by at
  least 25%;
- reduce or hold cyclomatic/cognitive complexity rather than hiding it in template
  callbacks;
- preserve existing JSON contracts, service-health semantics and topology
  classification;
- keep fetching, reconciliation, status policy and topology analysis outside the
  template layer;
- pin the exact dependency in the lockfile and keep dependency/SBOM/security
  scanning enabled;
- bundle or vendor the runtime locally; `/api` must still render when Internet/CDN
  access is unavailable;
- do not use `unsafeHTML`, `unsafeSVG`, `unsafeStatic` or equivalent directives for
  runtime/untrusted data;
- validate the resulting page under the existing CSP/Trusted Types direction and
  preserve safe text interpolation;
- preserve keyboard navigation, focus visibility, ARIA state and reduced-motion
  behavior;
- measure initial render plus refresh/update cost before and after the pilot;
- remove more maintained application code than the integration/build plumbing
  adds.

If the pilot does not meet these criteria, keep the current browser-native module
architecture and continue extracting pure data/policy helpers instead. Only
consider LitElement/Web Components after standalone templates demonstrate reuse
across several independent screens.

### Existing library to exploit: Jinja2

Jinja2 is already part of the application stack. Page shells that are mostly
static HTML should progressively move out of large Python f-strings and into Jinja
templates. This reduces Python module complexity without adding another runtime
dependency. Dynamic health and topology data should continue to arrive through
explicit API contracts.

### Alternatives considered

- **React / React Flow:** strong ecosystem, but it would introduce a second
  frontend application/runtime solely for diagnostics and duplicate capabilities
  now isolated to the optional Cytoscape topology view.
- **htmx:** small and effective for HTML-over-the-wire forms/CRUD, but using it for
  the current live health UI would require replacing established JSON rendering
  paths with server-rendered fragments. Re-evaluate for future server-owned forms.
- **Alpine.js:** useful for lightweight local state, but it addresses the large
  repeated rendering blocks less directly than declarative templates and adds CSP
  considerations for its expression evaluation model.
- **Preact:** substantially smaller than React, but still introduces a component
  runtime and state model that is unnecessary for a first rendering-only pilot.
- **smaller template libraries:** bundle size alone is not sufficient. Prefer the
  maintenance history, security documentation, Trusted Types support and ecosystem
  of Lit unless a measured payload budget proves that difference material.

## Presentation design sequence

Planning status belongs in `docs/engineering-roadmap.md`; this list records the UI
architecture sequence and acceptance boundaries.

1. Keep the page-wide sticky health filter consistent with the homelab site and
   add presentation-group/environment facets only from canonical topology/catalog
   metadata. Implemented by the health-filter work through PR #247.
2. Separate topology **Dependencies** and **Network paths** presets so functional
   dependencies and transport/ingress paths are not mixed by default. The focused
   presets use declared relation types only; structural/observability relations
   remain available through **All relations**. Implemented by PR #250.
3. Surface canonical runtime ownership and lifecycle phase/priority as declared
   node context, including a shareable lifecycle phase filter. Do not derive the
   canonical TrueNAS planner order in FastAPI. Implemented by PR #250 after
   `nabla-compose#191` merged.
4. Add compound trust/network zones only when the topology contract can identify
   them without UI-side inference: Internet/Cloudflare, pfSense/LAN,
   TrueNAS/Docker, Talos/Kubernetes and external providers. This remains blocked
   on canonical zone metadata.
5. Add an optional health overlay to `/api/topology` using the same status/evidence
   contract as `/api`; declared state and observed state must remain visibly
   distinct.
6. Keep focused health and topology views shareable with URL-backed filters and no
   server-side operator session state. Health state is implemented through PR #247;
   topology state includes search, preset, relation, strength, lifecycle phase and
   layout through PR #250.
7. Keep quantitative traffic/latency flow visualisation separate from dependency
   topology; use Plotly only when measurements justify a Sankey or time-series
   view.
8. Measure maintained JS/CSS/Python UI source size after each presentation change;
   refactors that only move boilerplate between files do not count as reductions.
