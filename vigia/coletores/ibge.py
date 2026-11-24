"""Coletor do IBGE: índice do IPCA (inflação), para comparar gastos de anos diferentes.

Fonte oficial: API SIDRA do IBGE, tabela 1737 (IPCA, série histórica), variável 2266
("IPCA - Número-índice, base dezembro de 1993 = 100"), Brasil, todos os meses:
    https://apisidra.ibge.gov.br/values/t/1737/n1/all/v/2266/p/all?formato=json
Sem chave, sem limite relevante: uma chamada por dia, ~600 linhas.

Para que serve: "R$ 700 milhões em 2019" e "R$ 1,7 bilhão em 2025" não se comparam sem descontar a
inflação. O refino (vigia/refino.py) usa a média do índice de cada ano para trazer tudo a preços do
último ano fechado. A população vem do Siconfi (a mesma que o Tesouro usa, origem IBGE).

Formato da resposta (conferido com a documentação da API SIDRA): lista de objetos; o primeiro é o
cabeçalho (nomes das colunas), os demais trazem "V" (valor) e "D3C" (mês, AAAAMM). Como o nome da
coluna do mês pode mudar de posição, o leitor acha a coluna do período pelo formato AAAAMM.
"""
from __future__ import annotations

import logging
import re

import pandas as pd

from .. import armazem, qualidade
from ..config import DADOS
from ..http import sessao

log = logging.getLogger("vigia.ibge")
URL_IPCA = "https://apisidra.ibge.gov.br/values/t/1737/n1/all/v/2266/p/all"
PASTA = DADOS / "ibge"
ANO_INICIAL = 2015
OBRIGATORIAS = {"ano": r"\d{4}", "mes": r"\d{1,2}", "indice": r"\d+\.\d+"}


def ler_sidra(linhas: list[dict]) -> pd.DataFrame:
    """Transforma a resposta do SIDRA em (ano, mes, indice, referencia)."""
    if not linhas or len(linhas) < 2:
        raise ValueError("SIDRA: resposta vazia")
    corpo = linhas[1:]
    chave_periodo = next((k for k, v in corpo[0].items() if re.fullmatch(r"\d{6}", str(v))), None)
    if not chave_periodo or "V" not in corpo[0]:
        raise ValueError(f"SIDRA: formato inesperado {list(corpo[0].keys())}")
    chave_nome = chave_periodo[:-1] + "N" if chave_periodo.endswith("C") else chave_periodo
    saida = []
    for r in corpo:
        periodo = str(r.get(chave_periodo, ""))
        try:
            indice = float(str(r.get("V", "")).replace(",", "."))
        except ValueError:
            continue   # "..." ou "-" nos meses sem dado
        if re.fullmatch(r"\d{6}", periodo) and indice > 0:
            saida.append({"ano": int(periodo[:4]), "mes": f"{int(periodo[4:]):02d}", "indice": f"{indice:.2f}",
                          "referencia": str(r.get(chave_nome, ""))})
    df = pd.DataFrame(saida)
    if df.empty:
        raise ValueError("SIDRA: nenhum mês com índice")
    return df[df["ano"] >= ANO_INICIAL].sort_values(["ano", "mes"]).reset_index(drop=True)


def coletar() -> None:
    s = sessao()
    r = s.get(URL_IPCA, params={"formato": "json"}, timeout=120)
    r.raise_for_status()
    qualidade.guardar_bruto("ibge_ipca.json", r.content, r.url)
    df = ler_sidra(r.json())
    arquivo = "ipca.csv"
    chs = qualidade.validar_tabela(df, armazem.ler(PASTA / arquivo), fonte="ibge", arquivo=arquivo,
                                   obrigatorias=OBRIGATORIAS, coluna_total="indice", brutos=["ibge_ipca.json"])
    if not qualidade.aprovado(chs):
        log.error("%s NÃO gravado: falhou na checagem; mantida a versão anterior", arquivo)
        return
    armazem.gravar(df, PASTA / arquivo, chave=["ano", "mes"], ordenar=["ano", "mes"])
    ultimo = df.iloc[-1]
    log.info("IBGE IPCA: %d meses, último %s (%s/%s)", len(df), ultimo["indice"], ultimo["mes"], ultimo["ano"])
