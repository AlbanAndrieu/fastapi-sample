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

### Corréler les cycles existants (PR #350, aucun nouveau probe)

```bash
python scripts/audit/summarize_homelab_cycles.py --aggregate \
  < /chemin/vers/health-board-cycles.jsonl
```

Cette commande limite l'entrée à **64 instantanés** et produit uniquement des
compteurs et des maxima assainis. Les comparaisons `public_completed_range`,
`public_deadline_range` et `observed_phase_maxima_ms` excluent les réponses
`stale` et les vagues homelab `probe_cache.source=memory`, même si
l'enveloppe HTTP se dit `fresh`. S'il n'existe aucune vague `origin`
exploitable, `interpretation=insufficient_current_origin_evidence`.

Sur le futur runtime #350, le panneau « Homelab probe fan-out » montrera les
durées d'attente de sémaphore, DNS, HTTP et vérification secondaire Access
**déjà collectées** : les maxima ne concernent que les sondes terminées.
Les probes annulées par la deadline 4 s restent « phase unknown » ; un champ
manquant ne signifie jamais une phase instantanée. Aucune nouvelle requête
externe ou interne n'est introduite et ces informations **ne sont pas encore
présentes sur le staging au commit `5fe39a33`**.

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

## Affichage de Garage dans `/api` : régression de projection

Après le déploiement de `master` `5fe39a33`, les trois identités
apparaissent dans `/api/health-board.homelab`, mais l'utilisateur ne les voit
pas parmi les cartes de `https://sample.albandrieu.com/api`.
La page produit initialement ses cartes depuis `healthz.checks`; le raccord
`mergeHomelabEvidence` enrichit uniquement les entrées déjà présentes.
Les preuves Garage ne sont donc pas nécessairement visibles.

La PR #350 introduit `api-health-garage.js` pour créer **seulement** les
trois contrôles Garage manquants, sans doublons de `healthz` : `garage`
(S3), `garage-admin` (Admin) et `garage-webui` (Web). Le statut LAN d'un
snapshot récent est visible, mais la route Admin inattendue conserve le
badge *At risk*. Le WebUI est le seul membre pouvant obtenir un lien externe
depuis sa déclaration ; jamais l'Admin ni le S3. Une donnée de probe périmée
reste inconnue.

Le site est protégé par Cloudflare Access : l'agent n'a pas pu observer le
navigateur authentifié. Validation de rendu, filtres et navigation dans
l'environnement TrueNAS à faire après le prochain déploiement explicite ;
le runtime `5fe39a33` ne contient pas cette correction de l'UI.

## Déploiement PR #350 et diagnostic de phases incomplètes

Après la fusion #342, un déploiement **staging volontaire de la PR #350** a
construit le SHA `0902a9a08fed614b5e7112ce3cbcc2867c3ca501` en local
sur TrueNAS. La version de runtime est `1.22.2`, image
`sha256:9f43ba4924b13072f49b43230a7019e1a30c3d90f3eb08d7431f1fce6645107c`,
et l'image rollback antérieure
`sha256:cef90cebc67f4411f09726b0d03c770548d6911e3ab36099ed3d7f7d559a37e8`
reste taguée `fastapi-sample:rollback-before-pr350`. Deux nouveaux assets
JavaScript répondent HTTP 200, la WebUI montre Garage après filtrage, pfSense
RBAC valide 7/7 et Gatus/Prometheus fournit 78 séries success, 78 duration,
55 availability. `build_revision=null` : cette association de SHA résulte
du journal de build, **pas d'une attestation de l'image par l'API**.

L'initialisation du health-board s'est stabilisée : `pending` au premier
rafraîchissement sans cache, puis `fresh` et `stale` pendant les cycles
suivants ; log `snapshot refreshed duration_seconds=6.673`.

Les relevés de performance publics ont été **variables** :

| Vague observée | Terminées | Expirées | Attente max | DNS max | HTTP max | Access max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A | 2/12 | 10/12 | 27 ms | 1 600 ms | 1 937 ms | 1 499 ms |
| B | 1/12 | 11/12 | 31 ms | 1 102 ms | 785 ms | non observé |
| C | 12/12 | 0/12 | 1 779 ms | 599 ms | 635 ms | 1 000 ms |

La vague C a pris `3 073 ms`, et le résultat a été consulté dans une
enveloppe `stale` âgée de `140,517 s`. Cela ne signifie **pas** que les
sondes sont restées actives pendant ces 140 secondes. Tous ces maxima
concernent les probes **terminées** et peuvent correspondre à des services
différents. Les 12/12 sont des **terminaisons techniques** : LanguageTool
renvoie HTTP 400 et `state=fail`, Keycloak/Garage WebUI des avertissements
HTTP 403, sans invalider le décompte `completed=12`.

### Capture de la phase au moment de la deadline — prochain SHA de PR

Le nouveau code de PR, **non inclus dans le staging `0902a9a0`**, prend un
instantané en mémoire de la phase courante **avant** l'annulation des tâches :
`not_started`, `waiting_on_semaphore`, `dns_in_progress`,
`head_get_in_progress`, `access_secondary_in_progress`,
`tcp_in_progress`. L'identification de chaque tentative est ensuite
rejetée du registre faible ; seules l'étiquette de phase et une durée
partielle bornée (ms) peuvent être rendues.

- `probe_summary.public.deadline_phase_counts` donne les effectifs par
  phase à la deadline. La somme doit coïncider avec `timed_out`.
- `public_probe_results[]` possède `deadline_phase` et
  `deadline_phase_elapsed_ms` pour les probes en `probe_source=deadline`.
- Si une preuve précédente est réutilisée, `probe_source=memory` conserve
  sa santé déjà attestée et expose séparément
  `last_probe_attempt_deadline_phase` et
  `last_probe_attempt_deadline_phase_elapsed_ms`, sans changer son statut
  en DOWN ou en nouveau GREEN.
- La commande de synthèse hors réseau `--aggregate` produit désormais
  `deadline_phase_totals` sur **les vagues origin uniquement**.

Ces mesures de phase à l'annulation ne prouvent pas que la phase a échoué :
elles indiquent uniquement **où se trouvait la tâche quand le budget global
de 4 secondes a été atteint**. Comparer plusieurs vagues avant toute
optimisation. Les limites de concurrence 4, de sélection 12 par scope et
les conditions de sécurité/Access restent inchangées.

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
