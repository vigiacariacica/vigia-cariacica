"""Fila de espera de consultas e exames especializados (Secretaria Municipal de Saúde), planilha mensal.

Página: https://cariacica.es.gov.br/pagina/ler/951/semus-fila-de-espera-para-agendamento-de-consultas-e-exames
Cada mês tem um link para a planilha: xlsx no site da prefeitura ou planilha/arquivo do Google (maio a agosto de
2026). Os rótulos dos links às vezes vêm trocados (o "PDF" de maio é a planilha), então o coletor baixa todos os
links de planilha e descobre o mês pelo nome da aba ("SETEMBRO 2026") ou, se não houver, pela data de pedido
mais recente.

DADO PESSOAL: a planilha publicada traz nome completo e data de nascimento de cada paciente. O Vigia lê o arquivo
na memória e só usa esses dois campos para duas contas, feitas ali mesmo e descartadas:
- a idade de verdade, calculada pela data de nascimento no último dia do mês (a coluna "Idade do paciente" da
  planilha não bate com a data de nascimento na maior parte das linhas, então ela é ignorada; o resumo mensal mostra
  quanto confere em idade_planilha_confere_pct);
- quantas pessoas diferentes estão na fila (um pedido não é uma pessoa: a mesma pessoa pode esperar dois exames),
  com uma impressão digital de nome + nascimento feita com uma chave aleatória que nasce e morre em cada execução.
Nenhum nome, data de nascimento, impressão digital ou cópia do arquivo vai para o git (nada de guardar_bruto; só o
hash do arquivo é registrado). Em 12/11/2026 o Vigia pediu à prefeitura, pela Ouvidoria da Saúde, a fila sem esses
dados.

Crescimento: a lista de procedimentos muda de um mês para outro (121 em maio, 147 em setembro de 2026). Comparar só
o total exagera o crescimento; comparavel() soma só os procedimentos que aparecem em todos os meses.

Espera = dias entre a "Data da solicitação" e o último dia do mês da planilha: há quanto tempo espera quem ainda
está na fila. A prefeitura informa no topo da planilha outra medida (tempo médio de espera).

-> data/fila/fila_resumo_mensal.csv          uma linha por mês
-> data/fila/fila_especialidade_AAAA-MM.csv  pedidos, mediana e mais de 1 ano por procedimento
-> data/fila/fila_unidade_AAAA-MM.csv        o mesmo por unidade que pediu
-> data/fila/arquivos.csv                    url, hash, mês e data de leitura (para não reler o mesmo arquivo)
-> data/fila/links.csv                       links de planilha achados na página (o site da prefeitura recusa o
                                             GitHub com 403 desde 12/11/2026; aí o robô usa os links já conhecidos,
                                             e os do Google continuam baixando)
"""
from __future__ import annotations

import calendar
import hashlib
import io
import logging
import os
import re
from datetime import date, datetime

import pandas as pd

from .. import armazem, qualidade
from ..config import DADOS
from ..http import sessao

log = logging.getLogger("vigia.fila")
PASTA = DADOS / "fila"
PAGINA = "https://cariacica.es.gov.br/pagina/ler/951/semus-fila-de-espera-para-agendamento-de-consultas-e-exames"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
MESES = {m: i for i, m in enumerate(["JANEIRO", "FEVEREIRO", "MARCO", "ABRIL", "MAIO", "JUNHO", "JULHO", "AGOSTO",
                                     "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"], start=1)}
COLUNAS = {"data": r"^data da solicita", "unidade": r"^unidade solicitante", "idade_planilha": r"^idade",
           "item": r"^item", "prioridade": r"^prioridade"}
PESSOAIS = {"nascimento": r"^data (de )?nasc", "nome": r"^nome"}   # só na memória, nunca saem de ler_planilha
_CHAVE = os.urandom(16)        # muda a cada execução: a impressão digital de uma pessoa não serve fora dela
RESUMO = PASTA / "fila_resumo_mensal.csv"
ARQUIVOS = PASTA / "arquivos.csv"
LINKS = PASTA / "links.csv"
NAVEGADOR = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
             "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.5"}


