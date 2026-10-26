# Incident /api Cloud — boucle DOM après fusion PR #378

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

**Fichier Playwright absent :** `node
scripts/diagnose-production-api-ui-freeze.mjs` a donné
`MODULE_NOT_FOUND` parce que le fichier a été ajouté dans la
**PR #379 encore ouverte**, et non sur `master`.
Il ne s'agit ni d'une erreur Node 24.22.1 ni d'une preuve de bug
runtime. Depuis le checkout du dépôt, obtenir cette branche
dans un worktree séparé (ne pas réinitialiser les modifications
courantes) :

```bash
git fetch origin fix/api-ui-observer-render-loop-20261026
git worktree add /tmp/fastapi-ui-freeze-pr379 \
  origin/fix/api-ui-observer-render-loop-20261026
cd /tmp/fastapi-ui-freeze-pr379
node scripts/diagnose-production-api-ui-freeze.mjs
```

Ce script importe le paquet **Playwright** et nécessite Chromium ;
le dépôt déclare déjà un autre vérificateur Playwright.
Si le module ou le binaire Chrome est absent, conserver le message
exact de cette nouvelle erreur et utiliser les DevTools du
navigateur plutôt que des installations globales non supervisées.

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

Depuis un checkout local doté de Playwright et du navigateur Chromium,
sans accès OWNER ni secret de production :

```bash
node scripts/diagnose-production-api-ui-freeze.mjs
```

La sonde vérifie le code HTTP de `/api`, les requêtes même origine
vers les routes UI essentielles, les erreurs JavaScript (compte
uniquement), les cartes encore sur Loading, les long tasks et
la réactivité du thread JS. Elle **ne lit ni cookies ni réponse
JSON des services** et ne déclenche pas d'appel de diagnostic OWNER.
Elle attend 14 secondes après le chargement DOM, puis limite
l'extraction du rapport à trois secondes.

**Limite :** sans connectivité DNS à FastAPI Cloud ni binaire
Playwright installé, ce test ne peut pas être exécuté par l'agent.
Les tests unitaires Node de pure logique ne remplacent pas ce
contrôle end-to-end.

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
