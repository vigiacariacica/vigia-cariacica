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
    if pct >= 99.5:
        return "todas"
    if pct >= 95:
        return "quase todas"
    if pct <= 0.5:
        return "nenhuma"
    if pct < 100 / base / 2:
        return "quase nenhuma"
    return f"{max(1, round(pct * base / 100))} de cada {base}"


def casas(pct: float, resto: str) -> tuple[str, str]:
    """(número, frase): '7 de cada 10' + 'das casas têm…' ou 'Quase todas' + 'as casas têm…'."""
    n = de_cada(pct)
    return n.capitalize(), ("casas " if "de cada" in n else "as casas ") + resto


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

def bairros() -> list[dict]:
    b = pd.read_csv(RAIOX / "bairros-cariacica.csv")
    b = b[~b["bairro"].str.startswith("Área Não Identificada")].copy()
    b["nome"] = b["bairro"].map(lambda x: NOME_EXIBICAO.get(x, x))
    b["slug"] = b["nome"].map(slug)
    b["chave"] = b["bairro"].map(normalizar)
    b["sem_rede"] = (b["domicilios"] * (1 - b["pct_esgoto_rede"] / 100)).round().astype(int)
    b["pct_nao_le"] = 100 - b["pct_alfabetizados_15mais"]
    grandes = b[b["domicilios"] >= MIN_DOMICILIOS_RANKING]
    pior_esgoto = set(grandes.nsmallest(10, "pct_esgoto_rede")["slug"])
    pior_leitura = set(grandes.nlargest(10, "pct_nao_le")["slug"])
    renda_baixa = set(grandes.nsmallest(20, "renda_mediana")["slug"])
    out = []
    for r in b.sort_values("nome", key=lambda s: s.map(normalizar)).to_dict("records"):
        r["pior_esgoto"] = r["slug"] in pior_esgoto
        r["pior_leitura"] = r["slug"] in pior_leitura
        r["renda_baixa"] = r["slug"] in renda_baixa
        r["pequeno"] = r["domicilios"] < MIN_DOMICILIOS_RANKING
        out.append(r)
    return out


def cidade(bs: list[dict]) -> dict:
    d = pd.DataFrame(bs)
    w = d["domicilios"]
    pop15 = d["pessoas_15mais_nao_alfabetizadas"] / (1 - d["pct_alfabetizados_15mais"] / 100)
    return {
        "populacao": int(d["populacao"].sum()),
        "pct_esgoto_rede": float((d["pct_esgoto_rede"] * w).sum() / w.sum()),
        "pct_agua_rede": float((d["pct_agua_rede"] * w).sum() / w.sum()),
        "pct_lixo_coletado": float((d["pct_lixo_coletado"] * w).sum() / w.sum()),
        "pct_nao_le": float(100 * d["pessoas_15mais_nao_alfabetizadas"].sum() / pop15.sum()),
        "sem_rede": int(d["sem_rede"].sum()),
    }


