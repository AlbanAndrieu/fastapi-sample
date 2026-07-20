import requests
from fastapi import APIRouter, Response
from nabla.integrations.truenas_apps import get_truenas_apps_json
import logging

router = APIRouter()

REFERENCE_URL = "https://www.albanandrieu.com/homelab-services.json"


# Helper: build index from reference by (name, internalPort)
def service_index(services):
    idx = {}
    for s in services:
        k = (s.get("name"), s.get("internalPort"))
        idx[k] = s
    return idx


@router.get("/internal/services.json")
def merged_services():
    logging.info("Fetching reference services from master JSON...")
    try:
        ref = requests.get(REFERENCE_URL, timeout=15)
        ref.raise_for_status()
        ref_json = ref.json()
    except Exception as e:
        return Response(f"Failed to fetch reference JSON: {e}", status_code=502)
    ref_svcs = ref_json.get("services", [])
    ref_idx = service_index(ref_svcs)

    try:
        tn_json = get_truenas_apps_json()
        tn_svcs = tn_json.get("services", [])
    except Exception as e:
        return Response(f"Failed to fetch TrueNAS apps: {e}", status_code=502)

    # Merge!
    merged = []
    used_keys = set()
    # Always include all reference+enrich where possible
    for s in tn_svcs:
        k = (s.get("name"), s.get("internalPort"))
        ref = ref_idx.get(k, {})
        # Prefer the reference fields, but override port/host with live TrueNAS
        merged_s = dict(ref)  # Copy all enrichment fields
        merged_s.update(s)  # But ensure name, host, port, and minimal info up to date
        merged.append(merged_s)
        used_keys.add(k)
    # Add any reference service not already used (TrueNAS didn't detect it but it's in the master list)
    for k, ref in ref_idx.items():
        if k not in used_keys:
            merged.append(dict(ref))
    return {"version": 1, "services": merged}
