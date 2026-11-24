"""Dívida da prefeitura: empréstimos pedidos e contratados, dívida consolidada, caixa por fonte.

Fontes (todas do Tesouro Nacional, sem chave; confirmadas pela sonda de 10/11/2026):
    SADIPEM   https://apidatalake.tesouro.gov.br/ords/sadipem/tt/pvl?uf=ES
              cada pedido de empréstimo (PVL): credor, valor, finalidade, situação, se foi contratado
              -> data/divida/pedidos_emprestimo.csv (só Cariacica)
    Siconfi   RGF Anexo 2 (dívida consolidada e precatórios), Anexo 4 (operações de crédito e limites),
              Anexo 5 (caixa por fonte e restos a pagar; só no 3º quadrimestre), das cidades da Grande Vitória
              -> data/siconfi/rgf_divida.csv, rgf_operacoes_credito.csv, rgf_caixa.csv

Por que existe: os pagamentos de juros (elemento 329021) e de principal (469071) foram de R$ 8,7 mi em 2019
para R$ 72,1 mi em 2025, e desde 2019 a prefeitura contratou cinco empréstimos na Caixa (R$ 285,4 mi). A
finalidade registrada é só "Infraestrutura" ou "Novo PAC": a pergunta é que obras cada um pagou.

Cuidados descobertos:
- o filtro `cod_ibge` da API do SADIPEM é ignorado (devolve outras cidades). Filtra-se por `uf` e o Vigia
  refiltra pelo código do IBGE; a coleta falha alto se o filtro de UF também for ignorado.
- o Anexo 5 do RGF só existe no último quadrimestre (LRF, art. 55, III).
- dívida consolidada sobre a receita corrente líquida é a conta do RGF; a CAPAG do Tesouro usa outro
  conceito e outro período (conferir antes de comparar os dois números).
"""
from __future__ import annotations

import logging
import time
from datetime import date

import pandas as pd

from .. import armazem, qualidade
from ..config import ANO_INICIAL_SICONFI, CARIACICA_IBGE, DADOS, GRANDE_VITORIA
from ..http import sessao
from . import siconfi

log = logging.getLogger("vigia.divida")
FONTE = "divida"
PASTA = DADOS / "divida"
SADIPEM = "https://apidatalake.tesouro.gov.br/ords/sadipem/tt/pvl"
# anexo -> (arquivo, quadrimestres)
ANEXOS = {
    "RGF-Anexo 02": ("rgf_divida", (1, 2, 3)),
    "RGF-Anexo 04": ("rgf_operacoes_credito", (1, 2, 3)),
    "RGF-Anexo 05": ("rgf_caixa", (3,)),
}
COLUNAS_PVL = ["id_pleito", "num_pvl", "num_processo", "interessado", "cod_ibge", "uf", "tipo_interessado",
               "status", "data_status", "data_protocolo", "tipo_operacao", "finalidade", "tipo_credor", "credor",
               "moeda", "valor", "pvl_assoc_divida", "pvl_contradado_credor"]


def paginar(s, url: str, params: dict) -> list[dict]:
    itens, offset = [], 0
    while True:
        p = dict(params, **({"offset": offset} if offset else {}))
        r = s.get(url, params=p, timeout=180)
        r.raise_for_status()
        j = r.json()
        lote = j.get("items", [])
        itens.extend(lote)
        if not j.get("hasMore") or not lote:
            return itens
        offset += len(lote)
        time.sleep(0.3)


def filtrar_pvl(itens: list[dict], ibge: int = CARIACICA_IBGE) -> pd.DataFrame:
    """Pedidos do SADIPEM -> só os do município, colunas fixas, valor com ponto decimal."""
    ufs = {str(i.get("uf")) for i in itens}
    if itens and ufs != {"ES"}:
        raise ValueError(f"SADIPEM ignorou o filtro de UF (vieram {sorted(ufs)[:5]})")
    linhas = [i for i in itens if str(i.get("cod_ibge")) == str(ibge)]
    df = pd.DataFrame(linhas, columns=COLUNAS_PVL).fillna("")
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce").map(lambda v: "" if pd.isna(v) else f"{v:.2f}")
    df["data_protocolo"] = df["data_protocolo"].astype(str).str[:10]
    return df.sort_values(["data_protocolo", "num_pvl"]).reset_index(drop=True)


