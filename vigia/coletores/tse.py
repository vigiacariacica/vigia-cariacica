"""Coletor do TSE: fornecedores das campanhas municipais de Cariacica (2020 e 2024).

Fonte oficial: dados abertos do TSE (prestação de contas eleitorais e candidatos)
    https://cdn.tse.jus.br/estatistica/sead/odsele/prestacao_contas/prestacao_de_contas_eleitorais_candidatos_AAAA.zip
Dos ZIPs nacionais o Vigia lê só os arquivos do ES e guarda só as campanhas de Cariacica (prefeito,
vice e vereadores, de TODOS os partidos), e só fornecedores com CNPJ (empresas), sem doações entre campanhas,
sem CNPJ de campanha ou partido e sem o nome do titular de MEI (ver limpar()). Uma linha por empresa
e eleição, SEM nome de candidato e SEM partido, de propósito: o mesmo critério vale para todos, e as
publicações do Vigia não citam políticos. Serve à regra R25 (cruza essas empresas com os pagamentos
da prefeitura). Substitui o antigo ferramentas/financas/gerar_fornecedores_campanha.py (mesmo formato).

Dado que não muda depois da eleição: baixa uma vez (ou com `forcar=True`). Arquivos de 2020 e 2024
são grandes (centenas de MB); rodam no GitHub Actions, não precisam do computador de ninguém.
"""
from __future__ import annotations

import io
import logging
import re
import tempfile
import zipfile

import pandas as pd

from .. import armazem, qualidade
from ..config import DADOS
from ..http import sessao
from ..texto import mascarar_cpfs, so_digitos
from .transparencia import decimal_br

log = logging.getLogger("vigia.tse")
PASTA = DADOS / "tse"
ARQUIVO = PASTA / "fornecedores_campanha.csv"
MUNICIPIO = "CARIACICA"
ELEICOES = {
    2020: ("https://cdn.tse.jus.br/estatistica/sead/odsele/prestacao_contas/prestacao_de_contas_eleitorais_candidatos_2020.zip", None),
    2024: ("https://cdn.tse.jus.br/estatistica/sead/odsele/prestacao_contas/prestacao_de_contas_eleitorais_candidatos_2024.zip", None),
}
COLUNAS = ["cnpj", "fornecedor", "ano_eleicao", "cargos", "candidaturas", "valor_campanha", "cnae", "tipo_despesa"]
NULOS = {"", "#NULO", "#NULO#", "#NE", "#NE#"}
# Regras de publicação do arquivo (decididas em 07/11/2026; ver docs/METODOLOGIA.md, seção 7):
# 1) Só fornecedores. "Doações financeiras a outros candidatos/partidos" não é contratação: o "fornecedor" é
#    o CNPJ de outra campanha ("ELEICAO 2020 <NOME> VEREADOR") ou de partido, com o nome do político.
RE_DOACAO = re.compile(r"doa[cç][oõ]es financeiras a outros candidatos", re.I)
RE_POLITICA = re.compile(r"organiza[cç][oõ]es pol[ií]ticas", re.I)          # CNAE 94.92-8 (partidos, campanhas)
RE_CNPJ_DE_CAMPANHA = re.compile(r"^\s*ELEI[CÇ][AÃ]O\s+\d{4}\b", re.I)
# 2) MEI: na Receita, o nome da empresa é o nome do dono seguido do CPF. O nome da pessoa não é necessário
#    para a regra R25 (que usa o CNPJ) e fica omitido; se ela vier a receber da prefeitura, o portal da
#    prefeitura publica o nome no pagamento.
#    Formato novo do MEI (2025+): o começo do CNPJ antes do nome ("12.345.678 FULANO"): também omitido (24/11/2026).
RE_CPF_NO_NOME = re.compile(r"\*{3}\.\d{3}\.\d{3}-\*{2}|\d{3}\.?\d{3}\.?\d{3}-?\d{2}\s*$|^\s*\d{2}\.?\d{3}\.?\d{3}\s")
NOME_MEI = "MEI (nome do titular omitido)"


def limpar(df: pd.DataFrame) -> pd.DataFrame:
    """Aplica as regras de publicação: fora CNPJs de campanhas e partidos; nome de MEI omitido. Idempotente."""
    if df.empty:
        return df
    politica = (df["cnae"].str.contains(RE_POLITICA) | df["fornecedor"].str.contains(RE_CNPJ_DE_CAMPANHA)
                | df["tipo_despesa"].map(lambda t: bool(t) and all(RE_DOACAO.search(x) for x in str(t).split(";"))))
    df = df[~politica].copy()
    df.loc[df["fornecedor"].str.contains(RE_CPF_NO_NOME), "fornecedor"] = NOME_MEI
    return df.reset_index(drop=True)


