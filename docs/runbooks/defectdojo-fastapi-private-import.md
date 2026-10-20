# FastAPI Sample → DefectDojo : import uniquement sur le LAN

**Statut : code préparé dans la PR #353, pas d'import ni de preuve WAN/LAN exécutés.** Ce projet n'agrège pas les rapports d'autres dépôts. L'importeur est limité aux résultats produits pour le **seul** projet `fastapi-sample`.

## Architecture et frontières

Le compose de référence `nabla-compose/apps/defectdojo/compose.yml` publie le frontend DefectDojo :
- Traefik `websecure` : `https://defectdojo.int.albandrieu.com/`, SNI TLS/certificat attendus, destination LAN `172.17.0.24:443`.
- Docker : `172.17.0.24:31085 → :8080` en HTTP. **Ce chemin ne doit pas servir à exporter les rapports d'un autre hôte.** Auditer les ACL inter-VLAN et l'éventuel NAT WAN. L'adresse RFC1918 n'est pas à elle seule une restriction d'accès.

Le nouvel importeur utilise **exclusivement** la première voie ; il ne fait pas de résolution DNS côté envoi : socket connecté à `172.17.0.24:443`, avec hostname TLS `defectdojo.int.albandrieu.com`, validation de la chaîne de confiance et du certificat, Host HTTP correct. Pas de `-k`, pas de proxy, pas de redirection, pas de downgrade HTTP. Le socket refuse un chemin utilisant une interface source hors `172.17.0.0/24` : un runner sur Kubernetes/Docker ou VPN sans interface approuvée échoue délibérément.

Cette contrainte logicielle ne remplace **ni l'ACL de Traefik, ni pfSense, ni l'inventaire NAT/Cloudflare**. Le nom privé ne prouve pas l'absence de routage via WAN-IP + SNI/Host. Refuser de rendre `defectdojo.int.albandrieu.com` ou `:31085` public.

## Flux complet et validation des données

1. Sur un runner LAN **isolé**, produire le scan de `master` depuis un checkout Git à SHA immuable :
    `python scripts/security/run_security_scans.py --mode master`.
    Le script exécute Betterleaks, Trivy (vulnérabilités, lockfiles, secrets, licences), SBOM CycloneDX, Semgrep et ne génère `scan-receipt.json` qu'après exécution technique complète des scanners demandés. Un `CRITICAL` bloque la PR ; sur `master`, le reçu porte `policy_status=needs_review`, la commande reste en échec, mais son rapport complet peut faire l'objet d'un import de triage explicitement approuvé. Les scans DAST restent manuels (option `--dast` après autorisation et bornage des cibles), **pas de ZAP/Nuclei sur chaque PR**.
2. Garder les rapports dans un répertoire **privé et vide au départ**, hors Git, sous permissions 0700 ; fichiers 0600 au maximum. Le reçu décrit seulement projet, `master`, SHA Git, état `complete`, chemins relatifs de rapports et SHA-256. Ne pas placer credentials, réponses authentifiées ou fichiers privés dans des artefacts GitHub.
3. Dry-run : `python scripts/security/import_defectdojo.py --kind trivy --reports-dir /chemin/prive`. Il vérifie le reçu, le format, les symlinks, les permissions, les données Trivy secret-free et le checksum. **Aucune connexion ni lecture de jeton.**
4. Le reviewer valide le rapport réellement fourni (pas seulement le reçu auto-généré), le SHA-256, le scanner, l'engagement et le périmètre. Pour appliquer, le job exige `--apply --approved-sha256 <SHA_APPROUVE>`, `DD_IMPORT_APPROVED=YES`, `DD_FASTAPI_ENGAGEMENT_ID` fixé et `DD_FASTAPI_TOKEN_FILE` pointant vers un fichier 0400/0600 possédé par l'UID effectif. **Ne pas mettre la valeur du jeton en variable d'environnement ou en argument CLI.**
5. L'importeur envoie `POST /api/v2/reimport-scan/` avec `engagement` et `test_title=fastapi-sample-<kind>` ; `auto_create_context=false`, `close_old_findings=false`, `verified=false`. Seuls Trivy sans preuve de secrets, CycloneDX, ZAP et Nuclei **validés** sont acceptés. Aucun Betterleaks brut, Gitleaks, token, SARIF arbitraire ni archive CI n'est importé.
6. Réponse HTTP 2xx signifie **accepté**, pas `Processed`. Vérifier dans DefectDojo le `test_id`, l'état de traitement asynchrone, le parser et la déduplication ; détecter `Failed`. La lecture de réponse de l'importeur est volontairement plafonnée et ne divulgue pas de findings.

