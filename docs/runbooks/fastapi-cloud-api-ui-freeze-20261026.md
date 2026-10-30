# Runbook — interface `/api` bloquée (Cloud ou TrueNAS)

Ce runbook décrit une **procédure de diagnostic réutilisable**, sans statut
de PR ni résumé chronologique. Les observations du 26–30 octobre sont dans
[le registre d'incidents](../incidents.md) et
[l'archive intégrale](../archive/2026-10-30/fastapi-cloud-api-ui-freeze-20261026-history.md).
Pour une recette complète, utiliser
[la validation OWNER/TrueNAS/Cloud](fastapi-truenas-owner-acceptance-20261029.md).
Pour décider de la prochaine action, utiliser
[la roadmap active](../engineering-roadmap.md).

## Correctif OWNER-first — PR #383 (30/10/2026)

La PR [#382](https://github.com/AlbanAndrieu/fastapi-sample/pull/382)
est **fusionnée**, mais aucune recette Cloud du SHA déployé n'est encore
attestée. Depuis `master` `7fbd2f61`, le démarrage simultané
`?operator=1&ui_full=1` importait le contrôleur OWNER et le graphe riche
en parallèle. L'installation du gestionnaire `Unlock diagnostics`
n'était pas garantie avant le chargement lourd.

La [PR #383](https://github.com/AlbanAndrieu/fastapi-sample/pull/383)
conserve le catalogue public immédiatement accessible et **attend**
l'installation des contrôles puis l'authentification OWNER avant le
premier import riche. Pour `?ui_full=1` sans OWNER, une capacité
`readOnlyDiagnostics` vérifiée est exigée ; 401/403/timeout gardent le
catalogue public. Les doubles abonnements au catalogue sont empêchés.
La disparition du fallback attend `health-board-refreshed`, pas
seulement l'import du module. Aucun paramètre URL ne confère OWNER.

**Contournement tant que #383 n'est pas déployée :** ouvrir
`/api?operator=1` sans `ui_full=1`, puis utiliser le formulaire
`Unlock diagnostics` depuis une source approuvée. Le mode
`/api?ui_safe=1` reste indépendant. Le contournement ne résout pas
un gel éventuel du tableau riche après authentification.

**Recette requise :** `just ui-quick` sur le HEAD #383, puis Chromium
sur le SHA **effectivement déployé** : `?operator=1&ui_full=1`
avant login doit permettre de cliquer `Unlock diagnostics` sans
charger `api-health.js`. Après login, vérifier les détails. Un
`main_thread_unresponsive` après l'import riche reste un incident
distinct et n'est **pas** marqué résolu par cette PR.

## Validation locale de #383 et incident nodeenv du 30/10

Sur TrueNAS, au SHA `cd3eb037`, `just ui-quick` a réussi
**35 tests sur 35** (165 ms). Le contrôle OWNER, les refus 401/403/503
et le fallback public sont validés **sans navigateur réel**.

`just quality` a ensuite passé les vérifications de base Git, de
suppression destructive et de mode exécutable. Il s'est arrêté dans
`nodeenv.py` avec `ValueError: invalid literal for int() with base 10:
'0-alpha'` pendant la préparation de pre-commit. Cela ne constitue
**ni un échec du lint JS ni une réussite de la quality gate**.

La PR #383 choisit maintenant `default_language_version: node: system`
dans `.pre-commit-config.yaml`. Tous les hooks restent actifs ;
Node/npm doivent être disponibles sur le PATH. Cette politique évite
la résolution d'une version Node distante potentiellement incompatible
avec le parseur de `nodeenv`. Aucune installation ni migration Python
n'est nécessaire pour ce correctif.

Reprendre depuis le worktree propre à la PR et le HEAD actuel :

```bash
cd /mnt/cpool/compose/fastapi-sample-pr383-acceptance
git status --short
git fetch origin fix/ui-owner-auth-before-rich-import-20261030
git switch --detach origin/fix/ui-owner-auth-before-rich-import-20261030
node --version
npm --version
just ui-quick
just quality
```

Si `just quality` échoue encore, conserver le **premier échec causal**
et son nom de hook (pre-commit peut ensuite rencontrer d'autres erreurs
que la précédente trace masquait). Ne pas effacer le cache pre-commit
global, ne pas modifier la venv partagée, ne pas ignorer de hook et
ne pas considérer le SHA publiable avant validation. La recette Chromium
Cloud réelle, sans déploiement implicite, reste obligatoire.

## 1. Distinguer disponibilité et interface bloquée

Comparer, depuis **le même navigateur et le même réseau** :

| URL | Contrat attendu | Ce que le résultat prouve |
| --- | --- | --- |
| `/api?ui_safe=1` | Catalogue public léger | Le parcours de secours peut être utilisable indépendamment de l'UI riche |
| `/api` | Catalogue public sans module riche | Le chargement de base est fonctionnel |
| `/api?operator=1` | Bouton `Unlock diagnostics` ; pas d'import riche | L'entrée OWNER est visible, **sans authentifier** |
| `/api?ui_full=1` | Cartes/sondes riches et page interactive | Le bundle avancé fonctionne côté navigateur |

**Ne pas conclure** qu'un `GET /api` HTTP 200 prouve le rendu Chromium.
Un `401/403` peut désigner une politique d'accès ; il ne signifie pas que
le processus FastAPI ou l'origine réseau est arrêté. Le paramètre
`ui_safe=1` n'accorde aucun privilège.

## 2. Vérifier le code et le navigateur, sans installation

1. Identifier le **SHA déployé**, son environnement et le point d'observation.
   Un SHA de PR ne prouve pas le contenu d'une image Cloud/TrueNAS.
2. Sur un checkout isolé de FastAPI Sample, exécuter `just agent-context ui`.
   Le résultat sélectionne les fichiers et le skill utiles sans réseau.
3. Exécuter `just ui-quick`. Cela vérifie les contrats Node ciblés, sans
   npm install ni GitHub Actions ; cela **ne vaut pas** recette navigateur.
4. Si Playwright/Chromium natifs sont déjà disponibles, exécuter la
   sonde spécifique au contexte :

```bash
# FastAPI Cloud : vue riche uniquement (aucun cookie ni clé OWNER)
node scripts/diagnose-production-api-ui-freeze.mjs cloud --full --native

# TrueNAS, depuis une machine qui accède réellement au LAN
node scripts/diagnose-production-api-ui-freeze.mjs truenas --full --native
```

5. Pour confronter les quatre modes et les chemins HTTP, utiliser le
   [lanceur consolidé](fastapi-truenas-owner-acceptance-20261029.md),
   avec `--phase runtime --target cloud --browser` ou `truenas`.

Le navigateur produit notamment :
- `main_thread_unresponsive` : thread principal indisponible ;
- `ui_loading_without_content` : thread réactif mais écran Loading sans lignes ;
- `http_access_restricted` / redirection : accès refusé, **DENIED** ;
- `sampled` : le DOM a pu être lu ; vérifier encore les lignes et les actions.

Les états absents ou expirés sont `UNVERIFIED` ou `NOT_RUN`, jamais `PASS`.
Ne pas exposer logs bruts, cookies, clés, jetons ou réponses OWNER.

## 3. Chercher la première couche en défaut

- **Import ESM** : `api-health-entry.js` sépare le catalogue léger
  de `api-health.js` chargé explicitement en mode riche.
- **Boucle DOM** : examiner les `MutationObserver`, animations répétées,
  réécritures `hidden`/`class` et dispatchs `service-filter-changed`.
  La PR #382 limite les réconciliations de diagnostics et les mutations
  de visibilité identiques. Ce correctif est un candidat, non une
  preuve qu'il est déjà déployé.
- **API/transport** : distinguer DNS/TCP/TLS, HTTP, origine, contrôle d'accès
  et lecture du tableau. Les sondes lentes ne doivent pas bloquer le
  catalogue public.
- **Identité OWNER** : vérifier séparément `/api/ui/session` et le
  formulaire HTTPS sur le réseau approuvé. `readOnlyDiagnostics=true`
  ne signifie pas `authenticated=true`.

## 4. Acceptation avant clôture

La recette réussit **sur le SHA effectivement déployé** lorsque le mode
public reste interactif, les cartes du mode riche chargent sans boucle,
les détails sont navigables, les refus 401/403 restent correctement classés
et la recette OWNER fonctionne sans publier de secret.

Un correctif non déployé, une réponse HTTP 200, un `sampled` sans
cartes, ou une gate locale réussie sur un autre SHA ne ferment pas l'incident.
Respecter `AGENTS.md` : aucune fusion, CI, rotation de secret ni
publication automatique au cours du diagnostic.
