# Archive de diagnostic — gel UI Cloud/TrueNAS (26–30 octobre 2026)

> Copie historique intégrale de `docs/runbooks/fastapi-cloud-api-ui-freeze-20261026.md`
> avant consolidation. Les constats, SHA et procédures ci-dessous sont **datés** ;
> ils ne constituent pas une recette de déploiement actuelle. Certains liens relatifs
> peuvent renvoyer à l'ancien emplacement.
> Utiliser [la roadmap active](../../engineering-roadmap.md),
> [le registre d'incidents](../../incidents.md) et
> [la recette OWNER/Cloud/TrueNAS](../../runbooks/fastapi-truenas-owner-acceptance-20261029.md)
> pour les décisions présentes.

---

# Incident /api Cloud — boucle DOM après fusion PR #378

> **Mise à jour du 29 octobre 2026 — document d'incident historique.**
> Les PR [#380](https://github.com/AlbanAndrieu/fastapi-sample/pull/380)
> et [#381](https://github.com/AlbanAndrieu/fastapi-sample/pull/381)
> sont **fusionnées**. La [PR #382](https://github.com/AlbanAndrieu/fastapi-sample/pull/382)
> reste **Draft** et traite la visibilité du panneau OWNER sur mobile.
> Leur état Git ne prouve pas un déploiement TrueNAS.
> La [roadmap active consolidée](../engineering-roadmap.md) fait foi
> pour les priorités ; les observations ci-dessous sont datées et conservées.

**26 octobre 2026 — P0, correctif candidat non déployé.**
L'opérateur confirme que `https://fastapi-sample.fastapicloud.dev/`
répond alors que `/api` reste sur Loading puis fige le navigateur.
PR #378 fusionnée dans master à **21:43:56 UTC = 22:43:56 CET**,
commit `f10c8147dd0f7e1c05d21c5f44229e5ee37f4e1e`.

## Cause à forte confiance dans le code fusionné

Le HTML /api active plusieurs `MutationObserver` autour de
`#health-board`, puis reprogramme un `requestAnimationFrame` sur
chaque changement. Deux mutations **inconditionnelles** assurent
un recyclage sans fin même après stabilisation :

1. `api-health-ui-final-followup.js`, `stabilizeProbeSlots` :
   `strip.appendChild(probe)` pour *tous* les badges à chaque frame.
   Réinsérer un nœud existant le déplace et déclenche `childList`.
2. `api-global-service-filter.js`, `renderStatusChips` :
   `button.innerHTML = ...` à chaque frame, sans contrôle des valeurs
   déjà affichées. `renderActiveFilters` remplace également ses
   enfants même quand le filtre n'a pas changé.

`api-health-ui-polish.js` réécrivait en plus systématiquement
`note.textContent` de la ligne pfSense. Ces opérations peuvent
maintenir une boucle de mutations et monopoliser le thread principal
du navigateur. **Cause runtime hautement probable, à confirmer via
profilage navigateur**. Les timeouts réseau ajoutés dans #378
ne règlent pas cette classe de bug.

## Corrections PR de hotfix

- Trier les sondes **uniquement quand l'ordre change**.
- Conserver la signature des filtres. Ne pas réécrire
  `innerHTML` / `replaceChildren` si l'état est identique.
- Ne pas modifier la classe de présentation et les champs de
  télémétrie si la valeur est déjà correcte.
- Ne plus réécrire inconditionnellement le label pfSense.
- Tests Node avec 100 frames de rendu identiques : aucune nouvelle
  mutation DOM après la stabilisation.

## Preuve serveur confirmée : `/api/site/health/v2` HTTP 500 (26/10)

L'opérateur a réussi `mise exec -- uv run fastapi cloud whoami` :
une identité Cloud et un API token d'environnement sont présents.
Le CLI Cloud fonctionne ; ne pas renouveler ce token ni l'imprimer.
Les logs applicatifs `--tail 200 --since 2h --no-follow` montrent :

- `GET /api/site/health/v2` → **HTTP 500** à
  `2026-10-26T22:16:50Z`.
- Origine identifiée : `nabla/api/health_routes.py:171`,
  `logger.info("site_health_v2 trace_id={}", trace_id)`.
- `structlog` utilise la substitution de format `%` pour les
  arguments positionnels ; une chaîne à accolades produit
  `TypeError: not all arguments converted during string formatting`.
- `GET /api` → **HTTP 200** en `0.006` seconde autour de
  `2026-10-26T22:43:50Z` ; le HTML a été servi et la charge JS
  reste un incident distinct.
- `GET /vercel.svg` → **HTTP 404**, ressource décorative
  indépendante du gel. Ne pas l'escalader comme incident API.

Le hotfix #379 remplace la ligne par
`logger.info("site_health_v2", trace_id=trace_id)`,
et ajoute un test de régression avec en-tête `traceparent` valide.
Le statut `200` de la route ne sera prouvé qu'après fusion et
déploiement ; l'exception n'est pas résolue par la configuration réseau.

## Reprise après deux erreurs de commande locales (26/10)

**CLI FastAPI :** la commande `fastapi cloud login` exécutée sans
`mise exec -- uv run` a appelé `/usr/bin/fastapi`, paquet
Python de la distribution qui ne possède pas les extras CLI
`fastapi[standard]`. Cela **n'établit aucune panne Cloud**.
Ne pas installer un second FastAPI système pour contourner le problème.
Utiliser les dépendances épinglées du dépôt :

```bash
mise exec -- uv run which fastapi
mise exec -- uv run fastapi --version
mise exec -- uv run fastapi cloud whoami
```

Si la session n'est pas authentifiée, lancer **interactivement** :
`mise exec -- uv run fastapi cloud login`. Les logs sont ensuite
consultés avec `mise exec -- uv run fastapi cloud logs .`.
La session interactive n'est **pas** un jeton CI ou un déploiement.

**Playwright (erreur `ERR_MODULE_NOT_FOUND: playwright`) :**
le script est bien présent dans le worktree de #379 ; c'est
l'import de `playwright` **pour Node** qui échoue, car il n'est pas
déclaré dans le `package.json` du dépôt. Le projet possède déjà
l'extra Python de test `pytest-playwright`. La PR #379 remplace
maintenant le lanceur Node par un wrapper `mise exec -- uv run
--no-project --with playwright python`, avec le vrai diagnostic dans
`scripts/diagnose-production-api-ui-freeze.py`.

Le worktree `/tmp/fastapi-ui-freeze-pr379` **existe déjà**.
Ne pas relancer `git worktree add` ; actualiser son HEAD
détaché par fast-forward (en l'absence de changements locaux) :

```bash
git fetch origin fix/api-ui-observer-render-loop-20261026
git -C /tmp/fastapi-ui-freeze-pr379 merge --ff-only \
  origin/fix/api-ui-observer-render-loop-20261026
cd /tmp/fastapi-ui-freeze-pr379
node scripts/diagnose-production-api-ui-freeze.mjs
```

Le wrapper installe ou réutilise Playwright **dans un environnement
Python uv isolé, sans synchroniser les dépendances du projet**. Aucun `npm install`, `node_modules` ou
installation globale n'est requis. Il faut en revanche que Chromium
soit installé pour Playwright sur la workstation ; en cas de
`browser_unavailable`, le prochain contrôle explicite est
`mise exec -- uv run --with playwright python -m playwright install chromium`.
Aucune permission OWNER ou clé de diagnostic n'est utilisée.

## Logs FastAPI Cloud — lecture seule opérateur

L'agent ne dispose pas de la session FastAPI Cloud et **n'a pas
consulté les logs applicatifs** : ne pas prétendre que les serveurs
rapportent une exception. Depuis un checkout lié au projet et une
session CLI FastAPI Cloud déjà authentifiée :

```bash
mise exec -- uv run fastapi cloud whoami
mise exec -- uv run fastapi cloud logs . --tail 200 --since 2h --no-follow
```

Pour analyse de la fenêtre incluant la fusion/deploiement :

```bash
mise exec -- uv run fastapi cloud logs . --tail 500 --since 2h --no-follow --json
```

**Masquer clés, cookies, en-têtes d'authentification, URL contenant des
credentials et informations privées avant partage.** Corréler les
requêtes `/api`, `/api/ui/session`, `/api/ui/services`,
`/api/health-board`, `/api/assets/*.js` aux statuts 4xx/5xx,
délais et logs `health board snapshot refresh timed out`.
Les logs de serveur ne permettent pas à eux seuls de voir un
`MutationObserver` qui boucle dans le navigateur.

## Contrôle navigateur automatisé (read-only)

Depuis le checkout actualisé de #379 avec `mise`, `uv` et Chromium,
sans accès OWNER ni secret de production :

```bash
node scripts/diagnose-production-api-ui-freeze.mjs
```

La sonde vérifie le code HTTP de `/api`, les requêtes même origine
vers les routes UI essentielles, les erreurs JavaScript (compte
uniquement), les cartes encore sur Loading, les long tasks et
la réactivité du thread JS. Elle **ne lit ni cookies ni réponse
JSON des services** et ne déclenche pas d'appel de diagnostic OWNER.
Elle échantillonne 14 secondes après le chargement DOM et
le lanceur Node impose une limite globale de 50 secondes à la
commande ; un navigateur bloqué n'occupe donc pas indéfiniment
le terminal.

**Limite :** sans connectivité DNS à FastAPI Cloud ni binaire
Playwright installé, ce test ne peut pas être exécuté par l'agent.
Les tests unitaires Node de pure logique ne remplacent pas ce
contrôle end-to-end.

## Nouvelle preuve : TrueNAS et Cloud sur l'ancien code (27/10/2026)

L'opérateur a redéployé TrueNAS avec
`scripts/truenas/update-fastapi-sample.sh`. Le journal de
déploiement contient **`Selected ref: origin/master`**, commit
**`f10c8147dd0f7e1c05d21c5f44229e5ee37f4e1e`**, même base que
le Cloud après #378. `/api` sur
`https://sample.albandrieu.com/api` reste en état `Loading`
malgré `/health` sain (4/4), LiteLLM/Ollama/OpenRAG backend HTTP 200
et Prometheus prêt. **#379 n'est pas inclus dans l'image de staging** :
ce test n'invalide pas encore le correctif DOM proposé.

Le premier diagnostic Chromium a échoué avant lancement ;
après installation de Chromium, le second lançait le processus,
mais son ancien wrapper `spawnSync` expirait au bout de 50 s et
n'indiquait pas si le blocage provenait du navigateur ou de l'UI.
Le nouveau diagnostic a un échantillonnage **async** avec
`page.evaluate` borné à 2 s, des phases imprimées et un arrêt forcé
après **35 s**. Il accepte exactement trois cibles approuvées.

### Diagnostic réseau sans navigateur, lecture seule

Dans le worktree #379 **actualisé**, lancer séparément :

```bash
python3 scripts/diagnose-api-ui-transport.py --target truenas
python3 scripts/diagnose-api-ui-transport.py --target cloud
python3 scripts/diagnose-api-ui-transport.py --target staging
```

Chaque commande ne fait que trois GET anonymes (`/api`,
`/api/ui/session`, `/api/ui/services`) avec timeout 3 s et
sans lire le corps des réponses. Un `401`/`403` n'est pas
un freeze du serveur. La cible `staging` est derrière Cloudflare
Access et peut répondre avec une redirection ou un 403 même si
la UI est utilisable depuis le navigateur connecté.
**La cible `truenas` (LAN direct 172.17.0.24:8091) est la
preuve de référence**, sans redirection Access.

### Diagnostic navigateur borné, lecture seule

```bash
node scripts/diagnose-production-api-ui-freeze.mjs truenas
node scripts/diagnose-production-api-ui-freeze.mjs cloud
node scripts/diagnose-production-api-ui-freeze.mjs staging
```

Les appels ne partagent pas les cookies de la session Chrome,
ne lisent pas de réponses JSON privées et n'utilisent aucun token.
Ils produisent des messages `phase` :
`launch_chromium`, `navigate`, `observe`, puis un rapport
`sampled`, `main_thread_unresponsive`,
`browser_or_transport_unavailable` ou un
`browser_diagnostic_timeout` précisant la dernière phase.
Une absence de DOM sur le site de connexion Cloudflare ne prouve
pas que la UI de FastAPI est défectueuse.

### Prochaine étape de déploiement

Ne pas redéployer `master` pour tester #379 :
`update-fastapi-sample.sh` utilise master par défaut.
Après revue et validation du hotfix, une recette TrueNAS peut
sélectionner un **SHA immuable** de #379 via `FASTAPI_SAMPLE_REF`
(dans le dépôt **nabla-compose**, pas le worktree FastAPI).
Contrôler l'empreinte sélectionnée dans les logs de build et
éviter le rechargement des images de base tant que la mémoire
de TrueNAS est dégradée. **Aucun déploiement du hotfix n'a
été exécuté par l'agent.**

## Cause supplémentaire isolée après la fusion de #379 (27/10)

La sonde HTTP côté workstation reçoit pour TrueNAS :
`GET /api = 200 (4ms)`, `GET /api/ui/session = 200 (2ms)`,
`GET /api/ui/services = 200 (766ms)`. La sonde Chromium
produit **`main_thread_unresponsive`** sur les cibles
`truenas` et `cloud` malgré `/api` et JS statiques HTTP 200,
aucune erreur `pageerror`. Un gel synchrone de l'UI est donc
une cause prioritaire. Le Cloud a même servi les modules du
hotfix #379, preuve que l'ancien correctif ne suffit pas.

**Boucle identifiée dans `api-global-service-filter.js`** :

```text
observer(#health-board, data-semantic-status)
  → scheduleRefresh() / requestAnimationFrame()
  → refreshGlobalFilter() / mapTrueNasStatus()
  → panel.dataset.semanticStatus = SAME_VALUE
  → nouvelle mutation de data-semantic-status
  → observer...
```

Le navigateur Chromium local confirme que deux affectations
identiques de `data-semantic-status` émettent deux notifications
`MutationObserver`. Le correctif #380 emploie désormais
`setDatasetValueIfChanged()`. Dans un fixture Chromium
réel, **100 cycles ne produisent qu'une seule notification**.
Les trois tests unitaires Node liés au garde-fou sont PASS,
dont un avec 1000 cycles. Cette preuve localisée ne remplace
pas encore le test de la page réelle après déploiement.

**Séquence opérateur sans déploiement parallèle** :

1. Laisser se terminer la commande TrueNAS déjà en cours qui
   déploie le commit **`fa13c08d`** ; recueillir ses étapes
   `3/6` à `6/6` et les éventuelles erreurs.
2. Depuis le worktree FastAPI qui contient #380, relancer
   `node scripts/diagnose-production-api-ui-freeze.mjs truenas`
   puis `node scripts/diagnose-production-api-ui-freeze.mjs cloud`.
3. Après revue/validation de #380, tester son commit immuable
   sur TrueNAS et comparer `main_thread_unresponsive` à
   `sampled`. Ne pas conclure au succès avant cette preuve.

Les GET Python vers Cloud et `sample.albandrieu.com` renvoient
`403`, alors que Chromium reçoit `200` depuis Cloud :
ces différences entre clients ne constituent pas un diagnostic
de crash serveur. La cible **`truenas` LAN direct** est la
plus interprétable pour l'UI locale.

## Nouvelle réception opérateur après #379 sur TrueNAS (27/10)

`FASTAPI_SAMPLE_REF=fa13c08db05ce8ce086d2366e1f35706913f05be
./scripts/truenas/update-fastapi-sample.sh` a **terminé 6/6** :
HTTP healthy 4/4, Prometheus/Gatus contrat OK, observer OK,
pfSense RBAC `warning` facultatif. L'image ne publie toujours
pas `build_revision`, mais la provenance de la construction est
présente dans le journal opérateur.

Playwright **après** ce déploiement a confirmé de nouveau :
`truenas: /api=200, pageErrors=0, main_thread_unresponsive` ;
`cloud: /api=200, pageErrors=0, main_thread_unresponsive`.
Le hotfix #379 est donc **insuffisant** pour supprimer le gel.

### Correctif #380 : statut TrueNAS sans réécriture cyclique

Le filtre global observait `data-semantic-status` dans
`#health-board` puis réaffectait `panel.dataset.semanticStatus`
à chaque frame, même pour une valeur inchangée.
`setDatasetValueIfChanged(panel, "semanticStatus", status)` coupe
la boucle ; les métadonnées `probeKinds`, `presentationGroup`
et `environments` utilisent le même garde-fou.
Une reproduction Chromium synthétique montre une seule
mutation en 100 cycles après correction ; tests Node
sur 1000 cycles idempotents PASS.
La page complète doit encore être retestée après déploiement.

### Mode de secours `?ui_safe=1` (nouveau dans #380)

Si un autre enrichisseur DOM reste défectueux, la page
`http://172.17.0.24:8091/api?ui_safe=1` contourne tous
les installateurs UI avancés : **catalogue public uniquement**,
`/api/ui/services` avec délai 6,5 s, pas d'auth OWNER,
pas de probes privées ni actions de mutation.

Après une recette #380 réussie, comparer :

```bash
node scripts/diagnose-production-api-ui-freeze.mjs truenas
node scripts/diagnose-production-api-ui-freeze.mjs truenas --safe
node scripts/diagnose-production-api-ui-freeze.mjs cloud
```

**Avant le déploiement de #380, `ui_safe` n'est pas pris en
charge par la version fa13c08d**. Ne pas interpréter un
`main_thread_unresponsive` en mode safe avec l'ancienne
version comme un échec du mode de secours.

## Contrôle Chrome sans secrets

1. Ouvrir DevTools → **Performance** ; enregistrer 5 s sur
   `/api`, puis arrêter.
2. Repérer les longues tâches JS (`requestAnimationFrame`,
   `MutationObserver`) et le temps `Scripting`.
3. Dans Network, filtrer `Doc`, `Fetch/XHR`, `JS` ; contrôler
   les statuts/latences et l'éventuel échec d'import de modules.
4. Après le déploiement du hotfix, recharger sans cache, vérifier
   que les compteurs ne restent pas sur Loading et qu'un clic
   sur filtre ou détail reste réactif.
5. Avec TrueNAS simulé indisponible, confirmer le repli
   `UNKNOWN`/stale et **aucune boucle de render**.

N'utiliser ni `fastapi deploy`, ni modification d'environnement,
ni mutation TrueNAS dans cette procédure de diagnostic. La plateforme
FastAPI Cloud gère son propre déploiement après fusion approuvée.

## Confinement P0 — catalogue public prioritaire (28/10/2026)

Les PR #379 et #380 ont corrigé plusieurs écritures DOM qui redéclenchaient leurs propres MutationObserver. Après le déploiement TrueNAS FastAPI 1.25.0, l'opérateur signale toujours un gel de /api. L'hypothèse d'autres boucles reste à vérifier avec un navigateur. La réponse HTTP 200 de /health ou /api ne démontre pas que le thread principal du navigateur reste disponible. LiteLLM HTTP 401 est un incident d'authentification distinct, sans lien causal démontré avec le gel.

Pour contenir ce défaut, /api sans paramètre initialise uniquement le catalogue public, sans installer les observateurs de détails/probes et sans attendre les appels de contrôle de session. La navigation **/api?ui_full=1** conserve l'ancien tableau détaillé avec toutes les règles d'accès OWNER : ce paramètre n'accorde aucune identité supplémentaire. **/api?operator=1** préserve le parcours opérateur et **/api?ui_safe=1** préserve le mode strict public, sans lien d'accès aux détails. La page publique affiche un lien « Open detailed diagnostics » vers l'interface complète.

Compromis UX : le catalogue reste interactif par défaut, mais le tableau détaillé n'est plus chargé automatiquement. **Ce confinement ne corrige pas à lui seul une éventuelle boucle en mode complet.** Après publication, comparer les parcours normal, ui_full et ui_safe dans un vrai navigateur, enregistrer les Long Tasks et la réactivité du thread principal.

Validation locale sans GitHub Actions :
~~~bash
node --test tests/js/api-public-fast-start.test.mjs
node scripts/diagnose-production-api-ui-freeze.mjs truenas --safe
node scripts/diagnose-production-api-ui-freeze.mjs truenas
node scripts/diagnose-production-api-ui-freeze.mjs cloud
~~~

Ces tests n'affirment aucune modification de production : l'agent ne possède pas de canal d'exécution vers TrueNAS ni de session de déploiement FastAPI Cloud. Le test Node vérifie le contrat du code et non le comportement navigateur final.


## Retour du 28 octobre — Playwright bloqué AVANT /api

Le test Node n'a pas trouvé le fichier api-public-fast-start.test.mjs parce que le
checkout local ne contient pas encore la branche PR #381. Les trois lancements
Chromium ont échoué pendant launch_chromium, avec http=[] et pageErrors=0.
**Aucune requête HTTP vers Cloud ou TrueNAS et aucune évaluation DOM n'a eu
lieu.** Il ne s'agit donc pas d'une nouvelle preuve de gel du serveur ou du
frontend.

### Validation de PR #381 en worktree isolé

Sur TrueNAS, le sous-module FastAPI du dépôt nabla-compose est encore lié à
l'image immuable déjà déployée. Ne pas nettoyer ou écraser ce sous-module.

~~~bash
cd /mnt/cpool/compose/nabla-compose
FASTAPI_REPO="$PWD/fastapi-sample"
git -C "$FASTAPI_REPO" fetch origin fix/api-ui-public-fast-start-20261028

WT="$(mktemp -d /tmp/fastapi-ui-pr381.XXXXXX)"
rmdir "$WT"
git -C "$FASTAPI_REPO" -c submodule.recurse=false worktree add --detach \
  "$WT" origin/fix/api-ui-public-fast-start-20261028

test_status=0
(
  set -e
  cd "$WT"
  node --test tests/js/api-public-fast-start.test.mjs
  node scripts/diagnose-production-api-ui-freeze.mjs truenas --preflight
) || test_status=$?
git -C "$FASTAPI_REPO" worktree remove "$WT"
test "$test_status" -eq 0
~~~

Le test Node ne requiert ni réseau ni Playwright. Le preflight vérifie le
binaire Chromium associé au Playwright Python installé, sans ouvrir la page,
faire de requête HTTP, ni télécharger le navigateur. Il dépend de mise et uv.

La PR #381 distingue maintenant browser_launch_unavailable de
navigation_failed et navigation_timeout ; elle ne confond plus un HTTP
401/403, une redirection d'auth ou une page vide avec une UI saine.
Une classe de lancement fixe identifie le binaire Chromium absent, les
librairies système manquantes, le sandbox ou les permissions. Les chemins
exécutables et les erreurs brutes ne sont pas rendus.

Si le navigateur est absent, préférer effectuer cette validation depuis la
workstation ayant Chromium disponible. Installer Chromium est une action
facultative explicite, qui télécharge des données :

~~~bash
mise exec -- uv run --no-project --with playwright python -m playwright install chromium
~~~

Après réussite du preflight, comparer normal et les deux chemins explicites :

~~~bash
node scripts/diagnose-production-api-ui-freeze.mjs truenas --safe
node scripts/diagnose-production-api-ui-freeze.mjs truenas
node scripts/diagnose-production-api-ui-freeze.mjs truenas --full
node scripts/diagnose-production-api-ui-freeze.mjs cloud
node scripts/diagnose-production-api-ui-freeze.mjs cloud --full
~~~

La branche PR #381 n'est PAS déployée ; les URLs publiques ne valident pas
encore le mode public-first tant que le déploiement n'est pas effectué.
Aucune CI, rotation de clé ou modification du runtime n'est nécessaire.


## Résultat opérateur — PR #381 : tests oui, Chromium non ; catalogue lent

Depuis un worktree détaché `72b97623`, le test
`node --test tests/js/api-public-fast-start.test.mjs` a réussi **4/4**.
L'ancien `--preflight` a rendu `browser_diagnostic_failed`, phase
`spawn`, sans le moindre rapport Python : **ceci teste le runner, pas
Chromium ni le frontend**.

La sonde HTTP directe a produit les résultats suivants :
- TrueNAS : `/api=200` (3 ms), `/api/ui/session=200` (2 ms),
  `/api/ui/services=timeout_or_network_failure` après 3002 ms ;
- Cloud : `/api=403`, `/api/ui/session=403`,
  `/api/ui/services=403` depuis le client Python anonyme sans proxy.
  Ces statuts n'établissent pas que le navigateur authentifié reçoit
  également 403, ni que l'instance Cloud est hors service.

**Corrections dans #381, pas encore déployées :**

1. Le préflight `node ... truenas --preflight` utilise désormais
   directement le `python3` natif sans invoquer mise/uv ni télécharger de
   paquet. Si Playwright Python manque, il produit
   `state=playwright_python_missing`, `network_requests_sent=0`.
   `--native` permet aussi le test navigateur depuis ce même Python,
   **uniquement si le module Python et le binaire Chromium sont présents**.
2. Le runner capture stderr localement, ne le reproduit jamais, et ne
   publie qu'une classe d'échec fixe (mise/uv/dépendance/résolution/etc.).
   La navigation échouée, le refus HTTP 403 et le blocage réel
   `main_thread_unresponsive` restent des états distincts.
3. La sonde HTTP a un délai de 3 s pour `/api` et
   `/api/ui/session`, et de **7 s pour `/api/ui/services`** afin de
   mesurer son délai réel au-delà du plafond client 6,5 s.
4. La route publique serveur borne désormais la récupération Backstage
   à 1,5 s, l'instantané de santé à 0,7 s, puis affiche un inventaire
   embarqué et **des états UNKNOWN** si la preuve vivante manque.
   Deux tests asynchrones isolent les dépendances qui ne répondent jamais.

**Validation locale recommandée depuis le worktree PR #381 :**

~~~bash
node --test tests/js/api-public-fast-start.test.mjs \
  tests/js/api-chromium-preflight-runner.test.mjs
python3 -m pytest -q \
  tests/unit/test_browser_launch_failure_codes.py \
  tests/unit/test_cloud_browser_diagnostic_contract.py \
  tests/unit/test_ui_public_services.py
node scripts/diagnose-production-api-ui-freeze.mjs truenas --preflight
python3 scripts/diagnose-api-ui-transport.py --target truenas
python3 scripts/diagnose-api-ui-transport.py --target cloud
~~~

Exécuter la sonde Playwright réelle uniquement sur un hôte avec Chromium
fonctionnel : `node scripts/diagnose-production-api-ui-freeze.mjs truenas
--native` si Python natif dispose de Playwright, ou le lanceur mise/uv
si ce runtime est confirmé. Ne jamais interpréter un
`playwright_python_missing` ou un `browser_runner_failed` comme un
gel de la page. Le code public-first n'est pas encore déployé :
la validation Cloud/TrueNAS dépend d'une publication ultérieure approuvée.


## Avancement PR #381 — désactiver le coût des imports ESM en public (28/10)

**Cause de surcharge prouvée par lecture du code :** le `if (publicFirst)`
dans `api-health.js` ne protégeait pas le navigateur du chargement et de
l'évaluation de la trentaine d'imports statiques de ce module. Même en
mode `?ui_safe=1`, tous les modules du tableau avancé étaient résolus
avant que le navigateur ne puisse prendre la branche publique.

**Correctif publié dans la PR #381, non déployé :**

- `/api` importe `api-health-entry.js`, un petit amorceur avec
  **un seul import statique**, `api-public-services.js`.
- `/api?ui_safe=1` utilise uniquement ce catalogue read-only ; il masque
  les vues privées et n'autorise pas l'ouverture des diagnostics riches.
- `/api?ui_full=1` et `/api?operator=1` utilisent
  `import("./api-health.js")` pour charger le graphe complet de modules,
  dont la vérification normale d'identité OWNER/SERVICE. Le paramètre
  ne confère aucun privilège.
- Sur un échec du chargement dynamique, le frontend retrouve le catalogue
  public sans présenter une fausse santé opérationnelle.
- Les tests de contrat HTTP et Node vérifient le nouvel entrypoint, la
  restriction des imports statiques et l'isolation des modes.

**Recette locale dans un worktree de la branche #381 :**

```bash
node --test tests/js/api-public-fast-start.test.mjs \
  tests/js/api-chromium-preflight-runner.test.mjs
python3 -m pytest -q \
  tests/unit/test_api_ui_assets.py \
  tests/unit/test_ui_public_services.py \
  tests/unit/test_browser_launch_failure_codes.py \
  tests/unit/test_cloud_browser_diagnostic_contract.py
node scripts/diagnose-production-api-ui-freeze.mjs truenas --preflight
python3 scripts/diagnose-api-ui-transport.py --target truenas
```

En navigateur Chrome/Chromium **après un déploiement futur**, contrôler
dans Network que `/api` ne requiert **pas**
`/api/assets/api-health.js` ni ses modules riches, alors que
`?ui_full=1` les charge. Vérifier la réactivité des boutons de
filtre, les cartes, la sécurité OWNER et les sondes dans le mode riche.
Cela ne prouve pas encore la disparition d'une éventuelle boucle DOM :
aucune session Chromium réelle n'a été exécutée depuis cet agent.


## P1 — OWNER mobile LAN sans import riche, PR #382 (28/10/2026)

**Symptôme utilisateur :** depuis le Wi-Fi du domicile, `/api/ui/session`
retourne `{ "authenticated": false, "readOnlyDiagnostics": true }` et
`http://172.17.0.24:8091/api` est joignable. Cependant, `?operator=1`
n’affiche pas `Unlock diagnostics`. Cela prouve l’accessibilité directe
LAN et la lecture seule autorisée, **pas** une session OWNER.

**Défaut de frontend :** `#owner-session-panel` part masqué dans HTML.
Avant #382, le rendre visible exigeait d’importer tout `api-health.js`
par `?operator=1` ; cet import contient les observateurs et le chemin
qui a déjà produit `main_thread_unresponsive`. Le code pouvait geler
avant `panel.hidden = false`. On ne peut pas attribuer à coup sûr le
gèle de ce téléphone sans une mesure Chromium sur son runtime.

**Contrat #382 :**

1. Une entrée `Owner access` est présente dans la navigation HTML même
   lorsque le JavaScript du catalogue échoue.
2. `/api?operator=1` reste sur le catalogue public rapide et fait
   apparaître immédiatement `Unlock diagnostics`, via un module léger.
3. `/api?ui_full=1` déclenche *uniquement sur demande* le tableau riche.
   `?operator=1&ui_full=1` combine les deux sans double binding.
4. Le retour depuis 4G/5G vers le Wi-Fi revalide l’état de session sur
   les événements `online`, `pageshow` et `visibilitychange`. Aucun
   événement réseau n’authentifie OWNER automatiquement.
5. `?ui_safe=1` garde la priorité et ne monte pas la connexion OWNER.
   Les routes privées requièrent toujours une clé correcte, un cookie
   signé et une source approuvée.

**Recette sans CI et sans toucher aux secrets :**

```bash
# Depuis un checkout fastapi-sample de la PR #382, PAS nabla-compose
node --test tests/js/api-public-fast-start.test.mjs
node --test tests/js/api-chromium-preflight-runner.test.mjs
python3 -m pytest -q tests/unit/test_api_ui_assets.py
```

Après recette et déploiement **par SHA immuable** sur TrueNAS :

- Ouvrir `/api` : lien `Owner access` visible, catalogue réactif.
- Ouvrir `/api?operator=1` : bouton `Unlock diagnostics` visible sans
  module `api-health.js` dans l’onglet Network.
- Essayer la clé via le formulaire (jamais en URL ou dans un log).
  Un succès doit produire `authenticated=true` sur le même navigateur.
- Un `403 source_unverified` impose d’examiner la chaîne HAProxy /
  Cloudflare et les CIDR de proxy connus, sans contourner l’ACL.
- Après succès, cliquer `Open detailed diagnostics`; le gel éventuel
  du tableau riche est une **anomalie distincte** à corriger avant GO.

**État :** modifications publiées dans la PR #382 ; tests Node et recette
Chromium réelle **non exécutés ici**. Le dernier runtime TrueNAS attesté
dans le journal est `fa13c08d` ; le build de `0266f20d` a échoué à
l’étape Docker 3/6 avec l’ancienne image conservée. La PR #289 de
`nabla-compose` est fusionnée, mais le classifieur ne démontre aucune
cause tant que son journal privé n’a pas été traité localement.
