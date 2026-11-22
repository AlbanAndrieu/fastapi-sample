# Control plane integrations — F15/F16/F17/F18

FreshRSS: reuse Compose GReader identity separation; dedicated private FastAPI account/token, read-only subscriptions/stream; no article writeback, HTML sanitization and bounded titles/summaries before inference. Project Backstage V2 entity names/tags/type only, no topology, IPs or credentials. Managed Langfuse prompt source `config/prompts/nabla-homelab-rss-relevance.txt`, publish to private Langfuse with production label via approved operator; record actual version. Existing resolver silently falls back: for this pipeline require verified prompt version and strict homelab LiteLLM adapter (no Azure/direct OpenAI fallback). Dedicated virtual key/model alias and budget. Cache by article/content hash + catalog revision + prompt version + model, PostgreSQL durable article decisions when needed, Redis cache only. Offline pytest dependency seams and the bounded CLI reader/classifier are CODED in #453; prompt publication, live TrueNAS acceptance, ingestion scheduling and UI remain NOT_RUN or NOT_CODED as applicable.

**API / MCP ownership and trust boundary (21/11):** `nabla-compose` already owns
`scripts/mcp/freshrss_readonly.py`, a stdio-only MCP with
`list_security_feeds` and `recent_security_articles` and an isolated
`securityagent` identity. Its historical `config/freshrss/security-sources.json`
contains 10 curated security feeds; the canonical broader site-alban OPML
contains 78 feeds. Do not quietly promote the ten-feed MCP into unrestricted
feed administration or reimport the 78 sources automatically. FastAPI's
`freshrss_greader.py` remains a separate service-account read-only GReader
consumer used by the TrueNAS-only Langfuse/LiteLLM classifier, with fixed
HTTPS origin, no write endpoints, and no scheduler. The GReader Auth credential
is not a server-enforced read-only scope: apply account isolation and optional
Cloudflare Access. The article title and summary are untrusted input,
normalized to bounded plain text; neither the MCP nor the classifier
is authorized to execute article instructions. Live network acceptance and
account provisioning remain NOT_RUN.


Approvals: existing Notes uses databases/SQLAlchemy PostgreSQL and Redis RPUSH/BLPOP with unconstrained prompt, demo email handler and mutable completed flag; none may authorize apply. Extract shared UTC helpers, add separate pending-only table with explicit migration and idempotent digest insert, bounded list (not exposed). Next implement durable immutable challenge provenance, verify signature with existing Compose approval.py, one-time CAS transition + transactional outbox, separate privileges, expiry/replay tests, worker leases and audit. No destructive migration of demo rows. Inventory actual Notes REST/HTMX/MCP consumers, replace with approval list/notification views, archive legacy worker and template/demo routes only after test parity. Redis TTL for read projection, never approval or queue authority. Existing notes workers are not production approval handlers.

Slack: existing nabla-openclaw App, Socket Mode owner-managed, token/installation not confirmed. Reuse approved delivery boundary; avoid copying app-level xapp token or expanding scope. Outbox retries and idempotency, fixed channel IDs configured privately, minimal summary/link, no plan/raw secrets/signatures, no approval from Slack click.

Dashboards: inventory Grafana provisioned dashboards and Prometheus recording rules, Home Operations, heatmap, UI probe health and provider metrics. Reuse existing datasource and links. No fabricated or duplicate series, 0 != absent. New dashboard panels only after coverage/gap evidence.

Perimeter: Compose owns existing Traefik, CrowdSec and Cloudflare Terraform; rateLimit middleware Traefik, CrowdSec AppSec WAF in addition to existing bouncer, Cloudflare WAF edge. No in-app replacement or new service; keep HMAC verification. Runtime NOT_RUN.

## Avancement 21/11 — intégration fonctionnelle pilote

