from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List


@dataclass
class Dossier:
    ien: str
    delegataire: str
    client_nom: str

    # Champs CRM (tu complèteras avec les vrais noms plus tard)
    fields: Dict[str, str]  # ex: {"N° SIRET": "500298...", "Type d'opération": "..."}

    # Liste des chemins des PDF associés
    pdf_files: List[Path] = field(default_factory=list)

    @property
    def label_client(self) -> str:
        """Nom lisible pour le dossier client."""
        return f"{self.ien} - {self.client_nom}"
