"""O Estado do ES em Cariacica: transferências constitucionais e convênios com a prefeitura.

Fonte: dados abertos do Governo do ES (CKAN, Portal da Transparência do Estado), confirmados pela sonda em 08/11/2026:
    portal-da-transparencia-transferencias-para-municipios   TransfEstadoMunicipios-AAAA.csv (ICMS, IPVA, IPI,
        Fundo de Redução das Desigualdades, CIDE, compensação financeira), um mês por linha e município
        -> data/estado/transferencias_AAAA.csv (só Cariacica)
    portal-da-transparencia-convenios-do-estado   Convenios-AAAA.csv, ConveniosExecucaoOrcamentaria-AAAA.csv,
        AditivosConvenios-AAAA.csv
        -> data/estado/convenios_AAAA.csv: convênios com a prefeitura (CNPJ 27.150.549/0001-19) ou com entidade
           de Cariacica (código IBGE do município do convênio)
        -> data/estado/convenios_pagamentos_AAAA.csv: pagamentos desses convênios (só favorecido com CNPJ)
        -> data/estado/convenios_aditivos_AAAA.csv

LGPD e segurança: saem as colunas de banco, agência e conta e os nomes dos responsáveis; pagamento a pessoa
física (CPF/NIS) não entra.

Para não pesar: arquivo nacional baixado só quando o CSV de Cariacica ainda não existe ou quando a data de
modificação do recurso no catálogo mudou (anotada em data/estado/recursos.csv). Os arquivos nacionais não
são guardados; o SHA-256 vai para o manifesto.
"""
from __future__ import annotations

import csv
import hashlib
import io
import logging
import re
from datetime import date

import pandas as pd

from .. import armazem, qualidade
from ..config import CARIACICA_IBGE, DADOS
from ..http import sessao
from ..texto import so_digitos

log = logging.getLogger("vigia.estado")
FONTE = "estado"
PASTA = DADOS / "estado"
RECURSOS = PASTA / "recursos.csv"
CKAN = "https://dados.es.gov.br/api/3/action/package_show"
CNPJ_PREFEITURA = "27150549000119"
ANO_INICIAL = 2019
CONJ_TRANSF = "portal-da-transparencia-transferencias-para-municipios"
CONJ_CONV = "portal-da-transparencia-convenios-do-estado"
TIPOS = {  # prefixo do nome do recurso -> arquivo do Vigia
    "TransfEstadoMunicipios": "transferencias",
    "Convenios": "convenios",
    "ConveniosExecucaoOrcamentaria": "convenios_pagamentos",
    "AditivosConvenios": "convenios_aditivos",
}
SEM_COLUNA = re.compile(r"(?i)banco|agencia|domicilio|responsavel")
COLS_PAGTO = ["CodigoConvenioConcedido", "Ano", "DataPagamento", "ValorPago", "ValorRap", "CpfCnpjNis", "Favorecido",
              "Documento", "DocumentoEmpenho", "UnidadeGestora", "Funcao", "SubFuncao", "Programa", "Acao", "Fonte",
              "CategoriaEconomica", "GrupoDespesa", "HistoricoDocumento"]


def recursos(s, conjunto: str) -> dict[tuple[str, int], dict]:
    r = s.get(CKAN, params={"id": conjunto}, timeout=120)
    r.raise_for_status()
    j = r.json()
    if not j.get("success"):
        raise ValueError(f"CKAN não achou {conjunto}")
    saida = {}
    for rec in j["result"].get("resources", []):
        m = re.fullmatch(r"([A-Za-z]+)-(\d{4})\.csv", str(rec.get("name", "")).strip())
        if not m or m.group(1) not in TIPOS:
            continue
        chave = (TIPOS[m.group(1)], int(m.group(2)))
        if chave in saida:
            raise ValueError(f"{conjunto}: dois recursos para {chave}")
        saida[chave] = {"url": rec["url"], "modificado": rec.get("last_modified") or rec.get("created") or ""}
    return saida


def ler_csv(conteudo: bytes) -> pd.DataFrame:
    for enc in ("utf-8-sig", "latin-1"):
        try:
            texto = conteudo.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    return pd.read_csv(io.StringIO(texto), sep=";", dtype=str, keep_default_na=False, quoting=csv.QUOTE_MINIMAL)