# ---------------------------------------------------------------- links e download

def links(html: str) -> list[str]:
    """URLs de download das planilhas (xlsx do site, planilha do Google ou arquivo do Drive), sem repetir."""
    urls = []
    for href in re.findall(r'href="([^"]+)"', html):
        href = href.replace("&amp;", "&")
        if m := re.search(r"docs\.google\.com/spreadsheets/d/([\w-]+)", href):
            u = f"https://docs.google.com/spreadsheets/d/{m.group(1)}/export?format=xlsx"
        elif m := re.search(r"drive\.google\.com/file/d/([\w-]+)", href):
            u = f"https://drive.google.com/uc?export=download&id={m.group(1)}"
        elif re.search(r"fila.*\.xlsx$", href, re.I):
            u = href if href.startswith("http") else "https://cariacica.es.gov.br" + href
        else:
            continue
        if u not in urls:
            urls.append(u)
    return urls


def _sem_acento(t: str) -> str:
    return t.upper().replace("Ç", "C").replace("Ã", "A").replace("Á", "A").replace("Ê", "E").replace("É", "E")


# ---------------------------------------------------------------- leitura (só colunas não pessoais)

def _data(v, formato: str):
    if isinstance(v, (datetime, date)):
        return pd.Timestamp(v)
    if isinstance(v, (int, float)) and not pd.isna(v):
        return pd.Timestamp("1899-12-30") + pd.Timedelta(days=float(v))
    m = re.match(r"^\s*(\d{1,2})/(\d{1,2})/(\d{4})", str(v))
    if not m:
        return pd.NaT
    a, b, ano = int(m.group(1)), int(m.group(2)), int(m.group(3))
    mes, dia = (a, b) if formato == "M/D" else (b, a)
    try:
        return pd.Timestamp(ano, mes, dia)
    except ValueError:
        return pd.NaT


def _formato(serie: pd.Series) -> str:
    """'M/D' se algum texto só pode ser mês/dia (segundo número > 12) e nenhum só pode ser dia/mês."""
    partes = [m for m in serie.map(lambda v: re.match(r"^\s*(\d{1,2})/(\d{1,2})/\d{4}", v)
                                   if isinstance(v, str) else None) if m]
    md = any(int(m.group(2)) > 12 for m in partes)
    dm = any(int(m.group(1)) > 12 for m in partes)
    return "M/D" if md and not dm else "D/M"


def _idade(nasc: pd.Series, ref: pd.Timestamp) -> pd.Series:
    """Anos completos no dia ref; vazio se a data for impossível (antes de 1900 ou depois de ref)."""
    anos = ref.year - nasc.dt.year
    antes = (nasc.dt.month > ref.month) | ((nasc.dt.month == ref.month) & (nasc.dt.day > ref.day))
    idade = anos - antes.astype(int)
    return idade.where(nasc.notna() & (idade >= 0) & (idade <= 125))


def _pessoa(nome, nascimento) -> str | None:
    t = re.sub(r"\s+", " ", str(nome or "")).strip().upper()
    if not t:
        return None
    return hashlib.blake2b(f"{t}|{nascimento}".encode(), key=_CHAVE, digest_size=8).hexdigest()


