# Garage S3 API — HTTP, exposition et liens

**Propriétaire :** `fastapi-sample` pour la représentation des preuves.
La topologie, les réseaux et la configuration déployée appartiennent à
[`nabla-compose`](https://github.com/AlbanAndrieu/nabla-compose).

## Catalogue déclaré (ne constitue pas un test réseau)

| Composant | URL du catalogue | Périmètre |
| --- | --- | --- |
| Garage S3 API | `http://172.17.0.24:3900` | Endpoint **interne** ; requêtes AWS SigV4 |
| Garage S3 hostname | `https://s3.int.albandrieu.com` | Nom DNS privé / Traefik, **pas** une publication Internet garantie |
| Garage Admin API | `http://172.17.0.24:3903` | API d'administration, `GET /` non pertinent |
| Garage Web UI | `http://172.17.0.24:3909/` | Interface Web distincte |

`external=false` dans le catalogue Garage S3. La présence de
`tunnelUrl` n'autorise **pas** la publication : c'est une adresse
déclarée pour la navigation et la réconciliation.

La fiche détaillée doit offrir des **liens cliquables distincts** pour
le hostname configuré, l'URL LAN et le permalien des diagnostics.
La génération des URL LAN utilise exclusivement les champs
`internal_host/internal_port/internal_secure` du même ID catalogué ;
elle ne fait pas de jointure approximative sur l'IP TrueNAS partagée.

## Pourquoi HTTP failed ne prouve pas la panne S3

Garage :3900 est une **API S3**, pas une interface HTTP interactive.
Un `GET /` anonyme peut retourner `403 AccessDenied` ou un autre
code d'erreur S3 alors qu'une requête S3 signée fonctionne.
Un timeout TCP, une erreur DNS, un HTTP 5xx et un refus d'authentification
S3 sont **des causes différentes** ; ne pas les réduire à « service DOWN ».

Depuis la workstation du LAN (aucun secret dans la commande) :

```bash
dig @172.17.0.1 s3.int.albandrieu.com A +short
curl -sS -o /dev/null -w 'http=%{http_code} connect=%{time_connect}s\n' \
  --connect-timeout 2 --max-time 8 http://172.17.0.24:3900/
curl -sS -o /dev/null -w 'http=%{http_code} tls=%{ssl_verify_result}\n' \
  --connect-timeout 2 --max-time 8 https://s3.int.albandrieu.com/
```

Les deux commandes `curl` sont volontairement **non authentifiées**.
Elles prouvent un transport HTTP/TLS, **pas** les droits d'accès S3.

Pour prouver la fonction S3 avec une identité préexistante autorisée
(et un **bucket de test identifié**), dans un shell privé avec AWS CLI :

```bash
: "${GARAGE_TEST_BUCKET:?set an approved test bucket}"
: "${AWS_PROFILE:?select a least-privilege Garage test profile}"
aws --profile "$AWS_PROFILE" --endpoint-url http://172.17.0.24:3900 \
  s3api head-bucket --bucket "$GARAGE_TEST_BUCKET"
```

Ne pas imprimer la configuration du profil, les clés S3, les réponses XML
d'erreur ni les secrets. `head-bucket` peut être refusé par la
politique du bucket : vérifier l'autorisation avant de conclure à un
problème technique. Aucun objet n'est créé ni modifié.

## Pourquoi Policy failed est indépendant de HTTP failed

`/sickz` confronte `external=false` aux **observations outside-in**
depuis FastAPI Cloud et à l'inventaire Cloudflare. Le verdict d'exposition
passe à `fail` si un accès public, un Tunnel déclaré pour ce hostname ou
une application Cloudflare Access est observé **malgré l'intention privée**.

Un HTTP 401/403 sur un edge Cloudflare **ne prouve pas** que l'origine S3
a répondu. En revanche, une route publique inattendue peut rester une
violation de la politique `external=false` même si Access bloque
le client. Vérifier `security_policy_detail`, `cloudflare_tunnel_observed`,
`cloudflare_access_observed` et `reachable` de **la même identité Garage**
avant de corriger une route.

Ne pas changer `external` à `true` pour obtenir une pastille verte,
ne pas supprimer Cloudflare Access et ne pas exposer l'API S3 sans
validation d'architecture.

## Acceptation UX

- La carte S3 garde un HTTP/S3 `unknown` tant qu'il n'y a pas de
  preuve signée valide. Ne pas transformer un `GET /` non signé
  en `ok`.
- Le verdict `Policy failed` reste rouge quand `/sickz` observe une
  anomalie réelle. La fiche affiche **la cause observée** et un lien
  vers la ligne `/sickz` correspondante.
- « Details » reste la dernière action dans la carte, sur une ligne
  complète, utilisable au clavier et sur mobile.
- Les URLs sont des **valeurs de catalogue**, pas des preuves de connexion.
  Un navigateur hors LAN ne pourra pas forcément ouvrir le lien interne.
- Contrats locaux ciblés et syntaxe JS avant déploiement ; production
  et configuration réseau **NOT_RUN** depuis l'agent.
