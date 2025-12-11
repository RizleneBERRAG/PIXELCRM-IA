# src/homelior_rules.py

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, date
from typing import Dict, Any, List, Optional, Tuple

from .models import Dossier


# ---------------------------------------------------------------------------
#  Helpers génériques
# ---------------------------------------------------------------------------


def _normalize(s: str) -> str:
    """
    Normalise une chaîne pour les recherches approximatives :
    - minuscule
    - suppression des accents
    - espaces multiples compressés
    """
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = s.replace("\u00a0", " ")  # espaces insécables
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _parse_date(s: str) -> Optional[date]:
    """
    Parse une date au format jj/mm/aaaa.
    Retourne None si échec.
    """
    try:
        return datetime.strptime(s, "%d/%m/%Y").date()
    except Exception:
        return None


def _find_date_any(text: str) -> Optional[str]:
    """
    Renvoie la première date jj/mm/aaaa trouvée dans le texte normalisé.
    """
    m = re.search(r"\b(\d{2}/\d{2}/\d{4})\b", text)
    return m.group(1) if m else None


def _find_doc_by_name(
    pdf_texts: Dict[str, str],
    keywords: List[str],
) -> Optional[Tuple[str, str, str]]:
    """
    Retourne (nom_fichier, texte_brut, texte_normalisé) du premier fichier
    dont le nom contient tous les mots-clés (en minuscule).
    """
    for name, content in pdf_texts.items():
        name_norm = name.lower()
        if all(k in name_norm for k in keywords):
            return name, content, _normalize(content)
    return None


# ---------------------------------------------------------------------------
#  Analyse spécifique HOMELIOR
# ---------------------------------------------------------------------------