def ler_planilha(conteudo: bytes) -> tuple[str, pd.DataFrame]:
    """Devolve o mês 'AAAA-MM' (pelo nome da aba ou, se não houver, pela data de pedido mais recente) e uma tabela
    com data, unidade, idade (calculada pela data de nascimento), idade da planilha, item, prioridade e pessoa (uma
    impressão digital que só vale nesta execução). Nome e data de nascimento nunca saem desta função."""
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
    ws = wb.worksheets[0]
    mes = None
    if m := re.search(r"([A-ZÇÃ]+)\s*/?\s*(\d{4})", _sem_acento(ws.title or "")):
        if _sem_acento(m.group(1)) in MESES:
            mes = f"{m.group(2)}-{MESES[_sem_acento(m.group(1))]:02d}"
    idx, linhas = None, []
    for row in ws.iter_rows(values_only=True):
        if idx is None:
            textos = [str(c or "").strip().lower() for c in row]
            if any(t.startswith("código de solicita") or t.startswith("codigo de solicita") for t in textos):
                idx = {k: next((i for i, t in enumerate(textos) if re.search(rx, t)), None)
                       for k, rx in {**COLUNAS, **PESSOAIS}.items()}
            continue
        if idx["item"] is None or idx["item"] >= len(row) or not row[idx["item"]]:
            continue
        val = lambda k: row[idx[k]] if idx[k] is not None and idx[k] < len(row) else None  # noqa: E731
        linha = {k: val(k) for k in COLUNAS}
        linha["nascimento"] = val("nascimento")
        linha["pessoa"] = _pessoa(val("nome"), linha["nascimento"])      # o nome não é guardado
        linhas.append(linha)
    wb.close()
    if idx is None:
        raise ValueError("cabeçalho 'Código de Solicitação' não encontrado")
    df = pd.DataFrame(linhas, columns=[*COLUNAS, "nascimento", "pessoa"])
    del linhas
    fd, fn = _formato(df["data"]), _formato(df["nascimento"])
    df["data"] = df["data"].map(lambda v: _data(v, fd))
    df = df.dropna(subset=["data"])
    mes = mes or f"{df['data'].max():%Y-%m}"
    ano, m = map(int, mes.split("-"))
    ref = pd.Timestamp(ano, m, calendar.monthrange(ano, m)[1])
    nasc = pd.to_datetime(df["nascimento"].map(lambda v: _data(v, fn)), errors="coerce")
    df["idade"] = _idade(nasc, ref)
    df = df.drop(columns=["nascimento"])
    del nasc
    df["idade_planilha"] = pd.to_numeric(df["idade_planilha"].astype(str).str.extract(r"(\d+)")[0], errors="coerce")
    df["item"] = (df["item"].astype(str).str.strip().str.replace(r"\s+METROPOLITANA$", "", regex=True)
                  .str.replace(r"\s*-\s*$", "", regex=True))
    df["unidade"] = (df["unidade"].astype(str).str.strip().str.replace(r"^CARIACICA\s*-\s*", "", regex=True)
                     .str.replace(r"\s*-\s*$", "", regex=True))
    df["prioridade"] = df["prioridade"].fillna("").astype(str).str.strip()
    return mes, df[["data", "unidade", "idade", "idade_planilha", "item", "prioridade", "pessoa"]]


# ---------------------------------------------------------------- somas