def coletar_pvl(s) -> pd.DataFrame:
    itens = paginar(s, SADIPEM, {"uf": "ES"})
    df = filtrar_pvl(itens)
    caminho = PASTA / "pedidos_emprestimo.csv"
    chs = qualidade.validar_tabela(df, armazem.ler(caminho), fonte=FONTE, arquivo=caminho.name,
                                   obrigatorias={"id_pleito": r"\d+", "status": r".+"}, coluna_total="valor")
    if qualidade.aprovado(chs):
        armazem.gravar(df, caminho, chave=["id_pleito"], ordenar=["data_protocolo", "num_pvl"])
        log.info("SADIPEM: %d pedidos de Cariacica (%d no ES)", len(df), len(itens))
    return df


def coletar_rgf(s, ano_atual: int, refazer_recentes: bool = True) -> None:
    """Anos fechados já baixados são pulados; os dois mais recentes são refeitos só quando refazer_recentes
    (segunda-feira), porque as prefeituras retificam o RGF mas não toda semana."""
    for anexo, (nome, periodos) in ANEXOS.items():
        existente = armazem.ler(siconfi.PASTA / f"{nome}.csv")
        novos = []
        for ano in range(ANO_INICIAL_SICONFI, ano_atual + 1):
            for periodo in periodos:
                if ano == ano_atual and periodo * 4 + 1 > date.today().month:
                    continue   # quadrimestre ainda não fechado (o RGF sai 30 dias depois)
                for ente in GRANDE_VITORIA:
                    recente = ano >= ano_atual - 1 and refazer_recentes
                    if not recente and siconfi._ja_tem(existente, ente, ano, periodo):
                        continue
                    novos.extend(siconfi.paginar(s, "rgf", {
                        "an_exercicio": ano, "in_periodicidade": "Q", "nr_periodo": periodo,
                        "co_tipo_demonstrativo": "RGF", "no_anexo": anexo,
                        "co_esfera": "M", "co_poder": "E", "id_ente": ente,
                    }))
                    time.sleep(0.2)
        siconfi._salvar(nome, novos, ["exercicio", "periodo", "cod_ibge", "coluna", "cod_conta", "conta"])


def coletar(hoje: date | None = None, s=None) -> None:
    hoje = hoje or date.today()
    s = s or sessao()
    erros = []
    try:
        coletar_pvl(s)
    except Exception as e:  # noqa: BLE001
        erros.append(f"SADIPEM: {type(e).__name__}: {str(e)[:120]}")
    try:
        coletar_rgf(s, hoje.year, refazer_recentes=hoje.weekday() == 0)
    except Exception as e:  # noqa: BLE001
        erros.append(f"RGF: {type(e).__name__}: {str(e)[:120]}")
    if erros:
        raise RuntimeError("; ".join(erros))


# ---------------------------------------------------------------- leitura para o relatório

def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def divida_por_ano(ibge: int = CARIACICA_IBGE) -> pd.DataFrame:
    """Dívida consolidada, dívida líquida, RCL e precatórios no 3º quadrimestre de cada ano (RGF Anexo 2)."""
    df = armazem.ler(siconfi.PASTA / "rgf_divida.csv")
    if df.empty:
        return df
    df = df[(df["cod_ibge"].astype(str) == str(ibge)) & (df["periodo"].astype(str) == "3")
            & df["coluna"].str.contains("3º Quadrimestre", na=False)]
    alvo = {"DÍVIDA CONSOLIDADA - DC (I)": "divida_consolidada",
            "DÍVIDA CONSOLIDADA LÍQUIDA (DCL) (III) = (I - II)": "divida_liquida",
            "RECEITA CORRENTE LÍQUIDA - RCL (IV)": "rcl"}
    linhas = {}
    for _, r in df.iterrows():
        conta = str(r["conta"]).strip()
        chave = alvo.get(conta) or ("precatorios_fora_da_dc" if conta.startswith("Precatórios Posteriores") else None)
        if chave:
            linhas.setdefault(int(r["exercicio"]), {})[chave] = float(r["valor"] or 0)
    out = pd.DataFrame.from_dict(linhas, orient="index").sort_index()
    if "divida_consolidada" in out and "rcl" in out:
        out["dc_sobre_rcl"] = out["divida_consolidada"] / out["rcl"]
    return out


