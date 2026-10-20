# DefectDojo — contrats des rapports fastapi-sample

**Décision 2026-10-19 : supprimer l'exporteur spécifique Trivy.**
Le collecteur GitHub Actions est **unique dans nabla-compose** ; ce dépôt
produit les rapports natifs des scanners et le reçu privé
`scan-receipt.json` avec leurs empreintes SHA-256. Aucun filtrage
ou format de rapport spécifique à DefectDojo n'est requis côté application.

## Producteur

- `scripts/security/run_security_scans.py` produit `trivy.json`,
  `sbom.cdx.json`, les résultats Betterleaks et, sur `master`, les
  rapports complémentaires Semgrep/licences/DAST autorisés.
- Option `--sarif` : `trivy.sarif` est converti depuis le même rapport
  natif, **sans second scan**. Les fichiers restent privés et ne sont
  pas des artefacts GitHub publics par défaut.
- Betterleaks et Trivy CRITICAL/secrets demeurent **bloquants** pour les
  gates de sécurité PR. Ne pas déclarer un scan non exécuté PASS.
- SARIF CodeQL est lisible par le parseur `CodeQL Scan` de DefectDojo ;
  le parseur générique SARIF exige une politique spécifique. Eviter les
  doublons natif + SARIF dans deux Tests d'un même Engagement.

## Consommateur partagé (nabla-compose)

Le même `scripts/security/poll-defectdojo-gh-artifacts.py` peut collecter
les artefacts existants de dépôts allowlistés, **sans nouveau collecteur**
ni Cron par dépôt. Il doit valider la provenance GitHub du workflow,
`master`, le commit SHA, un inventaire ZIP explicite et les tailles
avant de déposer un rapport dans sa boîte privée.
Le transport GitHub est facultatif ; aucun nouveau workflow coûteux
n'est lancé pour DefectDojo par ce contrat.

**Règle de confidentialité :** aucun artefact brut contenant des
secrets, cookies, captures HTTP d'administration, PII ou données
opérationnelles internes ne doit être envoyé à GitHub. Dans ce cas,
l'importeur LAN `scripts/security/import_defectdojo.py` conserve les
rapports complets via HTTPS/SNI vérifié et jeton non-admin,
après reçu `master/complete` et empreinte approuvée.
Il refuse les preuves de secrets Trivy, sans transformer ou réécrire
le rapport accepté. L'absence de filtrage n'autorise pas la publication
incontrôlée de données sensibles.

## Acceptation encore nécessaire

- Lier les noms réels des workflows/artefacts et leurs sorties natives
  au collecteur existant, sans le faux workflow
  `DefectDojo Trivy Handoff (FastAPI)` ni le ZIP filtré antérieur.
- Vérifier une collecte depuis TrueNAS sur un run `master` réellement
  réussi ; toute absence d'artefact doit produire `NOT_OBSERVED`.
- Confirmer ACL LAN seules pour `defectdojo.int.albandrieu.com`,
  TLS origine, absence de NAT/Cloudflare public et test RBAC négatif
  sur un autre Product/Engagement.
- Import API accepté != traitement Celery ni déduplication prouvée ;
  vérifier ces étapes séparément avant activation automatique.

Le runtime DefectDojo, son GitHub App et sa Cron sont gérés uniquement
dans `nabla-compose`; ce document décrit l'interface applicative.
