"""Coletor do Tribunal de Contas do ES (TCE-ES): receita e despesa mês a mês.

Fonte oficial: dados abertos do TCE-ES no portal do Governo do ES (CKAN)
    https://dados.es.gov.br/api/3/action/package_show?id=receitas-municipios
    https://dados.es.gov.br/api/3/action/package_show?id=despesas-municipios
São os dados que a própria prefeitura envia todo mês ao Tribunal (sistema CidadES, IN 68/2020).
Cada recurso é um ZIP por ano com os 78 municípios; o Vigia guarda só Cariacica.

Para que serve: acompanhar, mês a mês, se a arrecadação está acima ou abaixo da previsão do
orçamento (excesso de arrecadação) e quanto do orçamento foi aumentado por créditos adicionais,
sem depender da palavra de ninguém.

Como baixa (para não pesar nem errar):
- Só recursos em ZIP com exatamente um ano no nome; ano repetido no catálogo é erro (não adivinha qual vale).
- Baixa um ano quando o CSV ainda não existe ou quando a data de modificação do recurso no catálogo mudou
  (anotada em data/tcees/recursos.csv). Sem data no catálogo, baixa os dois últimos anos todo dia.
- O ZIP vai para um arquivo temporário e é lido em blocos, guardando só as linhas de Cariacica. O ZIP
  nacional não é guardado: o SHA-256 dele vai para o manifesto (qualquer pessoa baixa de novo na fonte).
- Confere que o ZIP tem um único CSV e que a coluna Ano é o ano do recurso; senão, não grava.
- Um ano com erro não impede os outros; no fim, a coleta falha alto dizendo quais anos falharam.
- Ano corrente ainda sem nenhuma linha de Cariacica até março (a prefeitura ainda não enviou janeiro):
  aviso, não erro.

Cuidados conhecidos (descobertos em nov/2026):
- "Arrecadada", "Empenhada", "Liquidada" e "Paga" são valores DO MÊS (somar os meses dá o ano).
- "PrevisaoInicial" aparece inteira no mês 1 (é a previsão da LOA). "PrevisaoAtualizada" tem
  semântica mensal ambígua; vigia/indicadores.py só usa o que confere com o RREO do Siconfi.
- Os arquivos vêm em UTF-8 ou latin-1, separados por ponto e vírgula, com vírgula decimal.
"""
from __future__ import annotations

import hashlib
import io
import logging
import re
import tempfile
import zipfile
from datetime import date

import pandas as pd

from .. import armazem, qualidade
from ..config import DADOS
from ..http import sessao
from .transparencia import decimal_br

log = logging.getLogger("vigia.tcees")
CKAN = "https://dados.es.gov.br/api/3/action/package_show"
PASTA = DADOS / "tcees"
RECURSOS = PASTA / "recursos.csv"
MUNICIPIO = "Cariacica"
ANO_INICIAL = 2019
ANOS_ATUALIZADOS = 2
MES_LIMITE_ANO_VAZIO = 3

RECEITA = ["Ano", "Mes", "CodigoUnidadeGestora", "UnidadeGestora", "ClassificacaoReceita", "NomeCategoria",
           "NomeOrigem", "NomeEspecie", "NomeDetalhamentoNivel1", "NomeDetalhamentoNivel2",
           "NomeDetalhamentoNivel3", "CodigoFonteReduzida", "NomeFonteReduzida",
           "PrevisaoInicial", "PrevisaoAtualizada", "Arrecadada"]
# Despesa: agregada por mês, órgão, função e fonte (o arquivo completo tem uma linha por elemento de despesa)
DESPESA_CHAVE = ["Ano", "Mes", "CodigoOrgao", "NomeOrgao", "CodigoFuncao", "DescricaoFuncao",
                 "CodigoFonteReduzida", "NomeFonteReduzida"]
DESPESA_VALORES = ["PrevisaoInicial", "PrevisaoAtualizada", "Empenhada", "Liquidada", "Paga"]
CONJUNTOS = {
    "receitas": ("receitas-municipios", RECEITA, "Arrecadada"),
    "despesas": ("despesas-municipios", DESPESA_CHAVE + DESPESA_VALORES, "Empenhada"),
}
OBRIGATORIAS = {"Ano": r"\d{4}", "Mes": r"\d{1,2}"}
VALORES = ("Previsao", "Arrecadada", "Empenhada", "Liquidada", "Paga")