def servico_da_divida() -> pd.DataFrame:
    """Juros (329021) e principal (469071) pagos por ano, do portal (data/refinado/elemento_ano.csv)."""
    el = armazem.ler(DADOS / "refinado" / "elemento_ano.csv")
    if el.empty:
        return el
    el = el[el["elemento"].isin(["329021", "469071"])].copy()
    el["pago"] = _num(el["pago"])
    piv = el.pivot_table(index="ano", columns="elemento", values="pago", aggfunc="sum").fillna(0)
    piv = piv.rename(columns={"329021": "juros", "469071": "principal"})
    piv["total"] = piv.sum(axis=1)
    return piv


def _mi(v) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "-"
    if pd.isna(f):
        return "-"
    return f"{f / 1e6:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")


def secao_markdown() -> str:
    pvl = armazem.ler(PASTA / "pedidos_emprestimo.csv")
    div = divida_por_ano()
    serv = servico_da_divida()
    if pvl.empty and div.empty:
        return ""
    partes = ["## Dívida: empréstimos e quanto custam\n",
              "Fontes: SADIPEM (Tesouro Nacional, pedidos de empréstimo), RGF Anexo 2 (Siconfi) e pagamentos do "
              "portal (elementos 329021 juros e 469071 principal).\n"]
    if not pvl.empty:
        p = pvl[(pvl["pvl_contradado_credor"].astype(str) == "1") & (pvl["data_protocolo"] >= "2017")]
        if not p.empty:
            linhas = ["| Pedido | Protocolo | Credor | Valor (R$ mi) | Finalidade registrada | Situação |",
                      "|---|---|---|---:|---|---|"]
            for _, r in p.iterrows():
                linhas.append(f"| {r['num_pvl']} | {r['data_protocolo']} | {r['credor']} | {_mi(r['valor'])} | "
                              f"{r['finalidade']} | {r['status']} |")
            total = _num(p["valor"]).sum()
            partes.append(f"### Empréstimos contratados desde 2017: R$ {_mi(total)} mi\n\n" + "\n".join(linhas) + "\n")
    if not serv.empty:
        linhas = ["| Ano | Juros | Principal | Total (R$ mi) |", "|---|---:|---:|---:|"]
        for ano, r in serv.iterrows():
            linhas.append(f"| {ano} | {_mi(r.get('juros', 0))} | {_mi(r.get('principal', 0))} | {_mi(r['total'])} |")
        partes.append("### Juros e amortização pagos (portal da prefeitura)\n\n" + "\n".join(linhas) + "\n")
    if not div.empty:
        linhas = ["| Ano | Dívida consolidada (R$ mi) | % da RCL | Dívida líquida (R$ mi) | Precatórios fora da dívida (R$ mi) |",
                  "|---|---:|---:|---:|---:|"]
        for ano, r in div.iterrows():
            pct = f"{r['dc_sobre_rcl']:.1%}".replace(".", ",") if "dc_sobre_rcl" in r and pd.notna(r.get("dc_sobre_rcl")) else "-"
            linhas.append(f"| {ano} | {_mi(r.get('divida_consolidada'))} | {pct} | {_mi(r.get('divida_liquida'))} | "
                          f"{_mi(r.get('precatorios_fora_da_dc'))} |")
        partes.append("### Dívida no fim de cada ano (RGF, 3º quadrimestre)\n\nDívida líquida negativa quer dizer "
                      "que o caixa é maior que a dívida. O limite legal é 120% da RCL (Resolução do Senado 40/2001).\n\n"
                      + "\n".join(linhas) + "\n")
    return "\n".join(partes)
