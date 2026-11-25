"""Os dados de cada página do site público, montados a partir dos CSVs do robô.

Tudo aqui é fato com fonte oficial. Nada de alerta com nome de empresa (esses ficam no robô até a revisão
jurídica) e nada de dado pessoal. Os números saem em linguagem simples: "7 de cada 10 casas", "quase 8 meses".
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import date, timedelta

import pandas as pd

from .. import pedidos as reg_pedidos
from ..config import DADOS

RAIOX = DADOS / "raiox"
FILA = DADOS / "fila"
EQUIP = DADOS / "equipamentos"
SITE = DADOS / "site"
SONDA = DADOS / "sonda"

# Nomes do Censo escritos de outro jeito no dia a dia (e no Portal da Transparência)
NOME_EXIBICAO = {
    "Campo verde": "Campo Verde", "Presidente Médice": "Presidente Médici", "Bubú": "Bubu",
    "Porto Santana": "Porto de Santana", "Santa Barbara": "Santa Bárbara", "Santa Cecilia": "Santa Cecília",
    "Itaciba": "Itacibá",
}
# Bairro como aparece no CNES ou no mapa do Estado -> bairro do Censo (depois de tirar acento e maiúsculas)
APELIDOS = {
    "NOVA ROSA DA PENHA I": "NOVA ROSA DA PENHA", "NOVA ROSA DA PENHA II": "NOVA ROSA DA PENHA",
    "SAO GERALDO I": "SAO GERALDO", "PORTO DE SANTANA": "PORTO SANTANA", "ALTO BOA VISTA": "ALTO DA BOA VISTA",
    "PRESIDENTE MEDICI": "PRESIDENTE MEDICE", "SANTA FE": "MORADA DE SANTA FE", "JARDIM BOTANICO": "JARDIM BOTANICO",
    "FLEXAL 1": "FLEXAL I", "FLEXAL 2": "FLEXAL II", "BAIRRO OPERARIO": "OPERARIO",
}
MIN_DOMICILIOS_RANKING = 100   # bairro muito pequeno não entra em "um dos 10" (o número oscila demais)


def normalizar(txt: str) -> str:
    t = unicodedata.normalize("NFKD", str(txt)).encode("ascii", "ignore").decode().upper()
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", " ", t)).strip()


def slug(txt: str) -> str:
    return normalizar(txt).lower().replace(" ", "-")


def br(n: float, casas: int = 0) -> str:
    s = f"{n:,.{casas}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def reais(v: float) -> str:
    return "R$ " + br(v)


def de_cada(pct: float, base: int = 10) -> str:
    """71,7% -> '7 de cada 10'. Nas pontas, palavras: 'todas', 'quase todas', 'quase nenhuma'."""
    # "todas" e "nenhuma" só quando o número é exato (100,0% e 0,0%): 99,7% é "quase todas" (24/11/2026)
    if pct >= 99.95:
        return "todas"
    if pct >= 95:
        return "quase todas"
    if pct < 0.05:
        return "nenhuma"
    if pct < 100 / base / 2:
        return "quase nenhuma"
    return f"{max(1, round(pct * base / 100))} de cada {base}"


def casas(pct: float, resto: str) -> tuple[str, str]:
    """(número, frase): '7 de cada 10' + 'casas têm…', 'Quase todas' + 'as casas têm…' ou, no singular,
    'Nenhuma' + 'casa tem…' (antes saía "Nenhuma as casas têm", 24/11/2026)."""
    n = de_cada(pct)
    if "nenhuma" in n:
        return n.capitalize(), "casa " + resto.replace("têm ", "tem ", 1)
    return n.capitalize(), ("casas " if "de cada" in n else "as casas ") + resto


def parte_ano(n: int, total: int, onde: str = "") -> str:
    """Quantos pedidos esperam há mais de 1 ano, em palavras (fila). Poucos casos vão com o número ("Só 5 pedidos
    deste posto esperam há mais de 1 ano."), e 45% a 50% é "quase metade", nunca "5 de cada 10" (24/11/2026)."""
    pct = 100 * n / total if total else 0
    if n == 0:
        return f"Nenhum pedido{onde} espera há mais de 1 ano."
    if n < 10 or pct < 5:
        return f"Só {br(n)} {'pedido' if n == 1 else 'pedidos'}{onde} {'espera' if n == 1 else 'esperam'} há mais de 1 ano."
    if 45 <= pct < 50:
        return f"Quase metade dos pedidos{onde}."
    if pct >= 99.95:
        return f"Todos os pedidos{onde}."
    if pct >= 95:
        return f"Quase todos os pedidos{onde}."
    return f"São {de_cada(pct)} pedidos{onde}."


def meses(dias: int) -> str:
    m = dias / 30.44
    f = int(m)
    if m - f >= 0.5:
        c = f + 1
        return "quase 1 ano" if c == 12 else ("quase 2 anos" if c == 24 else f"quase {c} meses")
    if f >= 12:
        return "mais de 1 ano"
    return "cerca de 1 mês" if f <= 1 else f"mais de {f} meses"


def falado(n: int) -> str:
    """40.829 -> 'quase 41 mil'; 2.569 -> 'quase 2.600'; 987 -> '987'."""
    if n >= 10_000:
        mil = n / 1000
        return f"quase {br(-(-mil // 1))} mil" if mil % 1 >= 0.5 else f"mais de {br(int(mil))} mil"
    if n >= 1_000:
        c = n / 100
        return f"quase {br(-(-c // 1) * 100)}" if c % 1 >= 0.5 else f"mais de {br(int(c) * 100)}"
    return br(n)


def reais_cheio(v: float) -> str:
    """O valor com todos os zeros, para o tamanho pesar: 76413310.65 -> 'R$ 76.413.311'."""
    return f"R$ {br(round(v))}"


def extenso(v: float) -> str:
    """Como se lê o valor cheio, para quem não lê número grande: 1663887316 -> '1 bilhão e 664 milhões de reais';
    76413310 -> '76 milhões e 413 mil reais'; 297000 -> '297 mil reais'."""
    v = round(v)
    if v >= 1_000_000_000:
        b, m = divmod(v, 1_000_000_000)
        m = round(m / 1_000_000)
        if m == 1000:
            b, m = b + 1, 0
        cab = f"{br(b)} {'bilhão' if b == 1 else 'bilhões'}"
        return f"{cab} e {br(m)} {'milhão' if m == 1 else 'milhões'} de reais" if m else f"{cab} de reais"
    if v >= 1_000_000:
        m, k = divmod(v, 1_000_000)
        k = round(k / 1000)
        if k == 1000:
            m, k = m + 1, 0
        cab = f"{br(m)} {'milhão' if m == 1 else 'milhões'}"
        return f"{cab} e {br(k)} mil reais" if k else f"{cab} de reais"
    if v >= 1000:
        return f"{br(round(v / 1000))} mil reais"
    return f"{br(v)} reais"


def posicao(valor: float, todos: list[float]) -> int:
    """1 = o maior número entre os bairros (mesma regra em toda a tabela, para ninguém se confundir)."""
    return 1 + sum(1 for x in todos if x > valor)


# ---------------------------------------------------------------- bairros (Censo 2022)

GRUPO_RENDA = 20   # "os bairros de menor/maior renda": os 20 das pontas, mais os empatados no corte


def _grupos_renda(d: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Os bairros de menor e de maior renda (só os de 100 casas ou mais). Empate no corte entra inteiro: 29 bairros
    têm a mesma renda, R$ 1.212, e cortar em 20 deixava 9 de fora só pela ordem alfabética (24/11/2026)."""
    g = d[d["domicilios"] >= MIN_DOMICILIOS_RANKING].dropna(subset=["renda_mediana"]).sort_values("renda_mediana")
    if g.empty:
        return g, g
    corte_baixo = g["renda_mediana"].iloc[min(GRUPO_RENDA, len(g)) - 1]
    corte_alto = g["renda_mediana"].iloc[-min(GRUPO_RENDA, len(g))]
    return g[g["renda_mediana"] <= corte_baixo], g[g["renda_mediana"] >= corte_alto]


def bairros() -> list[dict]:
    b = pd.read_csv(RAIOX / "bairros-cariacica.csv")
    b = b[~b["bairro"].str.startswith("Área Não Identificada")].copy()
    b["nome"] = b["bairro"].map(lambda x: NOME_EXIBICAO.get(x, x))
    b["slug"] = b["nome"].map(slug)
    b["chave"] = b["bairro"].map(normalizar)
    # casas sem rede: a conta exata do IBGE (domicílios permanentes menos os ligados à rede); a conta antiga, pela
    # porcentagem arredondada, errava em até algumas dezenas de casas (24/11/2026)
    aprox = (b["domicilios"] * (1 - b["pct_esgoto_rede"] / 100)).round()
    if "domicilios_sem_rede" in b:
        b["sem_rede"] = b["domicilios_sem_rede"].fillna(aprox).astype(int)
    else:
        b["sem_rede"] = aprox.astype(int)
    b["pct_nao_le"] = 100 - b["pct_alfabetizados_15mais"]
    grandes = b[b["domicilios"] >= MIN_DOMICILIOS_RANKING]
    pior_esgoto = set(grandes.nsmallest(10, "pct_esgoto_rede")["slug"])
    pior_leitura = set(grandes.nlargest(10, "pct_nao_le")["slug"])
    renda_baixa = set(_grupos_renda(b)[0]["slug"])
    out = []
    for r in b.sort_values("nome", key=lambda s: s.map(normalizar)).to_dict("records"):
        r["pior_esgoto"] = r["slug"] in pior_esgoto
        r["pior_leitura"] = r["slug"] in pior_leitura
        r["renda_baixa"] = r["slug"] in renda_baixa
        r["pequeno"] = r["domicilios"] < MIN_DOMICILIOS_RANKING
        out.append(r)
    return out


def _soma_bairros(bs: list[dict]) -> dict:
    """Plano B, se faltar o arquivo do município: a soma dos bairros (fica de fora a zona rural)."""
    d = pd.DataFrame(bs)
    w = d["domicilios"]
    pop15 = (d["pessoas_15mais"] if "pessoas_15mais" in d
             else d["pessoas_15mais_nao_alfabetizadas"] / (1 - d["pct_alfabetizados_15mais"] / 100))
    return {"populacao": int(d["populacao"].sum()), "domicilios": int(w.sum()), "area_km2": float(d["area_km2"].sum()),
            "pct_esgoto_rede": float((d["pct_esgoto_rede"] * w).sum() / w.sum()),
            "pct_agua_rede": float((d["pct_agua_rede"] * w).sum() / w.sum()),
            "pct_lixo_coletado": float((d["pct_lixo_coletado"] * w).sum() / w.sum()),
            "nao_le": int(d["pessoas_15mais_nao_alfabetizadas"].sum()), "pessoas_15mais": float(pop15.sum()),
            "sem_rede": int(d["sem_rede"].sum()), "rotulo": f"Soma dos {len(d)} bairros"}


def cidade(bs: list[dict]) -> dict:
    """Cariacica inteira, pelo agregado do IBGE por município (data/raiox/cariacica-municipio.csv). A soma dos 99
    bairros deixava de fora 4.387 moradores e a zona rural, e a densidade saía 3.106 em vez de 1.264 (24/11/2026)."""
    f = RAIOX / "cariacica-municipio.csv"
    if f.exists():
        m = pd.read_csv(f).iloc[0]
        c = {"populacao": int(m["populacao"]), "domicilios": int(m["domicilios"]), "area_km2": float(m["area_km2"]),
             "pct_esgoto_rede": float(m["pct_esgoto_rede"]), "pct_agua_rede": float(m["pct_agua_rede"]),
             "pct_lixo_coletado": float(m["pct_lixo_coletado"]),
             "nao_le": int(m["pessoas_15mais_nao_alfabetizadas"]), "pessoas_15mais": float(m["pessoas_15mais"]),
             "sem_rede": int(m["domicilios_sem_rede"]), "rotulo": "Cariacica"}
    else:
        c = _soma_bairros(bs)
    c["pct_nao_le"] = 100 * c["nao_le"] / c["pessoas_15mais"]
    c["densidade"] = c["populacao"] / c["area_km2"]
    baixa = [b for b in bs if b.get("renda_baixa")]
    c["n_renda_baixa"] = len(baixa)
    c["renda_baixa_ate"] = max((b["renda_mediana"] for b in baixa), default=0)
    return c


def padroes(bs: list[dict]) -> dict:
    """O padrão da cidade em uma frase: onde a renda é menor, falta mais esgoto."""
    d = pd.DataFrame(bs)
    def esg(x):
        return float((x["pct_esgoto_rede"] * x["domicilios"]).sum() / x["domicilios"].sum())
    baixa, alta = _grupos_renda(d)
    d = d[d["domicilios"] >= MIN_DOMICILIOS_RANKING]
    return {"esgoto_renda_baixa": esg(baixa), "esgoto_renda_alta": esg(alta),
            "n_renda_baixa": len(baixa), "n_renda_alta": len(alta),
            "renda_baixa_ate": float(baixa["renda_mediana"].max()), "renda_alta_desde": float(alta["renda_mediana"].min()),
            "piores_esgoto": [dict(x, com_rede=" ".join(casas(x["pct_esgoto_rede"], "com rede")))
                              for x in d.nsmallest(10, "pct_esgoto_rede")[["nome", "slug", "pct_esgoto_rede", "sem_rede"]]
                              .to_dict("records")]}


def cartoes_bairro(b: dict, c: dict) -> list[dict]:
    """Os padrões do bairro, um por cartão, sempre comparados com Cariacica."""
    cards = []
    esg = b["pct_esgoto_rede"]
    num, frase = casas(esg, "têm esgoto ligado na rede.")
    cards.append({
        "tema": "Esgoto", "pergunta": "O esgoto das casas vai para a rede?",
        "numero": num, "frase": frase,
        "cidade": f"Em Cariacica: {de_cada(c['pct_esgoto_rede'])}.",
        "extra": (f"No Censo, {br(b['sem_rede'])} casas ainda não estavam ligadas à rede." if b["sem_rede"] >= 5 else ""),
        "selo": "Um dos 10 bairros com menos esgoto na rede" if b["pior_esgoto"] else "",
        "valor": esg, "ref": c["pct_esgoto_rede"], "bom": esg >= c["pct_esgoto_rede"],
        "grafico": "dez", "g_aqui": esg, "g_cid": c["pct_esgoto_rede"],
        "g_txt_aqui": de_cada(esg), "g_txt_cid": de_cada(c["pct_esgoto_rede"]),
        "exato": f"{br(esg, 1)}% das casas", "ref_exato": f"{br(c['pct_esgoto_rede'], 1)}%",
    })
    nl = b["pct_nao_le"]
    n_pessoas = int(b["pessoas_15mais_nao_alfabetizadas"])
    p15 = b.get("pessoas_15mais")
    leitura = {
        "tema": "Ler e escrever", "pergunta": "Quantos vizinhos não sabem ler?",
        "numero": (f"{max(1, round(nl))} de cada 100" if nl >= 0.5 else "Menos de 1 de cada 100"),
        "frase": "pessoas com 15 anos ou mais não sabem ler e escrever.",
        "cidade": f"Em Cariacica: {round(c['pct_nao_le'])} de cada 100.",
        "extra": f"São {br(n_pessoas)} pessoas no bairro." if n_pessoas >= 5 else "",
        "selo": "Um dos 10 bairros com mais gente sem saber ler" if b["pior_leitura"] else "",
        "valor": None, "ref": None, "bom": nl <= c["pct_nao_le"],
        "grafico": "cem", "g_aqui": nl, "g_cid": c["pct_nao_le"],
        "exato": f"{br(nl, 1)}% não alfabetizados", "ref_exato": f"{br(c['pct_nao_le'], 1)}%",
    }
    if b["pequeno"] and p15 is not None and p15 == p15:
        # bairro com menos de 100 casas: "de cada 100" com 3 pessoas engana; vai o número de pessoas (24/11/2026)
        p15, um = int(p15), int(p15) == 1
        base = (f"No Censo, só {br(p15)} {'pessoa' if um else 'pessoas'} de 15 anos ou mais "
                f"{'foi contada' if um else 'foram contadas'} aqui")
        if n_pessoas == 0:
            fim = "Ela sabe ler e escrever." if um else "Todas sabem ler e escrever."
        elif n_pessoas == p15:
            fim = "Ela não sabe ler e escrever." if um else f"As {br(p15)} não sabem ler e escrever."
        else:
            fim = f"Delas, {br(n_pessoas)} não {'sabe' if n_pessoas == 1 else 'sabem'} ler e escrever."
        leitura.update(numero=f"{br(n_pessoas)} de {br(p15)}", grafico="", extra="", frase=f"{base}. {fim}")
    cards.append(leitura)
    renda_cid = ""
    if b["renda_baixa"]:
        renda_cid = (f"Está entre os {c['n_renda_baixa']} bairros onde metade ganha até 1 salário mínimo (R$ 1.212)."
                     if abs(c["renda_baixa_ate"] - 1212) < 1 else
                     f"Está entre os {c['n_renda_baixa']} bairros de menor renda de Cariacica.")
    cards.append({
        "tema": "Renda", "pergunta": "Quanto ganha quem sustenta a casa?",
        # a mediana do IBGE (V06006) só conta quem tem renda (24/11/2026)
        "numero": reais(b["renda_mediana"]),
        "frase": "por mês: metade dos responsáveis pela casa que têm renda ganha até esse valor.",
        "cidade": renda_cid,
        "extra": "Era o valor do salário mínimo em 2022, ano do Censo." if abs(b["renda_mediana"] - 1212) < 1 else "",
        "selo": "", "valor": None, "ref": None, "bom": None,
        "exato": f"mediana {reais(b['renda_mediana'])}", "ref_exato": "",
    })
    agua, lixo = b["pct_agua_rede"], b["pct_lixo_coletado"]
    if agua >= 95 and lixo >= 95:
        cards.append({"tema": "Água e lixo", "pergunta": "Tem água da rede e coleta de lixo?",
                      "numero": "Quase todas" if min(agua, lixo) < 99.95 else "Todas",
                      "frase": "as casas têm água da rede e lixo recolhido.", "cidade": "",
                      "extra": "", "selo": "", "valor": None, "ref": None, "bom": True, "certo": True,
                      "exato": f"água {br(agua, 1)}% · lixo {br(lixo, 1)}%", "ref_exato": ""})
    else:
        for tema, pct, ref, resto in (("Água", agua, c["pct_agua_rede"], "têm água da rede."),
                                      ("Lixo", lixo, c["pct_lixo_coletado"], "têm o lixo recolhido.")):
            num, frase = casas(pct, resto)
            cards.append({"tema": tema, "pergunta": "Tem água da rede?" if tema == "Água" else "O lixo é recolhido?",
                          "numero": num, "frase": frase,
                          "cidade": f"Em Cariacica: {de_cada(ref)}.", "extra": "", "selo": "",
                          "valor": pct, "ref": ref, "bom": pct >= ref,
                          "grafico": "dez", "g_aqui": pct, "g_cid": ref,
                          "g_txt_aqui": de_cada(pct), "g_txt_cid": de_cada(ref),
                          "exato": f"{br(pct, 1)}%", "ref_exato": f"{br(ref, 1)}%"})
    return cards


# ---------------------------------------------------------------- fila da saúde

def fila() -> dict:
    arquivos = sorted(FILA.glob("fila_unidade_*.csv"))
    ult = arquivos[-1]
    mes = ult.stem.rsplit("_", 1)[-1]
    u = pd.read_csv(ult)
    nomes = pd.read_csv(FILA / "unidades.csv")
    u = u.merge(nomes, on="unidade_solicitante", how="left")
    resumo = pd.read_csv(FILA / "fila_resumo_mensal.csv")
    r = resumo[resumo["mes"] == mes].iloc[0]
    unidades = []
    for x in u.to_dict("records"):
        if not isinstance(x.get("slug"), str):
            continue
        unidades.append({"slug": x["slug"], "nome": x["nome"], "tipo": x.get("tipo", ""),
                         "origem": x["unidade_solicitante"], "pedidos": int(x["pedidos"]),
                         "mediana": int(x["mediana_dias_espera"]), "ano": int(x["mais_de_1_ano"])})
    unidades.sort(key=lambda x: -x["pedidos"])
    ano, m = mes.split("-")
    nomes_mes = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro",
                 "outubro", "novembro", "dezembro"]
    return {"mes": mes, "mes_texto": f"{nomes_mes[int(m) - 1]} de {ano}", "data_ref": r["data_referencia"],
            "pedidos": int(r["pedidos"]), "mediana": int(r["mediana_dias_espera"]), "ano": int(r["mais_de_1_ano"]),
            "pessoas": int(r["pessoas"]) if str(r.get("pessoas", "")).isdigit() else None,
            "unidades": unidades}


def _equip_saude() -> pd.DataFrame:
    """Postos com bairro: cadastro do Ministério da Saúde (CNES, coletor equipamentos) somado ao mapa de saúde do
    Governo do ES (amostra da sonda), que traz alguns postos que a primeira página do CNES não trouxe."""
    partes = []
    f = EQUIP / "saude.csv"
    if f.exists():
        partes.append(pd.read_csv(f, dtype=str, keep_default_na=False)[["cnes", "nome", "bairro"]])
    s = SONDA / "es_georref_saude.csv"
    if s.exists():
        d = pd.read_csv(s, sep=";", dtype=str, keep_default_na=False, encoding="utf-8-sig", on_bad_lines="skip")
        d = d[d["MUNICIPIO"].str.lower() == "cariacica"]
        if "CNES" not in d:
            d = d.assign(CNES="")
        partes.append(d.rename(columns={"NOME": "nome", "BAIRRO": "bairro", "CNES": "cnes"})[["cnes", "nome", "bairro"]])
    if not partes:
        return pd.DataFrame(columns=["cnes", "nome", "bairro"])
    return pd.concat(partes, ignore_index=True).drop_duplicates("nome")


def chave_bairro(nome_bairro: str, chaves: set[str]) -> str | None:
    k = normalizar(nome_bairro)
    k = APELIDOS.get(k, k)
    return k if k in chaves else None


PALAVRAS_VAZIAS = {"US", "USF", "UBS", "DE", "DA", "DO", "DOS", "DAS", "E", "CENTRO", "SAUDE", "UNIDADE", "BASICA"}


def _tokens(nome: str) -> set[str]:
    return {t for t in normalizar(nome).split() if t not in PALAVRAS_VAZIAS and len(t) > 1}


def _achar_cadastro(origem: str, eq: pd.DataFrame) -> dict | None:
    """O cadastro do posto da planilha: nome igual; se não houver, o cadastro cujas palavras estão todas no nome da
    planilha ("US DE ITAPEMIRIM" = "US ITAPEMIRIM"; "US JARDIM AMERICA CENTRO DE SAUDE JARDIM AMERICA" =
    "US JARDIM AMERICA"). Só aceita quando um cadastro só combina."""
    alvo = normalizar(origem)
    iguais = eq[eq["nome"].map(normalizar) == alvo]
    if len(iguais):
        return iguais.iloc[0].to_dict()
    t = _tokens(origem)
    cands = [r for r in eq.to_dict("records") if _tokens(r["nome"]) and _tokens(r["nome"]) <= t]
    return cands[0] if len({c["bairro"] for c in cands}) == 1 and cands else None


def _achar_posto(origem: str, eq: pd.DataFrame) -> str | None:
    """Bairro do posto da planilha (veja _achar_cadastro)."""
    c = _achar_cadastro(origem, eq)
    return c["bairro"] if c else None


# posto do bairro = unidade básica (US, USF, UBS); presídio, vigilância, saúde bucal e policlínica ficam de fora
_BASICA = re.compile(r"^(US|USF|UBS|UNIDADE BASICA)\b")
_MINUSCULAS = {"DE", "DA", "DO", "DOS", "DAS", "E"}


def _nome_posto(nome: str, nomes_bairro: list[str]) -> str:
    """'US ITACIBA' -> 'US Itacibá': letra normal, com o nome do bairro escrito como no site."""
    toks = normalizar(nome).split()
    alvos = sorted(((normalizar(n).split(), n.split()) for n in nomes_bairro), key=lambda x: -len(x[0]))
    out, i = [], 0
    while i < len(toks):
        for nt, disp in alvos:
            if i > 0 and nt and toks[i:i + len(nt)] == nt:
                out += disp
                i += len(nt)
                break
        else:
            t = toks[i]
            out.append(t if (i == 0 and t in ("US", "USF", "UBS")) or re.fullmatch(r"[IVX]+", t)
                       else t.lower() if t in _MINUSCULAS else t.capitalize())
            i += 1
    return " ".join(out)


def _lugar(nome: str) -> set[str]:
    """As palavras de lugar no nome de um posto ('US Mucuri (Alice Coutinho Santos)' -> {'MUCURI'})."""
    return {t for t in normalizar(re.sub(r"\(.*?\)", "", nome)).split() if t not in PALAVRAS_VAZIAS}


def postos_por_bairro(bs: list[dict], fl: dict) -> dict[str, list[dict]]:
    """bairro (slug) -> postos de saúde (unidades básicas) que ficam nele, pelo cadastro do Ministério da Saúde (CNES)
    e pelo mapa do Governo do ES. A fila só diz quanto se espera: posto que não aparece na planilha continua sendo o
    posto do bairro (antes, Itacibá, Campo Grande e Alto da Boa Vista diziam "não achamos um posto", 24/11/2026).
    Cada posto: nome, cnes, fila (a unidade da planilha, ou None) e o bairro. A unidade da fila ganha bairro_slug."""
    chave_para_slug = {b["chave"]: b["slug"] for b in bs}
    nome_de = {b["slug"]: b["nome"] for b in bs}
    eq = _equip_saude()
    basicas = eq[eq["nome"].map(lambda n: bool(_BASICA.match(normalizar(n))))]
    # o mesmo posto com dois nomes (o mapa do ES e o CNES): fica um por código CNES
    basicas = basicas[(basicas["cnes"] == "") | ~basicas["cnes"].duplicated()]
    fila_de: dict[str, dict] = {}
    for u in fl["unidades"]:
        if u.get("tipo") != "ubs":     # CAPS, IST/Aids e a própria Secretaria atendem a cidade toda
            continue
        cad = _achar_cadastro(u["origem"], eq)
        if not cad:
            continue
        k = chave_bairro(cad["bairro"], set(chave_para_slug))
        if k:
            u["bairro_slug"] = chave_para_slug[k]
        fila_de[cad.get("cnes") or normalizar(cad["nome"])] = u
    out: dict[str, list[dict]] = {}
    for r in basicas.to_dict("records"):
        k = chave_bairro(r["bairro"], set(chave_para_slug))
        if not k:
            continue
        s = chave_para_slug[k]
        u = fila_de.get(r["cnes"] or normalizar(r["nome"]))
        out.setdefault(s, []).append({"nome": u["nome"] if u else _nome_posto(r["nome"], list(nome_de.values())),
                                      "cnes": r["cnes"], "fila": u, "bairro_slug": s, "bairro_nome": nome_de[s]})
    for ps in out.values():
        ps.sort(key=lambda p: (p["fila"] is None, normalizar(p["nome"])))
    return out


def postos_com_nome_do_bairro(bs: list[dict], postos: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """Bairro sem posto, mas com um posto que leva o nome dele em outro bairro: "A US Rio Marinho, que tem o nome do
    bairro, fica em Castelo Branco." (Rio Marinho, Itapemirim e Mucuri, 24/11/2026)."""
    todos = [p for ps in postos.values() for p in ps]
    out: dict[str, list[dict]] = {}
    for b in bs:
        if b["slug"] in postos:
            continue
        alvo = _lugar(b["nome"])
        achados = [p for p in todos if alvo and _lugar(p["nome"]) == alvo]
        if achados:
            out[b["slug"]] = achados
    return out


def escolas_por_bairro(bs: list[dict]) -> dict[str, list[dict]]:
    f = EQUIP / "escolas.csv"
    if not f.exists():
        return {}
    e = pd.read_csv(f, dtype=str, keep_default_na=False)
    ideb = pd.read_csv(RAIOX / "ideb-escolas-cariacica.csv", dtype=str, keep_default_na=False)
    ideb = ideb.rename(columns={"id_escola": "inep"})
    chave_para_slug = {b["chave"]: b["slug"] for b in bs}
    # acentos: o mapa do ES escreve com acento ("Teotônio"), o INEP não ("TEOTONIO")
    acento = {normalizar(w): w for n in e["nome"] for w in n.split() if normalizar(w) and not w.isupper()}
    out: dict[str, list[dict]] = {}
    for x in e.to_dict("records"):
        k = chave_bairro(x["bairro"], set(chave_para_slug))
        if not k:
            continue
        notas = ideb[ideb["inep"] == x["inep"]]
        x["ideb"] = [{"etapa": n["etapa"], "nota": n["ideb_2025"] or n["ideb_2023"],
                      "ano": "2025" if n["ideb_2025"] else "2023"} for n in notas.to_dict("records")
                     if n["ideb_2025"] or n["ideb_2023"]]
        if len(notas):
            # escola com nota: nome e rede do INEP, que é de onde vem a nota. O mapa do ES está desatualizado em 17
            # escolas (EMEF como estadual) e, em Jardim América, põe o código da EMEFTI Professor Cerqueira Lima na
            # EEEF Pautila Rodrigues Xavier (24/11/2026)
            n0 = notas.iloc[0]
            x["nome"] = _nome_escola(n0["escola"], acento)
            x["rede"] = n0["rede"]
        out.setdefault(chave_para_slug[k], []).append(x)
    for s, xs in out.items():
        # o mapa às vezes repete a escola com o código antigo: some a cópia sem nota que tem o mesmo nome
        com_nota = {_nucleo_escola(x["nome"]) for x in xs if x["ideb"]}
        out[s] = [x for x in xs if x["ideb"] or _nucleo_escola(x["nome"]) not in com_nota]
    return out


SIGLAS_ESCOLA = {"EMEF", "EMEFTI", "EEEF", "EEEFM", "CEEFTI", "CMEI", "EEEM", "EMEB", "CEEMTI", "EEEFTI"}


def _nucleo_escola(nome: str) -> str:
    return " ".join(t for t in normalizar(nome).split() if t not in SIGLAS_ESCOLA)


def _nome_escola(nome: str, acento: dict[str, str]) -> str:
    """'EMEF TEOTONIO BRANDAO VILELA' -> 'EMEF Teotônio Brandão Vilela'."""
    out = []
    for i, t in enumerate(nome.split()):
        n = normalizar(t)
        if n in SIGLAS_ESCOLA or (i == 0 and t.isupper() and not acento.get(n)):
            out.append(t)
        elif n in _MINUSCULAS and i:
            out.append(t.lower())
        else:
            out.append(acento.get(n) or t.capitalize())
    return " ".join(out)


def ideb_cidade() -> dict[str, dict[str, str]]:
    """Nota do MEC de Cariacica (escolas públicas) por etapa e ano: {'Anos finais (6º–9º)': {'2023': '4.7', ...}}.
    A escola é comparada com a cidade no mesmo ano (24/11/2026)."""
    d = pd.read_csv(RAIOX / "ideb-cidades.csv", dtype=str, keep_default_na=False)
    d = d[d["cidade"] == "Cariacica"]
    return {r["etapa"]: {"2023": r["ideb_2023"], "2025": r["ideb_2025"]} for r in d.to_dict("records")}


# ---------------------------------------------------------------- perguntas (Lei de Acesso)

def perguntas(hoje: date) -> dict:
    """Perguntas da Lei de Acesso. O resultado que vale é o do Vigia (respondido, parcial, negado), nunca a
    etiqueta do e-SIC: resposta incompleta aparece como "respondida em parte"."""
    p = reg_pedidos.situacao(pd.read_csv(reg_pedidos.ARQUIVO, dtype=str, keep_default_na=False), hoje)
    if "resultado" not in p.columns:
        p["resultado"] = ""
    p["res"] = [estado_vigia(e, r) for e, r in zip(p["estado"], p["resultado"])]
    pub = pd.read_csv(DADOS / "pedidos" / "perguntas_publicas.csv", dtype=str, keep_default_na=False)
    pub = dict(zip(pub["protocolo"], zip(pub["para"], pub["pergunta"])))
    itens = {}
    for r in p.to_dict("records"):
        para, perg = pub.get(r["protocolo"], (r.get("orgao") or "Prefeitura", ""))
        if not perg:   # pergunta sem texto público revisado: nunca mostrar o assunto interno
            perg = f"Pergunta à {para or 'prefeitura'} (texto em revisão)"
        chave = (r["prazo"], perg)
        it = itens.setdefault(chave, {"prazo": r["prazo"], "enviado": r["enviado_em"], "para": para or "Prefeitura",
                                      "pergunta": perg, "numeros": [], "estados": [],
                                      "respondido_em": r.get("respondido_em", ""), "recurso": ""})
        # "parcial (recurso em 2ª instância desde 24/11)": a página diz "Recurso desde 24/11." (só texto; o prazo
        # continua o do registro)
        if m := re.search(r"recurso[^)]*?desde (\d{2}/\d{2})", r.get("resultado") or ""):
            it["recurso"] = m.group(1)
        it["numeros"].append(r["protocolo"])
        it["estados"].append(r["res"])
    for it in itens.values():
        it["estado"] = estado_do_cartao(it["estados"])
        it["n"] = len(it["numeros"])
    lista = sorted(itens.values(), key=lambda x: (x["prazo"], x["enviado"]))
    # conta perguntas (cartões), não protocolos: a mesma pergunta mandada a dois órgãos é uma pergunta só
    conta = lambda e: sum(1 for it in lista if it["estado"] == e)
    grupos: dict[date, list] = {}
    for it in lista:
        grupos.setdefault(it["prazo"], []).append(it)
    esperando = [it for it in lista if "no prazo" in it["estados"]]
    prox = min((it["prazo"] for it in esperando), default=None)
    por_destino = {"prefeitura": 0, "camara": 0, "estado": 0}
    for it in lista:
        por_destino[destino(it["para"])] += 1
    return {"total": len(lista), "pedidos": len(p), "por_destino": por_destino,
            "destinos": destinos_texto(por_destino),
            "respondidas": conta("respondido"), "parciais": conta("parcial"),
            "negadas": conta("negado"), "atrasadas": conta("vencido"), "esperando": conta("no prazo"),
            "respondidos": [it for it in lista if it["estado"] in ("respondido", "parcial", "negado")],
            "grupos": grupos, "proximo": prox,
            "n_proximo": sum(1 for it in esperando if it["prazo"] == prox)}


def destino(para: str) -> str:
    """A quem foi a pergunta: Câmara, Governo do ES (governo do Estado e Cesan) ou prefeitura (o resto)."""
    p = normalizar(para)
    if p.startswith("CAMARA"):
        return "camara"
    if "ESTADO" in p or p.startswith("CESAN"):
        return "estado"
    return "prefeitura"


def destinos_texto(por_destino: dict[str, int]) -> str:
    """'à prefeitura, à Câmara e ao Governo do ES' (só quem recebeu pergunta). Antes o início dizia só "à
    prefeitura", com 7 perguntas à Câmara e ao Governo do ES no meio (24/11/2026)."""
    nomes = [t for k, t in (("prefeitura", "à prefeitura"), ("camara", "à Câmara"), ("estado", "ao Governo do ES"))
             if por_destino.get(k)]
    return " e ".join([", ".join(nomes[:-1]), nomes[-1]]) if len(nomes) > 1 else (nomes[0] if nomes else "")


def estado_vigia(estado: str, resultado: str) -> str:
    """Situação de um pedido pelo critério do Vigia: só é "respondido" quando a resposta é completa."""
    if estado != "respondido":
        return estado                      # "no prazo" ou "vencido"
    r = (resultado or "").strip().lower()
    if r.startswith("parcial"):
        return "parcial"
    if r.startswith("negad"):
        return "negado"
    return "respondido" if r in ("respondido", "completo", "completa", "") else "parcial"


def estado_do_cartao(estados: list[str]) -> str:
    """Um cartão pode juntar mais de um número (a mesma pergunta a dois órgãos)."""
    if all(e == "respondido" for e in estados):
        return "respondido"
    if "vencido" in estados:
        return "vencido"
    if any(e in ("parcial", "respondido", "negado") for e in estados):
        return "negado" if all(e == "negado" for e in estados) else "parcial"
    return "no prazo"


def pergunta_por_numero(numero: str, hoje: date) -> dict | None:
    for grupo in perguntas(hoje)["grupos"].values():
        for it in grupo:
            if numero in it["numeros"]:
                return it
    return None


# ---------------------------------------------------------------- obras (Portal da Transparência)

TRANSP = DADOS / "transparencia"
PORTAL_OBRAS = "https://transparencia.cariacica.es.gov.br/"
# O que o sistema de obras da prefeitura diz, em palavras simples. "estado" decide o selo.
SITUACAO_OBRA = {
    "Concluída e Recebida Definitivamente": ("Pronta e entregue", "pronta"),
    "Concluída e Recebida Provisóriamente": ("Pronta, falta a vistoria final", "pronta"),
    "Em Execução": ("Em andamento", "andamento"),
    "Reiniciada": ("Recomeçou", "andamento"),
    "Paralisada por rescisão contratual": ("Parada: o contrato foi cancelado", "parada"),
}
# nome no sistema de obras -> bairro do Censo (depois de normalizar), quando a escrita muda
APELIDOS_OBRAS = {"FLOR DE PIRANEMA": "PIRANEMA"}


def _valor(x) -> float:
    try:
        return float(str(x).replace(",", "."))
    except ValueError:
        return 0.0


def _caixa(t: str) -> str:
    """Nome todo em maiúsculas vira letra normal; o resto fica como a prefeitura escreveu."""
    letras = [c for c in t if c.isalpha()]
    if letras and sum(c.isupper() for c in letras) / len(letras) > 0.8:
        t = t.lower()
        t = t[0].upper() + t[1:]
        t = re.sub(r"cariacica", "Cariacica", t)
        t = re.sub(r"/es\b", "/ES", t)
    return t


def _ano_contrato(numero: str, vig: list[str], exercicio: str) -> str:
    """Ano do contrato: o do número (069/2019 -> 2019); sem número, o início da vigência; senão, o ano do
    sistema. O portal lista obra antiga em exercício novo (o recapeamento 069/2019 aparece em 2022)."""
    m = re.search(r"/(\d{4})\b", numero or "")
    if m:
        return m.group(1)
    return vig[0][6:] if vig else exercicio


def _chave_obra(nome: str) -> str:
    k = normalizar(nome)
    return APELIDOS_OBRAS.get(k, APELIDOS.get(k, k))


def bairros_no_nome(nome: str, chaves: dict[str, str]) -> list[str]:
    """Bairros do Censo que o NOME da obra cita depois da palavra "bairro(s)": "...nos bairros Roda D'água, Nova
    Campo Grande e Vista Dourada" -> nova-campo-grande, vista-dourada. Só o nome inteiro conta: a rua Santa Luzia
    não é o bairro Santa Luzia, e "Jardim Campo Grande" não é Campo Grande."""
    out = []
    for m in re.finditer(r"\bbairros?\s+(.+?)(?=$|[.;:(]|\s-\s|/ES\b|\bno munic|\bem cariacica)", nome, re.I):
        for parte in re.split(r",|\s+e\s+", m.group(1)):
            parte = re.sub(r"^\s*(?:(?:no|na|nos|nas|em|do|da|dos|das)\s+)?bairros?\s+", "", parte, flags=re.I)
            k = _chave_obra(parte)
            if k in chaves and chaves[k] not in out:
                out.append(chaves[k])
    return out


def obras(bs: list[dict], hoje: date | None = None) -> dict:
    """Todas as obras do sistema de obras do Portal da Transparência (2010 em diante), ligadas aos bairros do
    Censo pelo campo Bairros e, desde 24/11/2026, também pelos bairros que o nome da obra cita (a obra 1748, de
    R$ 12 milhões, cita Nova Campo Grande e Vista Dourada, mas o campo só diz Roda D'água, que o Censo não separa).
    Obra em vários bairros aparece em cada um, com o valor inteiro da obra.
    Serviço contínuo (tipo "Serviço" no sistema, como o recapeamento de R$ 86,9 mi, contrato 069/2019, marcado só com
    Nova Rosa da Penha) não entra em bairro nenhum: fica na lista da cidade toda.
    Quando duas ou mais obras do mesmo contrato mostram o mesmo valor pago (154/2012: obras 8, 9 e 10), o valor é do
    contrato inteiro: a página diz isso e a soma conta o valor uma vez só."""
    chaves = {normalizar(b["bairro"]): b["slug"] for b in bs}
    nome_de = {b["slug"]: b["nome"] for b in bs}
    lista = []
    for f in sorted(TRANSP.glob("obras_*.csv")):
        d = pd.read_csv(f, dtype=str, keep_default_na=False)
        for r in d.to_dict("records"):
            nome_sit, estado = SITUACAO_OBRA.get(r.get("Situacao", ""), (r.get("Situacao", "") or "Sem situação", "outro"))
            nomes = [n.strip() for n in re.split(r"[,;]", r.get("Bairros", "")) if n.strip()]
            nome = re.sub(r"\s+", " ", r["Nome"]).strip()
            slugs = []
            servico = r.get("Tipo", "Obra") not in ("Obra", "")
            for n in ([] if servico else nomes):   # serviço contínuo (tapa-buraco, manutenção) é da cidade toda
                k = _chave_obra(n)
                if k in chaves and chaves[k] not in slugs:
                    slugs.append(chaves[k])
            citados = [] if servico else [s for s in bairros_no_nome(nome, chaves) if s not in slugs]
            slugs += citados
            todos = nomes + [nome_de[s] for s in citados]
            vig = re.findall(r"\d{2}/\d{2}/\d{4}", r.get("Vigencia", ""))
            fim = vig[1] if len(vig) > 1 else ""
            vencido = bool(fim and estado == "andamento" and hoje
                           and date(int(fim[6:]), int(fim[3:5]), int(fim[:2])) < hoje)
            lista.append({
                "id": r["Id"], "nome": nome, "nome_txt": _caixa(nome), "exercicio": f.stem[-4:], "vencido": vencido,
                "ano": _ano_contrato(r.get("NumeroContrato", ""), vig, f.stem[-4:]),
                "secretaria": r.get("Secretaria", "").replace("Secretaria Municipal de ", ""),
                "contratado": _valor(r.get("ValorContratado")), "pago": _valor(r.get("ValorPago")),
                "situacao": nome_sit, "estado": estado, "bairros_txt": ", ".join(todos), "slugs": slugs,
                "varios": len(todos) > 1, "servico": servico, "inicio": vig[0] if vig else "", "fim": vig[1] if len(vig) > 1 else "",
                "contrato": r.get("NumeroContrato", "").strip(), "junta": 1,
                "campo_txt": ", ".join(nomes), "citados_txt": " e ".join(nome_de[s] for s in citados),
            })
    # o mesmo valor pago em obras do mesmo contrato é o valor do contrato, não de cada obra
    grupos: dict[tuple, list[dict]] = {}
    for o in lista:
        if o["contrato"] and o["pago"] > 0:
            grupos.setdefault((o["contrato"], round(o["pago"], 2)), []).append(o)
    for g in grupos.values():
        if len(g) > 1:
            for o in g:
                o["junta"] = len(g)
    lista.sort(key=lambda o: (o["ano"], o["pago"]), reverse=True)
    por_bairro: dict[str, list[dict]] = {}
    for o in lista:
        for s in o["slugs"]:
            por_bairro.setdefault(s, []).append(o)
    sem_bairro = [o for o in lista if not o["slugs"]]
    anos = {}
    for o in lista:   # por ano do sistema (o portal separa as obras por exercício)
        anos[o["exercicio"]] = anos.get(o["exercicio"], 0) + 1
    contagem = {}
    for o in lista:
        contagem[o["situacao"]] = contagem.get(o["situacao"], 0) + 1
    def soma(xs):   # valor de contrato repetido em várias obras conta uma vez
        vistos, t = set(), 0.0
        for o in xs:
            k = (o["contrato"], round(o["pago"], 2)) if o["junta"] > 1 else id(o)
            if k not in vistos:
                vistos.add(k)
                t += o["pago"]
        return t
    return {
        "por_bairro": por_bairro, "sem_bairro": sem_bairro, "total": len(lista),
        "pago": soma(lista), "com_bairro": sum(1 for o in lista if o["slugs"]),
        "sem_bairro_pago": soma(sem_bairro), "anos": dict(sorted(anos.items())),
        "primeiro_ano": min(anos) if anos else "", "ultimo_ano": max(anos) if anos else "",
        "situacoes": contagem, "portal": PORTAL_OBRAS,
        "provisorias": contagem.get("Pronta, falta a vistoria final", 0),
        "recentes": _recentes(anos, (hoje or hoje_brasilia()).year),
    }


def _recentes(anos: dict, ano: int) -> str:
    """'Para 2025, tem só 1. Para 2026, nenhuma.' Mostra quando o sistema parou de receber obras."""
    partes = []
    for a in (ano - 1, ano):
        n = anos.get(str(a), 0)
        partes.append(f"Para {a}, {'nenhuma' if n == 0 else 'tem só 1' if n == 1 else f'tem {n}'}.")
    return " ".join(partes)


# ---------------------------------------------------------------- dinheiro e placar

SICONFI = DADOS / "siconfi"
CARIACICA = "3201308"
# "Em que foi gasto", sobre a despesa liquidada sem as intraorçamentárias (modalidade 91: dinheiro que passa de um
# órgão do município para outro, como a contribuição da prefeitura à previdência dos servidores). Contar a 91 somava
# R$ 45 milhões duas vezes (24/11/2026). Elementos de despesa das aplicações diretas (modalidade 90):
ELEM_EMPRESAS = {"30", "32", "35", "37", "39", "40", "51", "52"}   # material, serviços, mão de obra, obras, equipamentos
ELEM_SALARIO = {"08", "46", "49"}                                   # benefícios e auxílio-alimentação/transporte
BLOCOS = [("salarios", "Salários e aposentadorias", "dos servidores, da Câmara e da previdência, com o auxílio-alimentação"),
          ("empresas", "Empresas contratadas", "obras, limpeza, coleta de lixo, manutenção e material"),
          ("entidades", "Entidades", "que cuidam de unidades de saúde e de assistência social"),
          ("emprestimos", "Parcelas de empréstimos", "e os juros"),
          ("consorcios", "Compras junto com outras cidades", "os consórcios, como o da merenda"),
          ("outros", "Outros gastos", "impostos, auxílios, indenizações e sentenças")]


def _dca(arquivo: str, ano: int, cod: str = CARIACICA) -> pd.DataFrame:
    f = SICONFI / arquivo
    if not f.exists():
        return pd.DataFrame()
    d = pd.read_csv(f, dtype={"cod_ibge": str})
    return d[(d["exercicio"] == ano) & (d["cod_ibge"] == cod) & (d["coluna"] == "Despesas Liquidadas")]


def gasto_por_bloco(ano: int) -> dict | None:
    """Total e blocos "de cada R$ 100" das contas anuais (Siconfi, DCA Anexo I-D), sem as intraorçamentárias.
    O total é o mesmo do Tribunal de Contas do ES sem a modalidade 91 (R$ 1.619.123.621 em 2025)."""
    d = _dca("dca_despesa_natureza.csv", ano)
    if d.empty:
        return None
    mod, elem = {}, {}
    for c, v in zip(d["cod_conta"], d["valor"]):
        m = re.fullmatch(r"DO(\d)\.(\d)\.(\d\d)\.(\d\d)\.00\.00", str(c))
        if not m or m.group(3) in ("00", "91"):
            continue
        g, mo, el = m.group(2), m.group(3), m.group(4)
        if el == "00":
            mod[(g, mo)] = float(v)
        elif mo == "90":
            elem[(g, el)] = float(v)
    total = sum(mod.values())
    b = {k: 0.0 for k, _, _ in BLOCOS}
    for (g, mo), v in mod.items():
        if mo == "50":
            b["entidades"] += v
        elif mo in ("71", "93"):
            b["consorcios"] += v
        elif g in ("2", "6"):
            b["emprestimos"] += v
        elif g == "1":
            b["salarios"] += v
    for (g, el), v in elem.items():
        if g in ("3", "4") and el in ELEM_EMPRESAS:
            b["empresas"] += v
        elif g == "3" and el in ELEM_SALARIO:
            b["salarios"] += v
    b["outros"] = total - sum(v for k, v in b.items() if k != "outros")
    return {"total": total, "blocos": [{"nome": n, "detalhe": det, "milhoes": round(b[k] / 1e6, 1),
                                        "de_cada_100": round(100 * b[k] / total, 1)} for k, n, det in BLOCOS]}


def saude_por_morador(ano: int, populacao: dict[str, int]) -> dict[str, float]:
    """Gasto com saúde (função 10, liquidado, DCA Anexo I-E) dividido pela população, sem arredondar."""
    f = SICONFI / "dca_despesa_funcao.csv"
    if not f.exists():
        return {}
    d = pd.read_csv(f, dtype={"cod_ibge": str})
    d = d[(d["exercicio"] == ano) & (d["coluna"] == "Despesas Liquidadas") & d["conta"].str.match(r"^10 - Sa")]
    return {c: float(v) / populacao[c] for c, v in zip(d["cod_ibge"], d["valor"]) if populacao.get(c)}


def dinheiro() -> dict:
    """data/site/dinheiro.json, com o total, os blocos e a saúde por morador refeitos pelas contas anuais do
    Siconfi (data/siconfi) quando o ano está lá."""
    g = json.loads((SITE / "dinheiro.json").read_text(encoding="utf-8"))
    calc = gasto_por_bloco(int(g["ano"]))
    if calc:
        g.update(calc)
    entes = SICONFI / "entes.csv"
    if entes.exists():
        e = pd.read_csv(entes, dtype={"cod_ibge": str})
        pop = dict(zip(e["cod_ibge"], e["populacao"]))
        cod = {normalizar(n): c for c, n in zip(e["cod_ibge"], e["ente"])}
        exato = saude_por_morador(int(g["ano"]), pop)
        for s in g["saude"]:
            c = cod.get(normalizar(s["cidade"]))
            if c in exato:
                s["por_morador"] = exato[c]
    return g


def resultados() -> list[dict]:
    f = DADOS / "resultados.csv"
    if not f.exists() or f.stat().st_size == 0:
        return []
    d = pd.read_csv(f, dtype=str, keep_default_na=False)
    return d.sort_values("data", ascending=False).to_dict("records")


def hoje_brasilia() -> date:
    return reg_pedidos.hoje_brasilia()


def dias_ate(prazo: date, hoje: date) -> int:
    return (prazo - hoje).days


__all__ = ["bairros", "cidade", "padroes", "cartoes_bairro", "fila", "postos_por_bairro", "escolas_por_bairro",
           "ideb_cidade", "perguntas", "pergunta_por_numero", "dinheiro", "resultados", "hoje_brasilia", "br",
           "reais", "de_cada", "meses", "falado", "slug", "normalizar", "timedelta"]