def recursos_por_ano(s, slug: str) -> dict[int, dict]:
    """{ano: {"url", "modificado"}} a partir do catálogo CKAN (só ZIPs com um ano no nome)."""
    r = s.get(CKAN, params={"id": slug}, timeout=120)
    r.raise_for_status()
    j = r.json()
    if not j.get("success"):
        raise ValueError(f"CKAN não achou o conjunto {slug}")
    saida: dict[int, dict] = {}
    for rec in j["result"].get("resources", []):
        url = (rec.get("url") or "").strip()
        formato = (rec.get("format") or "").strip().lower()
        if not url or not (formato == "zip" or url.lower().split("?")[0].endswith(".zip")):
            continue                                     # dicionário de dados, PDF etc.
        anos = set(re.findall(r"(20\d\d)", rec.get("name") or ""))
        if len(anos) != 1:
            log.warning("TCE-ES %s: recurso %r ignorado (o nome não tem exatamente um ano)", slug, rec.get("name"))
            continue
        ano = int(anos.pop())
        if ano in saida:
            raise ValueError(f"TCE-ES {slug}: o catálogo tem dois ZIPs para {ano}; não dá para saber qual vale")
        saida[ano] = {"url": url, "modificado": (rec.get("last_modified") or rec.get("metadata_modified") or "").strip()}
    return saida


def ler_zip(arquivo) -> pd.DataFrame:
    """Lê o único CSV do ZIP do TCE-ES (UTF-8 ou latin-1, ';', vírgula decimal), em blocos, guardando só
    as linhas de Cariacica. `arquivo`: bytes, caminho ou arquivo aberto."""
    if isinstance(arquivo, (bytes, bytearray)):
        arquivo = io.BytesIO(arquivo)
    with zipfile.ZipFile(arquivo) as z:
        csvs = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if len(csvs) != 1:
            raise ValueError(f"ZIP do TCE-ES com {len(csvs)} CSVs (esperado 1): {csvs[:5]}")
        for cod in ("utf-8-sig", "latin-1"):
            try:
                with z.open(csvs[0]) as bruto:
                    texto = io.TextIOWrapper(bruto, encoding=cod, newline="")
                    partes = []
                    for bloco in pd.read_csv(texto, sep=";", dtype=str, keep_default_na=False, chunksize=100_000):
                        if "EsferaAdministrativa" not in bloco.columns:
                            raise ValueError("TCE-ES: coluna EsferaAdministrativa ausente")
                        partes.append(bloco[bloco["EsferaAdministrativa"].str.strip() == MUNICIPIO])
                return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()
            except UnicodeDecodeError:
                continue
    raise ValueError("TCE-ES: codificação desconhecida")


def preparar(df: pd.DataFrame, conjunto: str) -> pd.DataFrame:
    """Só Cariacica, colunas da lista, valores em formato numérico com ponto decimal."""
    _, colunas, _ = CONJUNTOS[conjunto]
    if df.empty:
        return pd.DataFrame(columns=DESPESA_CHAVE + DESPESA_VALORES if conjunto == "despesas" else colunas)
    df = df[df["EsferaAdministrativa"].str.strip() == MUNICIPIO]
    faltando = [c for c in colunas if c not in df.columns]
    if faltando:
        raise ValueError(f"TCE-ES {conjunto}: colunas ausentes {faltando}")
    df = df[colunas].copy()
    valores = [c for c in colunas if c.startswith(VALORES)]
    for c in valores:
        df[c] = df[c].map(decimal_br)
    for c in df.columns:
        if c not in valores:
            df[c] = df[c].astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
    if conjunto == "despesas":
        num = df.assign(**{c: pd.to_numeric(df[c], errors="coerce").fillna(0) for c in DESPESA_VALORES})
        df = num.groupby(DESPESA_CHAVE, as_index=False)[DESPESA_VALORES].sum()
        for c in DESPESA_VALORES:
            df[c] = df[c].map(lambda v: f"{v:.2f}")
    # mês em ordem numérica (1, 2, ..., 12), não de texto (1, 10, 11, 12, 2...)
    df = df.assign(_m=pd.to_numeric(df["Mes"], errors="coerce")).sort_values(["_m"] + [c for c in df.columns if c not in ("_m", "Ano", "Mes")][:3], kind="stable")
    return df.drop(columns="_m").reset_index(drop=True)


def _estado() -> dict[tuple[str, int], str]:
    e = armazem.ler(RECURSOS)
    if e.empty:
        return {}
    return {(r["conjunto"], int(r["ano"])): r["modificado"] for _, r in e.iterrows()}


def _anotar(conjunto: str, ano: int, url: str, modificado: str, sha: str) -> None:
    e = armazem.ler(RECURSOS)
    nova = pd.DataFrame([{"conjunto": conjunto, "ano": str(ano), "url": url, "modificado": modificado,
                          "sha256": sha, "baixado_em": qualidade.agora()}])
    e = pd.concat([e, nova], ignore_index=True) if not e.empty else nova
    armazem.gravar(e, RECURSOS, chave=["conjunto", "ano"], ordenar=["conjunto", "ano"])


