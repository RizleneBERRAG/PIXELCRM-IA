import requests

def verify_address(adresse: str, city: str = "", postal: str = "") -> bool:
    """
    Retourne True si l'adresse semble exister (géocodage OK), False sinon.
    """
    q = " ".join([adresse, postal, city])
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": q, "format": "json", "limit": 1}

    r = requests.get(url, params=params, headers={"User-Agent": "pixelcrm-ia"})
    r.raise_for_status()
    results = r.json()
    return len(results) > 0
