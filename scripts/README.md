# Scripts FastAPI — entrées canoniques

Les commandes de contrôle doivent partir des **recettes Just**, qui délèguent aux scripts conservés. Ne pas créer de seconde quality gate et ne pas déclencher automatiquement de CI ou de déploiement.

| Objectif | Point d'entrée unique | Type |
| --- | --- | --- |
| Identifier la tâche et la première vérification | `just agent-context auto` | Lecture seule, offline |
| Documentation active et liens locaux | `just docs-links` | Python stdlib, offline ; archives figées exclues |
| Tests JS de l’interface Cloud | `just ui-quick` | Node local |
| Tests Python bornés | `just test` | pytest, environnement déjà préparé |
| Correction de style explicite | `just fix` | Peut modifier les fichiers |
| Gate qualité complète | `just quality` | Sans GitHub Actions |
| Attestation de publication au SHA exact | `just publish-check` | Aucune publication |
| Diagnostic TrueNAS sans mutation | `just truenas-evidence` | Accès local requis |
| Snapshot de démarrage Backstage V2 | `bash scripts/refresh-catalog-snapshot.sh [fichier-local]` | Source Compose contrôlée ; aucune seconde autorité |

Les modules `scripts/ci/` et les helpers de quality gate restent les composants internes. `scripts/agent-quality-gate.sh` supervise une seule gate ; `scripts/run-pytest-compact.sh` est le lanceur canonique Python. Les scripts de diagnostic spécialisés restent dans leur domaine (`scripts/truenas/`, `scripts/pfsense/`).

Les alias E01–E14 sont archivés ; F01–F12 est l'index FastAPI actif. Le portefeuille H est exclusivement arbitré côté Compose. Ne lancer qu'une seule gate documentaire canonique `just docs-links` ; `scripts/check_docs_links.py --active-only` n'est qu'une implémentation, pas une seconde entrée à maintenir.

Une modification exclusivement documentaire suit : `just agent-context auto` → `just docs-links` → relecture du diff. Une modification mixte (code et docs) garde le contrôle du code ; le routeur ne doit jamais transformer un test non exécuté en PASS.

Le snapshot `nabla/api/data/catalog-snapshot.json` n'est qu'un **cache froid**, non un second inventaire. Le script canonique vérifie le SHA-256 du graphe V2 et l'unicité des `entityRef` avant remplacement atomique ; une source invalide ou inchangée n'est jamais publiée. Test hors ligne : `tests/unit/test_catalog_snapshot_refresh_contract.py`.

À conserver en archive : rapports détaillés de PR, relevés runtime historiques et commandes d'incident. **Ne pas supprimer** un vieux lanceur avant inventaire de ses consommateurs, remplacement documenté et test de compatibilité.

## Workstation Claude Code vs remote Codex

Use `python3 scripts/agent-task-context.py --task auto` for a bounded
path-only context. `bash scripts/agent-diagnostics.sh --static` is the default
no-network L1 route (existing `agent-offline-check.sh`).
When a real workstation/LAN session is available, opt in explicitly with
`AGENT_EXECUTION_MODE=workstation bash scripts/agent-diagnostics.sh --runtime`.
This delegates to the existing `truenas-runtime-evidence.sh --quick` with an
8-second evidence poll rather than the normal 50-second full wait.
`--dns-only` is separately opt-in; a remote session returns `NOT_RUN` and
never attempts LAN access. No route is proof of full L3 or runtime acceptance.
See [conditional playbook](../docs/agent-execution-playbook.md).
