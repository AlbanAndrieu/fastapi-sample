#!/usr/bin/env python3
"""
Dashboard Discovery Utility for opencode (adapté)

- Parcourt le fichier opencode.json
- Liste les commandes dashboard définies dans "command" (clé conforme OpenCode)
- Teste leur présence (health check sur l’URL)
- Propose d’ouvrir dans le navigateur

Usage :
    python scripts/discover_dashboards.py
"""

import json
import os
import sys
import requests
import webbrowser
from time import sleep

# Localisation classique
OPENCODE_JSON_PATH = os.path.join(os.path.dirname(__file__), "..", "opencode.json")


def load_dashboards():
    if not os.path.isfile(OPENCODE_JSON_PATH):
        print(f"Fichier {OPENCODE_JSON_PATH} introuvable.")
        return {}
    with open(OPENCODE_JSON_PATH) as f:
        config = json.load(f)
    # Adaptation: Parcourt la clé 'command' (conforme OpenCode)
    return config.get("command", {})


def check_dashboard(name, dash):
    url = dash.get("url")
    if not dash.get("enabled", False):
        print(f"\n❌ Dashboard {name} (désactivé dans la conf).")
        return False
    if not url:
        print(f"\n❌ Dashboard {name} n’a pas d’url définie.")
        return False
    print(f"\n🔍 Test du dashboard '{name}' sur {url}")
    try:
        resp = requests.get(url, timeout=3)
        if resp.status_code == 200:
            print(f"✅ Dashboard '{name}' dispo sur {url}")
            return True
        else:
            print(f"⚠️ Dashboard '{name}' répond mais code HTTP = {resp.status_code}")
            return False
    except Exception as exc:
        print(f"⚠️ Dashboard '{name}' non accessible: {exc}")
        return False


def main():
    dashboards = load_dashboards()
    found = False
    for name, dash in dashboards.items():
        ok = check_dashboard(name, dash)
        if ok:
            try:
                answer = input(f"Ouvrir dans le navigateur ? (Y/n) ")
            except KeyboardInterrupt:
                print()
                answer = "n"
            if not answer.strip().lower().startswith("n"):
                webbrowser.open(dash["url"])
            found = True
    if not found:
        print("\nAucun dashboard accessible n’a été trouvé dans la conf.")


if __name__ == "__main__":
    main()
