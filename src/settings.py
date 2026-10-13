from paths import ROOT, INBOX, PACKAGED
from pathlib import Path
import json
import os
import threading

SETTINGS_FILE = ROOT / "data/settings.json"
LOCK = threading.RLock()
DEFAULTS = {
    "source_folders": [str(INBOX)], "top_k": 8, "search_mode": "hybrid",
    "auto_scan": True, "scan_interval": 30, "start_service_on_launch": True,
    "keep_in_menu_bar": True, "app_managed": PACKAGED,
    "keep_snapshots": False, "cache_retention_days": 30,
}

def load_settings():
    with LOCK:
        if not SETTINGS_FILE.exists(): return dict(DEFAULTS)
        return {**DEFAULTS, **json.loads(SETTINGS_FILE.read_text())}

def save_settings(changes):
    with LOCK:
        if not isinstance(changes, dict) or set(changes) - set(DEFAULTS):
            raise ValueError("Unknown settings")
        value = {**load_settings(), **changes}
        if type(value["top_k"]) is not int or not 1 <= value["top_k"] <= 20:
            raise ValueError("Top K must be 1..20")
        if value["search_mode"] not in ("hybrid", "keyword", "semantic"):
            raise ValueError("Unknown search mode")
        if type(value["scan_interval"]) is not int or not 15 <= value["scan_interval"] <= 600:
            raise ValueError("Scan interval must be 15..600 seconds")
        if type(value['cache_retention_days']) is not int or not 1 <= value['cache_retention_days'] <= 365:
            raise ValueError('Cache retention must be 1..365 days')
        for key in ("keep_snapshots", "auto_scan", "start_service_on_launch", "keep_in_menu_bar", "app_managed"):
            if type(value[key]) is not bool: raise ValueError(f"{key} must be boolean")
        if not isinstance(value["source_folders"], list): raise ValueError("Folder list required")
        folders = []
        for item in value["source_folders"]:
            if not isinstance(item, str) or not Path(item).is_absolute(): raise ValueError("Absolute folder path required")
            p = Path(item).resolve()
            if p.exists() and not p.is_dir(): raise ValueError("Source must be a folder")
            # A temporarily disconnected disk stays configured and is shown as unavailable.
            if str(p) not in folders: folders.append(str(p))
        value["source_folders"] = folders
        temp = SETTINGS_FILE.with_suffix(".tmp")
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2))
        os.replace(temp, SETTINGS_FILE)
        return value