def padroes(bs: list[dict]) -> dict:
    """O padrão da cidade em uma frase: onde a renda é menor, falta mais esgoto."""
    d = pd.DataFrame(bs)
    d = d[d["domicilios"] >= MIN_DOMICILIOS_RANKING].sort_values("renda_mediana")
    def esg(x):
        return float((x["pct_esgoto_rede"] * x["domicilios"]).sum() / x["domicilios"].sum())
    baixa, alta = d.head(20), d.tail(20)
    return {"esgoto_renda_baixa": esg(baixa), "esgoto_renda_alta": esg(alta),
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
        "extra": (f"Cerca de {br(b['sem_rede'])} casas ainda não estão ligadas à rede." if b["sem_rede"] >= 5 else ""),
        "selo": "Um dos 10 bairros com menos esgoto na rede" if b["pior_esgoto"] else "",
        "valor": esg, "ref": c["pct_esgoto_rede"], "bom": esg >= c["pct_esgoto_rede"],
        "grafico": "dez", "g_aqui": esg, "g_cid": c["pct_esgoto_rede"],
        "g_txt_aqui": de_cada(esg), "g_txt_cid": de_cada(c["pct_esgoto_rede"]),
        "exato": f"{br(esg, 1)}% das casas", "ref_exato": f"{br(c['pct_esgoto_rede'], 1)}%",
    })
    nl = b["pct_nao_le"]
    n_pessoas = int(b["pessoas_15mais_nao_alfabetizadas"])
    cards.append({
        "tema": "Ler e escrever", "pergunta": "Quantos vizinhos não sabem ler?",
        "numero": (f"{max(1, round(nl))} de cada 100" if nl >= 0.5 else "Menos de 1 de cada 100"),
        "frase": "pessoas com 15 anos ou mais não sabem ler e escrever.",
        "cidade": f"Em Cariacica: {round(c['pct_nao_le'])} de cada 100.",
        "extra": f"São {br(n_pessoas)} pessoas no bairro." if n_pessoas >= 5 else "",
        "selo": "Um dos 10 bairros com mais gente sem saber ler" if b["pior_leitura"] else "",
        "valor": None, "ref": None, "bom": nl <= c["pct_nao_le"],
        "grafico": "cem", "g_aqui": nl, "g_cid": c["pct_nao_le"],
        "exato": f"{br(nl, 1)}% não alfabetizados", "ref_exato": f"{br(c['pct_nao_le'], 1)}%",
    })
    cards.append({
        "tema": "Renda", "pergunta": "Quanto ganha quem sustenta a casa?",
        "numero": reais(b["renda_mediana"]), "frase": "por mês: metade dos responsáveis pelas casas ganha até esse valor.",
        "cidade": "Está entre os 20 bairros de menor renda de Cariacica." if b["renda_baixa"] else "",
        "extra": "Era o valor do salário mínimo em 2022, ano do Censo." if abs(b["renda_mediana"] - 1212) < 1 else "",
        "selo": "", "valor": None, "ref": None, "bom": None,
        "exato": f"mediana {reais(b['renda_mediana'])}", "ref_exato": "",
    })
    agua, lixo = b["pct_agua_rede"], b["pct_lixo_coletado"]
    if agua >= 95 and lixo >= 95:
        cards.append({"tema": "Água e lixo", "pergunta": "Tem água da rede e coleta de lixo?",
                      "numero": "Quase todas" if min(agua, lixo) < 99.5 else "Todas",
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
        partes.append(pd.read_csv(f, dtype=str, keep_default_na=False)[["nome", "bairro"]])
    s = SONDA / "es_georref_saude.csv"
    if s.exists():
        d = pd.read_csv(s, sep=";", dtype=str, keep_default_na=False, encoding="utf-8-sig", on_bad_lines="skip")
        d = d[d["MUNICIPIO"].str.lower() == "cariacica"]
        partes.append(d.rename(columns={"NOME": "nome", "BAIRRO": "bairro"})[["nome", "bairro"]])
    if not partes:
        return pd.DataFrame(columns=["nome", "bairro"])
    return pd.concat(partes, ignore_index=True).drop_duplicates("nome")


def chave_bairro(nome_bairro: str, chaves: set[str]) -> str | None:
    k = normalizar(nome_bairro)
    k = APELIDOS.get(k, k)
    return k if k in chaves else None


PALAVRAS_VAZIAS = {"US", "USF", "UBS", "DE", "DA", "DO", "DOS", "DAS", "E", "CENTRO", "SAUDE", "UNIDADE", "BASICA"}


def _tokens(nome: str) -> set[str]:
    return {t for t in normalizar(nome).split() if t not in PALAVRAS_VAZIAS and len(t) > 1}


def _achar_posto(origem: str, eq: pd.DataFrame) -> str | None:
    """Bairro do posto: nome igual; se não houver, o cadastro cujas palavras estão todas no nome da planilha
    ("US DE ITAPEMIRIM" = "US ITAPEMIRIM"; "US JARDIM AMERICA CENTRO DE SAUDE JARDIM AMERICA" = "US JARDIM AMERICA").
    Só aceita quando um cadastro só combina."""
    alvo = normalizar(origem)
    iguais = eq[eq["nome"].map(normalizar) == alvo]
    if len(iguais):
        return iguais.iloc[0]["bairro"]
    t = _tokens(origem)
    cands = [b for n, b in zip(eq["nome"], eq["bairro"]) if _tokens(n) and _tokens(n) <= t]
    return cands[0] if len(set(cands)) == 1 else None


def postos_por_bairro(bs: list[dict], fl: dict) -> dict[str, list[dict]]:
    """bairro (slug) -> postos da fila que ficam nele, casando o nome do posto na planilha com o cadastro."""
    chave_para_slug = {b["chave"]: b["slug"] for b in bs}
    eq = _equip_saude()
    out: dict[str, list[dict]] = {}
    for u in fl["unidades"]:
        if u.get("tipo") != "ubs":     # CAPS, IST/Aids e a própria Secretaria atendem a cidade toda
            continue
        bairro = _achar_posto(u["origem"], eq)
        k = chave_bairro(bairro, set(chave_para_slug)) if bairro else None
        if k:
            out.setdefault(chave_para_slug[k], []).append(u)
            u["bairro_slug"] = chave_para_slug[k]
    return out


def escolas_por_bairro(bs: list[dict]) -> dict[str, list[dict]]:
    f = EQUIP / "escolas.csv"
    if not f.exists():
        return {}
    e = pd.read_csv(f, dtype=str, keep_default_na=False)
    ideb = pd.read_csv(RAIOX / "ideb-escolas-cariacica.csv", dtype=str, keep_default_na=False)
    ideb = ideb.rename(columns={"id_escola": "inep"})
    chave_para_slug = {b["chave"]: b["slug"] for b in bs}
    out: dict[str, list[dict]] = {}
    for x in e.to_dict("records"):
        k = chave_bairro(x["bairro"], set(chave_para_slug))
        if not k:
            continue
        notas = ideb[ideb["inep"] == x["inep"]]
        x["ideb"] = [{"etapa": n["etapa"], "nota": n["ideb_2025"] or n["ideb_2023"],
                      "ano": "2025" if n["ideb_2025"] else "2023"} for n in notas.to_dict("records")
                     if n["ideb_2025"] or n["ideb_2023"]]
        out.setdefault(chave_para_slug[k], []).append(x)
    return out


def ideb_cidade() -> dict[str, str]:
    d = pd.read_csv(RAIOX / "ideb-cidades.csv", dtype=str, keep_default_na=False)
    d = d[d["cidade"] == "Cariacica"]
    return {r["etapa"]: (r["ideb_2025"] or r["ideb_2023"]) for r in d.to_dict("records")}


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
                                      "respondido_em": r.get("respondido_em", "")})
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
    return {"total": len(lista), "pedidos": len(p), "respondidas": conta("respondido"), "parciais": conta("parcial"),
            "negadas": conta("negado"), "atrasadas": conta("vencido"), "grupos": grupos, "proximo": prox,
            "n_proximo": sum(1 for it in esperando if it["prazo"] == prox)}


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


