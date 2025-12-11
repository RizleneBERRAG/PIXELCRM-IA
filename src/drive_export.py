from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, List

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from .models import Dossier

# Accès aux fichiers créés par l'appli
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

BASE_DIR = Path(__file__).resolve().parent.parent

# 👉 Mets ici l'ID du dossier racine "PixelCRM-IA" sur ton Google Drive
ROOT_DRIVE_FOLDER_ID = "18M5EeWs37DtTJF83JSysE2m6eo4gefZo"


def get_drive_service():
    creds = None
    token_path = BASE_DIR / "token.json"
    cred_path = BASE_DIR / "credentials.json"

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(cred_path), SCOPES)
            creds = flow.run_local_server(port=0)
        with token_path.open("w") as token_file:
            token_file.write(creds.to_json())

    service = build("drive", "v3", credentials=creds)
    return service


def ensure_folder(service, name: str, parent_id: Optional[str]) -> str:
    """Retourne l'ID d'un dossier (le crée s'il n'existe pas)."""
    # On protège les apostrophes dans les noms
    safe_name = name.replace("'", "\\'")

    query_parts = [
        f"name = '{safe_name}'",
        "mimeType = 'application/vnd.google-apps.folder'",
        "trashed = false",
    ]
    if parent_id:
        query_parts.append(f"'{parent_id}' in parents")

    query = " and ".join(query_parts)

    resp = (
        service.files()
        .list(q=query, spaces="drive", fields="files(id, name)", pageSize=1)
        .execute()
    )
    files = resp.get("files", [])
    if files:
        return files[0]["id"]

    # Sinon on le crée
    metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
    }
    if parent_id:
        metadata["parents"] = [parent_id]

    folder = service.files().create(body=metadata, fields="id").execute()
    return folder["id"]


def upload_file(service, local_path: Path, parent_id: str):
    file_metadata = {
        "name": local_path.name,
        "parents": [parent_id],
    }
    media = MediaFileUpload(str(local_path), resumable=True)
    file = (
        service.files()
        .create(body=file_metadata, media_body=media, fields="id, name")
        .execute()
    )
    return file["id"]


def export_dossier_to_drive(dossier: Dossier, result: dict, pdf_paths: List[Path]) -> str:
    """
    Crée la structure sur Drive :
    PixelCRM-IA /
      Conforme | Non Conformes /
        Délégataire /
          IEN - NOM CLIENT /
            PDFs + rapport.json

    Retourne l'URL du dossier client sur Drive.
    """
    service = get_drive_service()

    status_folder_name = "Conforme" if result["status"] == "conforme" else "Non Conformes"

    # 1. /PixelCRM-IA/Conforme ou /Non Conformes
    status_folder_id = ensure_folder(service, status_folder_name, ROOT_DRIVE_FOLDER_ID)

    # 2. /.../<DÉLÉGATAIRE>
    deleg_folder_id = ensure_folder(service, dossier.delegataire, status_folder_id)

    # 3. /.../<DÉLÉGATAIRE>/<IEN - NOM CLIENT>
    client_folder_name = dossier.label_client
    client_folder_id = ensure_folder(service, client_folder_name, deleg_folder_id)

    # 4. Upload des PDFs
    for pdf in pdf_paths:
        upload_file(service, pdf, client_folder_id)

    # 5. Générer un rapport.json temporaire et l'uploader
    tmp_dir = BASE_DIR / "tmp"
    tmp_dir.mkdir(exist_ok=True)
    rapport_path = tmp_dir / "rapport.json"

    with rapport_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    upload_file(service, rapport_path, client_folder_id)

    # URL Drive du dossier client
    url = f"https://drive.google.com/drive/folders/{client_folder_id}"
    return url
