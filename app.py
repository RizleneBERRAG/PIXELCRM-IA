from pathlib import Path
from typing import List

from fastapi import FastAPI, Form, File, UploadFile, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.models import Dossier
from src.validator import validate_dossier
from src.drive_export import export_dossier_to_drive
from src.pixelcrm_client import get_dossier_from_pixelcrm

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="PixelCRM Conformité IA")

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    delegataires = [
        "ISOLIDARITE - TOTALENERGIES",
        "LSF ENERGIE - SCA PETROLE ET DERIVES",
        "HOMELIOR",
        "STEREF FRANCE",
    ]
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "delegataires": delegataires},
    )


@app.get("/pixelcrm-prefill")
async def pixelcrm_prefill(ien: str):
    """
    Endpoint appelé en AJAX depuis le front pour pré-remplir les champs
    à partir de PixelCRM.
    """
    try:
        data = get_dossier_from_pixelcrm(ien)
    except Exception as e:
        print("Erreur PixelCRM :", e)
        raise HTTPException(status_code=500, detail="Erreur lors de l'appel à PixelCRM.")

    if not data:
        raise HTTPException(status_code=404, detail="Dossier introuvable dans PixelCRM.")

    return JSONResponse(data)


@app.post("/analyze")
async def analyze_dossier(
    ien: str = Form(...),
    client_nom: str = Form(...),
    delegataire: str = Form(...),
    siret: str = Form(""),
    type_operation: str = Form(""),
    prime_cee: str = Form(""),
    numero_prime: str = Form(""),
    files: List[UploadFile] = File(...),
):
    # 1) Dossier local pour stocker les PDFs
    upload_root = BASE_DIR / "uploads"
    upload_root.mkdir(exist_ok=True)

    pdf_paths: list[Path] = []
    ignored_files: list[str] = []

    # 2) Sauvegarder chaque fichier (en ignorant les chemins des sous-dossiers)
    for f in files:
        safe_name = Path(f.filename).name  # on ne garde que le nom
        dest = upload_root / safe_name

        content = await f.read()
        if not content:
            ignored_files.append(safe_name)
            continue

        with dest.open("wb") as out:
            out.write(content)

        pdf_paths.append(dest)

    # 3) Construire l'objet Dossier pour les règles Python
    fields = {
        "N° SIRET": siret,
        "Type d'opération CEE": type_operation,
        "Prime CEE": prime_cee,
        "N° prime CEE": numero_prime,
    }

    dossier = Dossier(
        ien=ien,
        delegataire=delegataire,
        client_nom=client_nom,
        fields=fields,
        pdf_files=pdf_paths,
    )

    # 4) Analyse (règles Python)
    result = validate_dossier(dossier)

    if ignored_files:
        ignored_msg = f"Fichiers PDF ignorés car vides : {', '.join(ignored_files)}"
        result.setdefault("problems", []).append(ignored_msg)
        summary = result.setdefault("summary", {})
        reasons = summary.setdefault("main_reasons", [])
        if ignored_msg not in reasons:
            reasons.append(ignored_msg)

    # 5) Export sur Google Drive
    try:
        drive_url = export_dossier_to_drive(dossier, result, pdf_paths)
    except Exception as e:
        print("Erreur export Drive :", e)
        drive_url = None

    result["drive_url"] = drive_url
    return JSONResponse(result)
