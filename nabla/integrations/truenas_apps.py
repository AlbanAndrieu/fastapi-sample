from fastapi import APIRouter

from nabla.integrations.truenas_api_ws import fetch_truenas_apps_sync

router = APIRouter()


def get_truenas_apps_json():
    """
    Utilise le client officiel TrueNAS Websocket (chart.release.query, sync).
    Transforme la liste releases → format services attendu.
    """
    releases = fetch_truenas_apps_sync()
    services = []
    for app in releases:
        name = app.get("name", "?")
        res = app.get("resources") or {}
        internalPort = None
        if res.get("web_port"):
            internalPort = res["web_port"].get("port")
        elif res.get("host_ports"):
            internalPort = res["host_ports"][0].get("host_port")
        services.append(
            {
                "name": name,
                "status": app.get("status"),
                "internalHost": "172.17.0.24",  # ou param/auto si besoin
                "internalPort": internalPort,
                # Ajoute ici tunnel, icon, enrichissement selon besoin
            },
        )
    return {"version": 1, "services": services}


@router.get("/internal/truenas-apps", tags=["internal"])
def truenas_apps_endpoint():
    """Expose the TrueNAS applications list through FastAPI."""
    return get_truenas_apps_json()
