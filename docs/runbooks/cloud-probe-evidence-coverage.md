# Cloud probe evidence: guide d'exploitation

## Sens des chiffres

`eligible` compte les emplacements publics et les emplacements LAN *activés*.
`known` compte les preuves d'origine ou en mémoire qui ne sont pas périmées.
Les échecs de deadline, preuves périmées et emplacements sans observation ne
sont pas des services déclarés DOWN. `healthy / eligible` n'est pas un SLO.

Le processus limite chaque fenêtre à 12 sondes publiques et 12 LAN, avec
cache de réponse 30 secondes. Les vagues sont déclenchées par des requêtes API,
pas par un daemon de scheduling ; plusieurs workers ont chacun leur propre
mémoire et leur propre rotation. La durée minimale estimée sur **tous** les
candidats est une capacité théorique, pas une promesse de couverture.

## Diagnostic des warnings

- `ACCESS_PROTECTED` : contrôle Cloudflare Access visible, origine non prouvée.
- `AUTH_FAILED` : tentative explicite de jeton de service refusée.
- `ORIGIN_UNVERIFIED` : validation derrière le tunnel insuffisante.
- `DNS`, `TLS`, `TCP`, `TIMEOUT`, `HTTP`, `ORIGIN_ERROR` :
  indice technique de la couche observée ; confirmer avant d'attribuer une panne.
- `DEADLINE`, `STALE`, `NO_EVIDENCE` : qualité de preuve et exécution.

Une réponse HTTP 302/403 de Cloudflare ne doit jamais rendre l'origine verte.
Les données brutes d'une matrice protégée nécessitent l'autorisation OWNER.

## Recette après déploiement

1. Vérifier le SHA et la version effectivement en service.
2. Examiner `/api/homelab/probes` depuis une session autorisée : `probe_summary.public.unobserved_slots`, `estimated_full_cycle_seconds`, `probe_runtime.estimate_source`.
3. Capturer une suite d'observations à intervalle régulier. Si Redis est désactivé, conserver le même worker si possible ; sinon la couverture varie d'un worker à l'autre. Vérifier que chaque ID quitte `unobserved_slots` ou justifier son exclusion.
4. Regrouper chaque warning par `error_kind`, `http_status`, `public_probe_auth_mode` et `public_probe_verification`. Corriger la cause, ne pas modifier artificiellement les états.
5. Si le runtime est répliqué, configurer `REDIS_URL` et activer explicitement `HOMELAB_PUBLIC_PROBE_EVIDENCE_REDIS_ENABLED=true`. Définir `HOMELAB_PROBE_EVIDENCE_NAMESPACE` (identifiant alphanumérique, `_` ou `-`) pour isoler les déploiements. Les seuls champs partagés sont des diagnostics publics nettoyés ; TTL maximal 3600 s. Le backend continue en mémoire si Redis est absent ou inaccessible. Vérifier `probe_summary.public.evidence_storage` et `probe_runtime.evidence_storage`. Il n'existe **aucune** fédération automatique des données LAN.
6. Pour fédérer TrueNAS, exporter un résumé autorisé avec heure, source, staleness et signature ; contrôler l'accès côté Cloud. Ne jamais activer les connexions LAN depuis le runtime Cloud.

**Critère d'acceptation :** chaque cible éligible a une observation exploitable
ou une exclusion motivée ; les avertissements Access restent distincts d'une
panne origine ; les délais affichés ne sont pas présentés comme une garantie.
