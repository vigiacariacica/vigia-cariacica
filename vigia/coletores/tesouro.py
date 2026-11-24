"""Coletor das transferências da União aos municípios (Tesouro Nacional), mês a mês.

Fonte oficial: Tesouro Transparente, "Transferências constitucionais para municípios"
    https://www.tesourotransparente.gov.br/ckan/dataset/af4e7c47-2132-4d9a-bd7c-34e28a210b03
Um CSV por mês com todos os municípios do Brasil: FPM, ITR, IOF-ouro, a parte do Fundeb e as
complementações da União ao Fundeb (VAAF, VAAT e VAAR), por decêndio.

Para que serve: o VAAR é o dinheiro do Fundeb que a União só paga a quem cumpre condições de gestão e
resultado (Lei 14.113/2020, art. 14). Em 09/11/2026 o Vigia viu que Cariacica recebeu VAAR todo mês em
2024 e nada a partir de fevereiro de 2025, enquanto o VAAT seguiu chegando. Com este coletor, a pergunta
deixa de depender de alguém olhar à mão: o relatório mostra, todo dia, o que entrou de cada complementação.

Como baixa:
- Lista os recursos do conjunto no catálogo (CKAN) e baixa os que são novos ou cuja data de modificação
  mudou (anotada em data/tesouro/recursos.csv). O nome do recurso nem sempre bate com o mês do arquivo
  (ex.: "..._202502.csv" aponta para o arquivo de janeiro), então o mês vem do conteúdo (colunas ANO e Mês).
- Guarda só as cinco cidades da Grande Vitória que o Vigia compara; o CSV nacional não é guardado, só o
  SHA-256 dele no manifesto.
- Um recurso com erro não impede os outros; no fim, a coleta falha alto dizendo quais falharam.
"""
from __future__ import annotations

import hashlib
import io
import logging
import re

import pandas as pd

from .. import armazem, qualidade
from ..config import DADOS
from ..http import sessao
from ..texto import sem_acento

log = logging.getLogger("vigia.tesouro")
CKAN = "https://www.tesourotransparente.gov.br/ckan/api/3/action/package_show"
CONJUNTO = "af4e7c47-2132-4d9a-bd7c-34e28a210b03"
PAGINA = "https://www.tesourotransparente.gov.br/ckan/dataset/" + CONJUNTO
PASTA = DADOS / "tesouro"
SAIDA = PASTA / "transferencias.csv"
RECURSOS = PASTA / "recursos.csv"
ANO_INICIAL = 2021
MUNICIPIOS = {"CARIACICA": "Cariacica", "VITORIA": "Vitória", "VILA VELHA": "Vila Velha", "SERRA": "Serra",
              "VIANA": "Viana"}
CHAVE = ["municipio", "ano", "mes", "transferencia", "item"]
COLUNAS = CHAVE + ["valor"]


def recursos(s) -> list[dict]:
    """Recursos CSV do conjunto a partir de ANO_INICIAL: [{"id", "url", "modificado"}]."""
    r = s.get(CKAN, params={"id": CONJUNTO}, timeout=120)
    r.raise_for_status()
    j = r.json()
    if not j.get("success"):
        raise ValueError("CKAN do Tesouro não achou o conjunto de transferências")
    saida = []
    for rec in j["result"].get("resources", []):
        url = rec.get("url") or ""
        anos = [int(a) for a in re.findall(r"(20\d{2})\d{2}", f"{rec.get('name', '')} {url}")]
        if not url.lower().split("?")[0].endswith(".csv") or not anos or max(anos) < ANO_INICIAL:
            continue
        saida.append({"id": rec.get("id") or url, "url": url,
                      "modificado": rec.get("last_modified") or rec.get("metadata_modified") or ""})
    return saida


def _estado() -> dict[str, str]:
    e = armazem.ler(RECURSOS)
    return {} if e.empty else dict(zip(e["id"], e["modificado"]))


def para_baixar(recs: list[dict], estado: dict[str, str]) -> list[dict]:
    """Recurso novo ou modificado no catálogo (sem data no catálogo: só se nunca foi baixado)."""
    return sorted((r for r in recs if r["id"] not in estado or (r["modificado"] and estado[r["id"]] != r["modificado"])),
                  key=lambda r: (r["modificado"], r["url"]))


def _numero(serie: pd.Series, em_centavos: bool = False) -> pd.Series:
    """'759016.49' ou '759.016,49' -> 759016.49. Com em_centavos, '75901649' -> 759016.49."""
    s = serie.astype(str).str.strip()
    br = s.str.contains(",")
    s = s.where(~br, s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False))
    v = pd.to_numeric(s, errors="coerce").fillna(0.0)
    return v / 100 if em_centavos else v


