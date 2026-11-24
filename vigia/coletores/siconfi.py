"""Coletor do Siconfi (Tesouro Nacional): orçamento e execução das prefeituras.

Fonte oficial: https://apidatalake.tesouro.gov.br/docs/siconfi/
Os dados são declarados pela própria prefeitura ao Tesouro e são os mesmos
usados pelo Tribunal de Contas e pela nota Capag.

O que coletamos:
- DCA (contas anuais): despesa por função (saúde, educação...), por
  natureza (pessoal, obras...) e receitas. Um arquivo por ano fechado.
- RREO (bimestral): execução do orçamento do ano corrente.
- RGF (quadrimestral): gasto com pessoal versus limite da LRF.
"""
import logging
import time
from datetime import date

import pandas as pd

from .. import armazem
from ..config import ANO_INICIAL_SICONFI, DADOS, GRANDE_VITORIA
from ..http import sessao

log = logging.getLogger("vigia.siconfi")
BASE = "https://apidatalake.tesouro.gov.br/ords/siconfi/tt"
PASTA = DADOS / "siconfi"

ANEXOS_DCA = {
    "DCA-Anexo I-C": "dca_receitas",
    "DCA-Anexo I-D": "dca_despesa_natureza",
    "DCA-Anexo I-E": "dca_despesa_funcao",
}
ANEXOS_RREO = {
    "RREO-Anexo 01": "rreo_balanco_orcamentario",
    "RREO-Anexo 02": "rreo_despesa_funcao",
}
ANEXOS_RGF = {
    "RGF-Anexo 01": "rgf_pessoal",
}


def paginar(s, endpoint: str, params: dict) -> list[dict]:
    """A API do Siconfi (Oracle ORDS) devolve até 5000 itens por página."""
    itens, offset = [], 0
    while True:
        p = dict(params)
        if offset:
            p["offset"] = offset
        r = s.get(f"{BASE}/{endpoint}", params=p, timeout=120)
        r.raise_for_status()
        j = r.json()
        lote = j.get("items", [])
        itens.extend(lote)
        if not j.get("hasMore") or not lote:
            return itens
        offset += len(lote)
        time.sleep(0.3)


def validar_entes(s) -> pd.DataFrame:
    """Confere códigos IBGE e traz população (usada no gasto por habitante)."""
    entes = pd.DataFrame(paginar(s, "entes", {}))
    if entes.empty:
        raise RuntimeError("Siconfi não devolveu o cadastro de entes")
    entes["cod_ibge"] = entes["cod_ibge"].astype(int)
    gv = entes[entes["cod_ibge"].isin(GRANDE_VITORIA)].copy()
    for cod, nome in GRANDE_VITORIA.items():
        linha = gv[gv["cod_ibge"] == cod]
        if linha.empty:
            log.warning("Código IBGE %s (%s) não encontrado no Siconfi", cod, nome)
        elif nome.lower() not in str(linha.iloc[0]["ente"]).lower():
            log.warning("Código %s esperado '%s', Siconfi diz '%s'", cod, nome, linha.iloc[0]["ente"])
    armazem.gravar(gv, PASTA / "entes.csv", chave=["cod_ibge"], ordenar=["cod_ibge"])
    return gv


def _ja_tem(df: pd.DataFrame, ente: int, ano: int, periodo: int | None = None) -> bool:
    if df.empty or "cod_ibge" not in df.columns:
        return False
    m = (df["cod_ibge"] == str(ente)) & (df["exercicio"] == str(ano))
    if periodo is not None and "periodo" in df.columns:
        m &= df["periodo"] == str(periodo)
    return bool(m.any())


def _salvar(nome: str, novos: list[dict], chave: list[str]):
    if not novos:
        return
    caminho = PASTA / f"{nome}.csv"
    df = armazem.juntar(armazem.ler(caminho), pd.DataFrame(novos))
    armazem.gravar(df, caminho, chave=chave, ordenar=["cod_ibge", "exercicio"])
    log.info("%s: +%d linhas", nome, len(novos))


def coletar_dca(s, ano_atual: int):
    """Contas anuais. Anos já baixados são pulados, exceto os 2 mais recentes
    (as prefeituras retificam declarações)."""
    for anexo, nome in ANEXOS_DCA.items():
        existente = armazem.ler(PASTA / f"{nome}.csv")
        novos = []
        for ano in range(ANO_INICIAL_SICONFI, ano_atual):
            recente = ano >= ano_atual - 2
            for ente in GRANDE_VITORIA:
                if not recente and _ja_tem(existente, ente, ano):
                    continue
                itens = paginar(s, "dca", {"an_exercicio": ano, "no_anexo": anexo, "id_ente": ente})
                novos.extend(itens)
                time.sleep(0.3)
        _salvar(nome, novos, ["exercicio", "cod_ibge", "instituicao", "coluna", "cod_conta", "conta"])


def coletar_rreo(s, ano_atual: int):
    """Execução bimestral do ano corrente e do anterior."""
    for anexo, nome in ANEXOS_RREO.items():
        novos = []
        for ano in (ano_atual - 1, ano_atual):
            for periodo in range(1, 7):
                if ano == ano_atual and periodo > (date.today().month - 1) // 2 + 1:
                    break
                for ente in GRANDE_VITORIA:
                    novos.extend(paginar(s, "rreo", {
                        "an_exercicio": ano, "nr_periodo": periodo,
                        "co_tipo_demonstrativo": "RREO", "no_anexo": anexo,
                        "co_esfera": "M", "id_ente": ente,
                    }))
                    time.sleep(0.3)
        _salvar(nome, novos, ["exercicio", "periodo", "cod_ibge", "coluna", "cod_conta", "conta"])


def coletar_rgf(s, ano_atual: int):
    """Gasto com pessoal do Executivo (quadrimestral)."""
    for anexo, nome in ANEXOS_RGF.items():
        existente = armazem.ler(PASTA / f"{nome}.csv")
        novos = []
        for ano in range(ANO_INICIAL_SICONFI, ano_atual + 1):
            for periodo in (1, 2, 3):
                for ente in GRANDE_VITORIA:
                    if ano < ano_atual - 1 and _ja_tem(existente, ente, ano, periodo):
                        continue
                    novos.extend(paginar(s, "rgf", {
                        "an_exercicio": ano, "in_periodicidade": "Q", "nr_periodo": periodo,
                        "co_tipo_demonstrativo": "RGF", "no_anexo": anexo,
                        "co_esfera": "M", "co_poder": "E", "id_ente": ente,
                    }))
                    time.sleep(0.3)
        _salvar(nome, novos, ["exercicio", "periodo", "cod_ibge", "coluna", "cod_conta", "conta"])


def coletar(ano_atual: int | None = None):
    ano_atual = ano_atual or date.today().year
    s = sessao()
    validar_entes(s)
    coletar_dca(s, ano_atual)
    coletar_rreo(s, ano_atual)
    coletar_rgf(s, ano_atual)