def anos_para_baixar(conjunto: str, recursos: dict[int, dict], hoje: date, estado: dict | None = None) -> list[int]:
    """Ano novo, CSV que falta ou recurso modificado no catálogo. Sem data no catálogo: os anos recentes."""
    estado = estado if estado is not None else {}
    anos = []
    for ano in sorted(recursos):
        if ano < ANO_INICIAL:
            continue
        existe = (PASTA / f"{conjunto}_{ano}.csv").exists()
        modificado = recursos[ano].get("modificado", "") if isinstance(recursos[ano], dict) else ""
        if not existe:
            anos.append(ano)
        elif modificado:
            if estado.get((conjunto, ano)) != modificado:
                anos.append(ano)
        elif ano > hoje.year - ANOS_ATUALIZADOS:
            anos.append(ano)
    return anos


def _baixar(s, url: str):
    """Baixa para arquivo temporário; devolve (arquivo, sha256, bytes)."""
    tmp = tempfile.TemporaryFile()
    h, n = hashlib.sha256(), 0
    with s.get(url, stream=True, timeout=600) as r:
        r.raise_for_status()
        for bloco in r.iter_content(1 << 20):
            tmp.write(bloco)
            h.update(bloco)
            n += len(bloco)
    tmp.seek(0)
    return tmp, h.hexdigest(), n


def _coletar_ano(s, conjunto: str, ano: int, recurso: dict, hoje: date) -> None:
    _, _, coluna_total = CONJUNTOS[conjunto]
    url = recurso["url"]
    nome = f"tcees_{conjunto}_{ano}.zip"
    tmp, sha, tamanho = _baixar(s, url)
    with tmp:
        qualidade.registrar_bruto(nome, sha, tamanho, url)
        df = preparar(ler_zip(tmp), conjunto)
    arquivo = f"{conjunto}_{ano}.csv"
    if df.empty and ano == hoje.year and hoje.month <= MES_LIMITE_ANO_VAZIO:
        qualidade.REGISTRO.add(qualidade.Checagem("tcees", arquivo, "ano_sem_dados_ainda", False, False,
                                                  f"o ZIP de {ano} ainda não tem linhas de Cariacica (normal até março)"))
        return
    anos_no_arquivo = sorted(set(df["Ano"])) if not df.empty else []
    if anos_no_arquivo and anos_no_arquivo != [str(ano)]:
        qualidade.REGISTRO.add(qualidade.Checagem("tcees", arquivo, "ano_confere", False, True,
                                                  f"recurso de {ano} traz o(s) ano(s) {anos_no_arquivo}: não gravado"))
        return
    chs = qualidade.validar_tabela(
        df, armazem.ler(PASTA / arquivo), fonte="tcees", arquivo=arquivo,
        obrigatorias={**OBRIGATORIAS, coluna_total: r"-?\d+\.\d{2}"}, coluna_total=coluna_total,
        ano=ano, ano_fechado=ano <= hoje.year - ANOS_ATUALIZADOS, brutos=[nome])
    if not qualidade.aprovado(chs):
        log.error("%s NÃO gravado: falhou na checagem; mantida a versão anterior", arquivo)
        return
    armazem.gravar(df, PASTA / arquivo)
    _anotar(conjunto, ano, url, recurso.get("modificado", ""), sha)
    total = pd.to_numeric(df[coluna_total], errors="coerce").sum()
    log.info("TCE-ES %s %s: %d linhas, %s R$ %.1f mi", conjunto, ano, len(df), coluna_total, total / 1e6)


def coletar(hoje: date | None = None, s=None) -> None:
    hoje = hoje or date.today()
    if s is None:
        s = sessao()
        s.headers["Accept"] = "*/*"
    estado = _estado()
    erros = []
    for conjunto, (slug, _, _) in CONJUNTOS.items():
        recursos = recursos_por_ano(s, slug)
        baixar = anos_para_baixar(conjunto, recursos, hoje, estado)
        log.info("TCE-ES %s: %d anos no catálogo, %d a baixar %s", conjunto, len(recursos), len(baixar), baixar)
        for ano in baixar:
            try:
                _coletar_ano(s, conjunto, ano, recursos[ano], hoje)
            except Exception as e:                     # um ano com erro não derruba os outros
                log.error("TCE-ES %s %s: %s", conjunto, ano, e)
                qualidade.REGISTRO.add(qualidade.Checagem("tcees", f"{conjunto}_{ano}.csv", "erro_na_fonte", False,
                                                          False, f"{type(e).__name__}: {str(e)[:200]}; arquivo anterior mantido"))
                erros.append(f"{conjunto} {ano}")
    if erros:
        raise RuntimeError(f"TCE-ES: falha em {', '.join(erros)} (detalhes em docs/qualidade.md)")
