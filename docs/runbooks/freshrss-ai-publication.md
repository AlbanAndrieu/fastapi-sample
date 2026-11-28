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

**Couverture rotative :** le classifieur conserve sa limite de cinq inférences par exécution, mais parcourt désormais jusqu'aux 100 derniers articles publics FreshRSS par tranches tournantes dépendant de l'heure UTC. Ainsi, plusieurs exécutions approuvées successives ne reclassent pas systématiquement les cinq mêmes titres. La couverture réelle dépend de la cadence, du nombre de flux, de la fenêtre de 100 articles et des interruptions; elle n'est pas garantie par la seule présence du code.

## Dépannage réel du 28/11/2026 — ModuleNotFoundError et HTTP 404

Le chemin `/mnt/cpool/home/albandrieu/.cache/nabla-compose/dev-venv/bin/python` est le Python de **nabla-compose**, pas nécessairement celui du projet `fastapi-sample`. La forme `python -m nabla.integrations.rss_relevance_live` ne fonctionne que lorsque le paquet `nabla` est installé ou que le dépôt `fastapi-sample` se trouve sur `sys.path`.

**Exécution recommandée depuis la workstation administratrice/TrueNAS, dans le conteneur FastAPI réellement déployé** (ne pas utiliser l'environnement Compose) :

```bash
docker exec fastapi-sample /code/.venv/bin/python -c 'import nabla; print(nabla.__file__)'
docker exec fastapi-sample /code/.venv/bin/python -m nabla.integrations.rss_relevance_live --check
# Vérifier en premier que le conteneur a été rebâti depuis la fusion #462
# et que les variables requises sont montées depuis le coffre.
docker exec \
  -e FRESHRSS_RELEVANCE_RUN_APPROVED=YES \
  -e FRESHRSS_RELEVANCE_PUBLISH_APPROVED=YES \
  fastapi-sample /code/.venv/bin/python -m nabla.integrations.rss_relevance_live --publish
```

Si le conteneur se nomme autrement, obtenir son nom avec `docker ps --format '{{.Names}}'`. Un ancien conteneur peut ne pas contenir le module ou le flag `--publish`. Autre méthode, sur une copie de travail avec les dépendances Python de FastAPI installées : `cd apps/fastapi-sample && /chemin/venv-fastapi/bin/python -m nabla.integrations.rss_relevance_live --check`.

Le **HTTP 404** sur `/api/site/rss/v1` est prévu tant que `RSS_RELEVANCE_PUBLICATION_ENABLED` n'est pas strictement `true` côté **FastAPI Cloud**, ou si le code cloud n'est pas encore déployé sur une révision contenant #462. Une fois la publication activée, l'absence de Redis ou de décisions ingérées doit produire **503**, puis **200** après ingestion valide. Activer le flag sur **TrueNAS seulement** ne suffit pas. Le relais HMAC nécessite la même `TRUENAS_FEDERATION_SECRET` (≥32 caractères), une vraie URL Cloud configurée sur TrueNAS et `REDIS_URL` sur Cloud. Ne jamais copier les secrets dans les commandes de diagnostic.

## 28/11/2026 — Déploiement TrueNAS du classifieur RSS

`--check` peut réussir sur une image **ancienne** : ce mode vérifie le contrat hors réseau mais n'assure pas que `--publish` existe. Vérifier `docker exec fastapi-sample /code/.venv/bin/python -m nabla.integrations.rss_relevance_live --help` ; si seules `--check` et `--once` sont présentes, l'image en cours n'inclut pas la version de GitHub portant la publication (#462). Actualiser l'image suivant le processus de déploiement `nabla-compose/scripts/truenas/update-fastapi-sample.sh` (contrôler le SHA et sauvegarder le rollback), puis vérifier à nouveau `--help`. Ne pas considérer `--once` comme une publication : ce mode classe mais n'envoie rien au relais Cloud.


## CLI troubleshooting (2026-11-28)

`--check` n'exécute **aucun** prérequis. À partir de cette correction, `--preflight` vérifie uniquement la configuration locale (runtime, en-tête GReader présent, clés et URL Langfuse, destination et clé LiteLLM, paire CF Access, URL et secret de fédération). Résultat JSON booléen uniquement ; **pas d'appel réseau**, ni URL, ni jeton, ni données d'articles dans la sortie. Un `state=ready_for_live_validation` ne prouve pas l'authentification distante, la version du prompt, l'inférence ni la publication.

```bash
sudo docker exec fastapi-sample /code/.venv/bin/python -m nabla.integrations.rss_relevance_live --preflight
```

Le CLI conserve l'exécution explicite `FRESHRSS_RELEVANCE_RUN_APPROVED=YES`, ajoute des marqueurs de **phase sans secrets** (catalogue, Langfuse, GReader, LiteLLM, publication), et signale les erreurs codifiées `RSSConfigurationError` / `FreshRSSUnavailable` sans traces, URLs ni réponses brutes. Les autres exceptions ne divulguent que leur type. L'ancienne image qui retourne seulement `REJECTED: RSS relevance pilot could not be verified` nécessite la commande de diagnostic ponctuelle ou un redéploiement de cette correction.
