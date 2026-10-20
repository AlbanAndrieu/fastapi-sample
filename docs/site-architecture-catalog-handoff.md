# Architecture catalogue — FastAPI ↔ Site Alban (avant Keycloak)

Date : 2026-10-20. PR FastAPI #358, endpoint explicitement dédié à un consommateur machine. Ce document est le contrat de reprise pour le projet `AlbanAndrieu/nabla-site-alban`.

## Contrat serveur-à-serveur

```http
GET /api/site/catalog/v1 HTTP/1.1
Host: fastapi-sample.fastapicloud.dev
Accept: application/json
X-Diagnostics-Key: <secret serveur uniquement>
```

Réponse admise : `{"version":1,"services":[{"id":"garage-admin","name":"Garage Admin"}]}`. Il s'agit **uniquement** d'identités de présentation. Aucun champ `internalHost`, `internalPort`, `tunnelUrl`, `external`, `cloudflareAccessRequired`, log, sonde ou métrique n'est sérialisable dans ce DTO strict. Le schéma refuse noms contenant IP/URL/port ou attributs supplémentaires ; la source reste `nabla-compose`. Le catalogue complet de l'opérateur reste `/api/homelab-services` et demeure soumis à l'IP autorisée `HOMELAB_TRUSTED_CIDRS` **en plus** de l'authentification.

La clé `DIAGNOSTICS_ACCESS_KEY` est exigée sur ce chemin SERVICE (503 si non configurée, 401 si absente/invalide). Elle ne suffit pas à contourner le CIDR sur les routes propriétaire. Ne jamais utiliser de clés dans le client React, les URLs, les variables `NEXT_PUBLIC_*`, logs, cookies JS ou en-têtes renvoyés au navigateur. Secret dans Vaultwarden et configuration Vercel côté serveur seulement. À terme remplacer par une identité machine dédiée (Cloudflare Service Auth puis OIDC/Keycloak si accepté).

L'API n'utilise **pas** de fallback local sur ce chemin : uniquement une réponse autoritaire validée récemment (cache d'au plus 300 s depuis le dernier succès), sinon 503 neutre. Le fallback historique des routes internes de diagnostic n'est pas propagé au consommateur site. Entêtes `Cache-Control: no-store, max-age=0`, `Pragma: no-cache` et `X-Robots-Tag: noindex, nofollow`.

## À appliquer dans nabla-site-alban

1. Dans `lib/homelabServices.ts` remplacer le GET actuel `/api/homelab-services` par le chemin SERVICE ci-dessus, avec `process.env.DIAGNOSTICS_ACCESS_KEY`, `cache: "no-store"`, `redirect: "error"`, timeout borné et réponse strictement validée. Ne pas envoyer la clé depuis React ni dans une URL.
2. Retirer `LOCAL_FALLBACK`, `getStaticHomelabServicesCatalog`, le bloc `catch` renvoyant le JSON local et l'enrichissement de présentation local pouvant injecter des URL ou ports d'administration. Aucun succès synthétique en cas d'échec. Supprimer toute projection statique sensible dans `public/` sans relâcher les protections sur `/api/homelab-*`.
3. Conserver le garde CIDR/identité côté route Next `/api/homelab-services` propriétaire. Un appel Vercel sort avec une IP différente de celle du domicile : **ne pas** élargir `HOMELAB_TRUSTED_CIDRS` à Vercel pour contourner la politique. Les données enrichies d'architecture et les preuves privées restent sur un espace propriétaire, prévu sur `ops.albandrieu.com`. La vitrine publique peut afficher le DTO assaini ou un état « indisponible ».
4. Ajouter des tests sur l'absence de secret (503), mauvais secret (401), refus du catalogue riche depuis Vercel malgré une clé valide (403), réponse vide/invalide ou timeout (503 sans fallback), zéro champ sensible dans les réponses/HTML/JS Next publics, vérification EN/FR et preview externe. Un 403 Cloudflare et un scrape Gatus `up=1` ne prouvent pas la fermeture des ports origine.

## Recette à effectuer après déploiement

Vérifier les refus anonymes, la lecture serveur authentifiée, la validité du certificat HTTPS et de la provenance, la cohérence du catalogue vivant avec `nabla-compose`, et les deux perspectives d'accès (depuis le domicile puis hors domicile). Les mesures Prometheus/Gatus restent LAN-only et ne sont jamais publiées pour alimenter le site. Aucun état déployé, aucune série live ni configuration Vercel n'ont été vérifiés dans cette PR : **NOT_RUN**.

**Périmètre de ce commit : uniquement fastapi-sample.** Le dépôt du site, ses secrets, la CI complète et les modifications futures Keycloak nécessitent leurs propres validations.
