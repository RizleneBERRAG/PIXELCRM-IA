from pathlib import Path
from typing import Dict, List

from pypdf import PdfReader
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io


def extract_text_from_pdfs(pdf_paths: List[Path]) -> Dict[str, str]:
    """
    Pour chaque PDF :
    1) On essaie d'extraire le texte 'normal' avec pypdf.
    2) Si le texte est vide ou très court, on fait de l'OCR avec Tesseract.
    On retourne {nom_fichier: texte}.
    """
    texts: Dict[str, str] = {}

    for path in pdf_paths:
        print(f"[PDF] Lecture : {path}")
        text = ""

        # ---------- 1) Extraction classique avec pypdf ----------
        try:
            reader = PdfReader(str(path))
            pages_text: List[str] = []

            for i, page in enumerate(reader.pages):
                try:
                    page_text = page.extract_text() or ""
                    pages_text.append(page_text)
                except Exception as e_page:
                    print(f"[WARN] Erreur extraction texte page {i+1} de {path.name} : {e_page}")

            text = "\n".join(pages_text).strip()
            print(f"[DEBUG] {path.name} → texte brut pypdf = {len(text)} caractères")

        except Exception as e_pdf:
            print(f"[ERROR] Erreur pypdf sur {path.name} : {e_pdf}")
            text = ""

        # ---------- 2) Si pas de texte -> OCR avec Tesseract ----------
        if len(text) < 50:  # seuil : on considère que c'est un scan ou quasi vide
            print(f"[OCR] Texte trop court ou vide dans {path.name}, lancement OCR…")
            try:
                doc = fitz.open(str(path))
                ocr_chunks: List[str] = []

                for i, page in enumerate(doc):
                    try:
                        # rendu en image
                        pix = page.get_pixmap(dpi=200)
                        img_bytes = pix.tobytes("png")
                        img = Image.open(io.BytesIO(img_bytes))

                        # essai fra+eng, sinon fallback eng
                        try:
                            ocr_text = pytesseract.image_to_string(img, lang="fra+eng")
                        except Exception as e_lang:
                            print(f"[WARN] Langue 'fra+eng' indisponible, fallback 'eng' : {e_lang}")
                            ocr_text = pytesseract.image_to_string(img)

                        ocr_chunks.append(ocr_text)

                    except Exception as e_page:
                        print(f"[WARN] Erreur OCR page {i+1} de {path.name} : {e_page}")

                doc.close()
                ocr_full = "\n".join(ocr_chunks).strip()
                print(f"[DEBUG] {path.name} → texte OCR = {len(ocr_full)} caractères")

                # Si l'OCR a trouvé quelque chose, on l’utilise
                if ocr_full:
                    text = ocr_full

            except Exception as e_ocr:
                print(f"[ERROR] Erreur OCR sur {path.name} : {e_ocr}")

        texts[path.name] = text

    return texts


# Compatibilité avec d'anciens imports éventuels
def read_pdfs(pdf_paths: List[Path]) -> Dict[str, str]:
    return extract_text_from_pdfs(pdf_paths)
