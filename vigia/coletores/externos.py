"""Duas notas de fora sobre a prefeitura: a previdência dos servidores (ISP) e as pendências no CAUC.

ISP, Indicador de Situação Previdenciária (Ministério da Previdência), anual, planilha com todos os regimes:
    página  https://www.gov.br/previdencia/pt-br/assuntos/rpps/indice-de-situacao-previdenciaria
    arquivo resultado-final-isp-AAAA-...xlsx (o link é achado na página; a sonda de 10/11/2026 baixou o de 2025)
    -> data/previdencia/isp.csv: uma linha por cidade da Grande Vitória, planilha e indicador
    Para Cariacica (IPC) em 2025: nota geral B; gestão e transparência A; finanças e liquidez C; atuária A;
    R$ 597,5 mi aplicados em dez/2024 (R$ 500,7 mi em dez/2023); 4.050 servidores ativos, 1.240 aposentados e
    212 pensionistas no regime próprio.

CAUC (Tesouro Nacional), atualizado todo dia útil: situação de cada município em cada exigência para receber
transferências voluntárias da União. Data em uma exigência = comprovada até aquela data; "!" = sem comprovação
válida naquele dia; "Desabilitado" = exigência não aplicada.
    https://www.tesourotransparente.gov.br/ckan/dataset/cauc ("Relatório da situação dos municípios no CAUC")
    -> data/cauc/cauc.csv: uma linha por dia de pesquisa, cidade da Grande Vitória e exigência
    O significado de cada código (1.1, 2.1.1...) está nos metadados do Tesouro, no mesmo conjunto.
"""
from __future__ import annotations

import hashlib
import io
import logging
import re
from datetime import date

import pandas as pd

from .. import armazem, qualidade
from ..config import DADOS, GRANDE_VITORIA
from ..http import sessao

log = logging.getLogger("vigia.externos")
PASTA_ISP = DADOS / "previdencia"
PASTA_CAUC = DADOS / "cauc"
PAGINA_ISP = "https://www.gov.br/previdencia/pt-br/assuntos/rpps/indice-de-situacao-previdenciaria"
CKAN_TT = "https://www.tesourotransparente.gov.br/ckan/api/3/action/package_show"
UA_NAVEGADOR = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
PLANILHAS_ISP = ["RESULTADO", "GRUPOS", "ACUMULAÇÃO", "SUFICIÊNCIA (NOVO)", "COBERTURA", "SUSTENTABILIDADE",
                 "REFORMA", "GESTÃO", "ENVIOS", "REGULARIDADE"]
LINHA_CABECALHO_ISP = 3   # 4ª linha da planilha


def _nomes_alvo() -> dict[str, int]:
    """'CARIACICA - ES' -> 3201308 (nome como a planilha do ISP escreve)."""
    return {f"{nome.upper()} - ES": ibge for ibge, nome in GRANDE_VITORIA.items()}


# ---------------------------------------------------------------- ISP

def link_isp(html: str) -> tuple[int, str]:
    achados = re.findall(r'href="([^"]*resultado-final-isp-(\d{4})[^"]*\.xlsx)"', html, flags=re.I)
    if not achados:
        raise ValueError("página do ISP sem link para a planilha de resultado final")
    url, ano = max(achados, key=lambda x: int(x[1]))
    return int(ano), url


def ler_isp(conteudo: bytes, ano_isp: int) -> pd.DataFrame:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
    alvo = _nomes_alvo()
    linhas = []
    for nome in PLANILHAS_ISP:
        if nome not in wb.sheetnames:
            continue
        cab = None
        for i, row in enumerate(wb[nome].iter_rows(values_only=True)):
            if i == LINHA_CABECALHO_ISP:
                cab = [re.sub(r"\s+", " ", str(c)).strip() if c is not None else None for c in row]
                continue
            if cab is None or not row or not isinstance(row[0], str):
                continue
            ente = row[0].strip().upper()
            if ente not in alvo:
                continue
            for h, v in zip(cab, row):
                if h is None or h in ("ENTE", "UF", "CNPJ") or v is None or str(v).strip() in ("", "-"):
                    continue
                valor = v.isoformat()[:10] if hasattr(v, "isoformat") else str(v)
                linhas.append({"ano_isp": ano_isp, "cod_ibge": alvo[ente], "ente": ente, "planilha": nome,
                               "indicador": h, "valor": valor})
    df = pd.DataFrame(linhas)
    if df.empty or str(3201308) not in set(df["cod_ibge"].astype(str)):
        raise ValueError("planilha do ISP sem a linha de Cariacica")
    return df


