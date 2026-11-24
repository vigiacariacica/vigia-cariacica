"""Camada refinada: o "mapa do dinheiro" a partir dos dados brutos já coletados.

Os CSVs brutos do portal (data/transparencia/pagamentos_*.csv) trazem, em cada pagamento, a fonte
do dinheiro, a natureza da despesa, o órgão, a função e quem recebeu. Nada disso aparecia nas
tabelas públicas: o relatório mostrava só o gasto por área (Siconfi) e os maiores fornecedores.
Este módulo lê esses campos, traduz os códigos para categorias que qualquer pessoa entende e grava
tabelas pequenas em data/refinado/, sem trabalho manual e sem inventar número: tudo é soma dos
registros do portal, e cada tabela diz qual coluna somou.

Entra:  data/transparencia/pagamentos_*.csv   (portal da prefeitura, todos os órgãos do município)
        data/siconfi/dca_despesa_funcao.csv   (população por ano, a mesma que o Tesouro usa)
        data/siconfi/entes.csv                (população do ano corrente)
        data/receita/empresas.csv             (CNAE, porte, capital e natureza jurídica dos fornecedores)
        data/ibge/ipca.csv                    (índice do IPCA, se o coletor do IBGE já rodou)
Sai:    data/refinado/
        resumo_ano.csv          total empenhado, liquidado e pago por ano, população, valor por morador e,
                                com o IPCA, o valor real (a preços do último ano fechado)
        origem_ano.csv          de onde veio o dinheiro de cada pagamento (fonte de recursos) × ano
        origem_detalhe_ano.csv  cada código de fonte do portal, com o nome que a prefeitura usa, a
                                categoria atribuída e um aviso quando o nome sugere outra categoria
        tipo_ano.csv            tipo de gasto (pessoal, custeio, investimento, dívida...) × ano
        modalidade_ano.csv      quem executa (direto, entidade sem fins lucrativos, consórcio...) × ano
        orgao_ano.csv           órgão (secretaria, fundo, Câmara, IPC) × ano
        funcao_ano.csv          área de governo (função) × ano, pelo código, com nome único
        elemento_ano.csv        elemento de despesa (obras, locação de mão de obra, material...) × ano
        recebedor_ano.csv       tipo de quem recebeu (empresa, entidade, pessoa física, ente público) × ano
        fornecedores.csv        um por raiz de CNPJ: nome, tipo, total por ano, primeiro ano, órgão e
                                área principais, CNAE e situação na Receita (sem pessoa física)
        deflator.csv            IPCA médio de cada ano e o fator para trazer a preços do ano-base

"Pago" aqui é o pago sobre os empenhos do ano (o portal acumula os pagamentos de cada empenho,
inclusive os feitos em anos seguintes); por isso o ano corrente é parcial e os anos recentes ainda
crescem um pouco. Para o caixa do ano, use o Siconfi.
"""
from __future__ import annotations

import logging
import re

import pandas as pd

from . import armazem
from .config import CARIACICA_IBGE, DADOS
from .texto import so_digitos

log = logging.getLogger("vigia.refino")
PASTA = DADOS / "refinado"

# ---------------------------------------------------------------- origem do dinheiro (fonte de recursos)
# Portaria STN 710/2021 (fontes padronizadas, usadas pela prefeitura desde 2023) e o plano de fontes
# anterior do ES (2019–2022). O portal escreve "1.500.0025.0000": o 1º dígito diz se o recurso é do
# exercício corrente (1) ou de exercícios anteriores (2); os 3 dígitos seguintes são a fonte.
ANO_TROCA_DE_PLANO = 2023

ORIGENS = {
    "livres": "Impostos e transferências livres (IPTU, ISS, ICMS, FPM…)",
    "fundeb": "FUNDEB (educação básica)",
    "educacao_vinc": "Educação: salário-educação, FNDE (merenda, transporte) e convênios",
    "saude_vinc": "Saúde: SUS (fundo a fundo) e convênios",
    "assistencia": "Assistência social: FNAS e convênios",
    "convenios": "Convênios e outras transferências da União e do Estado",
    "royalties": "Royalties e compensações financeiras (petróleo, minerais)",
    "emendas_pix": "Emendas Pix (transferências especiais da União)",
    "cosip": "COSIP (contribuição de iluminação pública)",
    "emprestimos": "Operações de crédito (empréstimos)",
    "rpps": "Previdência dos servidores (RPPS)",
    "alienacao": "Alienação de bens",
    "outros_vinc": "Fundos e outros recursos vinculados",
    "nao_classificada": "Não classificada",
}

