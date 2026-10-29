# Recette consolidée FastAPI — UI OWNER, TrueNAS et sondes

**29 octobre 2026 · PR #382 · exécution sur demande uniquement.**
Cette recette ne déploie pas, ne redémarre aucun conteneur, ne modifie pas
les clés, les ACL ou les configurations. Les tests peuvent créer des caches
dans le checkout isolé. Elle ne consomme pas de crédits GitHub Actions.

## Objectif et états

Vérifier séparément le code local, le transport HTTP TrueNAS/HTTPS,
l'authentification, le scrape, l'échec Docker historique, le navigateur
et le parcours manuel OWNER sur smartphone.

- PASS : contrat testé et accepté sur le point d'observation sélectionné.
- FAIL : test échoué, authentification métrique anormale ou gel démontré.
- DENIED : HTTP 401/403 ; contrôle d'accès, pas nécessairement une panne.
- UNVERIFIED : données ou conclusion insuffisantes ; ne pas afficher vert.
- NOT_RUN : dépendance absente ou étape indisponible.

La sortie est un JSON expurgé. Les codes de sortie sont 0 (précontrôles
réalisés, acceptation OWNER manuelle toujours requise), 1 (FAIL),
2 (incomplet / DENIED). Aucun code de sortie n'autorise un déploiement.

## 1. Préparer un checkout isolé sur TrueNAS

~~~bash
cd /mnt/cpool/compose/nabla-compose

git -C fastapi-sample fetch origin \
  fix/owner-entry-public-first-20261028

git -C fastapi-sample worktree add --detach \
  /mnt/cpool/compose/fastapi-sample-pr382-acceptance \
  origin/fix/owner-entry-public-first-20261028

cd /mnt/cpool/compose/fastapi-sample-pr382-acceptance
git rev-parse HEAD
~~~

Ne pas changer la branche du sous-module FastAPI en cours d'utilisation
par TrueNAS. Si ce worktree existe déjà, ne pas relancer worktree add :
inspecter git worktree list et sa révision d'abord.

## 2. Contrats locaux, sans réseau

~~~bash
python3 scripts/truenas/validate-fastapi-ui-acceptance.py \
  --phase offline
~~~

Le lanceur exécute deux suites Node, les contrats UI pytest et ses
tests Python unittest. Sans Node ou pytest, l'étape est NOT_RUN.
Les journaux bruts ne sont pas transmis ; si un test échoue,
relancer la commande concernée séparément dans un terminal privé.

## 3. Transport TrueNAS, HTTPS, métriques et build historique

~~~bash
python3 scripts/truenas/validate-fastapi-ui-acceptance.py \
  --phase runtime \
  --target truenas \
  --target staging \
  --build-log /tmp/tmp.ngofCbFlgw \
  --extended
~~~

- TrueNAS : sondes épinglées à http://172.17.0.24:8091.
- Staging : sondes épinglées à https://sample.albandrieu.com.
- Le build-log est optionnel. Il est classé localement par le script
  nabla-compose fusionné en #289, sans afficher son contenu.
  Si ce fichier temporaire n'existe plus, omettre l'option.
- Si le journal exige sudo, appeler le classifieur Compose séparément
  avec les droits nécessaires ; ne pas élever toutes les suites Node.
- Extended exécute une recette Compose existante (1 cycle, lecture seule).
  Un exit 0 de Compose peut contenir WARN : le résultat global reste
  UNVERIFIED jusqu'à lecture du compte rendu privé.
- Sans jeton de scrape dédié, HTTP 401 anonyme pour /metrics est attendu,
  mais le scrape Prometheus reste UNVERIFIED.

Ne pas relancer le build Docker avant d'identifier sa classe de panne.

## 4. Recette navigateur réelle, facultative

~~~bash
python3 scripts/truenas/validate-fastapi-ui-acceptance.py \
  --phase runtime --target truenas --browser
~~~

Cette commande ne télécharge pas Playwright ou Chromium. Si l'environnement
Python natif ne possède pas les deux, le navigateur est NOT_RUN, jamais PASS.
Un checkout isolé depuis la workstation peut tester l'origine LAN si
Chromium y est installé.

| Mode | URL examinée | Contrat |
| --- | --- | --- |
| Public | /api | sampled, sans module riche ni bouton OWNER |
| Secours | /api?ui_safe=1 | sampled, sans module riche ni OWNER |
| OWNER | /api?operator=1 | sampled, bouton Unlock visible sans module riche |
| OWNER riche | /api?ui_full=1&operator=1 | sampled, module riche et bouton OWNER visibles |

Les requêtes sont bornées ; aucun cookie, clé, corps privé ou en-tête
d'authentification n'est enregistré.

## 5. Acceptation manuelle depuis le smartphone Wi-Fi

Sur le SHA réellement déployé :

1. Ouvrir https://sample.albandrieu.com/api : lien Owner access visible.
2. Ouvrir https://sample.albandrieu.com/api?operator=1 : bouton Unlock visible.
3. Saisir DIAGNOSTICS_ACCESS_KEY dans le formulaire HTTPS, jamais dans l'URL.
4. Dans le même navigateur, lire /api/ui/session : authenticated doit être true.
5. Ouvrir /api?operator=1&ui_full=1 : vérifier Details, TrueNAS, sondes
   DNS/TCP/TLS/HTTP, Access/token, Gatus, Prometheus et relations de services.
6. Depuis un réseau non autorisé, vérifier le refus des données OWNER.
   Ne pas modifier les CIDR ni faire confiance à X-Forwarded-For sans
   vérifier l'identité du proxy immédiat.

HTTP 401 signifie clé absente ou incorrecte. HTTP 403 source_unverified
signifie source/proxy non attesté ; origin_unverified signifie refus de
l'origine HTTPS ; HTTP 503 indique une configuration indisponible.
Wi-Fi ne signifie pas identité OWNER.

## 6. Condition de GO

GO uniquement si : tests locaux PASS, build maîtrisé, six étapes de
déploiement TrueNAS acceptées avec SHA attesté, navigateur interactif
sur les quatre modes et OWNER smartphone authentifié. Le script
n'accorde jamais le GO automatiquement.

Voir aussi [roadmap canonique](../engineering-roadmap.md) et
[historique du gel UI](fastapi-cloud-api-ui-freeze-20261026.md).
