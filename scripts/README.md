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

Les modules `scripts/ci/` et les helpers de quality gate restent les composants internes. `scripts/agent-quality-gate.sh` supervise une seule gate ; `scripts/run-pytest-compact.sh` est le lanceur canonique Python. Les scripts de diagnostic spécialisés restent dans leur domaine (`scripts/truenas/`, `scripts/pfsense/`).

Le tableau d'identifiants E01–E14 a été archivé après la consolidation F01–F11. Ne lancer qu'une seule gate documentaire canonique `just docs-links` ; `scripts/check_docs_links.py --active-only` n'est qu'une implémentation, pas une seconde entrée à maintenir.

Une modification exclusivement documentaire suit : `just agent-context auto` → `just docs-links` → relecture du diff. Une modification mixte (code et docs) garde le contrôle du code ; le routeur ne doit jamais transformer un test non exécuté en PASS.

À conserver en archive : rapports détaillés de PR, relevés runtime historiques et commandes d'incident. **Ne pas supprimer** un vieux lanceur avant inventaire de ses consommateurs, remplacement documenté et test de compatibilité.
