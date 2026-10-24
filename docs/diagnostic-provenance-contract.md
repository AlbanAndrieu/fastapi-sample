# Diagnostic de bout en bout — contrat FastAPI (v1)

**Propriétaire :** `fastapi-sample`. **État :** cible incrémentale ; aucun changement de droits implicite.
Le document [modèle des sondes](platform-service-diagnostics-model.md) reste canonique
pour DNS, TCP, TLS, pfSense, Cloudflare et TrueNAS. Le présent document décrit
**le passage d'une erreur entre les composants**, pas un second tableau de santé.

## Chaîne de provenance

`nabla-compose/catalog/generated/entities.json` (source déclarée, digest SHA-256)
→ lecture et validation par FastAPI (`/api/site/catalog/v2`)
→ adaptateur serveur Next.js (`/api/homelab-catalog-v2`)
→ interface SERVICE ou OWNER selon autorisation **côté serveur**.

Un échec du catalogue ne signifie pas que TrueNAS est en panne. Une sonde
TrueNAS en erreur ne signifie pas que le catalogue est invalide.
Une réponse 302/401 Cloudflare Access ne prouve ni la disponibilité ni la
panne de l'origine. Chaque preuve garde son `observer`, son `checked_at`,
son `catalogRevision` et sa fraîcheur ; aucun horodatage n'est inventé.

### Phase P0 implémentée dans cette PR

Les erreurs du lecteur v2 sont classées sous des codes **fermés** :
`upstream_timeout`, `upstream_network`, `upstream_http`, `upstream_auth`,
`catalog_validation`, `unknown`.
L'exception interne `SiteCatalogV2Unavailable` conserve `stage`. Le endpoint
machine existant retourne HTTP 503 et `X-Nabla-Diagnostic-Stage` ; aucun hôte,
clé, corps de réponse origine, adresse LAN ni stack trace dans la réponse.
Les consommateurs qui ignorent l'en-tête continuent à fonctionner.

Ce premier contrat ne fournit **pas encore** un trace ID réellement propagé
de FastAPI jusqu'au navigateur ; ne pas confondre un ID Next.js généré
indépendamment avec une trace distribuée.

## Cible P1 : problème HTTP structuré

Conserver les statuts HTTP. Pour OWNER et SERVICE autorisés, utiliser RFC 9457 :
`type`, `title`, `status`, `instance`, et extensions allowlist
`code`, `stage`, `source`, `observation_state`, `checked_at`,
`trace_id`, `catalog_revision` et `retry_after_seconds`.
Ne jamais copier les exceptions, headers JWT, tokens, URL amont, IP privées,
stack traces ou détails de règles Access vers les réponses publiques.

`traceparent` W3C / OpenTelemetry et `X-Request-ID` sont à intégrer via
middleware **à frontière de confiance**. L'edge remplace les valeurs fournies
par des clients non fiables. Journaliser les codes dans Sentry/OTel avec
scrubbing et échantillonnage. Empêcher l'exposition de métriques privées.

## Autorisation cible (pas de gateway requise)

| Classe | Identité prouvée | Réponse |
| --- | --- | --- |
| PUBLIC | aucune | code neutre, documentation d'aide générique |
| SERVICE | secret machine dédié ; jamais embarqué dans JS | DTO minimal, état agrégé expurgé |
| OWNER | JWT CF Access vérifié + policy propriétaire + contexte réseau validé | causes/sondes détaillées autorisées |
| INTERNAL | identité workload mTLS/JWT et réseau privé | preuves brutes bornées et diagnostics technique |

Une IP domestique **n'est pas** une identité. Une IP observée ne devient fiable
que via un saut proxy vérifié. Une session Cloudflare ne prouve pas l'accès
TrueNAS depuis FastAPI Cloud. Pas de bypass sur hostname ni de trust d'un
`X-Forwarded-For` émis par le client.

## Acceptation : chaîne d'échec

1. Fausser le digest du catalogue dans une fixture. Attendre
   `catalog_validation`, pas une panne TrueNAS.
2. Simuler 401/403 GitHub, puis timeout, puis réseau refusé.
   Contrôler les codes et l'absence de secrets.
3. Simuler un catalogue sain et une API TrueNAS inaccessible. Vérifier que
   l'erreur TrueNAS porte **un autre** `stage`/source et conserve la fraîcheur.
4. Tester anonyme, SERVICE, OWNER LAN, OWNER JWT externe, JWT expiré et
   header IP forgé. Tester sur chaque route et chaque méthode.
5. Contrôler les traces API → site → UI seulement après avoir prouvé
   un même `trace_id` sur les journaux serveur, la réponse et le support UI.

## Refactoring identifié

- Garder un seul fournisseur `site_architecture_catalog`; extraire la
  classification de transport/validation en fonction pure partagée.
- Remplacer la liste temporaire `_TEMPORARY_READ_ROUTES` par une politique
  générée à partir des routes enregistrées ; interdire une route inconnue
  en mode strict avec un plan de migration par étapes.
- Séparer DTO public/OWNER des snapshots runtime et de leurs caches ;
  conserver la clé machine uniquement côté serveur.
- Garder les runbooks incidents datés comme **preuves historiques** ;
  privilégier [le runbook du 403](runbooks/fastapi-cloud-owner-access-403.md)
  pour la décision sur l'identité et [la roadmap](engineering-roadmap.md)
  pour les tâches actives.

**Ne pas activer** `OPS_ROUTE_POLICY_STRICT` en production avant que le
manifeste des routes et les tests de refus aient validé le cutover.