def decimal(s: pd.Series) -> pd.Series:
    """'38939082,2700000' -> '38939082.27'"""
    v = pd.to_numeric(s.astype(str).str.replace(".", "", regex=False).str.replace(",", ".", regex=False),
                      errors="coerce")
    return v.map(lambda x: "" if pd.isna(x) else f"{x:.2f}")


def filtrar_transferencias(df: pd.DataFrame) -> pd.DataFrame:
    df = df[df["CodMunicipio"].astype(str).str.strip() == str(CARIACICA_IBGE)].copy()
    for c in df.columns:
        if c not in ("Id", "CodMunicipio", "NomeMunicipio", "Ano", "Mes"):
            df[c] = decimal(df[c]) if not c.startswith("Indice") else df[c].str.replace(",", ".", regex=False)
    return df.drop(columns=[c for c in ("Id",) if c in df.columns])


def filtrar_convenios(df: pd.DataFrame) -> pd.DataFrame:
    cnpj = df.get("cnpjConcedenteConvenente", df.get("codConcedenteConvenente", pd.Series("", index=df.index)))
    ibge = df.get("codIBGEMunicipio", pd.Series("", index=df.index)).astype(str).str.strip()
    alvo = (cnpj.astype(str).map(so_digitos) == CNPJ_PREFEITURA) | (ibge == str(CARIACICA_IBGE))
    df = df[alvo].copy()
    df = df[[c for c in df.columns if not SEM_COLUNA.search(c)]]
    for c in ("valorConcessao", "valorTotalAditivos", "valorContrapartida"):
        if c in df.columns:
            df[c] = decimal(df[c])
    df["com_a_prefeitura"] = (df.get("cnpjConcedenteConvenente", df.get("codConcedenteConvenente"))
                              .astype(str).map(so_digitos) == CNPJ_PREFEITURA).map({True: "sim", False: "não"})
    return df


def filtrar_pagamentos(df: pd.DataFrame, codigos: set[str]) -> pd.DataFrame:
    doc = df["CpfCnpjNis"].astype(str).map(so_digitos)
    alvo = (doc == CNPJ_PREFEITURA) | df["CodigoConvenioConcedido"].astype(str).str.strip().isin(codigos)
    df = df[alvo & (doc.str.len() == 14)].copy()     # só favorecido com CNPJ: pessoa física nunca entra
    df = df[[c for c in COLS_PAGTO if c in df.columns]]
    for c in ("ValorPago", "ValorRap"):
        if c in df.columns:
            df[c] = decimal(df[c])
    return df


def filtrar_aditivos(df: pd.DataFrame, codigos: set[str]) -> pd.DataFrame:
    df = df[df["codConvenio"].astype(str).str.strip().isin(codigos)].copy()
    for c in ("valorConcessao", "valorContrapartida"):
        if c in df.columns:
            df[c] = decimal(df[c])
    return df


def _estado() -> dict[str, str]:
    e = armazem.ler(RECURSOS)
    return {} if e.empty else dict(zip(e["arquivo"], e["modificado"]))


def _anotar(arquivo: str, url: str, modificado: str, sha: str) -> None:
    e = armazem.ler(RECURSOS)
    novo = pd.DataFrame([{"arquivo": arquivo, "url": url, "modificado": modificado, "sha256": sha,
                          "baixado_em": qualidade.agora()}])
    armazem.gravar(armazem.juntar(e, novo), RECURSOS, chave=["arquivo"], ordenar=["arquivo"])


def _codigos_cariacica() -> set[str]:
    cods = set()
    for arq in PASTA.glob("convenios_2*.csv"):
        df = armazem.ler(arq)
        if "cod" in df.columns:
            cods |= set(df["cod"].astype(str).str.strip())
    return cods


def _baixar(s, url: str, nome: str) -> bytes:
    r = s.get(url, timeout=600)
    r.raise_for_status()
    qualidade.registrar_bruto(nome, hashlib.sha256(r.content).hexdigest(), len(r.content), url)
    return r.content