FastAPI : `nabla/integrations/freshrss_greader.py` implémente le reader HTTPS GReader sur URL fixée, aucun POST/writeback, filtrage public des subscriptions et contenu HTML, limite stricte des réponses. `rss_relevance_live.py` exploite le catalogue V2 vérifié, prompt Langfuse versionné avec label `production` (aucun fallback), et LiteLLM local TrueNAS port 4000 (modèle `fastapi-qwen`, clé virtuelle). CLI read-only `python -m nabla.integrations.rss_relevance_live --check` hors réseau puis `FRESHRSS_RELEVANCE_RUN_APPROVED=YES ... --once` sur TrueNAS avec compte FreshRSS séparé, secrets Vaultwarden et `FASTAPI_RUNTIME_MODE=homelab`. Cette opération ne marque pas les articles comme lus et n'envoie pas de notifications. Le stockage PostgreSQL durable des décisions RSS n'est pas encore câblé ; le cache Redis opportuniste est désormais câblé (TTL 24 h), sans en faire une source d'autorité. Ne pas exécuter la version live sans prompt Langfuse réellement publié et compte service isolé.

API approbations : `GET /api/homelab/approvals/pending` lecture seule sur PostgreSQL en OWNER homelab, désactivée par défaut (`OPERATION_APPROVAL_READ_MODEL_ENABLED=false`). Rejette les requêtes avec paramètres, renvoie uniquement métadonnées et SHA, ignore les expirées. L'activation suppose migration DB et tests d'autorisation, jamais `apply` via cette API. Aucune mutation ou notification n'est câblée.

