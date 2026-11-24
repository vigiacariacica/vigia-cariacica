"""Perguntas feitas pela Lei de Acesso: o robô conta os dias de cada pedido e avisa quando vence.

A lista fica em data/pedidos/pedidos.csv, uma linha por protocolo. Quando chegar a resposta, preencha
`respondido_em` (AAAA-MM-DD) e `resultado` (respondido, parcial, negado); se o órgão prorrogar, ponha
`prorrogado` = sim. O resto é conta: prazo de 20 dias corridos na Lei de Acesso (mais 10 se prorrogar,
Lei 12.527/2011, art. 11) e de 30 dias na Ouvidoria (mais 30, Lei 13.460/2017, art. 16).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pandas as pd

from . import armazem
from .config import DADOS

ARQUIVO = DADOS / "pedidos" / "pedidos.csv"
BRASILIA = timezone(timedelta(hours=-3))
AVISO_DIAS = 7


def hoje_brasilia() -> date:
    return datetime.now(BRASILIA).date()


def _data(txt: str) -> date | None:
    try:
        return date.fromisoformat(str(txt).strip())
    except ValueError:
        return None


def situacao(pedidos: pd.DataFrame, hoje: date) -> pd.DataFrame:
    """Acrescenta prazo, dia corrido e situação (respondido, vencido ou no prazo) a cada pedido."""
    linhas = []
    for p in pedidos.to_dict("records"):
        enviado = _data(p.get("enviado_em", ""))
        if enviado is None:
            continue
        try:
            dias = int(p.get("prazo_dias"))
        except (TypeError, ValueError):
            dias = 20
        extra = dias if dias >= 30 else 10
        prorrogado = str(p.get("prorrogado", "")).strip().lower() in ("sim", "s", "true", "1")
        prazo = enviado + timedelta(days=dias + (extra if prorrogado else 0))
        while prazo.weekday() >= 5:   # prazo que cai no fim de semana passa para a segunda-feira
            prazo += timedelta(days=1)
        respondido = _data(p.get("respondido_em", ""))
        if respondido:
            estado = "respondido"
        elif hoje > prazo:
            estado = "vencido"
        else:
            estado = "no prazo"
        linhas.append({**p, "prazo": prazo, "dia": (hoje - enviado).days, "estado": estado})
    return pd.DataFrame(linhas)


def _rotulo(p: dict) -> str:
    """Pedido pela Lei de Acesso não tem código VC (desde 09/11, o VC é só da peça publicada): é o Pedido N."""
    nome = str(p.get("pedido", "")).strip()
    return f"Pedido {nome}" if nome[:1].isdigit() else nome


def secao_markdown(hoje: date | None = None) -> str:
    pedidos = armazem.ler(ARQUIVO)
    if pedidos.empty:
        return ""
    hoje = hoje or hoje_brasilia()
    s = situacao(pedidos, hoje)
    if s.empty:
        return ""
    total = len(s)
    resp = int((s["estado"] == "respondido").sum())
    vencidos = s[s["estado"] == "vencido"].sort_values("prazo", kind="stable")
    abertos = s[s["estado"] == "no prazo"]
    proximos = abertos[abertos["prazo"] <= hoje + timedelta(days=AVISO_DIAS)].sort_values("prazo", kind="stable")
    partes = [
        "## Perguntas feitas pela Lei de Acesso\n",
        "Cada pedido protocolado pelo Vigia e o prazo da resposta: 20 dias na Lei de Acesso, prorrogáveis por "
        "mais 10, e 30 dias na Ouvidoria. A lista completa, com protocolo e órgão, está em "
        "`data/pedidos/pedidos.csv`.\n",
        f"**Respondidas: {resp} de {total} ({resp / total:.0%}).** No prazo: {len(abertos)}. "
        f"Vencidas sem resposta: {len(vencidos)}.\n",
    ]

    def tabela(df: pd.DataFrame, atraso: bool) -> str:
        cab = "| Prazo | Pedido | Protocolo | Assunto |" + (" Dias de atraso |" if atraso else "")
        linhas = [cab, "|---|---|---|---|" + ("---|" if atraso else "")]
        for p in df.to_dict("records"):
            linha = f"| {p['prazo']:%d/%m/%Y} | {_rotulo(p)} | {p['protocolo']} | {p['assunto']} |"
            if atraso:
                linha += f" {(hoje - p['prazo']).days} |"
            linhas.append(linha)
        return "\n".join(linhas) + "\n"

    if not vencidos.empty:
        partes += ["### Vencidas sem resposta (cabe reclamação ou recurso)\n", tabela(vencidos, True)]
    if not proximos.empty:
        partes += [f"### Vencem nos próximos {AVISO_DIAS} dias\n", tabela(proximos, False)]
    return "\n".join(partes)


# ---------------------------------------------------------------- placar de resultados

RESULTADOS = DADOS / "resultados.csv"
TIPOS_RESULTADO = ("dado publicado", "resposta completa", "licitação aberta", "emergência evitada",
                   "procedimento aberto", "lei ou emenda aprovada", "serviço melhorou", "correção da prefeitura")


def secao_resultados() -> str:
    """O que mudou de verdade em Cariacica por causa de uma pergunta do Vigia (placar de resultados, docs/DECISOES.md).
    data/resultados.csv: data, campanha, tipo, o_que_mudou, fonte (link oficial), pedido (protocolo ou vazio)."""
    r = armazem.ler(RESULTADOS)
    linhas = ["## Placar de resultados\n",
              "_O que mudou de verdade em Cariacica depois de uma pergunta do Vigia. Conta só o que tem fonte oficial: "
              "dado publicado, resposta completa, licitação aberta, emergência evitada, procedimento aberto em órgão "
              "de controle, lei ou emenda aprovada, serviço que melhorou. Meta: 3 até 12/02/2027._\n"]
    if r.empty:
        linhas.append("**Nenhum resultado ainda.** As primeiras respostas vencem entre 27/11 e 10/12/2026.\n")
        return "\n".join(linhas)
    r = r.sort_values("data", ascending=False)
    linhas += [f"**{len(r)} resultado(s).**\n", "| Data | Campanha | O que mudou | Fonte |", "|---|---|---|---|"]
    linhas += [f"| {x['data']} | {x['campanha']} | {x['o_que_mudou']} | [fonte]({x['fonte']}) |"
               for _, x in r.iterrows()]
    return "\n".join(linhas) + "\n"