Le reçu SHA-256 protège contre la substitution involontaire après validation, **pas contre un scanner/runner compromis** : il n'est pas signé. Le SHA approuvé doit donc provenir d'un contrôle indépendant, et l'exécution doit rester sur un hôte/dataset maîtrisé. Ajouter une signature attestée si la source de scans devient moins fiable.

## Jeton à moindre privilège : différences à vérifier

L'API DefectDojo v2 utilise `Authorization: Token <secret>`. **Ce token représente un utilisateur DefectDojo**, il ne devient pas à lui seul un jeton restreint au seul endpoint ou produit.

- Créer un utilisateur de service non-superuser **distinct** du compte de l'interface UI et sans droits globaux. Associer uniquement l'accès nécessaire au produit/engagement `fastapi-sample`. Si l'édition installée offre le rôle **API Importer** ou un rôle RBAC personnalisé, le privilégier ; ne pas présumer que les fonctions Pro existent en OSS.
- Avant tout import réel, tester son périmètre : import autorisé dans l'Engagement prévu et refus sur un Engagement non autorisé. Ne pas conserver un token à droits globaux pour pallier un 403.
- Stocker le jeton dans Vaultwarden sous entrée dédiée, injecter dans un fichier 0400/0600 du compte importateur lors de l'exécution ; **jamais** dans les logs, variables GitHub, bundles Vercel ou image Docker. Ne pas recycler le mot de passe UI ou le Service Token Cloudflare.
- Ajouter rotation/révocation et journalisation minimale (SHA, nom du parser, ID de Test, statut ; jamais le contenu brut ou le token). Durée de rétention et droits de lecture du dataset à approuver.

## Gates réseau à valider indépendamment

- Sur Pi-hole `172.17.0.24` et Unbound `172.17.0.1` : A privée `172.17.0.24`. Le split DNS a déjà présenté des anomalies ; **ne pas supposer** qu'il est encore correct. Vérifier aussi AAAA.
- Via un résolveur public : aucun A/AAAA pour le FQDN privé. Ceci ne suffit pas : depuis un point Internet autorisé, vérifier également qu'aucune connexion à l'IP WAN avec Host/SNI DefectDojo ne peut atteindre l'origine.
- Sur TrueNAS : front `:31085` limité au LAN, labels Traefik et certificats corrects ; sur pfSense, pas de NAT/HAProxy WAN de `:31085` ni de `:443` routant ce hostname privé. Sur Traefik, limiter les IPs clientes aux runners approuvés pour l'API d'import, avec authentification DefectDojo en complément.
- La connexion depuis un runner LAN réel doit valider le TLS, le cookie/login UI anonyme ne prouve pas l'API authentifiée. Le retour 302/403 n'est **pas** une preuve d'un import réussi.

## Rollback et limites

Un échec de DNS, SNI, certificat, source réseau, format, digest, parser, autorisation ou réseau conduit à un **refus sans fallback HTTP/WAN**. Pour révoquer, désactiver le job, supprimer/faire tourner le jeton de service et conserver temporairement les rapports privés pour investigation. Supprimer les fichiers temporaires après clôture du triage et selon la rétention retenue. Ne pas merger/déployer automatiquement.

Sources : https://docs.defectdojo.com/automation/api/api-v2-docs/ et https://docs.defectdojo.com/admin/user_management/about_perms_and_roles/ et `nabla-compose/docs/runbooks/defectdojo-private-ingress-acceptance.md`.
