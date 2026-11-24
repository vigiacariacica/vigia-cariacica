"""Tudo o que o Vigia fez, numa linha do tempo: o que publicamos (vídeos, posts e apurações), as perguntas que
mandamos, as respostas que chegaram, os prazos que venceram e o que mudou de fato.

Nada é escrito à mão na página. Tudo sai de arquivos públicos deste repositório:
- data/site/publicacoes.csv: uma linha por peça que JÁ FOI AO AR (data, tipo, título, resumo, link, fonte).
  Só entra depois de publicada. Erro achado depois vai na coluna `correcao`, que aparece em destaque.
- data/pedidos/pedidos.csv e perguntas_publicas.csv: as perguntas pela Lei de Acesso.
- data/pedidos/respostas_publicas.csv: o resumo público de uma resposta, quando já foi conferido.
- data/resultados.csv: o que mudou, com prova.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from . import dados as D

ARQ_PUB = D.SITE / "publicacoes.csv"
ARQ_RESP = D.DADOS / "pedidos" / "respostas_publicas.csv"
TIPOS = {"video": "Vídeo", "post": "Post", "carrossel": "Carrossel", "apuracao": "Apuração"}
REDES = (("instagram.com", "Ver no Instagram"), ("tiktok.com", "Ver no TikTok"), ("x.com", "Ver no X"),
         ("facebook.com", "Ver no Facebook"), ("youtube.com", "Ver no YouTube"), ("youtu.be", "Ver no YouTube"))


def _ler(arq) -> list[dict]:
    if not arq.exists():
        return []
    return pd.read_csv(arq, dtype=str, keep_default_na=False).to_dict("records")


def ver_em(link: str) -> str:
    for dominio, texto in REDES:
        if dominio in link:
            return texto
    return "Ver a publicação"


def _junto(t: str) -> str:
    """'R$' nunca fica numa linha e o número na outra (espaço que não quebra)."""
    return t.replace("R$ ", "R$ ")


def publicacoes() -> list[dict]:
    """O que já foi ao ar, do mais novo para o mais antigo."""
    out = []
    for r in _ler(ARQ_PUB):
        r = {k: _junto(v) if k in ("titulo", "resumo", "outro_lado", "correcao") else v for k, v in r.items()}
        r["data"] = date.fromisoformat(r["data"])
        r["perguntas"] = r.get("perguntas", "").split()
        r["rotulo"] = TIPOS.get(r["tipo"], "Publicação")
        r["ver"] = ver_em(r["link"])
        out.append(r)
    return sorted(out, key=lambda x: x["data"], reverse=True)


def respostas() -> dict[str, dict]:
    """Resumo público de cada resposta já conferida, por número do pedido."""
    return {r["protocolo"]: r for r in _ler(ARQ_RESP)}


def _plural(n: int, um: str, varios: str) -> str:
    return f"{n} {um if n == 1 else varios}"


def _quem(itens: list[dict]) -> str:
    nomes = sorted({it["para"] for it in itens})
    if len(nomes) > 3:
        return f"{len(nomes)} órgãos diferentes"
    return nomes[0] if len(nomes) == 1 else ", ".join(nomes[:-1]) + " e " + nomes[-1]


ESTADO_RESPOSTA = {"respondido": "Resposta completa", "parcial": "Resposta só em parte", "negado": "Pedido negado"}


def linha_do_tempo(perg: dict, pubs: list[dict], resultados: list[dict], hoje: date) -> list[dict]:
    """Eventos do mais novo para o mais antigo. Cada um: data, tipo, rótulo, título, texto e link."""
    ev: list[dict] = []
    for p in pubs:
        ev.append({"data": p["data"], "tipo": p["tipo"], "rotulo": p["rotulo"], "titulo": p["titulo"],
                   "texto": p["resumo"], "link": p["link"], "ver": p["ver"], "correcao": p.get("correcao", ""),
                   "outro": p.get("outro_lado", ""), "fonte": p.get("fonte", ""), "pagina": p.get("pagina", ""),
                   "ordem": 0})
    itens = [it for g in perg["grupos"].values() for it in g]
    por_dia: dict[str, list] = {}
    for it in itens:
        por_dia.setdefault(it["enviado"], []).append(it)
    for dia, its in por_dia.items():
        ev.append({"data": date.fromisoformat(dia), "tipo": "pergunta", "rotulo": "Perguntas",
                   "titulo": f"Mandamos {_plural(len(its), 'pergunta oficial', 'perguntas oficiais')}",
                   "texto": f"Para: {_quem(its)}. A lei dá 20 dias para responder"
                            + (" (30 na Ouvidoria)." if any(it["para"] == "Ouvidoria" for it in its) else "."),
                   "link": "/perguntas/",
                   "ver": "Ver as perguntas", "ordem": 2})
    resp = respostas()
    for it in itens:
        if not it.get("respondido_em"):
            continue
        resumos = [resp[n]["resumo"] for n in it["numeros"] if n in resp]
        ev.append({"data": date.fromisoformat(it["respondido_em"]), "tipo": "resposta",
                   "rotulo": ESTADO_RESPOSTA.get(it["estado"], "Resposta"), "titulo": it["pergunta"],
                   "texto": " ".join(resumos) or f"Quem respondeu: {it['para']}. A gente confere e cobra o que faltar.",
                   "link": "/perguntas/", "ver": "Ver todas as respostas", "ordem": 1})
    vencidas: dict[date, list] = {}
    for it in itens:
        if it["estado"] == "vencido":
            vencidas.setdefault(it["prazo"], []).append(it)
    for prazo, its in vencidas.items():
        ev.append({"data": prazo + timedelta(days=1), "tipo": "prazo", "rotulo": "Prazo vencido",
                   "titulo": f"{_plural(len(its), 'pergunta ficou', 'perguntas ficaram')} sem resposta no prazo",
                   "texto": f"Para: {_quem(its)}. Agora a gente cobra.", "link": "/perguntas/",
                   "ver": "Ver as perguntas", "ordem": 1})
    for r in resultados:
        ev.append({"data": date.fromisoformat(r["data"]), "tipo": "resultado", "rotulo": "O que mudou",
                   "titulo": r["o_que_mudou"], "texto": "", "link": r.get("fonte", ""), "ver": "Ver a prova",
                   "ordem": 0})
    ev = [e for e in ev if e["data"] <= hoje]
    return sorted(ev, key=lambda e: (e["data"], -e["ordem"]), reverse=True)


MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
         "novembro", "dezembro"]


def por_mes(eventos: list[dict]) -> list[tuple[str, list[dict]]]:
    meses: dict[str, list] = {}
    for e in eventos:
        meses.setdefault(f"{MESES[e['data'].month - 1]} de {e['data'].year}", []).append(e)
    return list(meses.items())