_FONTES_STN = {
    **{c: "livres" for c in ("500", "501", "502")},
    **{c: "fundeb" for c in ("540", "541", "542", "543", "544", "545", "546", "547", "548", "549")},
    "706": "emendas_pix", "707": "convenios",
    **{c: "royalties" for c in ("704", "705", "708", "720")},
    "751": "cosip", "753": "emprestimos", "754": "emprestimos", "755": "alienacao", "756": "alienacao",
    "750": "outros_vinc", "752": "outros_vinc", "759": "outros_vinc",
}
_FONTES_ANTIGAS = {
    **{c: "livres" for c in ("001", "111", "211")},
    **{c: "fundeb" for c in ("102", "103", "112", "113", "118", "119", "151")},
    **{c: "educacao_vinc" for c in ("101", "104", "107", "108", "120", "122", "123", "124", "125", "150", "190", "199")},
    **{c: "saude_vinc" for c in ("201", "203", "204", "212", "213", "214", "215", "220", "250", "290", "299")},
    **{c: "assistencia" for c in ("301", "302", "311", "312", "390", "399")},
    **{c: "rpps" for c in ("404", "410", "420", "430")},
    **{c: "convenios" for c in ("510", "520", "560", "710")},
    **{c: "royalties" for c in ("530", "540")},
    "550": "emendas_pix",   # 2021–2022: "TRANSFERÊNCIA ESPECIAL DA UNIÃO" (emenda Pix) com este código
    "620": "cosip", "901": "emprestimos", "920": "emprestimos", "930": "alienacao",
    **{c: "outros_vinc" for c in ("610", "630", "940", "990", "999", "000")},
}


def origem_da_fonte(cod_fonte: str, ano: int) -> str:
    """Chave da ORIGENS para um código de fonte do portal ('1.500.0025.0000') e o ano do empenho."""
    partes = str(cod_fonte or "").split(".")
    esp = partes[1] if len(partes) > 1 else ""
    if not re.fullmatch(r"\d{3}", esp):
        return "nao_classificada"
    if ano < ANO_TROCA_DE_PLANO:
        return _FONTES_ANTIGAS.get(esp, "nao_classificada")
    if esp in _FONTES_STN:
        return _FONTES_STN[esp]
    n = int(esp)
    if 550 <= n <= 599:
        return "educacao_vinc"
    if 600 <= n <= 659:
        return "saude_vinc"
    if 660 <= n <= 699:
        return "assistencia"
    if 700 <= n <= 749:
        return "convenios"
    if 800 <= n <= 809:
        return "rpps"
    if 810 <= n <= 899:
        return "outros_vinc"
    return "nao_classificada"


def exercicio_anterior(cod_fonte: str) -> bool:
    """True quando o recurso é de exercícios anteriores (superávit, restos a pagar): código '2.xxx'."""
    return str(cod_fonte or "").startswith("2")


# O nome que a prefeitura dá à fonte deveria combinar com o código. Quando não combina, a linha de
# origem_detalhe_ano.csv ganha um aviso: pode ser erro de digitação do portal ou fonte reaproveitada.
_PALAVRAS_ORIGEM = [
    (re.compile(r"IMPOSTOS|ORDIN[AÁ]RIO|N[AÃ]O VINCULAD", re.I), "livres"),
    (re.compile(r"FUNDEB", re.I), "fundeb"),
    (re.compile(r"TRANSF\w*\.?\s*ESPEC", re.I), "emendas_pix"),
    (re.compile(r"\bSUS\b|SA[UÚ]DE", re.I), "saude_vinc"),
    (re.compile(r"SAL[AÁ]RIO.?EDUCA|FNDE|PNAE|PNATE|PDDE|EDUCA", re.I), "educacao_vinc"),
    (re.compile(r"FNAS|ASS\w*\.?\s*SOCIAL", re.I), "assistencia"),
    (re.compile(r"ROYALT|COMP\w*\.? FIN|PETR[OÓ]LEO|REC\w* NAT", re.I), "royalties"),
    (re.compile(r"COSIP|ILUMINA", re.I), "cosip"),
    (re.compile(r"OPERA[CÇ]\w* (DE )?CR[EÉ]D|OP\.? ?CRED", re.I), "emprestimos"),
    (re.compile(r"RPPS|PREVIDENCI", re.I), "rpps"),
    (re.compile(r"ALIENA", re.I), "alienacao"),
    (re.compile(r"CONV[EÊ]NIO|REPASSE|TERMO DE COMPROMISSO", re.I), "convenios"),
]


