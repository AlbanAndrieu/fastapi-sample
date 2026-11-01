# Runbook — pytest borné en CI

Le workflow `.github/workflows/python.yml` délègue ses deux chemins pytest à
`scripts/ci/run-pytest-bounded.sh`. Ce script **ne désactive aucun test**.
Il centralise les limites de durée, le diagnostic et la propagation des codes
d'échec, sans modifier l'environnement de production.

| Mode | Limite | Journaux | Utilisation |
| --- | --- | --- | --- |
| `full` | 12 minutes | `pytest.log`, résumé GitHub, métrique `seconds` | Suite complète après `uv sync --frozen` |
| `isolated` | 6 minutes | Journal temporaire privé, effacé à la fin | Contrats de qualité avant la synchronisation des dépendances |

Le workflow passe explicitement `-vv` et `faulthandler_timeout` (90 secondes
pour la suite complète, 60 pour les contrats). Les journaux indiquent le
dernier test en cours avant une interruption.

## Codes de retour

- **0** : la commande a réussi.
- **124** : GNU `timeout` a atteint sa limite, étiquette `PYTEST_TIMEOUT`.
- **137** : le processus a reçu SIGKILL, étiquette `PYTEST_KILLED`.
- **Autre code non nul** : échec de la commande, étiquette `PYTEST_FAILED`.

Le script réémet le **code original** et affiche les 180 dernières lignes du
journal en cas d'échec. Les jobs GitHub disposent également de limites
`timeout-minutes` indépendantes. Une expiration est un **FAIL**, jamais
un succès. Le script ne contrôle pas la file d'attente GitHub ou les incidents
du fournisseur de runners.

## Vérification locale ciblée (sans GitHub Actions)

Depuis un worktree isolé, avec Python et pytest installés :

```bash
bash -n scripts/ci/run-pytest-bounded.sh
python -m pytest -q tests/unit/test_ci_pytest_bounded.py
python -m pytest -q tests/unit/test_workflow_security.py
python -m pytest -q tests/unit/test_agent_quality_gate_contract.py
```

Le premier groupe teste des commandes synthétiques sans base PostgreSQL,
réseau ni credentials. En cas d'échec réel, conserver le SHA testé, le code
retour, le nom du dernier test et la trace Python. Ne pas publier de secrets
depuis les journaux ou les artefacts.
