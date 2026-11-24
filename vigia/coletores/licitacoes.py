"""Licitações e dispensas publicadas no Portal da Transparência de Cariacica, item a item.

Fonte: https://wstransparencia.cariacica.es.gov.br/api/licitacoes/csv?exercicio=AAAA (testada pela sonda em 08 e
10/11/2026). Uma linha por item: número, processo, modalidade (pregão, concorrência, dispensa...), situação
(homologação, deserta, fracassada, revogada...), datas, secretaria, objeto, item, quantidade, valor de referência
e valor homologado. Saída: data/transparencia/licitacoes_AAAA.csv.

Para que serve: o PNCP só tem as compras de 2023 em diante; o portal tem tudo desde 2019, inclusive as
licitações que não deram em nada (desertas e fracassadas) e o desconto entre o valor de referência e o
homologado. É a base para medir concorrência e para a regra de preço (R01).

Formato (conferido na amostra): CSV com vírgula, windows-1252, valores com ponto decimal. O texto do objeto
vem sem vírgulas, mas por segurança o leitor fixa 14 campos à esquerda e 5 à direita; o que sobrar no meio
é objeto + item (se houver vírgula a mais, tudo vai para o objeto e o item fica vazio).
"""
from __future__ import annotations

import csv
import logging
import re
from datetime import date

import pandas as pd

from .. import armazem
from . import transparencia
from .portal_extra import _por_ano, avisar, resposta_sem_dados
from .transparencia import _baixar_texto, _gravar_se_valido, anos_para_baixar

log = logging.getLogger("vigia.licitacoes")
COLUNAS = ["Numero", "Processo", "Modalidade", "Situacao", "DataPublicacao", "DataAberturaProposta",
           "DataHomologacao", "DataInicioSessao", "DataLimiteProposta", "DataInicioEntrega", "DataAdjudicacao",
           "Comissao", "Secretaria", "Coronavirus", "Objeto", "Item", "Unidade", "Quantidade", "ValorReferencia",
           "ValorTotal", "ValorTotalHomologado"]
ESQ, DIR = 14, 5
NUM = r"(-?\d+(\.\d+)?)?"
OBRIGATORIAS = {"Modalidade": r".+", "ValorTotal": NUM, "ValorTotalHomologado": NUM}


def _numero(t: str) -> str:
    t = (t or "").strip()
    if not t:
        return ""
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".")
    elif "," in t:
        t = t.replace(",", ".")
    try:
        return f"{float(t):.2f}"
    except ValueError:
        return ""


INICIO = re.compile(r"^[^,]{0,20}/\d{4},")   # um registro começa com o número "N/AAAA,"


def registros(texto: str) -> list[str]:
    """O CSV tem quebras de linha dentro do objeto, sem aspas (a coleta de 11/11/2026 falhou por isso em 2020-2025):
    uma linha que não começa com "N/AAAA," é continuação do registro anterior."""
    linhas = texto.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", " ").split("\n")
    saida: list[str] = []
    for i, linha in enumerate(linhas):
        if i == 0 or INICIO.match(linha) or not saida:
            saida.append(linha)
        else:
            saida[-1] += " " + linha
    return [s for s in saida if s.strip()]


def ler(texto: str) -> pd.DataFrame:
    regs = registros(texto)
    cab = [c.strip() for c in next(csv.reader([regs[0]]))] if regs else []
    if cab[:4] != COLUNAS[:4]:
        raise ValueError(f"licitações: cabeçalho inesperado {cab[:6]}")
    linhas, curtas = [], 0
    for reg in regs[1:]:
        campos = next(csv.reader([reg]))
        if len(campos) < len(COLUNAS):
            curtas += 1
            continue
        meio = campos[ESQ:len(campos) - DIR]
        objeto, item = (meio[0], meio[1]) if len(meio) == 2 else (" ".join(meio), "")
        linha = campos[:ESQ] + [objeto, item] + campos[-DIR:]
        linhas.append([" ".join(c.split()) for c in linha])
    if curtas:
        log.warning("licitações: %d registros com campos a menos foram ignorados", curtas)
    df = pd.DataFrame(linhas, columns=COLUNAS)
    for c in ("Quantidade", "ValorReferencia", "ValorTotal", "ValorTotalHomologado"):
        df[c] = df[c].map(_numero)
    return df


