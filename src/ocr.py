# src/ocr.py
from pathlib import Path
import tempfile
import pytesseract
from pdf2image import convert_from_path


def ocr_extract_text(pdf_path: Path) -> str:
    """
    Convertit un PDF en images puis applique Tesseract OCR.
    Utilisé uniquement si extract_text() retourne vide ou quasi-vide.
    """
    try:
        pages = convert_from_path(str(pdf_path), dpi=300)
    except Exception as e:
        print(f"[OCR] Erreur conversion PDF→image pour {pdf_path} : {e}")
        return ""

    text = ""

    for page in pages:
        try:
            with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
                page.save(tmp.name)
                text += pytesseract.image_to_string(tmp.name, lang="fra") + "\n"
        except Exception as e:
            print(f"[OCR] Impossible de traiter une page OCR ({pdf_path}) : {e}")
            continue

    return text.strip()
