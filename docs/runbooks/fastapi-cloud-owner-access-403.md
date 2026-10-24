# FastAPI Cloud : erreur 403 de diagnostics

**Point d'entrée actuel :**
[diagnostic télémétrie et accès Cloud](fastapi-observability-acceptance.md).
L'ancien runbook du 21 octobre est conservé sans perte dans
[les archives](../archive/2026-10-24/fastapi-cloud-owner-access-403.md).

Un 403 depuis le poste de diagnostic est un refus de politique,
pas une preuve de panne de l'API ou des cibles Akvorado. Ne jamais
désactiver Cloudflare Access ou l'allowlist source pour obtenir 200.
