# Inventaire des tableaux de bord et séries — H14 (21/11/2026)

Pré-requis de la ligne H14 du portefeuille et de F06/F07 : inventorier ce qui
existe **avant** tout nouveau panneau, série ou dashboard.

- **Vantage** : workstation, lecture seule, 21/11/2026 vers 00:30 UTC.
- **Sources** : API Prometheus TrueNAS (`/api/v1/label/__name__/values`,
  `/api/v1/query`, `/api/v1/rules`), dashboards Grafana provisionnés dans
  `nabla-compose` (`apps/grafana/config/dashboards/`, `master`), et requêtes
  PromQL du code FastAPI.
- **Hors périmètre** : les dashboards créés à la main dans l'UI Grafana
  (l'API de recherche exige une authentification) ; état **NOT_VERIFIED**.

## Prometheus

7 808 noms de séries, 39 jobs scrappés, 18 groupes de règles (28 règles
d'enregistrement `nabla:*`, 44 alertes).

| Famille | Présente | Consommateur FastAPI | Conséquence |
| --- | --- | --- | --- |
| `container_*` (job `truenas_cadvisor`) | **Non** : aucun job, aucune série sur 30 jours | heatmap F07 (`home-operations-model.js`), dimensionnement de la topologie (`topology_telemetry.py`), historique (`home_metrics_history.py`) | Vues vides **par conception** : Compose a désactivé cAdvisor (coût CPU/I/O, `apps/cadvisor/README.md`). L'interface affiche `telemetry_unavailable` / `—`, sans faux vert. |
| `nabla:network_flow:pfsense_*` | Règle présente, **aucune valeur** | flux de la topologie (`flow_source: pfsense_pflow_ipfix_via_akvorado`) | Source morte depuis le retrait de pfSense le 18/11. |
| `node_filesystem_{size,avail}_bytes{fstype="zfs"}` (job `truenas_node`) | Oui : 202 montages ZFS, dont **124** `/mnt/cpool/<service>` | aucun | Occupation par dataset disponible et sourcée (`size - avail`), sans passer par `container_fs_usage_bytes`. |
| `node_zfs_zpool_dataset_*` | Oui : compteurs d'I/O par dataset | aucun | Débit et opérations par dataset, pas l'occupation. |
| `fastapi_*` (job `fastapi_sample`) | Oui : 14 familles | métriques propres | Instance TrueNAS uniquement. |
| `gatus_results_*` | Oui | rapprochement F03 | Déjà consommé par le health board. |

## Grafana (dashboards provisionnés)

| UID | Panneaux | Familles utilisées | État |
| --- | --- | --- | --- |
| `nabla_observability_stack` | 8 | santé de la pile | réutilisable |
| `nabla_pfsense_netflow_akvorado` | 8 | `nabla:network_flow`, `nabla:core`, `nabla:telemetry` | flux pfSense morts depuis le 18/11 |
| `nabla_media_stack` | 14 | `container_*`, `node_filesystem` | panneaux `container_*` vides (cAdvisor absent) |
| `pfsense_*`, `pfsense-traffic`, `adkq2ms` (8 dashboards) | 46 | exporter pfSense | sans objet depuis le retrait de pfSense |

## Décision de couverture

- Ne créer **aucun** dashboard Grafana ni aucune série pour F06/F07 : la
  heatmap FastAPI reste la vue OWNER ; seule sa source manque.
- La recette F07 « heatmap cAdvisor OWNER » n'est pas exécutable tant que la
  source de ressources par App n'est pas choisie (question au propriétaire
  dans [l'état de la passe](2026-11-21-roadmap-loop-state.md)).
- L'occupation ZFS de F07 peut s'appuyer sur `node_filesystem_*` ; la
  correspondance dataset → service (`/mnt/cpool/<service>`) est une
  convention à confirmer avant de l'afficher.
- Le retrait des 8 dashboards pfSense et du panneau de flux appartient à
  Compose.

Reproduire (lecture seule, workstation) :

```bash
curl -sS -m 15 http://172.17.0.24:9090/api/v1/label/__name__/values | jq '.data | length'
curl -sS -m 15 -G http://172.17.0.24:9090/api/v1/query \
  --data-urlencode 'query=count(container_cpu_usage_seconds_total)' | jq '.data.result'
curl -sS -m 15 -G http://172.17.0.24:9090/api/v1/query \
  --data-urlencode 'query=count(node_filesystem_size_bytes{job="truenas_node",fstype="zfs",mountpoint=~"/mnt/cpool/[^/]+"})' | jq '.data.result'
```
