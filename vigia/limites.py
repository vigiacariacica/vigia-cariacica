"""Valores e limites legais usados pelas regras.

Os valores de dispensa são atualizados todo ano por decreto federal (art. 182 da Lei 14.133/2021).
CONFIRA o decreto do ano antes de usar um alerta de fracionamento numa denúncia.
"""
from __future__ import annotations

import re

# ano: (art. 75, I - obras e serviços de engenharia/manutenção de veículos, art. 75, II - demais)
LIMITES_DISPENSA = {
    2021: (100000.00, 50000.00),     # texto original da Lei 14.133/2021
    2022: (108040.82, 54020.41),     # Decreto 10.922/2021
    2023: (114416.65, 57208.33),     # Decreto 11.317/2022
    2024: (119812.02, 59906.02),     # Decreto 11.871/2023
    2025: (125451.15, 62725.59),     # Decreto 12.343/2024
    2026: (130984.20, 65492.11),     # Decreto 12.807/2025
}


def limite_dispensa(ano: int, inciso: str) -> float | None:
    anos = sorted(LIMITES_DISPENSA)
    if ano not in LIMITES_DISPENSA:
        ano = anos[-1] if ano > anos[-1] else anos[0]
    i, ii = LIMITES_DISPENSA[ano]
    return {"I": i, "II": ii}.get(inciso)


_INCISO = re.compile(r"art(?:igo)?\.?\s*75\s*,?\s*(?:inciso\s*)?([ivxl]+)\b", re.I)


def inciso_art75(amparo: str | None) -> str | None:
    """Extrai o inciso do art. 75 (dispensa) do texto do amparo legal."""
    if not amparo:
        return None
    m = _INCISO.search(amparo)
    return m.group(1).upper() if m else None


MODALIDADES = {
    1: "Leilão eletrônico", 2: "Diálogo competitivo", 3: "Concurso", 4: "Concorrência eletrônica",
    5: "Concorrência presencial", 6: "Pregão eletrônico", 7: "Pregão presencial",
    8: "Dispensa", 9: "Inexigibilidade", 10: "Manifestação de interesse",
    11: "Pré-qualificação", 12: "Credenciamento", 13: "Leilão presencial",
}