def resumir(df: pd.DataFrame, mes: str) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    ano, m = map(int, mes.split("-"))
    ref = pd.Timestamp(ano, m, calendar.monthrange(ano, m)[1])
    d = df.assign(espera=(ref - df["data"]).dt.days)

    def grupo(chave):
        g = d.groupby(chave)["espera"]
        return (pd.DataFrame({"pedidos": g.size(), "mediana_dias_espera": g.median().round().astype(int),
                              "mais_de_1_ano": g.apply(lambda s: int((s > 365).sum()))})
                .reset_index().sort_values("pedidos", ascending=False).assign(mes=mes))

    def foco(mask):
        s = d.loc[mask, "espera"]
        return (int(len(s)), int(round(s.median())) if len(s) else None, int((s > 365).sum()))

    ma = foco(d["prioridade"].str.upper() == "MUITO ALTA")
    eh_np = d["item"].str.fullmatch(r"CONSULTA EM NEUROLOGIA PEDIATRIA")
    npd = foco(eh_np)
    nad = foco(d["item"].str.fullmatch(r"CONSULTA EM NEUROLOGIA ADULTO"))
    e = d["espera"]
    ambas = d[["idade", "idade_planilha"]].dropna()
    confere = (ambas["idade"] - ambas["idade_planilha"]).abs().le(1).mean() if len(ambas) else None
    resumo = {"mes": mes, "data_referencia": f"{ref:%Y-%m-%d}", "pedidos": int(len(d)),
              "pessoas": int(d["pessoa"].nunique()), "procedimentos": int(d["item"].nunique()),
              "mediana_dias_espera": int(round(e.median())), "mais_de_180_dias": int((e > 180).sum()),
              "mais_de_1_ano": int((e > 365).sum()), "mais_de_2_anos": int((e > 730).sum()),
              "criancas_ate_12": int((d["idade"] <= 12).sum()), "idosos_60_mais": int((d["idade"] >= 60).sum()),
              "sem_idade": int(d["idade"].isna().sum()),
              "idade_planilha_confere_pct": None if confere is None else int(round(confere * 100)),
              "muito_alta_pedidos": ma[0], "muito_alta_mediana_dias": ma[1], "muito_alta_mais_de_1_ano": ma[2],
              "neuro_pediatria_pedidos": npd[0], "neuro_pediatria_pessoas": int(d.loc[eh_np, "pessoa"].nunique()),
              "neuro_pediatria_ate_5_anos": int((eh_np & (d["idade"] <= 5)).sum()),
              "neuro_pediatria_mediana_dias": npd[1],
              "neuro_pediatria_mais_de_1_ano": npd[2], "neuro_adulto_pedidos": nad[0],
              "neuro_adulto_mediana_dias": nad[1], "neuro_adulto_mais_de_1_ano": nad[2]}
    esp = grupo("item").rename(columns={"item": "procedimento"})
    uni = grupo("unidade").rename(columns={"unidade": "unidade_solicitante"})
    cols = ["mes", "pedidos", "mediana_dias_espera", "mais_de_1_ano"]
    return resumo, esp[["mes", "procedimento", *cols[1:]]], uni[["mes", "unidade_solicitante", *cols[1:]]]


# ---------------------------------------------------------------- coleta

