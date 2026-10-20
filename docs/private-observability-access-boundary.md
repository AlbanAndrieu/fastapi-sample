# FastAPI — plan public minimal / télémétrie privée

Date : 2026-10-18. **Spécification uniquement, sans modification runtime**.
Suivi : [FastAPI #352](https://github.com/AlbanAndrieu/fastapi-sample/issues/352).
Dépendances : [Site Alban #233](https://github.com/AlbanAndrieu/nabla-site-alban/issues/233) et
[Nabla Compose #262](https://github.com/AlbanAndrieu/nabla-compose/issues/262).

## Pourquoi la protection actuelle ne suffit pas

`nabla/access_control.py` connaît un ensemble borné de chemins diagnostiques, mais retourne
`call_next(request)` si `DIAGNOSTICS_ACCESS_KEY` est absent. Une nouvelle route/variante
peut donc rester publique par omission. Les routes opérateur, dashboards HTML, MCP,
métriques, WebSocket éventuels, OpenAPI, erreurs et URLs de provenance doivent être
inventoriés **depuis les routes réellement enregistrées**, pas uniquement une liste statique.

Un premier `/api/public-topology` existe avec projection assainie; il faut généraliser
ce modèle en **schémas de sortie explicites**, sans redaction a posteriori de JSON brut.

## Contrat v1 proposé

| Classe | Endpoint / comportement | Identité |
| --- | --- | --- |
| PUBLIC | `/api/public-homelab/v1` : identifiants et libellés publiables, catégories, états agrégés volontairement grossiers, date de collecte optionnelle sans détail de sonde | Anonyme; objet DTO allowlist validé |
| OWNER | `/private/ops/api/v1/*` : inventaire, preuves, topology, metrics, health board, diagnostic, latences | Cloudflare Access JWT vérifié à l'origine, `aud` + `iss` + signature + `exp` + `sub`/acteur autorisé |
| SERVICE | collectors/importers internes sur endpoints dédiés (aucune identité navigateur) | identifiants et clés machine distincts, réseau privé, expiration/rotation, privilèges minimaux |
| INTERNAL | `/metrics`, endpoints runtime TrueNAS/management, cache-reset, admin, debug, MCP opérateur | LAN/private uniquement, authentification de workload explicite; jamais sur un host partagé public |

Ne pas mettre un jeton `DIAGNOSTICS_ACCESS_KEY` ni un Cloudflare Service Token dans un bundle
Vercel, du HTML, une URL, un cookie accessible JavaScript ou une requête client publique.
Le JWT Access ne se remplace pas par le seul `cf-access-authenticated-user-email` ou par
la confiance dans un `Host`/IP source. Si l'origine est joignable autrement,
elle doit toujours rejeter une identité absente/non vérifiée.

## Roadmap de livraison

- [ ] **P0 policy catalogue d'endpoints** : générer un manifeste des routes à partir de
      `app.routes` dans `server_all:app` et classer tous les GET/POST/WebSockets/MCP
      (y compris aliases `/api/homelab-*`, `/api/health-board`, `/healthz`,
      `/sickz`, `/metrics`, `/docs`, `/openapi.json`, `/admin`). Une route
      non classée/diagnostique inconnue ne devient jamais publique par défaut.
- [ ] **P0 DTO public** : `nabla/api/homelab_topology.py` et `/api/public-topology`
      servent de point de départ; créer schéma versionné public, tests de validation
      et tests de **suppression par allowlist** des infos host/port/URL, IDs runtime,
      description non publique, règles Access et sources. Ne pas exposer les métriques.
- [ ] **P0 compatibilité/cutover** : conserver le contrat riche sous identité privée
      uniquement. Adapter le site public en premier si nécessaire (réponse neutre
      temporaire acceptable), puis activer fail-closed sur FastAPI Cloud et TrueNAS.
      Vérifier l'absence de fallback `DIAGNOSTICS_ACCESS_KEY=None` en production.
- [ ] **P1 Access origin** : dépendance JWT RS256 validée contre JWKS Cloudflare
      (clés cache TTL court, fail-closed si JWKS indisponible hors cache valide,
      issuer/audience exacts, exp/nbf/subject et autorisation de l'identité);
      séparer JWT humain et machine. Ne pas accepter un header fourni par un client
      non authentifié. Plan de protection/revocation/logout et tests horloge.
- [ ] **P1 UI opérateur** : écran réutilisant les états FastAPI read-only sous
      hostname `ops.albandrieu.com`; endpoints privés à granularité et pagination bornées,
      anti-N+1, debounce/singleflight de probes. Par défaut CSP stricte,
      CORS same-origin, `Cache-Control: private, no-store`, `Pragma: no-cache`,
      `X-Robots-Tag: noindex, nofollow`, `Referrer-Policy: no-referrer`;
      jamais d'URL interne dans un header public `X-*-Primary`.
- [ ] **P1 tests négatifs** : anonyme / mauvais aud, issuer, signature, subject /
      token expiré / imposture de header / credentials absents / accès LAN direct /
      erreur upstream / absence de clé / redirection / essais de variantes.
      Vérifier que les refus ne sérialisent aucune preuve privée.
- [ ] **P1 supervision distincte** : métriques Prometheus uniquement par scrape
      privé; exposer des agrégats non sensibles au public, sans accès direct à
      PromQL ni sortie brute.
- [ ] **P2 option Keycloak** : accepter OIDC Keycloak via Cloudflare Access uniquement
      après disponibilité, sauvegardes, rotation, TLS, readiness et audit; ne pas
      faire dépendre la réduction urgente des fuites de ce déploiement.

## Règles de sécurité

- 401/403 ne prouvent **pas** un backend opérationnel; séparer politique Access,
  tentative authentifiée et reachability origine interne.
- Fail closed en cas d'indisponibilité du provider, de clés JWT ou de secret;
  pas de `allow` sur exception.
- Mots de passe, service tokens, credentials, JWT, PII et cookies ne doivent jamais
  apparaître dans logs, réponses, exception HTML ou trace Sentry.
- Une preuve `NOT_RUN` n'est pas un `PASS`; tests locaux et CI sur HEAD exact
  avant déploiement, aucun merge automatique.

## Documentation de référence

- https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/application-token/
- https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/generic-oidc/
- https://owasp.github.io/API-Security/editions/2023/fr/0xa3-broken-object-property-level-authorization/

## Livraison ciblée sur `https://ops.albandrieu.com`

**Décision du 18 octobre 2026** : hostname unique `ops.albandrieu.com`
pour l'interface propriétaire. Ce domaine n'est pas provisionné à ce stade.
La surface publique `https://fastapi-sample.fastapicloud.dev` (production)
et `https://sample.albandrieu.com` (staging via Access) ne doivent jamais
devenir des contournements de l'interface privée.

### Frontière de routage

- `GET /api/public-homelab/v1` : projection publique minimale, indépendante
  du hostname; aucune métrique/URL/topologie non assainie.
- `GET /private/ops/api/v1/summary` : résumé propriétaire et état des
  sondes, latence/criticité/coverage seulement avec identité validée.
- `GET /private/ops/api/v1/services` : inventaire paginé, ports/URLs
  internes uniquement pour l'utilisateur autorisé.
- `GET /private/ops/api/v1/topology` : graph runtime, provenance contrôlée,
  sans accès brut arbitraire à l'API TrueNAS ou au Docker socket.
- `GET /private/ops/api/v1/metrics` : **projection** de métriques bornée,
  aucune requête PromQL libre, aucune réponse brute de `/metrics`.
- `GET /private/ops/` : page HTML propriétaire optionnelle, même origine,
  aucune logique de déchiffrement/devalidation d'identité dans le navigateur.

Ces chemins sont **proposés**, non implémentés. Les opérations mutantes
(`POST` de diagnostic, `DELETE`, commandes, shell) sont hors périmètre v1;
limiter le routeur privé à GET/HEAD si compatible avec les besoins.
Les credentials de sondes restent côté FastAPI/TrueNAS et dans le coffre.

### Authentification à l'origine

1. Utiliser la validation **signée** du JWT `Cf-Access-Jwt-Assertion`,
    clés JWKS récupérées depuis le tenant Cloudflare attendu, audience de
    l'application `ops`, `iss`, dates et `sub`/identité autorisée
    comparés avec la politique allowlist configurée côté serveur.
2. Éviter la réutilisation accidentelle de l'audience Access existante
    de `sample.albandrieu.com`; une assertion valable pour une autre app
    ne donne aucun droit sur `ops`.
3. Refuser l'absence de configuration `OPS_ACCESS_AUD`,
    `OPS_ACCESS_ISSUER`, identité autorisée, JWKS invalide, jeton expiré,
    mauvaise signature, mauvais algorithme ou en-tête email forgé.
    Les noms de variables restent **contractuels**, pas introduits
    dans le code runtime par cette PR documentaire.
4. Séparer la session propriétaire des credentials machines. Les agents
    ne reçoivent pas le droit d'utiliser l'UI opérateur ni de lancer des
    actions sur TrueNAS. Si un Service Token est utilisé, il possède sa
    propre audience/route et une policy Machine distincte.
5. Interdire cache CDN et pré-rendu partagé sur la surface privée,
    fournir `Vary` cohérent sans rediffusion de JWT en header de réponse,
    et des logs avec identification pseudonymisée, sans adresses internes
    dans les réponses anonymes.

### Gates

- [ ] G0 inventaire `app.routes` exhaustif, matrice des droits, logs des
      violations limités à catégories/comptages (aucune valeur confidentielle).
- [ ] G1 politique restrictive de toutes les routes riches présentes, sans
      chemin de contournement sur production, staging ou host TrueNAS.
- [ ] G2 tests de contrat publics (DTO v1 allowlist et absence des champs
      sensibles sur corps/en-têtes/erreurs).
- [ ] G3 tests JWT avec JWKS local de fixture; signature invalide,
      issuer/audience/identité inadaptés et indisponibilité de la clé rejetés.
- [ ] G4 tests d'intégration origin après approbation du plan réseau.
- [ ] G5 smoke read-only sécurisé, latence sous budget et aucun secret
      injecté dans bundle/HTML navigateur.

`NOT_RUN` par défaut; documentation ≠ test runtime.


## Réconciliation effective avec la roadmap et les trois dépôts (2026-10-18)

Cette section remplace les variations locales des libellés **G0–G5** ci-dessus :
les gates transverses sont définies par la table du début de
[la roadmap](engineering-roadmap.md), commune aux dépôts. Les anciens
« G0 route », « G1 policy », etc. de cette spécification sont des
**sous-contrôles FastAPI**, non des étapes supplémentaires déjà exécutées.

- **G0 partiel** : `scripts/audit/inventory_fastapi_routes.py` inventoriera les
  routes effectivement enregistrées via `app.routes` (HTTP, WebSocket,
  mounts) et attribuera une **intention**, jamais une garantie de protection.
  Les routes inconnues, les mounts opaques et `/api/public-topology`
  héritent de `REVIEW`. La classification reste incomplète tant que
  l'inventaire réel n'est pas audité et approuvé.
- **G1 non démarré** : `/api/public-topology` actuel expose, entre autres,
  des champs `description`, `lifecycle.priority`, `runtime.provider` et des
  descriptions de relations. Cette projection antérieure n'est **pas** la
  nouvelle projection minimale contractuelle `/api/public-homelab/v1`.
  La future sortie doit être construite par liste blanche, sans URLs,
  hosts/ports, métadonnées de déploiement ni inventaire privé.
- **G2–G4 non démarrés** : PR Compose #263 ouverte ; aucun JWT, DNS, Tunnel,
  identité owner, MFA ou anti-bypass n'est attesté. Ne pas prévoir Keycloak
  comme prérequis.
- **G5 non démarré** : la PR Site #234 est fusionnée, mais sa fusion
  documentaire n'est ni une purge CDN ni un scan réel du site public.
  Inspecter les bundles, données pré-rendues, routes API et anciens caches.

### Lecture seule : inventaire P0

```bash
python scripts/audit/inventory_fastapi_routes.py
# Après classification manuelle de toutes les entrées REVIEW :
python scripts/audit/inventory_fastapi_routes.py --strict
```

Le programme charge l'app FastAPI **localement seulement si invoqué** : son
import peut nécessiter toutes les dépendances du projet. Il n'envoie pas de
requêtes HTTP par lui-même. Le résultat contient chemins/méthodes déclarés,
pas les payloads de réponse, secrets ou preuves runtime ; ne pas le publier
sur la surface anonyme. Les 3 tests unitaires ne chargent pas l'application
ni l'infrastructure et ont été exécutés isolément. La gate complète
n'a pas été prétendue verte pour ce changement.

### Contrat de refactoring proposé

- Extraire le mapping `RoutePolicy` comme source d'autorité commune
  à l'inventaire, à une future vérification de couverture au démarrage et
  au middleware fail-closed. Le classement seul **n'autorise rien**.
- Distinguer schéma public Pydantic, modèle interne de topologie et
  preuve opérationnelle ; tester par mutation l'absence de fuite même
  lorsqu'un nouvel attribut sensible apparaît dans la source.
- Factoriser vérification JWT origine + contrôle de l'acteur propriétaire,
  et conserver des credentials machine strictement distincts.
- Conserver l'ordre d'acceptation G0→G5 et un rollback indépendant
  sur Vercel/Cloudflare/FastAPI ; aucun merge ni déploiement dans cette PR.



## Implémentation RoutePolicy / DTO v1 (18 octobre 2026)

### Modèle de contrôle d'accès

`nabla/route_policy.py` est désormais la source de classification commune à
l'inventaire de routes et au middleware HTTP : `PUBLIC_CANDIDATE`,
`OWNER`, `SERVICE`, `INTERNAL`, `REVIEW`. Chaque route sensible reconnue
associe une exigence de credential distincte. Une route inconnue n'est **pas**
considérée publique par classification : elle est `REVIEW`.

Le middleware HTTP refuse `OWNER/INTERNAL` **si une clé requise manque**
(503) ou si elle est invalide (401). L'API opérateur
`/private/ops/*` refuse toujours l'accès (503), car la validation de JWT
Access n'est pas encore codée. `OPS_ROUTE_POLICY_STRICT` est `false` par
défaut : c'est une **migration transitoire**, pas un certificat fail-closed
sur toutes les routes. Avec `true`, les HTTP non classées sont refusées 403 ;
le mode strict ne doit être activé qu'après classification et migration du
site public. Le middleware HTTP n'est pas une protection WebSocket/ASGI
complète : aucun accès `ops` ne doit être considéré sécurisé avant
l'ajout de gates distinctes pour ces transports.

### Contrat public effectivement disponible

`GET /api/public-homelab/v1` renvoie :

```json
{"version":1,"services":[]}
```

L'API est vide par défaut. Une liste de publication manuellement revue peut
être configurée via `PUBLIC_HOMELAB_V1_SERVICES_JSON` :

```json
[{"id":"garage-webui","label":"Garage UI","category":"storage"}]
```

Les services ne sont **pas** automatiquement choisis à partir d'un catalogue
runtime. La projection est indépendante de la topologie privée et ne contient
ni URL, hôte, IP, port, health-board, latence, statut de probe, source ni
règle Cloudflare. Pydantic refuse les clés supplémentaires et les valeurs
suspectes, sans les refléter en cas d'erreur. Limites : 30 entrées et
4096 octets de configuration. Mettre les valeurs approuvées sous contrôle
de version sans informations privées, et ajouter ensuite une validation des
IDs contre le catalogue autoritaire sans enrichir la réponse.

### Séquence de déploiement obligatoire

1. Migrer le site Vercel/les lecteurs anonymes qui utilisent
    `/api/public-topology` ou `/api/health-board` vers le DTO v1.
2. Fournir les credentials serveur appropriées hors navigateur aux lecteurs
    privés ; ne jamais mettre `DIAGNOSTICS_ACCESS_KEY` dans Next.js client.
3. Exécuter quality gate + tests de régression du HEAD exact, tester les cas
    401/403/503 sans divulgation, puis couvrir WebSocket/ASGI.
4. Valider JWKS et autorisation fine de l'owner, puis seulement DNS, Access,
    Tunnel et `OPS_ROUTE_POLICY_STRICT=true`, avec tests E2E et rollback.

`NOT_RUN` signifie non vérifié ; aucune infrastructure modifiée ici.

## État de l'implémentation FastAPI au 18 octobre — PR #353

La PR a désormais du **code** mais n'active aucun déploiement :

- `nabla/route_policy.py` et `nabla/access_control.py` classifient les chemins HTTP sensibles (dont `/api/runtime/topology`) et refusent les credentials absents. Le mode `OPS_ROUTE_POLICY_STRICT` est encore désactivé par défaut ; les routes `REVIEW` ne sont pas un périmètre fail-closed complet.
- `nabla/api/public_homelab_dto.py` + `GET /api/public-homelab/v1` implémentent déjà la projection explicitement allowlist `{version:1,services:[{id,label,category}]}`, vide par défaut. Les anciens catalogues riches et `/api/public-topology` ne doivent plus servir de DTO public.
- `nabla/cloudflare_ops_access.py` valide RS256, JWKS tenant, `iss`, `aud`, `exp/iat/nbf`, `sub` allowlist et rejette Service Tokens ; `nabla/asgi_transport_guard.py` protège le transport WebSocket ; `/a2a` est déclaré owner HTTP. Sans configuration Access authentique, ces routes restent fermées.
- Tests locaux JWT/ASGI ajoutés, **suite complète non exécutée sur le HEAD**. Les montages HTTP réellement enregistrés, les reverse proxies, le site Vercel et l'authentification MFA/Tunnel doivent encore être audités avec preuves négatives.
- La configuration d'identité nécessite **des valeurs déployées hors Git** : `OPS_ACCESS_ISSUER` (URL tenant Cloudflare), `OPS_ACCESS_AUD` (audience application `ops`) et `OPS_ACCESS_OWNER_SUBJECTS` (sujets utilisateur explicitement acceptés). Il ne faut jamais copier l'audience de `sample.albandrieu.com`, ni mettre un Service Token dans le navigateur.

**Coordination scans** : `fastapi-sample/scripts/security/run_security_scans.py` prépare Trivy JSON (incluant lockfiles), SBOM CycloneDX, Betterleaks, Semgrep sur master et DAST ZAP/Nuclei sur demande. `import_defectdojo.py` importe via API LAN restreinte, sans exposer Dojo au WAN. La génération utilisateur/password UI et Vaultwarden reste à réaliser dans `nabla-compose` PR #263. Semgrep est SAST sur sources Git et ne scanne pas des URL ; ZAP/Nuclei sont les DAST autorisés pour les FQDN explicitement listés.
