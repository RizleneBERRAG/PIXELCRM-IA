import json
from pathlib import Path
from typing import Dict, Any
from .models import Dossier


CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "rules.json"


def load_rules() -> Dict[str, Any]:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_fields(dossier: Dossier, rules_cfg: Dict[str, Any]) -> Dict[str, Any]:
    deleg = dossier.delegataire
    r = rules_cfg.get(deleg, {})

    required_fields = r.get("required_fields", [])
    required_docs = r.get("required_documents", [])

    missing_fields = [
        f for f in required_fields
        if not dossier.fields.get(f)
    ]

    # Ici, on suppose que dossier.fields contient aussi des indicateurs
    # sur la présence de documents (tu adapteras selon ce que donne le CRM)
    missing_docs = [
        d for d in required_docs
        if not dossier.fields.get(f"DOC::{d}")
    ]

    status = "conforme" if not missing_fields and not missing_docs else "non_conforme"

    return {
        "status": status,
        "missing_fields": missing_fields,
        "missing_documents": missing_docs
    }
