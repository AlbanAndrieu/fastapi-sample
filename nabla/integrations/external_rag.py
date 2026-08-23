import os
import requests

OPENRAG_URL = os.environ.get("OPENRAG_URL", None)


def external_rag_search(query: str, k: int = 3) -> list[str]:
    """
    Query OpenRAG external server (if configured/set) for relevant context. Fallback is handled by the caller.
    Returns a list of document texts. Returns [] if unavailable or error.
    """
    url = OPENRAG_URL and f"{OPENRAG_URL.rstrip('/')}/retrieve"
    if not url:
        return []
    try:
        resp = requests.post(url, json={"queries": [query], "k": k}, timeout=15)
        resp.raise_for_status()
        results = resp.json().get("responses", [{}])
        return results[0].get("results", []) if results and isinstance(results, list) else []
    except Exception:
        return []
