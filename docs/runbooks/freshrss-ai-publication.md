# FreshRSS — classement IA → publication contrôlée du site CISO

## Frontières de confiance

1. **TrueNAS** lit le compte technique FreshRSS via les deux GET GReader approuvés. Le prompt `nabla-homelab-rss-relevance` est récupéré auprès de Langfuse (`production`) puis exécuté avec le modèle LiteLLM privé `fastapi-qwen` (sans recours à un modèle externe).
2. **Publication** : seul le CLI explicitement approuvé peut envoyer un lot HMAC vers `POST https://fastapi-sample.fastapicloud.dev/federation/rss`. Transport de cinq décisions pertinentes au maximum, contenant uniquement le SHA-256 opaque de l’article et la liste de technologies. Ni titre, résumé, raison du modèle, URL de flux, IP interne, clé ni contenu du prompt ne traversent ce relais.
3. **FastAPI Cloud** valide la signature, le modèle, la version de prompt, l’horodatage et la révision Backstage ; Redis assure stockage et anti-rejeu. `GET /api/site/rss/v1` expose la seule projection publique validée, sans donnée privée.
4. **nabla-site-alban** continue de lire son compte FreshRSS *public*, vérifie la liste de sources `public/ciso-rss-feeds.json`, recalcule SHA-256(streamId + NUL + id) et ne présente en mode IA que les articles correspondant à la projection. La classification n’est **pas** une preuve de vulnérabilité, de version déployée ni de compromission.

## Pré-requis et activation

- Compte API FreshRSS technique limité aux flux publics approuvés et en-tête GReader `FRESHRSS_RELEVANCE_AUTH` sur TrueNAS. L’API GReader ne possède pas de restriction read-only au niveau du jeton : isoler le compte et ne jamais lui donner des flux privés.
- `LANGFUSE_BASE_URL`, `LANGFUSE_PUBLIC_KEY` et `LANGFUSE_SECRET_KEY` pour le prompt réellement publié avec label `production`, version vérifiée.
- `LITELLM_URL` du service homelab et clé virtuelle LiteLLM avec quota (configuration du runtime FastAPI).
- Sur FastAPI Cloud : `RSS_RELEVANCE_PUBLICATION_ENABLED=true`, `REDIS_URL` partagé entre réplicas, `TRUENAS_FEDERATION_SECRET` (≥32 caractères) identique à TrueNAS.
- Sur TrueNAS : `TRUENAS_FEDERATION_CLOUD_URL=https://fastapi-sample.fastapicloud.dev` et même secret HMAC ; `FRESHRSS_RELEVANCE_RUN_APPROVED=YES`, `FRESHRSS_RELEVANCE_PUBLISH_APPROVED=YES` pour publication.
- Sur Vercel : `FRESHRSS_AI_SELECTION_ENABLED=true` lorsque la publication Cloud répond `200` et la lecture FreshRSS publique fonctionne. Aucun jeton HMAC ni accès OWNER dans Vercel.

## Vérification graduée

```bash
python -m nabla.integrations.rss_relevance_live --check
FRESHRSS_RELEVANCE_RUN_APPROVED=YES python -m nabla.integrations.rss_relevance_live --once
FRESHRSS_RELEVANCE_RUN_APPROVED=YES FRESHRSS_RELEVANCE_PUBLISH_APPROVED=YES \
  python -m nabla.integrations.rss_relevance_live --publish

curl -fsS https://fastapi-sample.fastapicloud.dev/api/site/rss/v1 | \
  jq '{model,catalogRevision,promptVersion,matched:(.items|length)}'
```

Le retour `503` avant ingestion est normal : aucune décision n’est fabriquée. Les décisions positives s’accumulent en Redis et expirent individuellement après 24 h ; un changement de version de prompt ou de révision catalogue invalide la génération précédente. Le site conserve son mode lexical FreshRSS lorsqu'aucune publication validée n'est disponible.

## Recette et budget

Lancer les tests hermétiques, vérifier le HEAD SHA/CI sur chaque dépôt, puis valider sur TrueNAS la présence effective des clés, la publication Langfuse et les chemins réseau après migration Freebox. Le CLI traite cinq articles par passe (budget LiteLLM ≤30 s), sans tâche de fond implicite. Ne planifier un cron régulier que lorsque les quotas et la pertinence des sorties sont mesurés. Pas de POST GReader, pas de marquage `read`, pas de publication de secrets, pas de changement de la sécurité OWNER.

**Freebox / IP LAN** : le classifieur accepte désormais `http://<IPv4 RFC1918>:4000` ou `http://litellm:4000` tel que configuré dans `settings.litellm_url`, sans faire confiance à une IP historique. Pas d'adresse WAN, pas de port arbitraire, pas de redirection ni de proxy d'environnement. L'URL Langfuse peut également résider sur une IPv4 privée au port 3000/443.
