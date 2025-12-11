# src/pixelcrm_client.py

import os
from typing import Optional, Dict, Any

import requests
from bs4 import BeautifulSoup


PIXELCRM_AUTH_BASE_URL = "https://crm.pixel-crm.com"
PIXELCRM_LOGIN_URL = f"{PIXELCRM_AUTH_BASE_URL}/Account/Login"

PIXELCRM_APP_BASE_URL = "https://crm.pixel-crm.net"
PIXELCRM_DOSSIER_URL = f"{PIXELCRM_APP_BASE_URL}/Dossiers/Calorifuge/Fiche/Recherche"

PIXELCRM_COMPANY = os.getenv("PIXELCRM_COMPANY")
PIXELCRM_USERNAME = os.getenv("PIXELCRM_USERNAME")
PIXELCRM_PASSWORD = os.getenv("PIXELCRM_PASSWORD")


def _login_pixelcrm(session: requests.Session) -> None:
    if not PIXELCRM_COMPANY or not PIXELCRM_USERNAME or not PIXELCRM_PASSWORD:
        raise RuntimeError(
            "PIXELCRM_COMPANY / PIXELCRM_USERNAME / PIXELCRM_PASSWORD "
            "ne sont pas définies dans les variables d'environnement."
        )

    # on se fait passer pour un vrai navigateur
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/130.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.8,en;q=0.5",
    })

    resp = session.get(PIXELCRM_LOGIN_URL)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    token_input = soup.find("input", {"name": "__RequestVerificationToken"})
    token = token_input["value"] if token_input and token_input.get("value") else ""

    payload = {
        "Input.CustomerCode": PIXELCRM_COMPANY,
        "Input.UserName": PIXELCRM_USERNAME,
        "Input.Password": PIXELCRM_PASSWORD,
        "Input.RememberMe": "false",
        "__RequestVerificationToken": token,
    }

    print("[PixelCRM] POST", PIXELCRM_LOGIN_URL, "avec payload:", {
        "Input.CustomerCode": PIXELCRM_COMPANY,
        "Input.UserName": PIXELCRM_USERNAME,
        "Input.Password": "***",
    })

    login_resp = session.post(
        PIXELCRM_LOGIN_URL,
        data=payload,
        allow_redirects=True,
    )
    print("[PixelCRM] Réponse login:", login_resp.status_code, "URL finale:", login_resp.url)

    # Si PixelCRM nous bloque (403), on renvoie une erreur claire
    if login_resp.status_code == 403:
        raise RuntimeError(
            "Accès à PixelCRM bloqué (403 Forbidden). "
            "Le serveur refuse les connexions automatiques (probable protection anti-bot)."
        )

    login_resp.raise_for_status()

    if "Se connecter" in login_resp.text and "Mot de passe oublié" in login_resp.text:
        raise RuntimeError("Connexion PixelCRM échouée (vérifie les identifiants).")


def _nettoie_ien(ien: str) -> str:
    txt = ien.strip()
    if txt.lower().startswith("n°") or txt.lower().startswith("nº"):
        txt = txt[2:].strip()

    import re
    m = re.search(r"IEN-\d{4}-\d+", txt)
    if m:
        return m.group(0)
    return txt


def get_dossier_from_pixelcrm(ien: str) -> Optional[Dict[str, Any]]:
    ien_clean = _nettoie_ien(ien)
    print(f"[PixelCRM] Recherche dossier pour IEN = '{ien}' => nettoyé = '{ien_clean}'")

    with requests.Session() as s:
        _login_pixelcrm(s)

        params = {
            "handler": "Search",
            "NumDossierInterne": ien_clean,
        }

        print("[PixelCRM] GET", PIXELCRM_DOSSIER_URL, "params =", params)
        resp = s.get(PIXELCRM_DOSSIER_URL, params=params)
        print("[PixelCRM] Réponse recherche:", resp.status_code, "URL:", resp.url)
        resp.raise_for_status()

        html = resp.text
        with open("pixel_dossier_debug.html", "w", encoding="utf-8") as f:
            f.write(html)

        soup = BeautifulSoup(html, "html.parser")

        def _get_input_value(name: str) -> str:
            inp = soup.find("input", {"name": name})
            if inp and inp.get("value"):
                return inp["value"].strip()
            return ""

        data = {
            "ien": ien_clean,
            "client_nom": _get_input_value("Dossier.Beneficiaire_RaisonSociale"),
            "delegataire": _get_input_value("Dossier.Delegataire_Libelle"),
            "siret": _get_input_value("Dossier.Beneficiaire_Siret"),
            "type_operation": _get_input_value("Dossier.TypeOperationCEE_Libelle"),
            "prime_cee": _get_input_value("Dossier.PrimeCEE"),
            "numero_prime": _get_input_value("Dossier.NumeroPrimeCEE"),
        }

        print("[PixelCRM] Données extraites:", data)

        if not any(v for k, v in data.items() if k != "ien"):
            return None

        return data