def _ler_csv_tse(dados: bytes) -> pd.DataFrame:
    """Os arquivos do TSE vêm em latin-1; cópias já convertidas para UTF-8 também são aceitas."""
    try:
        texto = dados.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = dados.decode("latin-1")
    return pd.read_csv(io.StringIO(texto), sep=";", dtype=str, keep_default_na=False)


def _primeiro(serie: pd.Series) -> str:
    return next((str(v).strip() for v in serie if str(v).strip() not in NULOS), "")


def processar(despesas: pd.DataFrame, ano: int) -> pd.DataFrame:
    """Empresas contratadas por campanhas de Cariacica numa eleição: uma linha por CNPJ, sem candidato nem partido."""
    d = despesas[despesas["NM_UE"].str.upper().str.strip() == MUNICIPIO].copy()
    d["cnpj"] = d["NR_CPF_CNPJ_FORNECEDOR"].map(so_digitos)
    d = d[d["cnpj"].str.len() == 14]             # só empresas; CPF de pessoa fica de fora
    if "DS_ORIGEM_DESPESA" in d.columns:
        d = d[~d["DS_ORIGEM_DESPESA"].astype(str).str.contains(RE_DOACAO)]   # doação a outra campanha não é contratação
    if d.empty:
        return pd.DataFrame(columns=COLUNAS)
    d["valor"] = pd.to_numeric(d["VR_DESPESA_CONTRATADA"].map(decimal_br), errors="coerce").fillna(0.0)
    d["nome"] = [r if str(r).strip() not in NULOS else o for r, o in zip(d["NM_FORNECEDOR_RFB"], d["NM_FORNECEDOR"])]
    for col in ("DS_CNAE_FORNECEDOR", "DS_ORIGEM_DESPESA"):
        if col not in d.columns:
            d[col] = ""
    g = d.groupby("cnpj", sort=True)
    saida = pd.DataFrame({
        "fornecedor": g["nome"].agg(_primeiro),
        "cargos": g["DS_CARGO"].agg(lambda s: ", ".join(sorted({x.strip() for x in s if x.strip() not in NULOS}))),
        "candidaturas": g["SQ_CANDIDATO"].nunique(),
        "valor_campanha": g["valor"].sum().map(lambda v: f"{v:.2f}"),
        "cnae": g["DS_CNAE_FORNECEDOR"].agg(_primeiro),
        "tipo_despesa": g["DS_ORIGEM_DESPESA"].agg(lambda s: "; ".join(sorted({x.strip() for x in s if x.strip() not in NULOS}))),
    }).reset_index()
    saida["ano_eleicao"] = str(ano)
    saida["fornecedor"] = saida["fornecedor"].map(mascarar_cpfs)   # MEI às vezes tem o CPF no nome
    return limpar(saida[COLUNAS])


def _membro(z: zipfile.ZipFile, contem: str) -> bytes | None:
    for n in z.namelist():
        nl = n.lower()
        if contem in nl and nl.endswith("_es.csv"):
            return z.read(n)
    return None


def _baixar_zip(s, url: str) -> zipfile.ZipFile:
    tmp = tempfile.TemporaryFile()
    with s.get(url, stream=True, timeout=1800) as r:
        r.raise_for_status()
        for bloco in r.iter_content(1 << 20):
            tmp.write(bloco)
    tmp.seek(0)
    return zipfile.ZipFile(tmp)


def coletar(forcar: bool = False) -> None:
    if ARQUIVO.exists() and not forcar:
        log.info("TSE: %s já existe (dado eleitoral não muda); use forcar=True para refazer", ARQUIVO.name)
        return
    s = sessao()
    s.headers["Accept"] = "*/*"
    partes = []
    for ano, (url_contas, url_cand) in ELEICOES.items():
        z = _baixar_zip(s, url_contas)
        contas = _membro(z, "despesas_contratadas_candidatos")
        if contas is None:
            raise ValueError(f"TSE {ano}: arquivo de despesas do ES não encontrado no ZIP")
        qualidade.REGISTRO.manifesto.append({"arquivo_bruto": f"tse_{ano}_despesas_contratadas_ES.csv",
                                             "fonte": url_contas, "baixado_em": qualidade.agora(),
                                             "bytes": len(contas), "sha256": __import__("hashlib").sha256(contas).hexdigest()})
        partes.append(processar(_ler_csv_tse(contas), ano))
    df = pd.concat(partes, ignore_index=True)
    chs = qualidade.validar_tabela(df, armazem.ler(ARQUIVO), fonte="tse", arquivo=ARQUIVO.name,
                                   obrigatorias={"cnpj": r"\d{14}", "valor_campanha": r"-?\d+\.\d{2}"},
                                   coluna_total="valor_campanha")
    if qualidade.aprovado(chs):
        armazem.gravar(df, ARQUIVO, ordenar=["ano_eleicao", "cnpj"])
        log.info("TSE: %d empresas contratadas por campanhas de Cariacica", len(df))
