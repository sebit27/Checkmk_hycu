#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Checkmk local plugin - HYCU ALL Target Status
#
# Version: 1.2
# Author: SEBIT
#
# Description:
#   - Se connecte à l’API HYCU
#   - Liste toutes les target
#   - Récupère le statut 
#   - Génère une sortie compatible Checkmk
#   - CRITICAL si target non joignable
#

import requests
import sys
import urllib3

# --- Désactive les warnings InsecureRequestWarning ---
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- CONFIGURATION ---
HYCU_HOST = ""hycu.example.com"              # Remplace par l'IP ou hostname de ton Hycu
API_TOKEN = "xxxxxx"     # Ton token API
PAGE_SIZE = 100
URL = f"https://{HYCU_HOST}:8443/rest/v1.0/targets?pageSize={PAGE_SIZE}&pageNumber=1&includeDatastores=false&forceSync=false"

# --- FONCTIONS ---
def get_targets_status():
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Accept": "application/json"
    }
    try:
        response = requests.get(URL, headers=headers, verify=False, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get("entities", [])
    except Exception as e:
        print(f"2 hycu_targets - API request failed: {e}")
        sys.exit(2)

def main():
    targets = get_targets_status()
    if not targets:
        print("3 hycu_targets - No targets found")
        sys.exit(3)

    exit_code = 0
    output_lines = []

    for t in targets:
        name = t.get("name", "unknown")
        service_name = name.replace(" ", "_")  # Supprime les espaces dans le nom du service
        health = t.get("health", "UNKNOWN").upper()
        status_op = t.get("status", "UNKNOWN").upper()

        # Traduction en codes Checkmk
        if health == "GREEN" and status_op == "ACTIVE":
            code = 0
            msg = "OK"
        elif health == "YELLOW":
            code = 1
            msg = "WARNING"
        elif health == "RED":
            code = 2
            msg = "CRITICAL"
        else:
            code = 3
            msg = "UNKNOWN"

        output_lines.append(f"{code} hycu_target_{service_name} - {msg} health={health} status={status_op}")
        exit_code = max(exit_code, code)

    for line in output_lines:
        print(line)
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
