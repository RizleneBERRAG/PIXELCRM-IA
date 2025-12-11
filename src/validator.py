# src/validator.py
from pathlib import Path
from typing import Dict, Any, List  # <-- List + Path

from .models import Dossier
from .rules import load_rules, validate_fields
from .pdf_reader import extract_text_from_pdfs
from .ai_checker import check_pdfs_with_ai
from .homelior_rules import analyze_homelior   # <-- règles HOMELIOR en Python


def validate_dossier(dossier: Dossier) -> Dict[str, Any]:
    """
    Valide un dossier en combinant :
    - les règles "classiques" (champs CRM, documents attendus)
    - des contrôles techniques sur les PDF
    - une analyse PDF métier (IA pour certains délégataires, règles Python pour HOMELIOR)
    """

    # 1) Règles de configuration
    rules_cfg = load_rules()
    deleg_rules = rules_cfg.get(dossier.delegataire, {})

    # 2) Contrôle des champs CRM / règles basiques
    field_result = validate_fields(dossier, rules_cfg)

    # 3) Lecture des PDF (texte brut ou OCR)
    pdf_texts = extract_text_from_pdfs(dossier.pdf_files) if dossier.pdf_files else {}
    tech_problems: List[str] = []

    # Map nom_fichier -> Path, pratique pour récupérer la taille
    name_to_path: Dict[str, Path] = {p.name: p for p in dossier.pdf_files}

    # 3.a – Détection des PDF vides / scannés
    for name, text in pdf_texts.items():
        path = name_to_path.get(name)
        if not text:
            if path is not None and path.exists() and path.stat().st_size > 0:
                # Fichier non vide mais texte inexploitable → probable scan
                tech_problems.append(
                    f"Le fichier PDF '{name}' ne contient pas de texte exploitable "
                    f"(probablement un scan / une image). Certains contrôles devront être faits manuellement."
                )
            else:
                tech_problems.append(
                    f"Le fichier PDF '{name}' est vide ou illisible."
                )

    # 4) Présence minimale des types de documents **dans les PDF déposés**
    required_docs = deleg_rules.get("required_documents", [])
    lower_names = [p.name.lower() for p in dossier.pdf_files]

    uploaded_missing_docs: List[str] = []
    document_presence: List[Dict[str, Any]] = []

    doc_labels = {
        "devis": "Devis",
        "facture": "Facture",
        "attestation_sur_honneur": "Attestation sur l'honneur",
        "attestation_fin_travaux": "Attestation de fin de travaux",
        "bon_livraison": "Bon de livraison",
        "cadre_contribution": "Cadre de contribution",
    }

    for doc_type in required_docs:
        label = doc_labels.get(doc_type, doc_type)
        detected_name: str | None = None

        if doc_type == "devis":
            detected_name = next((n for n in lower_names if "devis" in n), None)
            if not detected_name:
                uploaded_missing_docs.append(
                    "Document 'devis' non détecté dans les PDF déposés (nom de fichier sans 'devis')."
                )
        elif doc_type == "facture":
            detected_name = next(
                (n for n in lower_names if "facture" in n or "fac_" in n or "fs_" in n),
                None,
            )
            if not detected_name:
                uploaded_missing_docs.append(
                    "Document 'facture' non détecté dans les PDF déposés."
                )
        elif doc_type == "attestation_sur_honneur":
            # on accepte 'attest', 'aft', 'attestation sur l'honneur' dans le nom
            detected_name = next(
                (
                    n
                    for n in lower_names
                    if "attest" in n or "aft" in n or "attestation sur l'honneur" in n
                ),
                None,
            )
            if not detected_name:
                uploaded_missing_docs.append(
                    "Attestation sur l'honneur non détectée dans les PDF déposés "
                    "(attendu : nom contenant 'attest' ou 'aft')."
                )
        elif doc_type == "attestation_fin_travaux":
            detected_name = next((n for n in lower_names if "fin de travaux" in n or "aft" in n), None)
            if not detected_name:
                uploaded_missing_docs.append(
                    "Attestation de fin de travaux non détectée dans les PDF déposés."
                )
        elif doc_type == "bon_livraison":
            detected_name = next((n for n in lower_names if "bl" in n or "livraison" in n), None)
            if not detected_name:
                uploaded_missing_docs.append(
                    "Bon de livraison non détecté dans les PDF déposés (nom contenant 'bl' ou 'livraison' attendu)."
                )
        elif doc_type == "cadre_contribution":
            detected_name = next((n for n in lower_names if "cadre" in n or "contribution" in n), None)
            if not detected_name:
                uploaded_missing_docs.append(
                    "Cadre de contribution non détecté dans les PDF déposés."
                )

        document_presence.append({
            "type": label,
            "present": bool(detected_name),
            "example": detected_name,
        })

    # 5) Analyse PDF
    #    - HOMELIOR : règles 100% Python (pas d'IA)
    #    - autres délégataires : IA comme avant
    if pdf_texts:
        if dossier.delegataire.upper() == "HOMELIOR":
            pdf_result = analyze_homelior(dossier, pdf_texts)
        else:
            pdf_result = check_pdfs_with_ai(dossier, deleg_rules, pdf_texts)
    else:
        pdf_result = {
            "status": "non_conforme",
            "problems": ["Aucun PDF fourni pour ce dossier."],
        }

    # 6) Agrégation du statut global
    global_status = "conforme"
    all_problems: List[str] = []

    # 6.a – Résultats champs CRM (ce que dit le CRM)
    if field_result["status"] != "conforme":
        global_status = "non_conforme"
        all_problems.append(f"Champs manquants: {field_result['missing_fields']}")
        all_problems.append(
            f"Documents manquants (d'après CRM): {field_result['missing_documents']}"
        )

    # 6.b – Problèmes "structurels" liés aux PDFs (vides, scannés, types manquants)
    if tech_problems:
        global_status = "non_conforme"
        all_problems.extend(tech_problems)

    if uploaded_missing_docs:
        global_status = "non_conforme"
        all_problems.extend(uploaded_missing_docs)

    # 6.c – Résultat de l'analyse PDF (IA ou règles Python)
    if pdf_result.get("status") != "conforme":
        global_status = "non_conforme"
        all_problems.extend(pdf_result.get("problems", []))

    summary_reasons: List[str]
    if global_status == "conforme":
        summary_reasons = ["Dossier conforme : aucun écart majeur détecté."]
    else:
        summary_reasons = all_problems[:5] if all_problems else [
            "Dossier non conforme sans détail identifié."
        ]

    return {
        "dossier": dossier.ien,
        "delegataire": dossier.delegataire,
        "status": global_status,
        "field_result": field_result,
        "pdf_result": pdf_result,
        "document_presence": document_presence,
        "problems": all_problems,
        "summary": {"main_reasons": summary_reasons},
    }
