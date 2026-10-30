# Runbook — validation consolidée Cloud, TrueNAS et OWNER

Cette procédure décrit **une recette de lecture seule**, à exécuter dans
un checkout FastAPI Sample **isolé**. Elle ne redéploie rien, ne change
aucune clé/ACL, n'installe aucun paquet et n'appelle pas GitHub Actions.
Elle peut produire des caches de tests dans le checkout. Les preuves
datées sont dans [les incidents](../incidents.md) et la décision active
dans [la roadmap](../engineering-roadmap.md).

## 1. Préparer un checkout séparé du runtime TrueNAS

Confirmer que le dépôt FastAPI existe sous `nabla-compose/fastapi-sample`
**avant** de lancer ces commandes. Ne jamais changer la branche de
l'éventuel sous-module utilisé par le runtime :

```bash
cd /mnt/cpool/compose/nabla-compose
git -C fastapi-sample rev-parse --show-toplevel
git -C fastapi-sample worktree list

git -C fastapi-sample fetch origin   fix/owner-entry-public-first-20261028

git -C fastapi-sample worktree add --detach   /mnt/cpool/compose/fastapi-sample-pr382-acceptance   origin/fix/owner-entry-public-first-20261028

cd /mnt/cpool/compose/fastapi-sample-pr382-acceptance
git rev-parse HEAD
```

Si le chemin source ou la branche distante n'existe pas, **STOP** :
retrouver le checkout Git FastAPI réel, sans toucher au conteneur.
Si le worktree cible existe déjà, **ne pas répéter** `worktree add` ;
vérifier son SHA et son état avant toute mise à jour. Ne jamais
exécuter `set -euo pipefail` avec `source` dans un shell interactif.

## 2. Contrôles locaux L1 — hors réseau

```bash
python3 scripts/truenas/validate-fastapi-ui-acceptance.py --phase offline
```

Le lanceur exécute les contrats Node, pytest et unittest prévus
par le dépôt, sans installation ni CI. Un outil manquant devient
`NOT_RUN`. Les sorties brutes des enfants sont masquées ; si un
test échoue, le relancer **seul** dans un terminal privé.

Les niveaux L2/L3 restent ceux du
[skill local-first](../../.agents/skills/local-first-quality/SKILL.md)
et exigent un HEAD propre. Le lanceur d'acceptation ne remplace pas la
quality gate de publication.

## 3. Transport TrueNAS/HTTPS et ancien build Docker

```bash
python3 scripts/truenas/validate-fastapi-ui-acceptance.py   --phase runtime --target truenas --target staging   --build-log /tmp/tmp.ngofCbFlgw --extended
```

Le chemin `--build-log` est **facultatif** : le retirer s'il n'existe
plus. Il appelle le classifieur de `nabla-compose` pour l'échec
Docker historique. Si les permissions empêchent sa lecture, exécuter
le classifieur séparément avec des droits appropriés ; ne pas lancer
tous les tests en root. Ne jamais copier le journal privé en PR.

`--extended` demande un seul cycle de diagnostic Compose. Il peut
retourner 0 avec des avertissements : le lanceur le laisse
`UNVERIFIED` jusqu'à analyse des preuves. Il ne construit et ne
redémarre aucun service. Aucun nouveau build avant classification
de la panne précédente.

Sans scrape authentifié, le `401` anonyme attendu sur `/metrics`
ne confirme pas `up{job="fastapi_sample"} == 1`.

## 4. Navigateur — choisir une cible explicite

Si Playwright Python/Chromium natifs sont **déjà** présents :

```bash
# Depuis une machine qui accède réellement à TrueNAS
python3 scripts/truenas/validate-fastapi-ui-acceptance.py   --phase runtime --target truenas --browser

# Depuis un client autorisé sur FastAPI Cloud
python3 scripts/truenas/validate-fastapi-ui-acceptance.py   --phase runtime --target cloud --browser
```

Le navigateur vérifie quatre parcours : `/api`, `?ui_safe=1`,
`?operator=1`, et `?ui_full=1&operator=1`.
Le bouton OWNER ne doit pas dépendre du chargement riche.
Un `main_thread_unresponsive` ou `ui_loading_without_content`
est distinct d'un `http_access_restricted`.
Pour n'inspecter que `ui_full=1` sur Cloud, suivre le
[runbook de gel UI](fastapi-cloud-api-ui-freeze-20261026.md).

L'absence de Chromium/Playwright = `NOT_RUN`, pas `PASS`.
La sonde anonyme ne transmet ni cookie, ni clé, ni preuve OWNER.
Le navigateur mesure la version **déployée**, pas le code de la PR.

## 5. Recette manuelle OWNER sur smartphone

Sur le **SHA effectivement déployé** et depuis le Wi-Fi approuvé :

1. Ouvrir `https://sample.albandrieu.com/api`.
   Résultat attendu : lien `Owner access` visible.
2. Ouvrir `https://sample.albandrieu.com/api?operator=1`.
   Résultat attendu : bouton `Unlock diagnostics` visible.
3. Saisir `DIAGNOSTICS_ACCESS_KEY` dans le formulaire HTTPS.
   Ne jamais mettre la clé dans une URL ou un log.
4. Lire `/api/ui/session` dans **le même navigateur**.
   Résultat attendu : `authenticated=true`.
5. Ouvrir `/api?operator=1&ui_full=1`.
   Résultat attendu : cartes DNS/TCP/TLS/HTTP, Access/token, Gatus,
   Prometheus/exporters, TrueNAS `Details` et liens de dépendances
   interactifs, sans gel.
6. Refaire un accès depuis une source non approuvée.
   Résultat attendu : les données OWNER sont refusées.

Interpréter `401` comme un problème de clé, `403 source_unverified`
comme une source/proxy non approuvé, `403 origin_unverified` comme
une origine rejetée et `503` comme une configuration absente.
Le Wi-Fi ne confère pas OWNER. Ne pas élargir les CIDR ni accepter
un `X-Forwarded-For` sans proxy vérifié.

## 6. Verdict et clôture

Le JSON consolidé utilise `PASS`, `FAIL`, `DENIED`,
`UNVERIFIED` et `NOT_RUN`. Son exit 0 signifie seulement que
les **précontrôles exécutés** sont passés ; la validation humaine
OWNER reste obligatoire. Une image/SHА, un build 6/6, les tests
L3 et les cartes riches doivent être attestés séparément.

**GO manuel** : build expliqué, SHA/image confirmé, tests L3 valides,
mode riche interactif, OWNER autorisé et refus WAN vérifié.
Sinon **HOLD**, conserver le mode public léger.
