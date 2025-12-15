#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Checkmk local plugin - HYCU All VMs Backup Status
#
# Version: 3.4
# Author: SEBIT
#
# Description:
#   - Se connecte à l’API HYCU
#   - Liste toutes les VMs et marque celles exclues
#   - Récupère le statut du dernier backup de chacune
#   - Ignore les VMs exclues
#   - Génère une sortie compatible Checkmk
#   - Chaque service a un nom unique basé sur l’UUID
#   - CRITICAL si dernier backup > 1 jour
#

import requests
import urllib3
import datetime
import re

# === CONFIGURATION ===
HYCU_HOST = "hycu.example.com"          # Nom ou IP du serveur HYCU
HYCU_API_TOKEN = "xxxxxxxxxxxxxxxxxxxx" # ⚠️ Mets ton token ici
VERIFY_SSL = False                      # True si certificat valide
TIMEOUT = 10                            # Timeout API
PAGE_SIZE = 200                         # Nombre de VMs par page
CRITICAL_DAYS = 1                        # Seuil critique en jours
# ======================

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
HEADERS = {"Authorization": f"Bearer {HYCU_API_TOKEN}"}


def cmk_output(status, service, message, uuid=None):
    """Sortie compatible Checkmk local check"""
    safe_service = re.sub(r'[^A-Za-z0-9_-]', '_', service)
    if uuid:
        safe_service = f"{safe_service}_{uuid[:8]}"
    safe_message = message.replace(" - ", " | ")
    print(f"{status} HYCU_{safe_service} - {safe_message}")


def get_all_vms():
    """Récupère toutes les VMs HYCU et marque celles exclues"""
    vms = []
    page = 1
    while True:
        url = f"https://{HYCU_HOST}:8443/rest/v1.0/vms?pageSize={PAGE_SIZE}&pageNumber={page}"
        try:
            r = requests.get(url, headers=HEADERS, verify=VERIFY_SSL, timeout=TIMEOUT)
            r.raise_for_status()
            j = r.json()
        except Exception as e:
            cmk_output(3, "HYCU", f"Erreur API (liste VMs): {e}")
            return []

        entities = j.get("entities", [])
        if not entities:
            break

        for vm in entities:
            # Marque la VM comme exclue si complianceReason indique l'exclusion
            vm['excluded'] = vm.get('complianceReason') == "The Exclude policy is assigned."
            vms.append(vm)

        if len(entities) < PAGE_SIZE:
            break
        page += 1

    return vms


def get_vm_backups(vm_uuid):
    """Récupère les sauvegardes récentes d'une VM"""
    url = f"https://{HYCU_HOST}:8443/rest/v1.0/vms/{vm_uuid}/backups?pageSize=5&pageNumber=1"
    try:
        r = requests.get(url, headers=HEADERS, verify=VERIFY_SSL, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def check_vm_backup(vm):
    """Analyse le statut de la dernière sauvegarde d'une VM"""
    if vm.get('excluded'):
        return  # VM exclue, on ne remonte rien

    vm_name = vm.get("vmName", "Unknown")
    vm_uuid = vm.get("uuid")
    backups = get_vm_backups(vm_uuid)

    # Gestion des erreurs API
    if "error" in backups:
        cmk_output(3, vm_name, f"Erreur API backup : {backups['error']}", vm_uuid)
        return

    # Vérifie s'il n'y a pas de backup
    if backups.get("metadata", {}).get("grandTotalEntityCount", 0) == 0:
        cmk_output(2, vm_name, "Aucune sauvegarde trouvée", vm_uuid)
        return

    last_backup = backups["entities"][0]
    status = last_backup.get("status", "UNKNOWN")

    # --- récupération du timestamp le plus fiable ---
    timestamp_ms = last_backup.get("restorePointInMillis")
    if timestamp_ms:
        backup_dt = datetime.datetime.utcfromtimestamp(timestamp_ms / 1000)
        backup_time = backup_dt.strftime("%Y-%m-%d %H:%M:%S")
    else:
        backup_time = (
            last_backup.get("endTime")
            or last_backup.get("startTime")
            or last_backup.get("creationTime")
            or "N/A"
        )

    # Mapping HYCU → Checkmk
    status_map = {
        "OK": 0,
        "WARNING": 1,
        "FATAL": 2,
        "IN_PROGRESS": 1,
        "UNKNOWN": 3,
    }
    cmk_state = status_map.get(status, 3)

    # Calcul de l'âge du backup et gestion alerte CRITICAL > 1 jour
    if backup_time != "N/A":
        try:
            if isinstance(timestamp_ms, int):
                age_days = (datetime.datetime.utcnow() - backup_dt).days
            else:
                backup_time_clean = backup_time.split(".")[0]
                dt = datetime.datetime.strptime(backup_time_clean, "%Y-%m-%dT%H:%M:%S")
                age_days = (datetime.datetime.utcnow() - dt).days

            if age_days > CRITICAL_DAYS:
                cmk_state = 2  # CRITICAL
                msg = f"Backup {status} ({backup_time}) - age={age_days}d (too old!)"
            else:
                msg = f"Backup {status} ({backup_time}) - age={age_days}d"
        except Exception:
            msg = f"Backup {status} ({backup_time})"
    else:
        msg = f"Backup {status} (no backup date)"

    cmk_output(cmk_state, vm_name, msg, vm_uuid)


def main():
    vms = get_all_vms()
    if not vms:
        cmk_output(3, "HYCU", "Aucune VM trouvée ou erreur API")
        return

    for vm in vms:
        check_vm_backup(vm)


if __name__ == "__main__":
    main()