def coletar(hoje: date | None = None, s=None) -> None:
    from .portal_extra import _sessao
    hoje = hoje or date.today()
    s = s or _sessao()

    def um_ano(ano: int) -> None:
        bruto = f"licitacoes_{ano}.csv"
        texto = _baixar_texto(s, "licitacoes/csv", {"exercicio": ano}, bruto)
        if resposta_sem_dados(texto):
            avisar(bruto, "sem_dados", "a prefeitura respondeu 'sem dados'; nada gravado")
            return
        df = ler(texto)
        _gravar_se_valido(df, bruto, obrigatorias=OBRIGATORIAS, coluna_total="ValorTotal", ano=ano, hoje=hoje,
                          ordenar=["Numero", "Processo"], brutos=[bruto])
        log.info("licitações %s: %d itens", ano, len(df))

    _por_ano(anos_para_baixar("licitacoes", hoje), um_ano, "licitacoes")


# ---------------------------------------------------------------- relatório

def resumo() -> pd.DataFrame:
    """Por ano e por processo (número + processo + modalidade): quantos, quantos deram em nada (deserta,
    fracassada), quantas adesões a ata ("carona") e o desconto do homologado sobre o estimado.

    Na amostra de 2026, ValorTotal é do item (quantidade x referência) e ValorTotalHomologado se repete em
    todos os itens: é o total homologado do processo. Por isso o estimado do processo é a soma de ValorTotal
    e o homologado é o primeiro valor do processo. Desconto só em licitações homologadas (sem dispensa,
    inexigibilidade nem adesão), com os dois valores positivos."""
    linhas = []
    for arq in sorted(transparencia.PASTA.glob("licitacoes_*.csv")):
        df = armazem.ler(arq)
        if df.empty:
            continue
        ano = int(arq.stem.split("_")[1])
        df["chave"] = df["Numero"] + "|" + df["Processo"] + "|" + df["Modalidade"]
        df["_est"] = pd.to_numeric(df["ValorTotal"], errors="coerce").fillna(0)
        proc = df.groupby("chave").agg(Modalidade=("Modalidade", "first"), Situacao=("Situacao", "first"),
                                       estimado=("_est", "sum"), homologado=("ValorTotalHomologado", "first"))
        proc["homologado"] = pd.to_numeric(proc["homologado"], errors="coerce")
        sit, mod = proc["Situacao"].str.upper(), proc["Modalidade"].str.upper()
        dispensa = mod.str.contains("DISPENSA|INEXIG", regex=True)
        adesao = mod.str.contains("ADES")
        alvo = ~dispensa & ~adesao & sit.str.contains("HOMOLOG") & proc["estimado"].gt(0) & proc["homologado"].gt(0)
        desconto = 1 - proc.loc[alvo, "homologado"].sum() / proc.loc[alvo, "estimado"].sum() if alvo.any() else float("nan")
        linhas.append({"ano": ano, "processos": len(proc), "dispensas_inexigibilidades": int(dispensa.sum()),
                       "adesoes_a_ata": int(adesao.sum()),
                       "desertas": int(sit.str.contains("DESERT").sum()),
                       "fracassadas": int(sit.str.contains("FRACASS").sum()),
                       "revogadas_anuladas": int(sit.str.contains("REVOG|ANULA", regex=True).sum()),
                       "desconto_homologado": desconto})
    return pd.DataFrame(linhas)


def secao_markdown() -> str:
    r = resumo()
    if r.empty:
        return ""
    linhas = ["| Ano | Processos | Dispensas e inexigibilidades | Adesões a ata | Desertas | Fracassadas | "
              "Revogadas ou anuladas |", "|---|---:|---:|---:|---:|---:|---:|"]
    for x in r.to_dict("records"):
        linhas.append(f"| {int(x['ano'])} | {int(x['processos'])} | {int(x['dispensas_inexigibilidades'])} | "
                      f"{int(x['adesoes_a_ata'])} | {int(x['desertas'])} | {int(x['fracassadas'])} | {int(x['revogadas_anuladas'])} |")
    return ("## Licitações da prefeitura (portal, desde 2019)\n\nFonte: Portal da Transparência de Cariacica, "
            "`licitacoes/csv` (dispensas e inexigibilidades contam só as que aparecem nesse arquivo). Deserta e "
            "fracassada mostram onde ninguém quis ou ninguém serviu. O desconto do homologado sobre o estimado "
            "(coluna desconto_homologado de `resumo()`) ainda não confere com os processos e fica fora da tabela "
            "até ser validado.\n\n" + "\n".join(linhas) + "\n")
