import csv
from pathlib import Path
from typing import Optional, Dict

BASE_DIR = Path(__file__).resolve().parents[1]
CSV_PATH = BASE_DIR / "data" / "crm_energie.csv"

def get_dossier_by_ien(ien: str) -> Optional[Dict[str, str]]:
    ien = ien.strip()
    if not CSV_PATH.exists():
        return None

    with CSV_PATH.open(encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            if row.get("IEN", "").strip() == ien:
                return row  # ou bien un dict nettoyé
    return None