def obras(bs: list[dict], hoje: date | None = None) -> dict:
    """Todas as obras do sistema de obras do Portal da Transparência (2010 em diante), ligadas aos bairros do
    Censo pelo campo Bairros. Obra em vários bairros aparece em cada um, com o valor inteiro da obra.
    Serviço contínuo (tipo "Serviço" no sistema, como o recapeamento de R$ 86,9 mi, contrato 069/2019, marcado só com
    Nova Rosa da Penha) não entra em bairro nenhum: fica na lista da cidade toda."""
    chaves = {normalizar(b["bairro"]): b["slug"] for b in bs}
    lista = []
    for f in sorted(TRANSP.glob("obras_*.csv")):
        d = pd.read_csv(f, dtype=str, keep_default_na=False)
        for r in d.to_dict("records"):
            nome_sit, estado = SITUACAO_OBRA.get(r.get("Situacao", ""), (r.get("Situacao", "") or "Sem situação", "outro"))
            nomes = [n.strip() for n in re.split(r"[,;]", r.get("Bairros", "")) if n.strip()]
            slugs = []
            servico = r.get("Tipo", "Obra") not in ("Obra", "")
            for n in ([] if servico else nomes):   # serviço contínuo (tapa-buraco, manutenção) é da cidade toda
                k = normalizar(n)
                k = APELIDOS_OBRAS.get(k, APELIDOS.get(k, k))
                if k in chaves and chaves[k] not in slugs:
                    slugs.append(chaves[k])
            vig = re.findall(r"\d{2}/\d{2}/\d{4}", r.get("Vigencia", ""))
            nome = re.sub(r"\s+", " ", r["Nome"]).strip()
            fim = vig[1] if len(vig) > 1 else ""
            vencido = bool(fim and estado == "andamento" and hoje
                           and date(int(fim[6:]), int(fim[3:5]), int(fim[:2])) < hoje)
            lista.append({
                "id": r["Id"], "nome": nome, "nome_txt": _caixa(nome), "exercicio": f.stem[-4:], "vencido": vencido,
                "ano": _ano_contrato(r.get("NumeroContrato", ""), vig, f.stem[-4:]),
                "secretaria": r.get("Secretaria", "").replace("Secretaria Municipal de ", ""),
                "contratado": _valor(r.get("ValorContratado")), "pago": _valor(r.get("ValorPago")),
                "situacao": nome_sit, "estado": estado, "bairros_txt": ", ".join(nomes), "slugs": slugs,
                "varios": len(nomes) > 1, "servico": servico, "inicio": vig[0] if vig else "", "fim": vig[1] if len(vig) > 1 else "",
            })
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
    return {
        "por_bairro": por_bairro, "sem_bairro": sem_bairro, "total": len(lista),
        "pago": sum(o["pago"] for o in lista), "com_bairro": sum(1 for o in lista if o["slugs"]),
        "sem_bairro_pago": sum(o["pago"] for o in sem_bairro), "anos": dict(sorted(anos.items())),
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

def dinheiro() -> dict:
    return json.loads((SITE / "dinheiro.json").read_text(encoding="utf-8"))


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