def origem_pelo_nome(nome: str) -> str:
    for rx, chave in _PALAVRAS_ORIGEM:
        if rx.search(str(nome or "")):
            return chave
    return ""


# ---------------------------------------------------------------- tipo de gasto (natureza da despesa)
# "33903700" = categoria 3 (corrente), grupo 3 (outras despesas correntes), modalidade 90 (aplicação
# direta), elemento 37 (locação de mão de obra), subelemento 00.
TIPOS = {
    "31": "Pessoal e encargos",
    "32": "Juros da dívida",
    "33": "Custeio (serviços, materiais, contratos)",
    "44": "Investimentos (obras e equipamentos)",
    "45": "Inversões financeiras",
    "46": "Amortização da dívida",
    "47": "Reserva",
}
MODALIDADES = {
    "90": "Aplicação direta (a prefeitura paga)",
    "91": "Entre órgãos do próprio município (intraorçamentária)",
    "50": "Entidade sem fins lucrativos (OS, OSCIP, associação)",
    "20": "Transferência à União",
    "30": "Transferência ao Estado",
    "40": "Transferência a outro município",
    "41": "Transferência a outro município (fundo a fundo)",
    "60": "Transferência ao exterior",
    "67": "Transferência a organismo internacional",
    "80": "Transferência a multigovernamentais",
    "99": "Reserva",
}
for _m in ("71", "72", "73", "74", "75", "76", "93", "94", "95", "96"):
    MODALIDADES[_m] = "Consórcio público (CIM Polinorte e outros)"


def tipo_gasto(cod_natureza: str) -> str:
    return TIPOS.get(str(cod_natureza or "")[:2], "Outro")


def modalidade(cod_natureza: str) -> str:
    return MODALIDADES.get(str(cod_natureza or "")[2:4], "Outra")


# ---------------------------------------------------------------- quem recebeu
DOC_FOLHA = "99.999.999/9999-99"
RE_ENTE_PUBLICO = re.compile(
    r"FOLHA DE PAGAMENTO|PREFEITURA|PREVID|^IPC\b|\bINSS\b|RECEITA FEDERAL|C[AÂ]MARA MUNICIPAL|TRIBUNAL|"
    r"CAIXA ECON[OÔ]MICA.*D[IÍ]VIDA|SECRETARIA|MINIST[EÉ]RIO|FUNDO MUNICIPAL|FUNDO NACIONAL|"
    r"PASEP|BANCO DO BRASIL|BANCO DO ESTADO|BANESTES|CONS[OÓ]RCIO P[UÚ]BLICO|GOVERNO DO ESTADO|"
    r"UNI[AÃ]O FEDERAL|MUNIC[IÍ]PIO DE|\bCIM\b|INSTITUTO NACIONAL|JUSTI[CÇ]A|TESOURO NACIONAL", re.I)
# Natureza jurídica como a Receita (via BrasilAPI) escreve: texto, não código.
RE_NATUREZA_PUBLICA = re.compile(
    r"[OÓ]rg[aã]o P[uú]blico|Autarquia|Funda[cç][aã]o P[uú]blica|Empresa P[uú]blica|Sociedade de Economia Mista|"
    r"Cons[oó]rcio P[uú]blico|Munic[ií]pio|Fundo P[uú]blico", re.I)