def analyze_homelior(dossier: Dossier, pdf_texts: Dict[str, str]) -> Dict[str, Any]:
    """
    Analyse "métier" pour le délégataire HOMELIOR, purement en Python
    (pas d'appel à l'IA).

    On applique les règles que tu as décrites :
    - cohérences devis / cadre / AH / AFT / facture / BL
    - mais avec des regex tolérants pour tenir compte de l'OCR.
    """

    problems: List[str] = []

    # On prépare les docs principaux
    devis = _find_doc_by_name(pdf_texts, ["devis"])
    cadre = _find_doc_by_name(pdf_texts, ["cadre"])
    facture = _find_doc_by_name(pdf_texts, ["facture"])
    bl = _find_doc_by_name(pdf_texts, ["bon", "livraison"])
    ah = _find_doc_by_name(pdf_texts, ["ah"]) or _find_doc_by_name(
        pdf_texts, ["attestation", "honneur"]
    )
    aft = _find_doc_by_name(pdf_texts, ["aft"]) or _find_doc_by_name(
        pdf_texts, ["fin", "travaux"]
    )

    # -----------------------------------------------------------------------
    # 1) Détermination des dates de référence (devis / facture / BL)
    # -----------------------------------------------------------------------
    date_devis: Optional[date] = None
    date_facture: Optional[date] = None
    date_bl: Optional[date] = None

    # Candidats pour chercher une date de devis
    candidats_devis_dates: List[str] = []

    # 1.a – Cadre : "Date de cette proposition"
    if cadre:
        _, cadre_txt, cadre_norm = cadre
        m = re.search(
            r"date de cette proposition\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})",
            cadre_norm,
            flags=re.IGNORECASE,
        )
        if m:
            d = _parse_date(m.group(1))
            if d:
                date_devis = d
        candidats_devis_dates.append(cadre_norm)

    # 1.b – Facture : mention "devis du ..."
    if facture:
        _, fac_txt, fac_norm = facture

        # date du devis mentionnée sur la facture
        m_dev = re.search(
            r"devis[^0-9]{0,30}(\d{2}/\d{2}/\d{4})",
            fac_norm,
            flags=re.IGNORECASE,
        )
        if m_dev:
            d2 = _parse_date(m_dev.group(1))
            if d2 and not date_devis:
                date_devis = d2
        candidats_devis_dates.append(fac_norm)

        # date de facture
        m_fact = re.search(
            r"date de facture\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})",
            fac_norm,
            flags=re.IGNORECASE,
        )
        if m_fact:
            d = _parse_date(m_fact.group(1))
            if d:
                date_facture = d
        else:
            s = _find_date_any(fac_norm)
            if s:
                d = _parse_date(s)
                if d:
                    date_facture = d

    # 1.c – Si on n'a toujours pas de date_devis, on prend la première date trouvée
    if not date_devis:
        for txt in candidats_devis_dates:
            s = _find_date_any(txt)
            if s:
                d = _parse_date(s)
                if d:
                    date_devis = d
                    break

    # 1.d – Date du BL
    if bl:
        _, bl_txt, bl_norm = bl
        s = _find_date_any(bl_norm)
        if s:
            d = _parse_date(s)
            if d:
                date_bl = d

    # -----------------------------------------------------------------------
    # 2) Règle DEVIS
    # -----------------------------------------------------------------------
    if devis:
        devis_name, devis_txt, devis_norm = devis

        # 2.a – En-tête "DEVIS 2024-xxxxx"
        if not re.search(r"devis\s+2024[- ]?\d{4,}", devis_norm):
            problems.append(
                "DEVIS : l'en-tête de type « DEVIS 2024-xxxxx » n'est pas retrouvé clairement."
            )

        # 2.b – Type d'éclairage « Éclairage ambiance ou privé »
        #      On accepte que ce soit présent dans devis OU facture OU AH (OCR ≈).
        def has_eclairage_ambiance_global() -> bool:
            targets: List[str] = [devis_norm]
            if facture:
                targets.append(facture[2])  # texte normalisé facture
            if ah:
                targets.append(ah[2])  # texte normalisé AH

            for txt in targets:
                if (
                    ("type d eclairage" in txt or "type d'eclairage" in txt)
                    and "eclairage ambiance" in txt
                    and "prive" in txt
                ):
                    return True
            return False

        if not has_eclairage_ambiance_global():
            problems.append(
                "DEVIS : le type d'éclairage « Éclairage ambiance ou privé » "
                "n'est pas retrouvé clairement dans les documents (devis / facture / AH)."
            )

        # 2.c – P.U TTC ~ 42,315 € pour mise en place de luminaires neufs
        #      (ici, on reste indicatif, mais on ne bloque pas trop fort)
        if "mise en place de luminaires neufs" in devis_norm:
            # On cherche un nombre autour de "mise en place de luminaires neufs"
            zone = devis_norm
            m_price = re.search(
                r"mise en place de luminaires neufs.*?(\d[\d\s]*[.,]\d{2})",
                zone,
            )
            if m_price:
                price_str = m_price.group(1)
                price_norm = price_str.replace(" ", "").replace(",", ".")
                try:
                    price_val = float(price_norm)
                    if not (42.0 <= price_val <= 43.0):
                        problems.append(
                            f"DEVIS : P.U TTC attendu ≈ 42,315 € pour 'mise en place de luminaires neufs', "
                            f"trouvé {price_str}."
                        )
                except ValueError:
                    problems.append(
                        "DEVIS : impossible d'interpréter le P.U TTC pour 'mise en place de luminaires neufs'."
                    )
            else:
                problems.append(
                    "DEVIS : aucun P.U TTC clair trouvé pour 'mise en place de luminaires neufs'."
                )

        # 2.d – Date de devis dans la fenêtre [01/01/2024 ; 28/02/2024]
        if date_devis:
            debut = date(2024, 1, 1)
            fin = date(2024, 2, 28)
            if not (debut <= date_devis <= fin):
                problems.append(
                    f"DEVIS : la date de devis {date_devis.strftime('%d/%m/%Y')} "
                    "n'est pas comprise entre le 01/01/2024 et le 28/02/2024."
                )
        else:
            problems.append(
                "DEVIS : impossible de déterminer clairement la date du devis "
                "(attendue entre le 01/01/2024 et le 28/02/2024)."
            )

        # 2.e – 'reste à payer 0,00 €' sur le devis
        devis_norm_sp = devis_norm.replace("\u00A0", " ")
        devis_norm_sp = devis_norm_sp.replace(",", ".")
        devis_norm_sp = re.sub(r"\s+", " ", devis_norm_sp)
        if not re.search(r"reste a payer\s*0\.0{2}", devis_norm_sp):
            # Pas bloquant à 100%, mais on signale
            problems.append(
                "DEVIS : la mention « Reste à payer 0,00 € » n'est pas retrouvée clairement."
            )
    else:
        problems.append("DEVIS : aucun document dont le nom contient 'DEVIS' n'a été trouvé.")

    # -----------------------------------------------------------------------
    # 3) Règle CADRE DE CONTRIBUTION
    # -----------------------------------------------------------------------
    if cadre:
        cadre_name, cadre_txt, cadre_norm = cadre

        # 3.a – phrase "une prime d'un montant de XXX euros"
        if "une prime d un montant de" not in cadre_norm:
            problems.append(
                "CADRE : la phrase « une prime d’un montant de ... euros » n'est pas retrouvée clairement."
            )
        else:
            # On peut essayer de comparer avec la prime CEE saisie dans le formulaire
            prime_str = (dossier.fields.get("Prime CEE") or "").strip()
            if prime_str:
                # On normalise "2 538,90" → "2538.90"
                prime_norm = prime_str.replace(" ", "").replace("\u00A0", "")
                prime_norm = prime_norm.replace(",", ".")
                try:
                    prime_val = float(prime_norm)
                    # on cherche un montant après "une prime d un montant de"
                    m_prime = re.search(
                        r"une prime d un montant de\s+(\d[\d\s]*[.,]\d{2})",
                        cadre_norm,
                    )
                    if m_prime:
                        cadre_amount = m_prime.group(1)
                        cadre_amount_norm = (
                            cadre_amount.replace(" ", "").replace("\u00A0", "").replace(",", ".")
                        )
                        try:
                            cadre_val = float(cadre_amount_norm)
                            if abs(cadre_val - prime_val) > 0.01:
                                problems.append(
                                    f"CADRE : le montant de prime ({cadre_amount}) "
                                    f"ne correspond pas à la prime CEE saisie ({prime_str})."
                                )
                        except ValueError:
                            problems.append(
                                "CADRE : impossible d'interpréter le montant de prime dans le cadre."
                            )
                    else:
                        problems.append(
                            "CADRE : la phrase avec le montant de prime n'est pas clairement exploitable."
                        )
                except ValueError:
                    # On ne bloque pas, on signale juste
                    problems.append(
                        f"CADRE : la prime CEE saisie « {prime_str} » n'est pas interprétable en montant numérique."
                    )

        # 3.b – Date de cette proposition = date devis (si on a les deux)
        m_prop = re.search(
            r"date de cette proposition\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})",
            cadre_norm,
            flags=re.IGNORECASE,
        )
        if m_prop and date_devis:
            d_prop = _parse_date(m_prop.group(1))
            if d_prop and d_prop != date_devis:
                problems.append(
                    "CADRE : la « Date de cette proposition » ne correspond pas à la date de devis."
                )
        elif not m_prop:
            # On le signale mais c'est souvent de l'OCR approximatif, donc message informatif
            problems.append(
                "CADRE : la mention « Date de cette proposition » n'a pas été retrouvée clairement."
            )
    else:
        problems.append("CADRE : aucun document dont le nom contient 'CADRE' n'a été trouvé.")

    # -----------------------------------------------------------------------
    # 4) Règle FACTURE
    # -----------------------------------------------------------------------
    if facture:
        fac_name, fac_txt, fac_norm = facture

        fac_norm_sp = fac_norm.replace("\u00A0", " ")
        fac_norm_sp = fac_norm_sp.replace(",", ".")
        fac_norm_sp = re.sub(r"\s+", " ", fac_norm_sp)

        # 4.a – Date de facture cohérente avec date_devis (au moins date_devis trouvée)
        if date_devis and date_facture:
            # ici on ne force pas d'égalité stricte, mais on sait que la facture
            # doit référencer le devis (ce qu'on a déjà utilisé plus haut)

            # Rien de spécial à signaler ici, on a déjà mis les problèmes sur le devis.

            pass

        # 4.b – "reste à payer 0,00 €"
        if not re.search(r"reste a payer\s*0\.0{2}", fac_norm_sp):
            problems.append(
                "FACTURE : la mention « Reste à payer 0,00 € » n'est pas retrouvée clairement."
            )
    else:
        problems.append("FACTURE : aucun document dont le nom contient 'FACTURE' n'a été trouvé.")

    # -----------------------------------------------------------------------
    # 5) Règle BON DE LIVRAISON
    # -----------------------------------------------------------------------
    if bl:
        bl_name, bl_txt, bl_norm = bl
        if date_facture and date_bl and date_facture != date_bl:
            problems.append(
                f"BON DE LIVRAISON : la date du BL ({date_bl.strftime('%d/%m/%Y')}) "
                f"est différente de la date de facture ({date_facture.strftime('%d/%m/%Y')})."
            )
    else:
        problems.append(
            "BON DE LIVRAISON : aucun document dont le nom contient 'BON DE LIVRAISON' n'a été trouvé."
        )

    # -----------------------------------------------------------------------
    # 6) Règle AH (Attestation sur l'honneur) – mode soft
    # -----------------------------------------------------------------------
    if ah:
        ah_name, ah_txt, ah_norm = ah
        if (
            "attestation sur l honneur" not in ah_norm
            and "attestation sur l'honneur" not in ah_norm
        ):
            problems.append(
                "AH : document présent mais la mention « attestation sur l'honneur » "
                "n'est pas clairement lisible (OCR) – à vérifier manuellement."
            )
    else:
        problems.append(
            "AH : aucune attestation sur l'honneur (AH) détectée dans les PDF (à vérifier manuellement)."
        )

    # -----------------------------------------------------------------------
    # 7) Règle AFT (Attestation de fin de travaux)
    # -----------------------------------------------------------------------
    if aft:
        aft_name, aft_txt, aft_norm = aft

        # On cherche "Le : 28/10/2025" ou "Le 28/10/2025"
        m_aft = re.search(r"\ble\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})", aft_norm)
        if m_aft:
            d_aft = _parse_date(m_aft.group(1))
            if d_aft and date_facture and d_aft != date_facture:
                problems.append(
                    f"AFT : la date « Le {m_aft.group(1)} » est différente "
                    f"de la date de facture ({date_facture.strftime('%d/%m/%Y')})."
                )
            if d_aft and date_bl and d_aft != date_bl:
                problems.append(
                    f"AFT : la date « Le {m_aft.group(1)} » est différente "
                    f"de la date du bon de livraison ({date_bl.strftime('%d/%m/%Y')})."
                )
        else:
            problems.append(
                "AFT : aucune date de type « Le : jj/mm/aaaa » n'a été trouvée clairement "
                "en bas de l'attestation de fin de travaux."
            )
    else:
        problems.append(
            "AFT : aucune attestation de fin de travaux (AFT) détectée dans les PDF (à vérifier manuellement)."
        )

    # -----------------------------------------------------------------------
    # 8) Statut global
    # -----------------------------------------------------------------------
    status = "conforme" if not problems else "non_conforme"

    return {
        "status": status,
        "problems": problems,
    }