def coletar(hoje: date | None = None, s=None) -> None:
    hoje = hoje or date.today()
    s = s or sessao()
    h = NAVEGADOR
    conhecidos = armazem.ler(LINKS)
    try:
        r = s.get(PAGINA, headers=h, timeout=120)
        r.raise_for_status()
        urls = links(r.text)
        if urls:
            novos_links = pd.DataFrame({"url": urls, "visto_em": f"{hoje:%Y-%m-%d}"})
            armazem.gravar(armazem.juntar(conhecidos, novos_links) if not conhecidos.empty else novos_links, LINKS,
                           chave=["url"], ordenar=["url"])
    except Exception as e:  # noqa: BLE001  (403 do site da prefeitura para o GitHub)
        if conhecidos.empty:      # repositório público: os links não ficam no git (docs/DECISOES.md, 24/11/2026)
            log.warning("fila: página fora (%s) e nenhum link guardado; a fila fica no último mês", type(e).__name__)
            qualidade.REGISTRO.add(qualidade.Checagem("fila", "fila_resumo_mensal.csv", "links_da_fila", False, False,
                                                      "página da fila fora para o robô e nenhum link guardado"))
            return
        log.warning("fila: página fora (%s); usando %d links já conhecidos", e, len(conhecidos))
        urls = list(conhecidos["url"])
    if not urls:
        qualidade.REGISTRO.add(qualidade.Checagem("fila", "fila_resumo_mensal.csv", "links_da_fila", False, False,
                                                  "nenhum link de planilha na página da fila"))
        return
    lidos = armazem.ler(ARQUIVOS)
    ja = set(lidos["url"]) if not lidos.empty else set()
    antigo = armazem.ler(RESUMO)
    refazer = hoje.day == 1 or antigo.empty or "pessoas" not in antigo.columns     # conta nova: relê todos os meses
    novos = urls if refazer else [u for u in urls if u not in ja] or urls[:1]       # o mais recente sempre
    resumos, registros = [], []
    for url in novos:
        try:
            arq = s.get(url, headers=h, timeout=300)
            arq.raise_for_status()
        except Exception as e:  # noqa: BLE001  (um mês fora do ar não derruba os outros)
            log.warning("fila: uma planilha falhou (%s)", type(e).__name__)   # sem a URL: o log é público
            continue
        if not arq.content.startswith(b"PK"):          # PDF ou página de aviso do Google: não é planilha
            continue
        sha = hashlib.sha256(arq.content).hexdigest()
        # só o hash, nunca o arquivo; e a fonte é a página oficial, não o link direto da planilha, que traz dados
        # de pacientes (docs/DECISOES.md, 24/11/2026)
        qualidade.registrar_bruto(f"fila_{sha[:12]}.xlsx", sha, len(arq.content), PAGINA)
        mes, df = ler_planilha(arq.content)
        resumo, esp, uni = resumir(df, mes)
        del df, arq
        armazem.gravar(esp, PASTA / f"fila_especialidade_{mes}.csv", chave=["mes", "procedimento"],
                       ordenar=["mes"])
        armazem.gravar(uni, PASTA / f"fila_unidade_{mes}.csv", chave=["mes", "unidade_solicitante"],
                       ordenar=["mes"])
        resumos.append(resumo)
        registros.append({"url": url, "sha256": sha, "mes": mes, "lido_em": f"{hoje:%Y-%m-%d}"})
        log.info("fila %s: %d pedidos, mediana %d dias", mes, resumo["pedidos"], resumo["mediana_dias_espera"])
    if not resumos:
        return
    novo = pd.DataFrame(resumos)
    junto = armazem.juntar(antigo, novo) if not antigo.empty else novo
    junto = junto.drop_duplicates("mes", keep="last")
    if "pessoas" in junto.columns:          # mês ainda não refeito: a idade vinha da coluna embaralhada; apaga
        velho = junto["pessoas"].isna() | (junto["pessoas"].astype(str).isin(["", "nan", "None"]))
        cols = ["criancas_ate_12", "idosos_60_mais"]
        junto[cols] = junto[cols].astype(object)
        junto.loc[velho, cols] = ""
    chs = qualidade.validar_tabela(junto, antigo, fonte="fila", arquivo=RESUMO.name,
                                   obrigatorias={"mes": r"\d{4}-\d{2}", "pedidos": r"\d+"}, coluna_total="pedidos")
    if qualidade.aprovado(chs):
        armazem.gravar(junto, RESUMO, chave=["mes"], ordenar=["mes"])
    reg = pd.DataFrame(registros)
    armazem.gravar(armazem.juntar(lidos, reg) if not lidos.empty else reg, ARQUIVOS, chave=["url"], ordenar=["mes"])


def comparavel() -> dict | None:
    """Crescimento do primeiro ao último mês, no total e só nos procedimentos que aparecem em todos os meses."""
    r = armazem.ler(RESUMO)
    arqs = sorted(PASTA.glob("fila_especialidade_*.csv"))
    if r.empty or len(arqs) < 2:
        return None
    esp = pd.concat([armazem.ler(a) for a in arqs], ignore_index=True)
    esp["pedidos"] = pd.to_numeric(esp["pedidos"], errors="coerce")
    meses = sorted(esp["mes"].unique())
    comuns = set.intersection(*(set(esp.loc[esp["mes"] == m, "procedimento"]) for m in meses))
    soma = esp[esp["procedimento"].isin(comuns)].groupby("mes")["pedidos"].sum()
    tot = r.set_index("mes")["pedidos"].astype(float)
    a, b = meses[0], meses[-1]
    if a not in tot.index or b not in tot.index:
        return None
    return {"de": a, "ate": b, "total_de": int(tot[a]), "total_ate": int(tot[b]),
            "cresc_total": tot[b] / tot[a] - 1, "procedimentos_comuns": len(comuns),
            "comum_de": int(soma[a]), "comum_ate": int(soma[b]), "cresc_comum": soma[b] / soma[a] - 1}


