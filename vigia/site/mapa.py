"""Mapa dos bairros de Cariacica, desenhado em SVG na hora de gerar o site (sem biblioteca de mapa, sem
servidor de terceiros, leve no celular).

A malha é a do IBGE (Censo 2022), baixada pelo robô em data/raiox/bairros-cariacica.geojson
(ferramentas/malha_bairros.py). Cada bairro vira um caminho SVG com o código do IBGE, e as camadas
(moradores, moradores por km², casas sem esgoto na rede, renda) mudam só a cor, por classe.
"""
from __future__ import annotations

import json
import math

from . import dados as D

ARQ = D.RAIOX / "bairros-cariacica.geojson"
LARGURA = 1000

# camada: (rótulo do botão, campo, como escrever o valor, explicação da legenda)
CAMADAS = {
    "pop": ("Moradores", "populacao", lambda v: D.br(round(v)), "Quanto mais escuro, mais gente mora no bairro."),
    "den": ("Moradores por km²", "densidade", lambda v: D.br(round(v)),
            "Quanto mais escuro, mais apertado: mais gente no mesmo espaço."),
    "esg": ("Casas sem esgoto na rede", "sem_rede", lambda v: D.br(round(v)),
            "Quanto mais escuro, mais casas sem esgoto ligado na rede."),
    "ren": ("Renda", "renda_mediana", lambda v: f"R$ {D.br(round(v))}",
            "Quanto mais escuro, maior a renda. Metade das famílias ganha até esse valor."),
}
CLASSES = 5


def existe() -> bool:
    return ARQ.exists()


def _aneis(geo: dict) -> list[list[list[float]]]:
    if geo["type"] == "Polygon":
        return geo["coordinates"]
    return [anel for poli in geo["coordinates"] for anel in poli]


def _quebras(valores: list[float]) -> list[float]:
    """Limites de 5 classes com o mesmo número de bairros em cada uma (quantis)."""
    v = sorted(valores)
    return [v[min(len(v) - 1, int(len(v) * i / CLASSES))] for i in range(1, CLASSES)]


def _classe(valor: float, quebras: list[float]) -> int:
    return sum(1 for q in quebras if valor >= q)


def mapa(bs: list[dict]) -> dict:
    """Caminhos SVG de cada bairro + classes de cada camada + legenda. Bairros sem dado ficam cinza."""
    geo = json.loads(ARQ.read_text(encoding="utf-8"))
    por_cd = {str(b["cd_bairro"]): b for b in bs}
    pontos = [p for f in geo["features"] for anel in _aneis(f["geometry"]) for p in anel]
    lon0, lon1 = min(p[0] for p in pontos), max(p[0] for p in pontos)
    lat0, lat1 = min(p[1] for p in pontos), max(p[1] for p in pontos)
    kx = math.cos(math.radians((lat0 + lat1) / 2))          # 1° de longitude é mais curto que 1° de latitude aqui
    escala = LARGURA / ((lon1 - lon0) * kx)
    altura = round((lat1 - lat0) * escala)

    def xy(p):
        return round((p[0] - lon0) * kx * escala, 1), round((lat1 - p[1]) * escala, 1)

    for b in bs:
        b["densidade"] = b["populacao"] / b["area_km2"] if b.get("area_km2") else 0
    validos = [b for b in bs if b["populacao"] > 0]
    quebras = {k: _quebras([b[c] for b in validos]) for k, (_, c, _, _) in CAMADAS.items()}

    caminhos = []
    for f in geo["features"]:
        cd = f["properties"]["cd_bairro"]
        b = por_cd.get(cd)
        partes = []
        for anel in _aneis(f["geometry"]):
            pts = [xy(p) for p in anel]
            ds = [f"M{pts[0][0]:g} {pts[0][1]:g}"]
            ultimo = pts[0]
            for p in pts[1:]:
                if p != ultimo:
                    ds.append(f"l{round(p[0] - ultimo[0], 1):g} {round(p[1] - ultimo[1], 1):g}")
                    ultimo = p
            partes.append("".join(ds) + "z")
        item = {"cd": cd, "d": "".join(partes), "nome": b["nome"] if b else f["properties"]["nome"],
                "slug": b["slug"] if b else "", "tem": bool(b and b["populacao"] > 0), "q": {}, "v": {}}
        if item["tem"]:
            for k, (_, campo, fmt, _) in CAMADAS.items():
                item["q"][k] = _classe(b[campo], quebras[k])
                item["v"][k] = fmt(b[campo])
            item["casas"] = D.br(b["domicilios"])
        caminhos.append(item)

    legendas = {}
    for k, (rot, campo, fmt, explica) in CAMADAS.items():
        q = quebras[k]
        vals = sorted(b[campo] for b in validos)
        faixas = [f"até {fmt(q[0])}"] + [f"{fmt(q[i])} a {fmt(q[i + 1])}" for i in range(len(q) - 1)] + \
                 [f"{fmt(q[-1])} ou mais"]
        legendas[k] = {"rotulo": rot, "explica": explica, "faixas": faixas, "min": fmt(vals[0]), "max": fmt(vals[-1])}
    return {"largura": LARGURA, "altura": altura, "caminhos": caminhos, "legendas": legendas, "camadas": CAMADAS}


def resumo(bs: list[dict]) -> dict:
    """Os números brutos da página do mapa."""
    v = [b for b in bs if b["populacao"] > 0]
    total = sum(b["populacao"] for b in v)
    ordem = sorted(v, key=lambda b: b["populacao"], reverse=True)
    soma, metade = 0, 0
    for b in ordem:
        soma += b["populacao"]
        metade += 1
        if soma >= total / 2:
            break
    dens = sorted(v, key=lambda b: b["populacao"] / b["area_km2"] if b["area_km2"] else 0, reverse=True)
    return {"total": total, "bairros": len(v), "metade": metade, "maior": ordem[0], "menor": ordem[-1],
            "mais_denso": dens[0], "densidade_max": round(dens[0]["populacao"] / dens[0]["area_km2"]),
            "area": sum(b["area_km2"] for b in v), "casas": sum(b["domicilios"] for b in v)}
