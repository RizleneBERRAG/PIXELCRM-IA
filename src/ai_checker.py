import os
import json
import re
from typing import Dict, Any

import openai
from openai import OpenAI

from .models import Dossier

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def _build_docs_summary(pdf_texts: Dict[str, str]) -> Dict[str, str]:
    """
    On limite la taille de chaque texte pour ne pas exploser les tokens.
    """
    summary: Dict[str, str] = {}
    for name, text in pdf_texts.items():
        # on garde ~1500 caractères max par document
        summary[name] = text[:1500]
    return summary


def check_pdfs_with_ai(
    dossier: Dossier, rules_for_deleg: Dict[str, Any], pdf_texts: Dict[str, str]
) -> Dict[str, Any]:
    checks = rules_for_deleg.get("pdf_checks", [])
    docs_summary = _build_docs_summary(pdf_texts)

    prompt = f"""
Tu es un contrôleur expert de dossiers CEE pour PixelCRM.

Tu dois analyser l'ensemble des PDF d'un dossier pour vérifier des règles
TRÈS PRÉCISES. Tu n'as PAS accès à Internet, tu dois donc uniquement
t'appuyer sur le contenu texte des PDF fournis.

IMPORTANT :
- Ne vérifie PAS la présence de signatures.
- Si une information n'apparaît pas clairement dans les PDF, tu signales
  que la règle est "non vérifiable" ou "non respectée" en expliquant pourquoi.
- Les documents sont identifiés principalement par leur NOM DE FICHIER.

Dossier :
- Numéro IEN : {dossier.ien}
- Client : {dossier.client_nom}
- Délégataire : {dossier.delegataire}
- Champs CRM saisis : {json.dumps(dossier.fields, ensure_ascii=False)}

Documents PDF disponibles (nom + début du texte) :
{json.dumps(docs_summary, ensure_ascii=False, indent=2)}

RÈGLES À CONTRÔLER (ne pas inventer d'autres règles) :
{json.dumps(checks, ensure_ascii=False, indent=2)}

RAPPEL :
- Tu ne contrôles PAS la présence de signatures.
- Tu n'inventes PAS d'autres règles que celles fournies.
- Si quelque chose n'est pas clairement visible dans le texte, tu écris
  que c'est "non vérifiable avec le texte extrait des PDF".

Tu dois répondre STRICTEMENT en JSON avec ce format :

{{
  "status": "conforme" | "non_conforme",
  "problems": [
    "description problème 1",
    "description problème 2",
    ...
  ]
}}

- "status" = "conforme" uniquement si toutes les règles ci-dessus sont respectées
  ou non vérifiables.
"""

    try:
        response = client.chat.completions.create(
            # modèle plus léger + limites de tokens
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "Tu es un expert contrôle CEE, très strict, mais toujours factuel et clair.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=800,
        )

    except openai.RateLimitError as e:
        # Quota OpenAI atteint → on ne casse pas l'appli
        print("[IA] Rate limit OpenAI atteint :", e)
        return {
            "status": "non_conforme",
            "problems": [
                "Analyse IA impossible : quota OpenAI atteint ou modèle temporairement indisponible. "
                "Les contrôles de base (champs CRM, présence des PDF) restent valides."
            ],
        }

    except Exception as e:
        # Toute autre erreur API → on renvoie une explication propre
        print("[IA] Erreur appel OpenAI :", e)
        return {
            "status": "non_conforme",
            "problems": [
                f"Analyse IA impossible (erreur technique OpenAI : {e}). "
                "Les contrôles de base restent valides."
            ],
        }

    content = response.choices[0].message.content or ""

    # --- extraction propre du JSON dans la réponse ---
    def extract_json(text: str) -> str:
        m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
        if m:
            return m.group(1).strip()
        text = text.strip()
        start = text.find("{")
        if start != -1:
            return text[start:]
        return text

    cleaned = extract_json(content)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        data = {
            "status": "non_conforme",
            "problems": [
                "Réponse IA non JSON exploitable.",
                cleaned,
            ],
        }

    if "status" not in data:
        data["status"] = "non_conforme"
    if "problems" not in data:
        data["problems"] = []

    return data
