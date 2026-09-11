# API diagnostics UI architecture

## Scope

The `/api` page remains the health-first operator view. It must not embed a network
or dependency graph. Interactive topology is a separate concern exposed through
`/api/topology`, with `/api/homelab-topology` remaining the machine-readable
contract.

The canonical declared topology still comes from `nabla-compose`. FastAPI may
classify, observe and present that topology, but presentation code must not become
a second source of infrastructure truth.

## Topology screen

The first standalone topology screen uses Cytoscape.js because it provides a
purpose-built graph model, selectors, layouts, viewport interactions and graph
algorithms without introducing React.

Current constraints:

- load Cytoscape only on `/api/topology`;
- pin the external version and require Subresource Integrity;
- keep a visible link to the JSON topology if the optional renderer cannot load;
- reuse `analyzeTopology()` for role, criticality, dependency and blast-radius
  semantics instead of duplicating them in the renderer;
- reuse the same topology loader/fallback in the health grouping and topology
  screen;
- keep live health separate from declared topology until the declared view is
  stable.

## Controlling frontend code growth

The current browser UI is deliberately framework-light, but repeated
`document.createElement()`, attribute mutation and append operations are becoming
a maintenance cost. The next refactor should reduce code before adding more
interactive health components.

### Preferred experiment: standalone `lit-html`

Pilot `lit-html` in one high-churn renderer rather than introducing a complete
frontend framework. Good candidates are the service-group summary renderer and
the diagnostic probe-badge renderer.

Do not add a new CDN availability dependency to the health view. The current
`/api/assets` modules are served locally without a frontend bundle, so a Lit pilot
must first provide a deterministic build-time bundle or vendored local artifact.
The topology screen may tolerate an optional external renderer because `/api`
remains independent and the machine-readable topology link remains usable.

Acceptance criteria for the pilot:

- reduce imperative DOM/rendering lines in the selected module by at least 25%;
- preserve the existing JSON contracts and health semantics;
- keep data fetching, topology analysis and status policy outside templates;
- introduce no application-global mutable state;
- keep accessibility attributes and safe text interpolation;
- keep the current deterministic Biome and unit-test gates;
- remove more maintained application code than the integration adds.

Only adopt full Lit Web Components if the standalone-template pilot demonstrates
clear reuse across several independent screens.

### Existing library to exploit: Jinja2

Jinja2 is already part of the application stack. Page shells that are mostly
static HTML should progressively move out of large Python f-strings and into
Jinja templates. This reduces Python module complexity without adding another
runtime dependency. Dynamic health and topology data should continue to arrive
through explicit API contracts.

### Alternatives not selected for the first refactor

- **React / React Flow:** excellent for a React application, but would introduce a
  second frontend runtime solely for FastAPI diagnostics.
- **htmx:** small and dependency-free, but its HTML-over-the-wire model would
  require replacing several established JSON rendering paths with server-rendered
  fragments. Re-evaluate only for server-owned forms or CRUD screens.
- **Alpine.js:** useful for lightweight local state, but does not address the
  largest repeated rendering blocks as directly as declarative templates; its
  standard expression model also needs separate CSP consideration.

## Follow-up presentation roadmap

1. Add topology presets for **Dependencies** and **Network paths** so functional
   dependencies and transport/ingress paths are not mixed by default.
2. Add compound trust/network zones when the topology contract can identify them
   without UI-side inference: Internet/Cloudflare, pfSense/LAN, TrueNAS/Docker,
   Talos/Kubernetes and external providers.
3. Add an optional health overlay to `/api/topology` using the same status/evidence
   contract as `/api`; declared state and observed state must remain visibly
   distinct.
4. Add URL-backed topology filters so focused views can be shared without storing
   UI state server-side.
5. Keep quantitative traffic/latency flow visualisation separate from dependency
   topology; use the existing Plotly dependency only when measurements justify a
   Sankey or time-series view.
6. Measure maintained JS/CSS/Python UI source size after each presentation change;
   refactors that only move boilerplate between files do not count as reductions.
