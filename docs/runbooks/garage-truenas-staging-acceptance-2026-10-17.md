# Acceptation staging Garage · 17 octobre 2026

Portée : `fastapi-sample` sur TrueNAS (`172.17.0.24:8091`), après fusion de
[la PR #342](https://github.com/AlbanAndrieu/fastapi-sample/pull/342).
Ceci est un relevé **fourni par l'opérateur**, pas un accès direct à son
TrueNAS depuis l'environnement de l'agent. Aucune modification réseau ou
Cloudflare n'est impliquée.

## Identité et santé du déploiement

- Source checkout : `5fe39a33c3b8c6bf86c3ab1b17384259e09e7af7`
  (`FASTAPI_SAMPLE_DEPLOY_MODE=build FASTAPI_SAMPLE_REF=master`).
- TrueNAS App `sample=RUNNING`, HTTP `/health=healthy`,
  `release_version=1.22.1`, pfSense RBAC **7/7**, secrets non affichés.
- `/v2/version.build_revision=null` : le SHA de source est connu du
  déployeur, **mais n'est pas attesté par l'image exécutée**. Dans
  `nabla-compose`, ajouter une étiquette OCI de révision et injecter la
  variable runtime `BUILD_REVISION`, avec validation du digest et tests.
  Ne jamais traiter la version sémantique comme preuve du SHA.
- Gitlink `nabla-compose` : `8c4492d1` ; checkout FastAPI :
  `5fe39a33`. Ce décalage pendant staging n'est pas une erreur de code
  ni une raison de faire un `git add fastapi-sample` automatique.

## Résultats des sondes

| Mesure | Campagne A (3 cycles) | Campagne B (3 cycles) |
| --- | --- | --- |
| Public `completed/12` | 1, 1, 11 | 11, 1, 12 |
| Public `timed_out/12` | 11, 11, 1 | 1, 11, 0 |
| Interne `completed/12` | 12, 12, 12 | 12, 12, 12 |
| Couverture interne | 14,0 / 14,0 / 17,4 % | 17,4 / 20,9 / 24,4 % |
| Source priorités | `bootstrap` | `bootstrap` |
| Garage LAN | 3/3, chaque cycle | 3/3, chaque cycle |

L'augmentation de la couverture est celle des **preuves mémorisées/rotatives**,
non une augmentation de 12 à davantage de connexions LAN par cycle.
`garage`, `garage-admin` et `garage-webui` ont tous
`internal_state=ok` sur les six observations. Les résultats d'exposition
restent distincts : `garage-admin` est déclaré `internal` mais
`unexpected_tunnel_route=true` ; la WebUI reste `public` et `warn`,
malgré sa santé LAN. La route Admin doit être auditée puis corrigée par
le dépôt autoritaire `nabla-compose` après preuve et rollback.

Une réponse health-board `state=stale` observée entre deux cycles
signifie que l'instantané est réutilisé/en cours de rafraîchissement ;
elle **ne prouve ni une nouvelle sonde réussie ni une panne**. Examiner
`age_seconds`, `refreshing`, `homelab.probe_cache` et
`probe_source` avant d'additionner des observations.

## DNS / TCP / TLS / Cloudflare

Mesure explicite depuis `docker exec -i` avec Python :

| Phase | Mesure |
| --- | ---: |
| DNS | 47 ms |
| TCP | 4 ms |
| TLS | 13 ms |
| IP edge | `188.114.97.2` |

Des appels curl indépendants vers Garage/Admin et FastAPI Cloud
répondent en ~0,1–0,6 s (HTTP 302 Access ou HTTP 200 Cloud).
Attention : les champs curl `time_connect` et `time_appconnect`
sont **cumulatifs depuis le début** ; leur différence, pas leur valeur
brute, est le temps de phase. Les mesures Python et curl ont des
conditions différentes et ne doivent pas être assimilées.

Ces résultats excluent un blocage DNS/TCP/TLS **permanent sur le seul
chemin testé**. Ils n'expliquent pas à eux seuls les expirations du
fan-out : les 12 sondes publiques et les 12 LAN partagent une limite
de concurrence de 4, chaque HTTP peut faire HEAD puis GET et certains
endpoints Access déclenchent une sonde secondaire hors sémaphore.
Le budget global de **4 secondes reste inchangé**.

La nouvelle instrumentation dans `nabla/api/homelab_probe_runner.py`
distingue par résultat `probe_timing.queue_wait_ms`,
`dns_probe_ms`, `http_request_ms`,
`http_request_count` et, lorsque présent,
`access_secondary_ms`. Le résumé de cycle
`homelab.probe_summary.public.timing` expose les maxima sur les
**sondes terminées seulement**, avec `completed_samples`.
Ne jamais attribuer zéro milliseconde à une sonde annulée.
Ces champs sont **préparés dans la PR #350** : ils ne sont pas encore
présents sur le staging `5fe39a33`.

### Résumé hors ligne sans secrets

Depuis un checkout FastAPI contenant le script de #350, et **sans
déclencher de rafraîchissement supplémentaire**, analyser un
instantané JSON déjà obtenu :

```bash
cat /chemin/vers/health-board.json |
  python scripts/audit/summarize_homelab_cycles.py
```

Pour plusieurs cycles, concaténer les objets JSON compacts, **un par
ligne**. Le script lit stdin, ne fait aucune requête réseau et émet
uniquement des champs autorisés (pas de `Location`, URL, en-têtes,
cookies, secrets, résultats bruts). Les données source restent à
protéger. Pour de nouveaux relevés, limiter à trois échantillons
espacés d'environ 31 secondes ; ne pas lancer de polling agressif.

## Prometheus / Gatus

Prometheus `/-/ready` répond et la requête instantanée retournait
`nabla:telemetry:gatus_up=1`. Trois familles manquent :
`nabla:service:synthetic_probe_success`,
`nabla:service:synthetic_probe_duration_seconds`,
`nabla:service:synthetic_availability_ratio_5m`.
Leur absence prouve une lacune d'évidence synthétique, **pas
`Gatus DOWN` ni les services DOWN**. Vérifier les recording rules,
les cibles de scrape, les labels et le chargement avant de changer
le mode de délégation dans FastAPI. Le déployeur/rules Prometheus sont
gérés dans `nabla-compose` (PR #257), pas dans cette PR.

## Exposition privée : preuve hors LAN encore requise

Depuis le LAN, `s3.int.albandrieu.com` a retourné
`HTTP 403` en résolvant l'adresse WAN `82.66.4.247`.
La réflexion NAT pfSense peut expliquer ce résultat : **on ne peut
pas conclure à l'accessibilité depuis Internet**. Faire le test
outside-in depuis FastAPI Cloud ou un réseau mobile indépendant,
puis auditer HAProxy/NAT/Traefik/DNS. Un `403` n'est pas une preuve
suffisante de protection ni de non-exposition.

## Critères de sortie et ownership

- [x] PR #342 merged / runtime Garage LAN 3/3 confirmé.
- [x] Mesure DNS/TCP/TLS directe et séries de cycles fournies.
- [ ] PR #350 : tests ciblés, formatage, quality gate complète au HEAD
      puis déploiement **explicite** si instrumentation acceptée.
- [ ] Diagnostiquer les délais par phases au même instant que le budget
      4 s et le cache, sans conclure à une panne DNS globale.
- [ ] Sécuriser la route Admin et vérifier S3 réellement hors LAN
      via le contrôle d'exposition `nabla-compose`.
- [ ] Publier priorités et `deploymentUnitId` dans le catalogue
      autoritaire et vérifier `priority_source=catalog`.
- [ ] Réparer les règles/scrapes Gatus et signer l'identité SHA de
      l'image TrueNAS (modifications `nabla-compose`).

Aucune action de réparation automatique Cloudflare, pfSense,
TrueNAS ou réseau ne fait partie de ce runbook.