def secao_markdown() -> str:
    r = armazem.ler(RESUMO)
    if r.empty:
        return ""
    r = r.sort_values("mes")
    n = lambda v: f"{int(float(v)):,}".replace(",", ".") if str(v) not in ("", "nan", "None") else "—"  # noqa: E731
    pct = lambda v: f"{v * 100:+.1f}%".replace(".", ",")  # noqa: E731
    tem = lambda c: c in r.columns  # noqa: E731
    linhas = ["## Fila de espera de consultas e exames especializados\n",
              "_Somas do Vigia sobre a planilha mensal da Secretaria de Saúde "
              f"([página oficial]({PAGINA})). Espera = há quanto tempo espera quem ainda está na fila, no último dia "
              "do mês. Um pedido não é uma pessoa: a mesma pessoa pode esperar mais de um procedimento. Idade calculada "
              "pela data de nascimento (a coluna de idade da planilha não confere). A planilha oficial traz nome e data "
              "de nascimento dos pacientes; o Vigia não guarda nada disso e pediu à prefeitura que publique sem esses "
              "dados. O agendamento das especialidades é feito pela Secretaria de Estado da Saúde._\n",
              "| Mês | Pedidos | Pessoas | Metade espera mais de | Mais de 1 ano | Crianças (até 12) | "
              "Idosos (60+) | Neurologia pediátrica (pedidos / mediana) |",
              "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for _, x in r.iterrows():
        linhas.append(f"| {x['mes']} | {n(x['pedidos'])} | {n(x['pessoas']) if tem('pessoas') else '—'} | "
                      f"{n(x['mediana_dias_espera'])} dias | {n(x['mais_de_1_ano'])} | {n(x['criancas_ate_12'])} | "
                      f"{n(x['idosos_60_mais'])} | "
                      f"{n(x['neuro_pediatria_pedidos'])} / {n(x['neuro_pediatria_mediana_dias'])} dias |")
    if c := comparavel():
        linhas += ["", f"**Crescimento de {c['de']} a {c['ate']}:** {n(c['total_de'])} → {n(c['total_ate'])} pedidos "
                   f"({pct(c['cresc_total'])}). Parte disso é procedimento novo na lista; contando só os "
                   f"{c['procedimentos_comuns']} procedimentos que aparecem em todos os meses: {n(c['comum_de'])} → "
                   f"{n(c['comum_ate'])} ({pct(c['cresc_comum'])})."]
    if tem("idade_planilha_confere_pct"):
        ult = r.iloc[-1]
        linhas += ["", f"_Qualidade do dado oficial: em {ult['mes']}, a coluna \"Idade do paciente\" bate com a data "
                   f"de nascimento em {n(ult['idade_planilha_confere_pct'])}% das linhas._"]
    ult = r.iloc[-1]["mes"]
    esp = armazem.ler(PASTA / f"fila_especialidade_{ult}.csv")
    if not esp.empty:
        esp = esp.assign(p=pd.to_numeric(esp["pedidos"])).sort_values("p", ascending=False).head(10)
        linhas += ["", f"**As 10 maiores filas em {ult}**", "",
                   "| Procedimento | Pedidos | Metade espera mais de | Mais de 1 ano |", "|---|---:|---:|---:|"]
        linhas += [f"| {x['procedimento']} | {n(x['pedidos'])} | {n(x['mediana_dias_espera'])} dias | "
                   f"{n(x['mais_de_1_ano'])} |" for _, x in esp.iterrows()]
    return "\n".join(linhas) + "\n"