RE_NATUREZA_SEM_FINS = re.compile(
    r"Associa[cç][aã]o|Funda[cç][aã]o Privada|Organiza[cç][aã]o Religiosa|Organiza[cç][aã]o Social|"
    r"Entidade Sindical|Servi[cç]o Social Aut[oô]nomo|Sem Fins Lucrativos|Comunidade|Partido", re.I)
RE_SEM_FINS_LUCRATIVOS = re.compile(
    r"INSTITUTO|ASSOCIA[CÇ]|FUNDA[CÇ][AÃ]O|SANTA CASA|MISERIC[OÓ]RDIA|SINDICATO|IGREJA|PAR[OÓ]QUIA|CONSELHO|"
    r"\bOSCIP\b|\bAPAE\b|\bONG\b|BENEFICENT|FILANTR|CENTRO ESP[IÍ]RITA|COOPERATIVA|AG[EÊ]NCIA ADVENTISTA|"
    r"HOSPITAL E MATERNIDADE|SOCIEDADE (CIVIL|BENEF)|MOVIMENTO|GR[EÊ]MIO|CLUBE", re.I)
RE_CONCESSIONARIA = re.compile(
    r"\bEDP\b|ESP[IÍ]RITO SANTO (CENTRAIS|DISTRIBUI)|\bCESAN\b|COMPANHIA ESP[IÍ]RITO.?SANTENSE DE SANEAMENTO|"
    r"TELEF[OÔ]NICA|\bVIVO\b|\bCLARO\b|\bTIM S\.?A|\bOI S\.?A|EMPRESA BRASILEIRA DE CORREIOS|CORREIOS", re.I)
RE_CONSORCIO_EMPRESAS = re.compile(r"CONS[OÓ]RCIO", re.I)
RECEBEDORES = ("Servidores ativos e aposentados (folha, encargos, previdência)", "Pessoa física",
               "Órgão público, consórcio público ou previdência", "Entidade sem fins lucrativos",
               "Concessionária (energia, água, telefonia, correios)", "Consórcio de empresas", "Empresa",
               "Dívida (bancos e credores)")


