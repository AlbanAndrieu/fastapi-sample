# Documentation — FastAPI Sample

La documentation est organisée par **décision** et par **tâche opérateur**.
Le [README du dépôt](../README.md) reste le point d'entrée développeur.

## Sources de vérité

| Besoin | Document canonique |
| --- | --- |
| **Que reste-t-il à faire ?** | [Roadmap d’ingénierie F01–F12 et rattachements H](engineering-roadmap.md) (historique du 13/11 archivé) |
| **Un symptôme déjà rencontré ?** | [Registre d'incidents](incidents.md) |
| **Un ancien item non requalifié ?** | [Backlog historique](engineering-backlog.md) |
| **Sémantique des preuves de santé ?** | [Modèle de diagnostics](platform-service-diagnostics-model.md) |
| **Architecture de l'interface ?** | [UI et topologie](api-ui-architecture.md) |
| **Règles sécurité homelab ?** | [Guardrails](homelab-security-roadmap.md) |
| **RTO/RPO et continuité ?** | [Business Impact Analysis](business-impact-analysis.md) |
| **Points d'entrée et dashboards ?** | [Entrypoints](entrypoints-and-dashboards.md) |
| **Affichage des services V2 et provenance ?** | [Réconciliation V2](archive/2026-11-14-catalog-v2-roadmap-alignment.md) et [handoff Site Alban](site-architecture-catalog-handoff.md) |

La [roadmap infrastructure Compose](https://github.com/AlbanAndrieu/nabla-compose/blob/master/docs/roadmap.md) et les [roadmaps du Site Alban](https://github.com/AlbanAndrieu/nabla-site-alban/blob/master/docs/README.md) restent distinctes : les dépendances sont liées, pas dupliquées.

Le [portefeuille Homelab](https://github.com/AlbanAndrieu/nabla-compose/blob/master/docs/roadmap-portfolio.md) présente les arbitrages inter-dépôts. Le [journal de réconciliation](archive/2026-11-13-roadmap-reconciliation.md) conserve la trace des travaux transférés. Le [bilan V2 du 14/11](archive/2026-11-14-catalog-v2-roadmap-alignment.md) distingue code fusionné, snapshot et recette runtime.

## Runbooks opérateur

| Tâche | Procédure |
| --- | --- |
| Loading de `/api?ui_full=1` sur Cloud/TrueNAS | [Diagnostiquer le gel UI](runbooks/fastapi-cloud-api-ui-freeze-20261026.md) |
| Tests locaux, build Docker, OWNER mobile, recette navigateur | [Validation consolidée Cloud/TrueNAS/OWNER](runbooks/fastapi-truenas-owner-acceptance-20261029.md) |
| Scrape/metrics, auth 401/403, Prometheus/Akvorado | [Acceptation observabilité](runbooks/fastapi-observability-acceptance.md) |
| Dépendances locales, cache et sondes | [Rapport de runtime local](local-runtime-dependency-report.md) |
| pfSense 502 : sémantique de l'observateur FastAPI | [Contrat pfSense](pfsense-webconfigurator-recovery.md) |
| pfSense : observabilité sécurité | [Diagnostics sécurité](pfsense-security-observability.md) |
| Cache des sondes extérieures | [Opérations cache](external-probe-cache-operations.md) |
| Trajet public TrueNAS | [Ingress public](truenas-public-ingress.md) |
| Cloudflare/Sentry dans l'application | [Observateurs et SDK](cloudflare-sentry-runtime-diagnostics.md) |
| Contrat réseau Cloudflare | [Réseau FastAPI](fastapi-sample-cloudflare-network-contract.md) |

La configuration réelle des services, des secrets, du réseau, de
l'infrastructure Gatus/Prometheus et les déploiements TrueNAS appartiennent
à [nabla-compose](https://github.com/AlbanAndrieu/nabla-compose).
FastAPI conserve les clients, diagnostics, DTO et tests.
Le provisionnement LiteLLM staging est documenté dans
[le runbook Compose](https://github.com/AlbanAndrieu/nabla-compose/blob/master/docs/runbooks/fastapi-sample-litellm.md).

## Agents et contrôles locaux

- [Règles de contribution](../AGENTS.md) : priorité des instructions et sécurité.
- [Scripts et points d'entrée](../scripts/README.md) : un seul lanceur par usage ; pour une modification uniquement documentaire, `just agent-context auto` propose `just docs-links` (tous les Markdown actifs, archives figées exclues ; aucun réseau, aucune CI).
- [Skill local-first](../.agents/skills/local-first-quality/SKILL.md) :
  L0 contexte, L1 ciblé, L2 convergence et L3 publication.
- [Reprise OpenCode d'une PR](../.opencode/commands/continue-pr.md) :
  portée de changement bornée et preuve au SHA exact.

## Références complémentaires et archives

Les documents de référence restent accessibles :
[MCP](mcp-integrations.md),
[monitoring](health-monitoring-environment.md),
[Kubernetes zero-trust](kubernetes-zero-trust-hardening.md),
[Cloudflare Tunnel](cloudflare-tunnel-audit.md),
[Snort WAN](snort-wan-validation.md) et
[Cashews](cashews-evaluation.md).

Les preuves et décisions anciennes sont conservées, sans statut courant :

- [Roadmap intégrale figée le 13 novembre](archive/2026-11-13/engineering-roadmap-before-reconciliation.md)
- [Roadmap détaillée du 29 octobre](archive/2026-10-29/engineering-roadmap-before-consolidation.md)
- [Ancienne roadmap du 24 octobre](archive/2026-10-24/engineering-roadmap.md)
- [Historique intégral du gel UI d'octobre](archive/2026-10-30/fastapi-cloud-api-ui-freeze-20261026-history.md)

## Règles de maintenance

1. **Une roadmap active** : seulement priorités, critères de fin et blocages.
2. **Un registre d'incidents** : symptômes datés et preuves attribuées.
3. **Des runbooks durables** : commandes, ordre d'exécution et résultats attendus.
4. **Historique archivé** : ne pas effacer les causes ni les procédures utiles.
5. **Preuves distinctes** : `CODED`, `TESTED`, `DEPLOYED`, `ACCEPTED`.
6. **Un seul propriétaire par domaine** : liens entre dépôts, sans recopier
    secrets, catalogues ou configurations d'appliance.