def coletar(hoje: date | None = None, s=None) -> None:
    hoje = hoje or date.today()
    s = s or sessao()
    recs = {**recursos(s, CONJ_TRANSF), **recursos(s, CONJ_CONV)}
    estado = _estado()
    # convênios antes de pagamentos e aditivos: os códigos de Cariacica saem deles
    ordem = ["transferencias", "convenios", "convenios_pagamentos", "convenios_aditivos"]
    erros = []
    for tipo in ordem:
        for (t, ano), rec in sorted(recs.items()):
            if t != tipo or ano < ANO_INICIAL or ano > hoje.year:
                continue
            arquivo = f"{tipo}_{ano}.csv"
            caminho = PASTA / arquivo
            if caminho.exists() and estado.get(arquivo) == rec["modificado"] and rec["modificado"]:
                continue
            try:
                bruto = _baixar(s, rec["url"], f"estado_{arquivo}")
                df = ler_csv(bruto)
                if tipo == "transferencias":
                    out, total, obrig = filtrar_transferencias(df), "IcmsTotal", {"Ano": r"\d{4}", "Mes": r"\d{1,2}"}
                elif tipo == "convenios":
                    out, total, obrig = filtrar_convenios(df), "valorConcessao", {"cod": r"\d+"}
                elif tipo == "convenios_pagamentos":
                    out, total, obrig = filtrar_pagamentos(df, _codigos_cariacica()), "ValorPago", {"Ano": r"\d{4}"}
                else:
                    out, total, obrig = filtrar_aditivos(df, _codigos_cariacica()), "valorConcessao", {"codConvenio": r"\d+"}
                if out.empty:
                    qualidade.REGISTRO.add(qualidade.Checagem(FONTE, arquivo, "sem_linhas_de_cariacica", True, False,
                                                              f"{len(df)} linhas no arquivo do Estado, nenhuma de Cariacica"))
                    _anotar(arquivo, rec["url"], rec["modificado"], hashlib.sha256(bruto).hexdigest())
                    continue
                chs = qualidade.validar_tabela(out, armazem.ler(caminho), fonte=FONTE, arquivo=arquivo,
                                               obrigatorias=obrig, coluna_total=total, ano=ano,
                                               ano_fechado=ano < hoje.year - 1)
                if qualidade.aprovado(chs):
                    armazem.gravar(out, caminho)
                    _anotar(arquivo, rec["url"], rec["modificado"], hashlib.sha256(bruto).hexdigest())
                    log.info("Estado %s: %d linhas de Cariacica", arquivo, len(out))
            except Exception as e:  # noqa: BLE001
                log.exception("Estado %s falhou", arquivo)
                erros.append(f"{arquivo}: {type(e).__name__}: {str(e)[:100]}")
    if erros:
        raise RuntimeError("estado: " + "; ".join(erros[:5]))


# ---------------------------------------------------------------- relatório

def _soma(padrao: str, coluna: str, filtro=None) -> pd.Series:
    out = {}
    for arq in sorted(PASTA.glob(padrao)):
        df = armazem.ler(arq)
        if df.empty or coluna not in df.columns:
            continue
        if filtro is not None:
            df = filtro(df)
        ano = int(re.search(r"(\d{4})", arq.name).group(1))
        out[ano] = pd.to_numeric(df[coluna], errors="coerce").sum()
    return pd.Series(out, dtype=float)


def _mi(v) -> str:
    return f"{float(v) / 1e6:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")


def secao_markdown() -> str:
    icms = _soma("transferencias_*.csv", "IcmsTotal")
    ipva = _soma("transferencias_*.csv", "Ipva")
    pago_pref = _soma("convenios_pagamentos_*.csv", "ValorPago",
                      lambda d: d[d["CpfCnpjNis"].astype(str).map(so_digitos) == CNPJ_PREFEITURA])
    if icms.empty and pago_pref.empty:
        return ""
    anos = sorted(set(icms.index) | set(pago_pref.index))
    linhas = ["| Ano | ICMS (R$ mi) | IPVA (R$ mi) | Convênios pagos à prefeitura (R$ mi) |", "|---|---:|---:|---:|"]
    for a in anos:
        linhas.append(f"| {a} | {_mi(icms.get(a, 0))} | {_mi(ipva.get(a, 0))} | {_mi(pago_pref.get(a, 0))} |")
    return ("## O que o Estado repassa a Cariacica\n\nFonte: Portal da Transparência do Governo do ES (dados.es.gov.br): "
            "transferências constitucionais e pagamentos de convênios. O ano corrente é parcial.\n\n" + "\n".join(linhas) + "\n")