def _em_centavos(df: pd.DataFrame, colunas: list[int]) -> bool:
    """O arquivo de outubro de 2024 (mês 09) veio com os valores em centavos, sem separador decimal
    ('70201795' em vez de '702017.95'). Num arquivo normal, milhares de valores têm casas decimais; se
    nenhum tem, o arquivo está em centavos."""
    valores = pd.concat([df.iloc[:, i].astype(str) for i in colunas])
    return not valores.str.contains(r"[.,]").any()


def ler_csv(conteudo: bytes) -> pd.DataFrame:
    """CSV nacional do Tesouro -> linhas das cidades de MUNICIPIOS, uma por (cidade, ano, mês, transferência, item)."""
    try:
        texto = conteudo.decode("utf-8")
    except UnicodeDecodeError:
        texto = conteudo.decode("latin-1")
    df = pd.read_csv(io.StringIO(texto), sep=";", dtype=str, keep_default_na=False)
    nomes = [sem_acento(c).strip().lower() for c in df.columns]
    pos = {n: i for i, n in enumerate(nomes)}
    precisa = ["municipio", "uf", "ano", "mes", "item transferencia", "transferencia"]
    faltam = [n for n in precisa if n not in pos]
    decendios = [i for i, n in enumerate(nomes) if "decendio" in n]
    if faltam or len(decendios) != 3:
        raise ValueError(f"colunas inesperadas no CSV do Tesouro: faltam {faltam}, decêndios {len(decendios)}")
    col = lambda n: df.iloc[:, pos[n]]  # noqa: E731
    cidade = col("municipio").map(lambda v: sem_acento(v).strip().upper())
    ano, mes = pd.to_numeric(col("ano"), errors="coerce"), pd.to_numeric(col("mes"), errors="coerce")
    manter = (col("uf").str.strip().str.upper() == "ES") & cidade.isin(MUNICIPIOS) & ano.notna() & mes.between(1, 12)
    if not manter.any():
        return pd.DataFrame(columns=COLUNAS)
    centavos = _em_centavos(df, decendios)
    valor = sum(_numero(df.iloc[:, i], centavos) for i in decendios)
    out = pd.DataFrame({
        "municipio": cidade[manter].map(MUNICIPIOS),
        "ano": ano[manter].astype(int).astype(str),
        "mes": mes[manter].astype(int).map(lambda m: f"{m:02d}"),
        "transferencia": col("transferencia")[manter].str.strip(),
        "item": col("item transferencia")[manter].str.strip(),
        "valor": valor[manter],
    })
    out = out.groupby(CHAVE, as_index=False)["valor"].sum()
    out["valor"] = out["valor"].map(lambda v: f"{v:.2f}")
    return out[COLUNAS]


def _anotar(rec: dict, sha: str) -> None:
    e = armazem.ler(RECURSOS)
    nova = pd.DataFrame([{"id": rec["id"], "url": rec["url"], "modificado": rec["modificado"], "sha256": sha,
                          "baixado_em": qualidade.agora()}])
    e = pd.concat([e, nova], ignore_index=True) if not e.empty else nova
    armazem.gravar(e, RECURSOS, chave=["id"], ordenar=["url"])


def coletar(s=None) -> int:
    if s is None:
        s = sessao()
        s.headers["Accept"] = "*/*"
    recs = recursos(s)
    novos = para_baixar(recs, _estado())
    log.info("Tesouro: %d arquivos mensais no catálogo, %d a baixar", len(recs), len(novos))
    base = armazem.ler(SAIDA)
    erros = []
    for rec in novos:
        try:
            r = s.get(rec["url"], timeout=300)
            r.raise_for_status()
            sha = hashlib.sha256(r.content).hexdigest()
            nome = "tesouro_" + rec["url"].rstrip("/").split("/")[-1]
            qualidade.registrar_bruto(nome, sha, len(r.content), rec["url"])
            df = ler_csv(r.content)
            if df.empty:
                qualidade.REGISTRO.add(qualidade.Checagem("tesouro", nome, "sem_linhas_es", False, False,
                                                          "arquivo sem linhas das cidades da Grande Vitória"))
            else:
                base = pd.concat([base, df], ignore_index=True) if not base.empty else df
                base = base.drop_duplicates(CHAVE, keep="last")
                armazem.gravar(base, SAIDA, chave=CHAVE, ordenar=["municipio", "ano", "mes", "transferencia", "item"])
            _anotar(rec, sha)
        except Exception as e:                        # um arquivo com erro não derruba os outros
            log.error("Tesouro %s: %s", rec["url"], e)
            qualidade.REGISTRO.add(qualidade.Checagem("tesouro", rec["url"].split("/")[-1], "erro_na_fonte", False,
                                                      False, f"{type(e).__name__}: {str(e)[:200]}"))
            erros.append(rec["url"].split("/")[-1])
    if erros:
        raise RuntimeError(f"Tesouro: falha em {len(erros)} arquivo(s): {', '.join(erros[:5])}")
    return len(novos)


