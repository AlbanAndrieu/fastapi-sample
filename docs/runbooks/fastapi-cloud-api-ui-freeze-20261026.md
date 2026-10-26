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
