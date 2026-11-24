"""Radar do dia: só o que mudou e pede atenção, a partir dos dados que o robô já coletou (sem rede, sem IA).

Lê:
    data/pedidos/pedidos.csv            prazos dos pedidos pela Lei de Acesso (vence em até 3 dias, vencido sem resposta)
    data/diario_oficial/edicoes.csv     edições novas do Diário Oficial com dispensa, inexigibilidade, emergência,
                                        aditivo, adesão a ata ou crédito extra acima de R$ 1 milhão
    data/pncp/contratos.csv             contratos novos acima de R$ 500 mil
    data/pncp/termos.csv                aditivos novos que aumentam valor
Grava:
    data/radar/hoje.md                  o resumo (vira o texto da issue "Radar do dia")
    data/radar/visto.json               o que já foi avisado, para não repetir
Uso: python -m vigia.radar [AAAA-MM-DD]   -> imprime "novo" ou "nada" na última linha (o workflow usa isso)

Só números, datas, protocolos públicos e links. Nenhum nome de pessoa nem de empresa (regra do CLAUDE.md).
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import date, timedelta

from .config import DADOS

PASTA = DADOS / "radar"
VISTO = PASTA / "visto.json"
LIMITE_CONTRATO = 500_000
LIMITE_CREDITO = 1_000_000
PNCP = "https://pncp.gov.br/app/contratos/"


def _ler(caminho):
    if not caminho.exists():
        return []
    with caminho.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _num(v) -> float:
    try:
        return float(v or 0)
    except ValueError:
        return 0.0


def brl(v: float) -> str:
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def prazos(pedidos, hoje):
    prox, venc = [], []
    for p in pedidos:
        if p.get("respondido_em") or not p.get("enviado_em"):
            continue
        dias = int(p.get("prazo_dias") or 20) + (10 if p.get("prorrogado") else 0)
        prazo = date.fromisoformat(p["enviado_em"]) + timedelta(days=dias)
        falta = (prazo - hoje).days
        if 0 <= falta <= 3:
            prox.append((prazo, p))
        elif falta < 0:
            venc.append((prazo, p))
    return prox, venc


def montar(hoje: date, visto: set[str]) -> list[str]:
    linhas = []
    prox, venc = prazos(_ler(DADOS / "pedidos" / "pedidos.csv"), hoje)
    if prox:
        linhas.append(f"### Lei de Acesso: {len(prox)} pedidos vencem em até 3 dias")
        linhas += [f"- {p['pedido']} · {p['protocolo']} · vence {d:%d/%m}" for d, p in sorted(prox, key=lambda x: x[0])]
    novos_venc = [(d, p) for d, p in venc if "lai:" + p["protocolo"] not in visto]
    if novos_venc:
        linhas.append(f"### Lei de Acesso: {len(novos_venc)} pedidos venceram sem resposta (cabe reclamação)")
        for d, p in sorted(novos_venc, key=lambda x: x[0]):
            linhas.append(f"- {p['pedido']} · {p['protocolo']} · venceu {d:%d/%m} · {p['assunto'][:80]}")
            visto.add("lai:" + p["protocolo"])

    eds = []
    for e in _ler(DADOS / "diario_oficial" / "edicoes.csv"):
        k = "do:" + e["edicao"]
        if k in visto:
            continue
        visto.add(k)
        partes = [f"{e[c]} × {n}" for c, n in (("dispensa", "dispensa"), ("inexigibilidade", "inexigibilidade"),
                  ("emergencia", "emergência"), ("aditivo", "aditivo"), ("carona_em_ata", "adesão a ata"))
                  if int(e.get(c) or 0)]
        if _num(e.get("creditos_valor")) >= LIMITE_CREDITO:
            partes.append(f"créditos extras {brl(_num(e['creditos_valor']))}")
        if partes:
            eds.append(f"- Edição {e['edicao']} ({e['data']}): " + ", ".join(partes))
    if eds:
        linhas += ["### Diário Oficial", *eds, "Ler: https://diariooficial.cariacica.es.gov.br/"]

    cts = []
    for c in _ler(DADOS / "pncp" / "contratos.csv"):
        k = "ct:" + c["id_pncp"]
        if k in visto or _num(c.get("valor_global")) < LIMITE_CONTRATO:
            continue
        visto.add(k)
        if c.get("data_publicacao", "")[:10] >= (hoje - timedelta(days=7)).isoformat():
            cts.append(f"- {brl(_num(c['valor_global']))} · assinado {c.get('data_assinatura', '')[:10]} · "
                       f"{(c.get('objeto') or '')[:110].strip()} · PNCP {c['id_pncp']}")
    if cts:
        linhas += [f"### Contratos novos acima de {brl(LIMITE_CONTRATO)}", *cts]

    ads = []
    for t in _ler(DADOS / "pncp" / "termos.csv"):
        k = f"ta:{t['id_contrato']}:{t['sequencial']}"
        if k in visto:
            continue
        visto.add(k)
        if _num(t.get("valor_acrescido")) > 0 and t.get("data_assinatura", "") >= (hoje - timedelta(days=7)).isoformat():
            ads.append(f"- +{brl(_num(t['valor_acrescido']))} no contrato {t['id_contrato']} · {t.get('data_assinatura')}")
    if ads:
        linhas += ["### Aditivos que aumentam valor", *ads]
    return linhas


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    hoje = date.fromisoformat(argv[0]) if argv else date.today()
    PASTA.mkdir(parents=True, exist_ok=True)
    primeira = not VISTO.exists()
    visto = set(json.loads(VISTO.read_text(encoding="utf-8"))) if not primeira else set()
    linhas = montar(hoje, visto)
    VISTO.write_text(json.dumps(sorted(visto), ensure_ascii=False, indent=0), encoding="utf-8")
    # Na primeira vez só marca o histórico como visto (senão a primeira issue teria anos de contratos).
    so_prazos = [l for l in linhas if l.startswith("### Lei de Acesso") or l.startswith("- ") and "· vence" in l]
    corpo = so_prazos if primeira else linhas
    texto = f"# Radar do Vigia · {hoje:%d/%m/%Y}\n\n" + ("\n".join(corpo) if corpo else "Nada novo.") + "\n"
    (PASTA / "hoje.md").write_text(texto, encoding="utf-8")
    print(texto)
    print("novo" if corpo else "nada")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
