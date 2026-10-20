# Contrat direct Backstage v2 — FastAPI ↔ Site Alban (pré-Keycloak)

Date : 2026-10-20. PR fastapi-sample #358 ; alignement sur **nabla-compose PR #265** et sur le parseur `nabla-site-alban/lib/homelabCatalogV2.ts` existant. **Aucun endpoint ou lecteur transitoire `/api/site/catalog/v1`**.

## Contrat unique

```http
GET /api/site/catalog/v2 HTTP/1.1
Host: fastapi-sample.fastapicloud.dev
Accept: application/json
X-Diagnostics-Key: <secret serveur uniquement>
```

La réponse suit exactement la forme canonique Backstage v2 :

```json
{
  "schemaVersion": 2,
  "model": "backstage",
  "catalogRevision": "sha256:<64 chiffres hexadécimaux>",
  "entities": [
    {
      "apiVersion": "backstage.io/v1alpha1",
      "kind": "Component",
      "entityRef": "component:default/api",
      "sourcePath": "apps/api/catalog-info.yaml",
      "metadata": {"name": "api", "title": "API"},
      "spec": {"type": "service", "dependsOn": ["resource:default/postgres"]}
    }
  ]
}
```

L'exemple n'est qu'une forme : les relations référencées doivent réellement exister dans le graphe. `catalogRevision` est le **hash de la source canonique complète**, calculé/contrôlé depuis les entités Backstage originelles de `nabla-compose`, **pas** le hash de la projection filtrée vers le site. Préserver `entityRef` et les relations Backstage ; ne pas revenir aux IDs ou `services[]` v1.

Le DTO serveur exclut explicitement les annotations, les descriptions privées, les URLs, IP, ports, preuves et secrets. Il conserve uniquement les identités, types, provenance portable Git, tags, deux labels de criticité, et les relations vers des références canoniques existantes. Les métadonnées **opérateur complètes** restent sur les routes OWNER avec vérification du CIDR.

## Source d'autorité et disponibilité

Le fournisseur est `https://raw.githubusercontent.com/AlbanAndrieu/nabla-compose/master/catalog/generated/entities.json`, fichier généré en PR Compose #265 (en attente sur `master`). `HOMELAB_CATALOG_V2_URL` peut pointer **temporairement** vers la branche de PR #265 pour une recette contrôlée, mais le schéma, le domaine, le dépôt et le chemin restent fixés ; les redirections HTTP et proxys ambiants sont refusés. Une fois #265 fusionnée, utiliser `master`. Aucun recours à `homelab-services.json`, `public/homelab-services.json` ou à une conversion v1 → v2. Cache uniquement des succès v2 vérifiés, max 300 s ; erreur upstream, source 404, schéma/empreinte/relations incohérents → HTTP 503 `no-store`. La disponibilité technique tant que #265 n'est pas fusionnée est donc volontairement **non assurée**.

## Adaptation nécessaire du site

1. Le serveur Next.js uniquement appelle `/api/site/catalog/v2` avec `process.env.DIAGNOSTICS_ACCESS_KEY` comme header `X-Diagnostics-Key`, `cache: "no-store"`, `redirect: "error"` et un timeout borné. Réutiliser **`parseHomelabCatalogV2` et `catalogV2ServiceViews`** déjà implémentés, sans nouveau parseur.
2. Retirer les chargements v1/fallback locaux dans `lib/homelabServices.ts`, et toute projection de fichiers statiques contenant IP internes/URL/ports. En cas de 401/403/404/503 ou réponse v2 invalide, afficher un état indisponible sans republier l'ancien catalogue.
3. Vercel reçoit une requête propriétaire **depuis l'IP du navigateur domicile** et effectue ensuite une sortie réseau depuis **une autre IP**, non à ajouter à `HOMELAB_TRUSTED_CIDRS`. Le nouvel endpoint est classé SERVICE, avec clé obligatoire, sans accès au catalogue brut. Aucun jeton dans React, `NEXT_PUBLIC_*`, HTML, URL, cache public ni logs. Le CIDR + identité propriétaire restent indispensables pour les routes diagnostics.
4. Vérifier EN/FR Architecture, les relations canoniques, le `catalogRevision` unique entre consommateurs, l'absence de fuite dans les bundles ou headers publics et l'indépendance des contrôles WAN FastAPI Cloud. Keycloak pourra ensuite remplacer la clé statique avec une identité machine OIDC distincte de l'identité humaine.

**Validation réelle : NON EFFECTUÉE** pour les configurations Vercel, Preview, déploiement production, Gatus/Prometheus ou sécurité des ports WAN. PR fastapi-sample conservée en Draft, sans fusion automatique.