# ---------------------------------------------------------------- leitura para o relatório

def _tipo_complementacao(item: str) -> str | None:
    m = re.search(r"VAA[FTR]", str(item).upper())
    return m.group(0) if m else None


def complementacao_fundeb(df: pd.DataFrame | None = None, municipio: str = "Cariacica") -> pd.DataFrame:
    """Complementação da União ao Fundeb por ano (VAAF, VAAT, VAAR em R$, ajustes incluídos), meses com VAAR e
    meses em que o arquivo do Tesouro veio sem nenhuma linha de complementação entre dois meses que têm."""
    df = armazem.ler(SAIDA) if df is None else df
    if df.empty:
        return pd.DataFrame()
    cidade = df[df["municipio"] == municipio]
    d = cidade.assign(tipo=cidade["item"].map(_tipo_complementacao)).dropna(subset=["tipo"])
    if d.empty:
        return pd.DataFrame()
    d = d.assign(valor=pd.to_numeric(d["valor"], errors="coerce").fillna(0.0))
    t = d.pivot_table(index="ano", columns="tipo", values="valor", aggfunc="sum").fillna(0.0)
    for tipo in ("VAAT", "VAAR"):
        if tipo not in t:
            t[tipo] = 0.0
    t["meses_com_vaar"] = d[(d["tipo"] == "VAAR") & (d["valor"] > 0)].groupby("ano")["mes"].nunique() \
        .reindex(t.index).fillna(0).astype(int)
    t["ultimo_mes"] = cidade.groupby("ano")["mes"].max().reindex(t.index)
    # buracos: mês sem VAAT entre o primeiro mês com VAAT e o último mês do arquivo. O VAAT chega todo mês às
    # redes que têm direito; se um mês do meio vem sem ele, o arquivo do Tesouro veio incompleto
    # (09/11/2026: jan, fev, ago, set e out de 2024).
    meses = sorted({(a, m) for a, m in zip(cidade["ano"], cidade["mes"])})
    com_vaat = sorted({(a, m) for a, m, tp in zip(d["ano"], d["mes"], d["tipo"]) if tp == "VAAT"})
    buracos = [f"{m}/{a}" for a, m in meses if com_vaat and com_vaat[0] < (a, m) and (a, m) not in com_vaat
               and (a, m) <= meses[-1]]
    t["sem_complementacao"] = [", ".join(b for b in buracos if b.endswith(ano)) for ano in t.index]
    return t.reset_index()


def secao_markdown() -> str:
    t = complementacao_fundeb()
    if t.empty:
        return ""
    mi = lambda v: f"{v / 1e6:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")  # noqa: E731
    linhas = ["| Ano (até o mês) | VAAT (R$ mi) | VAAR (R$ mi) | Meses com VAAR |", "|---|---|---|---|"]
    for _, r in t.iterrows():
        linhas.append(f"| {r['ano']} (até {r['ultimo_mes']}) | {mi(r['VAAT'])} | {mi(r['VAAR'])} "
                      f"| {r['meses_com_vaar']} |")
    ultimo = t.iloc[-1]
    buracos = [b for b in t["sem_complementacao"] if b]
    aviso = ""
    if buracos:
        aviso = ("\nO arquivo do Tesouro destes meses veio sem nenhuma linha de complementação, então o total do ano "
                 f"fica abaixo do real: {', '.join(buracos)}. Para o ano fechado, vale também a receita registrada pela "
                 "prefeitura (`data/transparencia/receitas_AAAA.csv`).\n")
    pergunta = ""
    if len(t) > 1 and float(ultimo["VAAR"]) == 0 and float(t["VAAR"].iloc[:-1].max()) > 0:
        pergunta = (f"\n**Pergunta:** Cariacica não recebeu VAAR em {ultimo['ano']} até o mês {ultimo['ultimo_mes']}, "
                    "e já recebeu em anos anteriores. Qual condição da Lei 14.113/2020, art. 14, não foi cumprida, e o "
                    "que a prefeitura está fazendo para voltar a receber?\n")
    return ("## Complementação da União ao Fundeb (VAAT e VAAR)\n\n"
            "O VAAT ajuda redes com pouco dinheiro por aluno. O VAAR é pago só a quem cumpre condições de gestão e "
            f"resultado. Fonte: [Tesouro Nacional, transferências mensais]({PAGINA}) (`data/tesouro/transferencias.csv`).\n\n"
            + "\n".join(linhas) + "\n" + aviso + pergunta)
