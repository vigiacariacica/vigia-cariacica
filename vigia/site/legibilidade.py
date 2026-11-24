"""Régua de linguagem simples, aplicada a toda página do site antes de publicar.

- Índice de Flesch adaptado ao português (Martins et al., 1996): 248,835 − 1,015 × (palavras/frase)
  − 84,6 × (sílabas/palavra). 75 a 100: muito fácil (primeiros anos do fundamental); 50 a 75: fácil (anos
  finais do fundamental); 25 a 50: difícil; 0 a 25: muito difícil.
- Frase longa: mais de 20 palavras.
- Palavras de dentro do projeto que não podem aparecer no texto corrido (só na linha da fonte).
- Palavras de julgamento que o Vigia nunca usa.

A contagem de sílabas é aproximada (grupos de vogais), o que basta para comparar textos e travar regressões.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser

VOGAIS = "aeiouáéíóúâêôãõàü"
JARGAO = ["LAI", "e-SIC", "e-Ouv", "liquidad", "empenh", "PNCP", "Siconfi", "protocolo", "VC·", "R31", "R32",
          "fiscaliza", "controle social", "transparência ativa", "licitaç", "dispensa", "inexigibilidade",
          "aditivo", "mediana", "indicador", "per capita", "domicílio", "munícipe"]
JULGAMENTO = ["escândalo", "roubo", "roubou", "desvio", "desviou", "esquema", "corrupto", "corrupção", "vergonha",
              "absurdo", "máfia", "ladrão", "bandido"]
FRASE_LONGA = 20


def silabas(palavra: str) -> int:
    p = palavra.lower()
    grupos = re.findall(f"[{VOGAIS}]+", p)
    n = 0
    for g in grupos:
        # ditongos e tritongos contam uma sílaba; hiato com acento ("saída", "país") conta duas
        n += 1 + sum(1 for ch in g[1:] if ch in "áéíóú")
    return max(1, n)


def frases(texto: str) -> list[str]:
    partes = re.split(r"(?<=[.!?:])\s+|\n+", texto)
    return [p.strip() for p in partes if re.search(r"[A-Za-zÀ-ú]", p or "")]


def palavras(frase: str) -> list[str]:
    return re.findall(r"[A-Za-zÀ-ú0-9][A-Za-zÀ-ú0-9\-\.,]*", frase)


def flesch(texto: str) -> float:
    fs = frases(texto)
    ps = [w for f in fs for w in palavras(f)]
    if not fs or not ps:
        return 100.0
    sil = sum(silabas(re.sub(r"[^A-Za-zÀ-ú]", "", w) or "a") for w in ps)
    return 248.835 - 1.015 * (len(ps) / len(fs)) - 84.6 * (sil / len(ps))


def frases_longas(texto: str, limite: int = FRASE_LONGA) -> list[str]:
    return [f for f in frases(texto) if len(palavras(f)) > limite]


def achar(texto: str, termos: list[str]) -> list[str]:
    baixo = texto.lower()
    out = []
    for t in termos:
        padrao = re.escape(t.lower())
        if t.isupper() or t.endswith("·"):        # siglas: palavra inteira, com maiúsculas
            if re.search(rf"(?<![A-Za-z]){re.escape(t)}(?![A-Za-z])", texto):
                out.append(t)
        elif re.search(rf"(?<![a-zà-ú]){padrao}", baixo):
            out.append(t)
    return out


class _Texto(HTMLParser):
    """Texto corrido de uma página: ignora script, style, a linha da fonte, os números de pedido e o que
    estiver marcado com data-fora-da-regua."""
    PULAR = {"script", "style", "svg", "head", "title"}
    VAZIOS = {"br", "img", "input", "meta", "link", "hr", "source", "wbr"}

    def __init__(self):
        super().__init__()
        self.pilha: list[bool] = []
        self.partes: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self.VAZIOS:
            if tag == "br":
                self.partes.append("\n")
            return
        a = dict(attrs)
        classes = (a.get("class") or "").split()
        pular = (tag in self.PULAR or "fonte" in classes or "meta" in classes or "data-fora-da-regua" in a
                 or bool(self.pilha and self.pilha[-1]))
        self.pilha.append(bool(pular))
        if tag in ("p", "li", "h1", "h2", "h3", "dt", "dd", "summary", "div", "section", "td", "th", "a", "button",
                   "label", "span"):
            self.partes.append("\n" if tag not in ("a", "span", "button") else " ")

    def handle_endtag(self, tag):
        if tag in self.VAZIOS:
            return
        if self.pilha:
            self.pilha.pop()
        if tag in ("p", "li", "h1", "h2", "h3", "dt", "dd", "summary", "td", "th", "label", "b"):
            self.partes.append("\n")

    def handle_data(self, data):
        if not (self.pilha and self.pilha[-1]):
            self.partes.append(data)


def texto_da_pagina(html: str) -> str:
    p = _Texto()
    p.feed(html)
    t = "".join(p.partes)
    t = re.sub(r"[ \t]+", " ", t)
    return "\n".join(l.strip() for l in t.splitlines() if l.strip())


def avaliar(html: str) -> dict:
    t = texto_da_pagina(html)
    return {"flesch": round(flesch(t), 1), "frases_longas": frases_longas(t), "jargao": achar(t, JARGAO),
            "julgamento": achar(t, JULGAMENTO), "palavras": len(palavras(t))}