def coletar_isp(s, hoje: date) -> None:
    """A página é lida todo dia (uma chamada); a planilha (3,5 MB) só é baixada quando sai um ano novo ou no
    dia 1 de cada mês (o Ministério às vezes republica o ano com correções)."""
    # Accept JSON faz o gov.br (Plone) responder pela API REST, que exige login (HTTP 401 em 11/11/2026)
    h = {"User-Agent": UA_NAVEGADOR, "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}
    r = s.get(PAGINA_ISP, headers=h, timeout=120)
    r.raise_for_status()
    ano, url = link_isp(r.text)
    caminho = PASTA_ISP / "isp.csv"
    antigo = armazem.ler(caminho)
    if not antigo.empty and str(ano) in set(antigo["ano_isp"].astype(str)) and hoje.day != 1:
        return
    r = s.get(url, headers=h, timeout=300)
    r.raise_for_status()
    sha = hashlib.sha256(r.content).hexdigest()
    qualidade.registrar_bruto(f"isp_{ano}.xlsx", sha, len(r.content), url)
    df = ler_isp(r.content, ano)
    junto = armazem.juntar(antigo, df) if not antigo.empty else df
    chs = qualidade.validar_tabela(junto, antigo, fonte="previdencia", arquivo=caminho.name,
                                   obrigatorias={"ano_isp": r"\d{4}", "indicador": r".+"}, coluna_total="ano_isp")
    if qualidade.aprovado(chs):
        armazem.gravar(junto, caminho, chave=["ano_isp", "cod_ibge", "planilha", "indicador"],
                       ordenar=["ano_isp", "cod_ibge", "planilha", "indicador"])
        log.info("ISP %d: %d indicadores da Grande Vitória", ano, len(df))


# ---------------------------------------------------------------- CAUC

def ler_cauc(texto: str) -> pd.DataFrame:
    linhas = texto.splitlines()
    data = ""
    for l in linhas[:5]:
        m = re.search(r"Data da Pesquisa:\s*(\d{2}/\d{2}/\d{4})", l)
        if m:
            data = m.group(1)
    inicio = next((i for i, l in enumerate(linhas) if l.startswith('"UF"')), None)
    if inicio is None or not data:
        raise ValueError("CAUC: cabeçalho ou data da pesquisa não encontrados")
    df = pd.read_csv(io.StringIO("\n".join(linhas[inicio:])), sep=";", dtype=str, keep_default_na=False)
    col_ibge = next(c for c in df.columns if "IBGE" in c.upper())
    df = df[df[col_ibge].astype(str).isin({str(k) for k in GRANDE_VITORIA})]
    itens = [c for c in df.columns if re.fullmatch(r"\d+(\.\d+)+", c.strip())]
    if not itens:
        raise ValueError("CAUC: nenhuma coluna de exigência (1.1, 2.1.1...)")
    d, m, a = data.split("/")
    longo = df.melt(id_vars=[col_ibge], value_vars=itens, var_name="item", value_name="situacao")
    longo = longo.rename(columns={col_ibge: "cod_ibge"})
    longo.insert(0, "data_pesquisa", f"{a}-{m}-{d}")
    longo["ente"] = longo["cod_ibge"].astype(int).map(GRANDE_VITORIA)
    longo["pendente"] = longo["situacao"].str.strip().eq("!").map({True: "sim", False: "não"})
    return longo[["data_pesquisa", "cod_ibge", "ente", "item", "situacao", "pendente"]]


def coletar_cauc(s) -> None:
    r = s.get(CKAN_TT, params={"id": "cauc"}, timeout=120)
    r.raise_for_status()
    rec = next((x for x in r.json()["result"]["resources"] if "munic" in x.get("name", "").lower()
                and x.get("url", "").lower().endswith(".csv")), None)
    if rec is None:
        raise ValueError("CAUC: recurso dos municípios não encontrado no catálogo")
    r = s.get(rec["url"], timeout=300)
    r.raise_for_status()
    qualidade.registrar_bruto("cauc_municipios.csv", hashlib.sha256(r.content).hexdigest(), len(r.content), rec["url"])
    df = ler_cauc(r.content.decode("latin-1"))
    caminho = PASTA_CAUC / "cauc.csv"
    antigo = armazem.ler(caminho)
    junto = armazem.juntar(antigo, df) if not antigo.empty else df
    chs = qualidade.validar_tabela(junto, antigo, fonte="cauc", arquivo=caminho.name,
                                   obrigatorias={"data_pesquisa": r"\d{4}-\d{2}-\d{2}", "item": r"[\d.]+"},
                                   coluna_total="cod_ibge")
    if qualidade.aprovado(chs):
        armazem.gravar(junto, caminho, chave=["data_pesquisa", "cod_ibge", "item"],
                       ordenar=["data_pesquisa", "cod_ibge", "item"])
        pend = df[(df["cod_ibge"].astype(str) == "3201308") & (df["pendente"] == "sim")]["item"].tolist()
        log.info("CAUC %s: Cariacica com %d exigências sem comprovação (%s)", df["data_pesquisa"].iloc[0], len(pend),
                 ", ".join(pend))


def coletar(hoje: date | None = None, s=None) -> None:
    s = s or sessao()
    hoje = hoje or date.today()
    erros, excecoes = [], []
    for nome, f in (("ISP", lambda x: coletar_isp(x, hoje)), ("CAUC", coletar_cauc)):
        try:
            f(s)
        except Exception as e:  # noqa: BLE001
            log.exception("%s falhou", nome)
            erros.append(f"{nome}: {type(e).__name__}: {str(e)[:120]}")
            excecoes.append(e)
    if erros:
        # Site do governo recusando o GitHub ou fora do ar (24/11/2026: gov.br e Tesouro abortaram a conexão):
        # é fonte fora, que só vira alarme se durar. Erro no nosso código continua sendo alarme na hora.
        if all(qualidade.erro_passageiro(e, []) for e in excecoes):
            raise RuntimeError("; ".join(erros)) from excecoes[0]
        raise RuntimeError("; ".join(erros))


# ---------------------------------------------------------------- relatório

def secao_markdown() -> str:
    partes = []
    isp = armazem.ler(PASTA_ISP / "isp.csv")
    if not isp.empty:
        ano = isp["ano_isp"].astype(int).max()
        r = isp[(isp["ano_isp"].astype(int) == ano) & (isp["planilha"] == "RESULTADO")]
        cols = {"INDICADOR DE SITUAÇÃO PREVIDENCIÁRIA": "Nota geral",
                "CLASSIFICAÇÃO EM GESTÃO E TRANSPARÊNCIA": "Gestão e transparência",
                "CLASSIFICAÇÃO EM FINANÇAS E LIQUIDEZ": "Finanças e liquidez", "CLASSIFICAÇÃO EM ATUÁRIA": "Atuária"}
        linhas = ["| Cidade | " + " | ".join(cols.values()) + " |", "|---|" + "---|" * len(cols)]
        for ente, g in r.groupby("ente"):
            m = dict(zip(g["indicador"], g["valor"]))
            cidade = GRANDE_VITORIA.get(int(g["cod_ibge"].iloc[0]), ente)
            linhas.append(f"| {cidade} | " + " | ".join(m.get(k, "-") for k in cols) + " |")
        partes.append(f"## Previdência dos servidores: nota no ISP {ano}\n\nFonte: Ministério da Previdência, Indicador "
                      "de Situação Previdenciária (A é a melhor nota, C a pior).\n\n" + "\n".join(linhas) + "\n")
    cauc = armazem.ler(PASTA_CAUC / "cauc.csv")
    if not cauc.empty:
        ult = cauc["data_pesquisa"].max()
        c = cauc[(cauc["data_pesquisa"] == ult) & (cauc["pendente"] == "sim")]
        por = c.groupby("ente")["item"].apply(lambda s: ", ".join(sorted(s))).to_dict()
        linhas = ["| Cidade | Exigências sem comprovação válida |", "|---|---|"]
        for ente in sorted(cauc["ente"].unique()):
            linhas.append(f"| {ente} | {por.get(ente, 'nenhuma')} |")
        partes.append(f"## Pendências no CAUC ({ult})\n\nFonte: Tesouro Nacional, CAUC (situação para receber "
                      "transferências voluntárias da União). \"!\" no relatório do Tesouro = sem comprovação válida "
                      "naquele dia; o nome de cada código está nos metadados do Tesouro.\n\n" + "\n".join(linhas) + "\n")
    return "\n".join(partes)