def eh_cpf(doc: str) -> bool:
    d = str(doc or "")
    return "*" in d or bool(re.fullmatch(r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}", d))


def tipo_recebedor(nome: str, doc: str, natureza_juridica: str = "", cod_natureza: str = "") -> str:
    """Quem recebeu o dinheiro. A natureza da despesa manda antes do nome: tudo que é pessoal (grupo 31)
    é gasto com servidores, mesmo quando o credor registrado é o INSS, o IPC ou a própria prefeitura
    (até 2022 a folha era lançada em nome da prefeitura); juros e amortização são a dívida."""
    nome = str(nome or "")
    grupo = str(cod_natureza or "")[:2]
    if grupo == "31" or doc == DOC_FOLHA or re.search(r"FOLHA DE PAGAMENTO", nome, re.I):
        return RECEBEDORES[0]
    if grupo in ("32", "46"):
        return RECEBEDORES[7]
    if eh_cpf(doc):
        return RECEBEDORES[1]
    nj = str(natureza_juridica or "")
    if RE_ENTE_PUBLICO.search(nome) or RE_NATUREZA_PUBLICA.search(nj):
        return RECEBEDORES[2]
    if RE_NATUREZA_SEM_FINS.search(nj) or RE_SEM_FINS_LUCRATIVOS.search(nome):
        return RECEBEDORES[3]
    if RE_CONCESSIONARIA.search(nome):
        return RECEBEDORES[4]
    if RE_CONSORCIO_EMPRESAS.search(nome):
        return RECEBEDORES[5]
    return RECEBEDORES[6]


# ---------------------------------------------------------------- população e inflação

def populacao_por_ano() -> dict[int, float]:
    """População de Cariacica em cada exercício, como declarada ao Tesouro (origem: IBGE)."""
    pop: dict[int, float] = {}
    dca = armazem.ler(DADOS / "siconfi" / "dca_despesa_funcao.csv")
    if not dca.empty and {"cod_ibge", "exercicio", "populacao"} <= set(dca.columns):
        c = dca[dca["cod_ibge"] == str(CARIACICA_IBGE)]
        for ano, grupo in c.groupby("exercicio"):
            v = pd.to_numeric(grupo["populacao"], errors="coerce").dropna()
            if not v.empty and v.iloc[0] > 0:
                pop[int(ano)] = float(v.iloc[0])
    entes = armazem.ler(DADOS / "siconfi" / "entes.csv")
    if not entes.empty and {"cod_ibge", "exercicio", "populacao"} <= set(entes.columns):
        e = entes[entes["cod_ibge"] == str(CARIACICA_IBGE)]
        for _, r in e.iterrows():
            try:
                if float(r["populacao"]) > 0:
                    pop.setdefault(int(r["exercicio"]), float(r["populacao"]))
            except (TypeError, ValueError):
                pass
    return pop


def deflator(anos: list[int]) -> pd.DataFrame:
    """IPCA médio de cada ano (data/ibge/ipca.csv: ano, mes, indice) e o fator que leva cada ano a
    preços do ano-base (o último ano com 12 meses). Sem o arquivo, devolve tabela vazia: o relatório
    fica em valores nominais e diz isso."""
    ipca = armazem.ler(DADOS / "ibge" / "ipca.csv")
    if ipca.empty or not {"ano", "mes", "indice"} <= set(ipca.columns):
        return pd.DataFrame()
    ipca = ipca.assign(ano=pd.to_numeric(ipca["ano"], errors="coerce"),
                       indice=pd.to_numeric(ipca["indice"], errors="coerce")).dropna()
    g = ipca.groupby("ano").agg(meses=("indice", "size"), indice_medio=("indice", "mean")).reset_index()
    completos = g[g["meses"] >= 12]
    if completos.empty:
        return pd.DataFrame()
    base = int(completos["ano"].max())
    base_indice = float(completos.loc[completos["ano"] == base, "indice_medio"].iloc[0])
    g = g[g["ano"].isin(anos)].copy()
    g["ano"] = g["ano"].astype(int)
    g["ano_base"] = base
    g["fator_para_ano_base"] = (base_indice / g["indice_medio"]).round(6)
    g["indice_medio"] = g["indice_medio"].round(4)
    return g[["ano", "meses", "indice_medio", "ano_base", "fator_para_ano_base"]]


# ---------------------------------------------------------------- tabelas

def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").fillna(0.0)


def preparar(pagamentos: pd.DataFrame, empresas: pd.DataFrame | None = None) -> pd.DataFrame:
    """Uma linha por pagamento do portal, com as categorias desta camada já atribuídas."""
    p = pagamentos.copy()
    p["ano"] = pd.to_numeric(p["Ano"], errors="coerce").fillna(0).astype(int)
    for c in ("ValorEmpenhado", "ValorLiquidado", "ValorPago"):
        p[c.replace("Valor", "").lower()] = _num(p[c])
    p["origem"] = [origem_da_fonte(f, a) for f, a in zip(p["CodFonte"], p["ano"])]
    p["origem_nome"] = p["origem"].map(ORIGENS)
    p["exercicio_anterior"] = p["CodFonte"].map(exercicio_anterior)
    p["tipo"] = p["CodNaturezaDespesa"].map(tipo_gasto)
    p["modalidade"] = p["CodNaturezaDespesa"].map(modalidade)
    p["elemento"] = p["CodNaturezaDespesa"].astype(str).str[:6]
    p["doc"] = p["CpfCnpjFornecedor"].astype(str)
    p["raiz"] = p["doc"].map(lambda d: so_digitos(d)[:8] if not eh_cpf(d) and len(so_digitos(d)) == 14 else "")
    natureza = {}
    if empresas is not None and not empresas.empty and "cnpj" in empresas.columns:
        for _, r in empresas.iterrows():
            natureza.setdefault(so_digitos(r["cnpj"])[:8], str(r.get("natureza_juridica", "") or ""))
    p["natureza_juridica"] = p["raiz"].map(lambda r: natureza.get(r, ""))
    p["recebedor"] = [tipo_recebedor(n, d, nj, cn) for n, d, nj, cn in
                      zip(p["NomeFornecedor"], p["doc"], p["natureza_juridica"], p["CodNaturezaDespesa"])]
    return p


def _por_ano(p: pd.DataFrame, chaves: list[str], total_por_ano: pd.Series) -> pd.DataFrame:
    g = p.groupby(chaves + ["ano"], as_index=False).agg(
        empenhado=("empenhado", "sum"), liquidado=("liquidado", "sum"), pago=("pago", "sum"),
        registros=("pago", "size"))
    g["pct_do_ano"] = (g["pago"] / g["ano"].map(total_por_ano)).fillna(0).round(4)
    for c in ("empenhado", "liquidado", "pago"):
        g[c] = g[c].round(2)
    return g.sort_values(["ano", "pago"], ascending=[True, False])


def _nome_unico(p: pd.DataFrame, cod: str, nome: str) -> dict:
    """O portal escreve o mesmo código com nomes diferentes (SAUDE/SAÚDE). Fica o mais frequente."""
    return p.groupby(cod)[nome].agg(lambda s: s.value_counts().index[0]).to_dict()


def tabela_fornecedores(p: pd.DataFrame, empresas: pd.DataFrame | None, anos: list[int]) -> pd.DataFrame:
    """Um por raiz de CNPJ (matriz e filiais juntas). Pessoas físicas ficam de fora (LGPD): elas
    aparecem só somadas em recebedor_ano.csv."""
    pj = p[p["raiz"] != ""]
    if pj.empty:
        return pd.DataFrame()
    linhas = []
    for raiz, g in pj.groupby("raiz"):
        por_ano = g.groupby("ano")["pago"].sum()
        org = g.groupby("Orgao")["pago"].sum()
        fun = g.groupby("CodFuncao")["pago"].sum()
        ele = g.groupby("elemento")["pago"].sum()
        linha = {
            "raiz_cnpj": raiz,
            "cnpj": g["doc"].value_counts().index[0],
            "nome": g["NomeFornecedor"].value_counts().index[0],
            "tipo": g["recebedor"].value_counts().index[0],
            "total_pago": round(float(g["pago"].sum()), 2),
            "empenhos": int(len(g)),
            "primeiro_ano": int(g["ano"].min()),
            "ultimo_ano": int(g["ano"].max()),
            "anos_com_pagamento": int((por_ano > 0).sum()),
            "orgaos": int(g["Orgao"].nunique()),
            "orgao_principal": org.idxmax() if not org.empty else "",
            "funcao_principal": fun.idxmax() if not fun.empty else "",
            "elemento_principal": ele.idxmax() if not ele.empty else "",
            "contratos": int(g.loc[g["NumeroContrato"].astype(str).str.strip().ne(""), "NumeroContrato"].nunique()),
        }
        for a in anos:
            linha[f"pago_{a}"] = round(float(por_ano.get(a, 0.0)), 2)
        linhas.append(linha)
    f = pd.DataFrame(linhas)
    nomes_funcao = _nome_unico(p, "CodFuncao", "Funcao")
    f["funcao_principal"] = f["funcao_principal"].map(lambda c: nomes_funcao.get(c, c))
    nomes_elemento = _nome_unico(p, "elemento", "NaturezaDespesa")
    f["elemento_principal"] = f["elemento_principal"].map(lambda c: nomes_elemento.get(c, c))
    if empresas is not None and not empresas.empty and "cnpj" in empresas.columns:
        e = empresas.assign(raiz_cnpj=empresas["cnpj"].map(lambda c: so_digitos(c)[:8]))
        cols = [c for c in ("cnae", "cnae_descricao", "natureza_juridica", "porte", "capital_social",
                            "data_abertura", "situacao", "municipio", "uf") if c in e.columns]
        e = e.drop_duplicates("raiz_cnpj")[["raiz_cnpj"] + cols]
        f = f.merge(e, on="raiz_cnpj", how="left")
    return f.sort_values("total_pago", ascending=False).reset_index(drop=True)


def refinar(pagamentos: pd.DataFrame, empresas: pd.DataFrame | None = None) -> dict[str, pd.DataFrame]:
    """Gera todas as tabelas de data/refinado/ e devolve um dicionário {nome: tabela}."""
    saida: dict[str, pd.DataFrame] = {}
    if pagamentos.empty:
        log.warning("refino: sem pagamentos do portal; nada gerado")
        return saida
    if empresas is None:
        empresas = armazem.ler(DADOS / "receita" / "empresas.csv")
    p = preparar(pagamentos, empresas)
    anos = sorted(int(a) for a in p["ano"].unique() if a > 0)
    total_por_ano = p.groupby("ano")["pago"].sum()

    # resumo por ano, por morador e a preços constantes
    pop = populacao_por_ano()
    defl = deflator(anos)
    resumo = p.groupby("ano", as_index=False).agg(
        empenhado=("empenhado", "sum"), liquidado=("liquidado", "sum"), pago=("pago", "sum"),
        registros=("pago", "size"), fornecedores=("doc", "nunique"))
    resumo["populacao"] = resumo["ano"].map(pop)
    resumo["pago_por_morador"] = (resumo["pago"] / resumo["populacao"]).round(2)
    if not defl.empty:
        fat = defl.set_index("ano")["fator_para_ano_base"]
        resumo["ano_base_precos"] = int(defl["ano_base"].iloc[0])
        resumo["pago_real"] = (resumo["pago"] * resumo["ano"].map(fat)).round(2)
        resumo["pago_real_por_morador"] = (resumo["pago_real"] / resumo["populacao"]).round(2)
    for c in ("empenhado", "liquidado", "pago"):
        resumo[c] = resumo[c].round(2)
    saida["resumo_ano"] = resumo

    saida["origem_ano"] = _por_ano(p, ["origem", "origem_nome"], total_por_ano)
    det = (p.groupby(["ano", "CodFonte", "Fonte", "origem"], as_index=False)
             .agg(pago=("pago", "sum"), registros=("pago", "size")))
    det["pago"] = det["pago"].round(2)
    det["exercicio_anterior"] = det["CodFonte"].map(exercicio_anterior)
    det["origem_pelo_nome"] = det["Fonte"].map(origem_pelo_nome)
    det["aviso"] = [("nome da fonte sugere outra origem" if n and n != o else "")
                    for n, o in zip(det["origem_pelo_nome"], det["origem"])]
    saida["origem_detalhe_ano"] = det.sort_values(["ano", "pago"], ascending=[True, False])
    saida["tipo_ano"] = _por_ano(p, ["tipo"], total_por_ano)
    saida["modalidade_ano"] = _por_ano(p, ["modalidade"], total_por_ano)
    saida["orgao_ano"] = _por_ano(p, ["CodOrgao", "Orgao"], total_por_ano)
    nomes_funcao = _nome_unico(p, "CodFuncao", "Funcao")
    p["funcao"] = p["CodFuncao"].map(nomes_funcao)
    saida["funcao_ano"] = _por_ano(p, ["CodFuncao", "funcao"], total_por_ano)
    nomes_elemento = _nome_unico(p, "elemento", "NaturezaDespesa")
    p["elemento_nome"] = p["elemento"].map(nomes_elemento)
    saida["elemento_ano"] = _por_ano(p, ["elemento", "elemento_nome", "tipo"], total_por_ano)
    saida["recebedor_ano"] = _por_ano(p, ["recebedor"], total_por_ano)
    saida["fornecedores"] = tabela_fornecedores(p, empresas, anos)
    if not defl.empty:
        saida["deflator"] = defl
    return saida


def gravar(tabelas: dict[str, pd.DataFrame]) -> None:
    PASTA.mkdir(parents=True, exist_ok=True)
    for nome, df in tabelas.items():
        if df is None or df.empty:
            continue
        armazem.gravar(df, PASTA / f"{nome}.csv")
        log.info("refinado: %s (%d linhas)", nome, len(df))


def rodar(pagamentos: pd.DataFrame) -> dict[str, pd.DataFrame]:
    tabelas = refinar(pagamentos)
    gravar(tabelas)
    return tabelas


# ---------------------------------------------------------------- relatório

def _mi(v) -> str:
    try:
        return f"{float(v) / 1e6:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return "—"


def _tabela_md(df: pd.DataFrame) -> str:
    linhas = ["| " + " | ".join(map(str, df.columns)) + " |", "|" + "---|" * len(df.columns)]
    linhas += ["| " + " | ".join(map(str, r)) + " |" for r in df.itertuples(index=False)]
    return "\n".join(linhas) + "\n"


def _pivot_md(df: pd.DataFrame, rotulo: str, coluna_rotulo: str, anos: list[int], top: int = 14) -> str:
    """Tabela rótulo × ano em R$ milhões, mais a coluna '% do último ano'."""
    df = df.copy()
    df["ano"] = pd.to_numeric(df["ano"], errors="coerce").astype(int)
    df["pago"] = _num(df["pago"])
    piv = df.pivot_table(index=rotulo, columns="ano", values="pago", aggfunc="sum").fillna(0)
    anos = [a for a in anos if a in piv.columns]
    if not anos:
        return ""
    ultimo = anos[-1]
    piv = piv[anos].sort_values(ultimo, ascending=False).head(top)
    total_ultimo = _num(df.loc[df["ano"] == ultimo, "pago"]).sum()
    t = piv.map(_mi)
    t.insert(0, coluna_rotulo, piv.index)
    t[f"% em {ultimo}"] = (piv[ultimo] / total_ultimo if total_ultimo else 0).map(lambda x: f"{x:.1%}".replace(".", ","))
    return _tabela_md(t.reset_index(drop=True))


def secoes_markdown(anos_mostrar: int = 5) -> str:
    """Seções do relatório público geradas a partir de data/refinado/ (vazio se ainda não existe)."""
    origem = armazem.ler(PASTA / "origem_ano.csv")
    tipo = armazem.ler(PASTA / "tipo_ano.csv")
    recebedor = armazem.ler(PASTA / "recebedor_ano.csv")
    resumo = armazem.ler(PASTA / "resumo_ano.csv")
    if origem.empty or tipo.empty or resumo.empty:
        return ""
    anos = sorted(int(a) for a in resumo["ano"].unique())
    # o ano corrente é parcial: mostramos os últimos N fechados mais o corrente
    anos = anos[-anos_mostrar - 1:] if len(anos) > anos_mostrar else anos
    partes = [
        "## O mapa do dinheiro: de onde vem e em que é gasto (R$ milhões pagos sobre os empenhos de cada ano)\n",
        "Fonte: Portal da Transparência de Cariacica, campo \"fonte de recursos\" e \"natureza da despesa\" de cada "
        "empenho de todos os órgãos do município (Prefeitura, fundos, Câmara, IPC). Tabelas completas em "
        "`data/refinado/`; como cada código vira categoria, em `vigia/refino.py`. O último ano é parcial.\n",
        "### De onde vem o dinheiro que a prefeitura gasta\n",
        _pivot_md(origem, "origem_nome", "Origem", anos),
        "### Em que tipo de gasto\n",
        _pivot_md(tipo, "tipo", "Tipo de gasto", anos),
    ]
    if not recebedor.empty:
        partes += ["### Quem recebe\n", _pivot_md(recebedor, "recebedor", "Quem recebeu", anos)]
    r = resumo.copy()
    r["ano"] = pd.to_numeric(r["ano"], errors="coerce").astype(int)
    r = r[r["ano"].isin(anos)]
    t = pd.DataFrame({"Ano": r["ano"], "Pago (R$ mi)": r["pago"].map(_mi),
                      "Moradores": _num(r["populacao"]).map(lambda x: f"{x:,.0f}".replace(",", ".")),
                      "Por morador (R$)": _num(r["pago_por_morador"]).map(lambda x: f"{x:,.0f}".replace(",", "."))})
    if "pago_real_por_morador" in r.columns:
        base = r["ano_base_precos"].iloc[0]
        t[f"Por morador, a preços de {base} (R$)"] = _num(r["pago_real_por_morador"]).map(lambda x: f"{x:,.0f}".replace(",", "."))
        nota = f"Preços de {base} pelo IPCA médio de cada ano (IBGE, `data/ibge/ipca.csv`)."
    else:
        nota = "Valores nominais (o coletor do IPCA ainda não rodou; quando rodar, esta tabela ganha a coluna a preços constantes)."
    partes += [f"### Gasto por morador\n\nPopulação: a declarada ao Tesouro em cada ano (IBGE). {nota}\n", _tabela_md(t)]
    return "\n".join(partes)
