# Runbook — interface `/api` bloquée (Cloud ou TrueNAS)

Ce runbook décrit une **procédure de diagnostic réutilisable**, sans statut
de PR ni résumé chronologique. Les observations du 26–30 octobre sont dans
[le registre d'incidents](../incidents.md) et
[l'archive intégrale](../archive/2026-10-30/fastapi-cloud-api-ui-freeze-20261026-history.md).
Pour une recette complète, utiliser
[la validation OWNER/TrueNAS/Cloud](fastapi-truenas-owner-acceptance-20261029.md).
Pour décider de la prochaine action, utiliser
[la roadmap active](../engineering-roadmap.md).

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
