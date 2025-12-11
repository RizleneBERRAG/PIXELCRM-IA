from pathlib import Path
from src.models import Dossier
from src.validator import validate_dossier


if __name__ == "__main__":
    dossier = Dossier(
        ien="IEN-TEST-0001",
        delegataire="ISOLIDARITE - TOTALENERGIES",
        client_nom="CLIENT TEST",
        fields={
            "N° SIRET": "50029875700013",
            "Type d'opération CEE": "Bâtiment tertiaire",
            "Prime CEE": "3189.9",
            "N° prime CEE": "",  # volontairement vide → NON CONFORME
            "DOC::Devis signé": "yes",
            "DOC::Facture": "yes",
            "DOC::Attestation sur l'honneur": ""
        },
        pdf_files=[Path("data/pdfs/test.pdf")]
    )

    result = validate_dossier(dossier)

    print("===== Résultat analyse dossier =====")
    print("Status global :", result["status"])
    print("Problèmes détectés :")
    for p in result["problems"]:
        print(" -", p)