**Cache Redis ajouté (PR #453, 21/11)** : classification JSON minimaliste validée avant écriture TTL 24h, clés SHA-256 liées au modèle LiteLLM, révision Backstage, version et hash du prompt Langfuse, et contenu normalisé. Aucune clé ou article brut dans les noms de clés. Redis timeout 0,8 s/read ou write ; erreur Redis ne transforme jamais l'état en succès ni n'autorise un fallback vers un fournisseur IA extérieur, l'inférence locale reste obligatoire. Limite interactive à 5 articles par passage, aucune planification. Recette locale/tests de cache encore NOT_RUN.

**Outbox transactionnelle CODED (21/11)** : `nabla/api/approvals/notification_outbox.py` sur le `approval_metadata` déjà utilisé par Alembic, migration `d818c14f420a`. L'unique mutation `record_pending_and_outbox()` est une fonction interne sans route HTTP ni déclenchement, qui exécute `pending_insert().returning()` et l'événement `approval_requested` dans une transaction PostgreSQL. Duplicate -> no-op sans notification ; échec de l'insert outbox -> rollback de l'approbation. Table dépourvue de contenu de plan, JWT, clé ou message Slack. Quatre types d'événements typés, destinataire logique `nabla-openclaw`, 5 tentatives maximum, sélection due `FOR UPDATE SKIP LOCKED`. Aucune livraison, aucune vérification de signature YubiKey ni consumption CAS : ne pas confondre la création de la demande avec son approbation. Tests SQL compilés et fausse transaction ajoutés, tests PostgreSQL réels NOT_RUN. Ne pas publier de notification tant que l'identité Slack et l'outbox worker isolé ne sont pas validés.

## Identité FreshRSS et recette opérateur (PR #453)

- **Pas de compte Google/GReader à créer.** `GReader` est le protocole API compatible FreshRSS. Créer plutôt un **utilisateur FreshRSS technique dédié** au pilote, avec uniquement des abonnements à des flux publics, HTTPS, et définir un mot de passe API distinct du mot de passe interactif.
- Activer l'API FreshRSS pour cet utilisateur, exécuter `POST /api/greader.php/accounts/ClientLogin` avec ses identifiants API depuis un hôte approuvé, récupérer le champ `Auth` et le stocker dans Vaultwarden sous `FRESHRSS_RELEVANCE_AUTH`. Ne jamais publier `Auth`, le mot de passe API, les en-têtes d'authentification ou une réponse ClientLogin dans les logs ou une PR. Ne pas présumer de privilèges GReader serveur en lecture seule : le jeton peut aussi autoriser des écritures, c'est le compte isolé et la restriction des méthodes/routes du client qui limitent le pilote.
- Cloudflare Access, si requis : utiliser une **paire de service tokens de portée restreinte** `FRESHRSS_CF_ACCESS_CLIENT_ID` et `FRESHRSS_CF_ACCESS_CLIENT_SECRET`, autorisée uniquement sur l'application et le chemin nécessaires. Ne pas employer le cookie OWNER, la clé diagnostics ni une identité GitHub App.
- Sur TrueNAS : vérifier les destinations réellement joignables depuis la migration Freebox avant l'exécution pilote. Le code impose actuellement une URL LiteLLM locale `http://172.17.0.24:4000` ; si l'adressage a changé, adapter **explicitement code, configuration et tests** au nouvel endpoint privé approuvé, plutôt que d'autoriser des redirections ou des fournisseurs cloud en fallback. Contrôler pareillement FreshRSS et Langfuse.
- Publier `nabla-homelab-rss-relevance` dans Langfuse avec label `production` et version entière non nulle ; délivrer une clé virtuelle LiteLLM dédiée au modèle `fastapi-qwen` avec quotas ; conserver `trust_env=False`, les limites de réponses et de temps, le JSON strict, et au plus cinq articles par exécution.
- **Recette** : `python -m nabla.integrations.rss_relevance_live --check` valide uniquement le contrat hors réseau. Puis, en environnement homelab isolé, avec secrets montés depuis le coffre et décision OWNER explicite, exécuter `FRESHRSS_RELEVANCE_RUN_APPROVED=YES python -m nabla.integrations.rss_relevance_live --once`. Vérifier sans exposer de contenu privé : nombre traité, faux positifs, pertinence, quotas, cache Redis 24 h, timeouts, refus en cas d'indisponibilité Langfuse/LiteLLM, aucun POST GReader, aucun marquage lu et aucune publication Slack.
- **Go/no-go :** CI complète verte sur SHA final et revue de toute détection de secrets Trivy, migrations PostgreSQL séparées, test FreshRSS/Langfuse/LiteLLM réel concluant. Aucune planification automatique avant validation.


## 2026-11-22 · Trivy container-image secret baselines — verified public SDK examples

Docker CI remains **fail-closed** after running Trivy `scanners: secret`: the
private JSON is never uploaded, and `validate_trivy_handoff.py` rejects every
remaining secret or misconfiguration finding. The `trivyignores` parameter
loads `.trivyignore.yaml` explicitly only for this private secret scan.

The 21/11 Docker run reported 12 matches, isolated by a metadata-only triage
without disclosing secret contents. Public upstream source review verified two
false-positive signatures in the exact pinned dependency versions:

- **Anthropic 2.8.0 (11 hits)**: Trivy v0.71.2 rule
  `gcp-service-account` matches the literal
  `{"type": "service_account"}`, a documented execution-identity discriminator
  in `src/anthropic/resources/beta/agents/agents.py` and the five
  `src/anthropic/types/beta/*agent*.py` models. Its compiled
  `agents.cpython-313.pyc` also repeats that public literal.
  [Pinned vendor source](https://github.com/anthropics/anthropic-sdk-python/tree/v2.8.0/src/anthropic);
  [Trivy rule](https://github.com/aquasecurity/trivy/blob/v0.71.2/pkg/fanal/secret/builtin-rules.go).
  This is not a JSON service-account credential (no key material).
- **FastAPI Users 15.0.5 (1 hit)**: Trivy rule `jwt-token` matches a
  fixed, public OpenAPI example access token in the compiled
  `fastapi_users/authentication/transport/__pycache__/bearer.cpython-313.pyc`.
  The source splits the example over adjacent string literals;
  the sample JWT claims `exp=1571504193` (2019-10-19 UTC), long expired.
  [Pinned vendor source](https://github.com/fastapi-users/fastapi-users/blob/v15.0.5/fastapi_users/authentication/transport/bearer.py).

**Scope and expiry:** only these two Trivy rule IDs and eight named vendor
files can be exempted, expiring **2026-12-22**; no rule is disabled globally and
no entire dependency directory or first-party code is skipped. Contract tests
pin the allowlist. New secrets anywhere else still fail CI. Re-qualify the
exceptions on upgrades of Trivy, the Anthropic SDK, Python, or FastAPI Users,
and confirm Docker CI on the exact HEAD before merging.

Runtime TrueNAS, IPv6 egress, FreshRSS and Freebox integration acceptance are
independent of this CI-only rule qualification.
