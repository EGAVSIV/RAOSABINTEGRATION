"""Incrementally mirror selected JSON folders from EGAVSIV/Data-Collector into COPIEDDATA.
Run inside EGAVSIV/MULTIS GitHub Actions. No schedule is used; workflow is triggered by source updates.
"""
from __future__ import annotations
import hashlib, json, os
from pathlib import Path
import requests

OWNER = "EGAVSIV"
SOURCE_REPO = "Data-Collector"
SOURCE_BRANCH = "main"
FOLDERS = ["stockdata_15", "stockdata_1H", "stockdata_D", "stockdata_W", "stockdata_M"]
ROOT = Path(__file__).resolve().parent
DEST = ROOT
MANIFEST = DEST / ".copy_manifest.json"
API = f"https://api.github.com/repos/{OWNER}/{SOURCE_REPO}/git/trees/{SOURCE_BRANCH}"

session = requests.Session()
session.headers.update({"Accept": "application/vnd.github+json", "User-Agent": "EGAVSIV-MULTIS-Datacopier"})


def load_manifest():
    if MANIFEST.exists():
        try: return json.loads(MANIFEST.read_text(encoding="utf-8"))
        except Exception: pass
    return {}


def main():
    r = session.get(API, params={"recursive": "1"}, timeout=60)
    r.raise_for_status()
    tree = r.json().get("tree", [])
    files = [x for x in tree if x.get("type") == "blob" and x.get("path", "").endswith(".json") and any(x["path"].startswith(f + "/") for f in FOLDERS)]
    old = load_manifest(); new = {}; changed = 0
    for item in files:
        rel = item["path"]; sha = item["sha"]; new[rel] = sha
        target = DEST / rel
        if old.get(rel) == sha and target.exists():
            continue
        raw = f"https://raw.githubusercontent.com/{OWNER}/{SOURCE_REPO}/{SOURCE_BRANCH}/{rel}"
        resp = session.get(raw, timeout=90); resp.raise_for_status()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(resp.content)
        changed += 1
        print("Copied:", rel)
    for rel in old:
        if rel not in new:
            target = DEST / rel
            if target.exists():
                target.unlink(); print("Deleted:", rel)
    DEST.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(new, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Source files: {len(files)} | changed/copied: {changed}")

if __name__ == "__main__": main()
