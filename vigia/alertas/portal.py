"""Regras R21–R27, R29 e R30, sobre o portal da transparência da prefeitura (pagamentos, contratos e licitações).
R25 cruza os pagamentos com as empresas contratadas por campanhas eleitorais (TSE); R26 cruza os
contratos emergenciais com as licitações publicadas no PNCP, e R27 faz o mesmo com os contratos de serviço que
chegam ao teto de prazo.

Regra de ouro do Vigia: um alerta é uma PERGUNTA, não uma acusação. Cada alerta traz o dado,
a regra que o disparou e o link da fonte oficial. A pergunta de cada regra está em vigia/regras.py.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd

from .. import armazem
from ..config import ALERTAS, DADOS
from ..texto import formatar_cnpj, so_digitos


@dataclass
class Alerta:
    regra: str              # código do catálogo (R21–R30)
    gravidade: str          # "alta" | "media" | "baixa"
    titulo: str             # o fato, em uma frase
    detalhe: str            # contexto e números
    valor: float
    fornecedor: str
    fornecedor_doc: str
    referencia: str         # ano, contrato ou período
    link: str
    data: str = ""          # AAAA-MM-DD de referência
    outros_links: list[str] = field(default_factory=list)   # mais fontes oficiais (ex.: um link por ano)


def _num(serie: pd.Series) -> pd.Series:
    return pd.to_numeric(serie, errors="coerce").fillna(0.0)


def _anos(v: float) -> str:
    return f"{v:.1f}".replace(".", ",")


def _brl(v: float) -> str:
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ---------------------------------------------------------------------------
# Alertas sobre o Portal da Transparência municipal (pagamentos e contratos)
# ---------------------------------------------------------------------------

# Órgãos públicos, folha e tributos aparecem como "fornecedores" nos pagamentos.
# Não são compras, então ficam fora dos rankings e alertas de fornecedor.
RE_ENTE_PUBLICO = re.compile(
    r"FOLHA DE PAGAMENTO|PREFEITURA|PREVID|^IPC\b|\bINSS\b|RECEITA FEDERAL|C[AÂ]MARA MUNICIPAL|TRIBUNAL|"
    r"CAIXA ECON[OÔ]MICA.*D[IÍ]VIDA|SECRETARIA|MINIST[EÉ]RIO|FUNDO MUNICIPAL|FUNDO NACIONAL|"
    r"PASEP|BANCO DO BRASIL|BANCO DO ESTADO|BANESTES|CONS[OÓ]RCIO P[UÚ]BLICO|GOVERNO DO ESTADO|"
    r"UNI[AÃ]O FEDERAL|MUNIC[IÍ]PIO DE", re.I)
DOC_FOLHA = "99.999.999/9999-99"


UG_ID = {"PREFEITURA": 6, "IPC PREVIDENCIA": 3, "INSTITUTO DE DESENVOLVIMENTO": 26}  # api/UnidadesGestoras


def link_contratos_portal(rota: str, unidade: str, ano) -> str:
    """CSV oficial do portal com os contratos da unidade gestora no ano (o contrato está pelo número).
    rota: "contratos" ou "contratos-emergenciais"."""
    ug = UG_ID.get(str(unidade or "").upper(), 6)
    return f"https://wstransparencia.cariacica.es.gov.br/api/{rota}/csv?unidadeGestoraId={ug}&exercicio={ano}"


def _iso(data_br) -> str:
    """'23/12/2025' -> '2025-12-23' (vazio se não der para ler)."""
    d = pd.to_datetime(str(data_br or ""), dayfirst=True, errors="coerce")
    return "" if pd.isna(d) else d.strftime("%Y-%m-%d")


def link_pagamentos(doc: str, ano: int | str) -> str:
    """Consulta oficial da prefeitura com o total pago a um fornecedor no ano."""
    from urllib.parse import quote
    return (f"https://wstransparencia.cariacica.es.gov.br/api/despesa/fornecedor?"
            f"exercicio={ano}&nomeCPFCNPJ={quote(str(doc))}")


def eh_ente_publico(nome: str, doc: str = "") -> bool:
    return doc == DOC_FOLHA or bool(RE_ENTE_PUBLICO.search(str(nome)))


def pagos_por_fornecedor(pagamentos: pd.DataFrame) -> pd.DataFrame:
    """Tabela fornecedor x ano com o valor pago, só empresas e pessoas (sem entes públicos)."""
    if pagamentos.empty:
        return pd.DataFrame()
    df = pagamentos.assign(valor=_num(pagamentos["ValorPago"]), ano=pagamentos["Ano"].astype(str))
    df = df[~df.apply(lambda r: eh_ente_publico(r["NomeFornecedor"], r["CpfCnpjFornecedor"]), axis=1)]
    # O mesmo CNPJ às vezes aparece com nomes ligeiramente diferentes; o CNPJ manda.
    nomes = df.groupby("CpfCnpjFornecedor")["NomeFornecedor"].agg(lambda s: s.value_counts().index[0])
    piv = df.pivot_table(index="CpfCnpjFornecedor", columns="ano", values="valor", aggfunc="sum").fillna(0.0)
    piv.insert(0, "fornecedor", piv.index.map(nomes))
    return piv


def crescimento_fornecedor(piv: pd.DataFrame, minimo: float = 5_000_000, fator: float = 4.0) -> list[Alerta]:
    """Fornecedor que passou a receber muito mais que nos anos anteriores.
    Explicações legítimas existem (contrato novo licitado, obra grande), mas o salto pede transparência."""
    if piv.empty:
        return []
    anos = sorted(c for c in piv.columns if c != "fornecedor")
    out = []
    for i, ano in enumerate(anos):
        if i < 2:
            continue
        anteriores = piv[anos[max(0, i - 3):i]].max(axis=1)
        atual = piv[ano]
        sel = piv[(atual >= minimo) & (atual >= fator * anteriores)]
        for doc, r in sel.iterrows():
            antes = float(anteriores.loc[doc])
            if antes == 0 and doc in piv.index and piv.loc[doc, anos[:i]].sum() == 0:
                base = "nada"
            else:
                base = f"no máximo {_brl(antes)} por ano"
            out.append(Alerta(
                regra="R21",
                gravidade="alta" if atual[doc] >= 20_000_000 else "media",
                titulo=f"{r['fornecedor']}: {_brl(atual[doc])} pagos sobre empenhos de {ano}",
                detalhe=(f"Valor pago até hoje sobre os empenhos feitos em {ano} (pode incluir pagamentos em anos "
                         f"seguintes). Nos três anos anteriores: {base}."),
                valor=float(atual[doc]), fornecedor=r["fornecedor"], fornecedor_doc=doc,
                referencia=str(ano), link=link_pagamentos(doc, ano), data=f"{ano}-12-31",
            ))
    return out


REAJUSTE_ANUAL_MAXIMO = 0.06    # teto conservador de reajuste por ano (IPCA 2021–2026 ficou abaixo disso na média)


def _fator_prorrogacao(anos: float, reajuste: float = REAJUSTE_ANUAL_MAXIMO) -> float:
    """Quantas vezes o valor de 12 meses cabe em `anos` de vigência, com reajuste anual composto."""
    inteiros = int(anos)
    soma = sum((1 + reajuste) ** k for k in range(inteiros))
    return soma + (anos - inteiros) * (1 + reajuste) ** inteiros


def aditivos_municipais(contratos_mun: pd.DataFrame, minimo: float = 500_000) -> list[Alerta]:
    """Contratos do portal municipal cujo aditivo passa de 25% do valor original.

    O portal só publica o TOTAL dos aditivos, sem dizer quanto foi prorrogação de prazo, reajuste pela
    inflação ou acréscimo de objeto. Prorrogar serviço contínuo e reajustar são permitidos; acréscimo tem
    limite de 25% (e ele se repete em cada ano prorrogado, porque aumenta o valor anual). Por isso esta
    regra é uma TRIAGEM e nunca dá gravidade alta (revisão de 08/11/2026): um contrato 100% legal, com 25%
    de acréscimo no 2º ano e 4 anos de vigência, já passa de 2 vezes o valor original. Supondo 12 meses no
    valor original e reajuste de até 6% ao ano, calcula-se:
      - o que a prorrogação com reajuste explica;
      - o máximo com acréscimo de 25% desde o primeiro dia (teto).
    Média quando o total passa do teto (ou sobra R$ 1 mi e 25% além da prorrogação); baixa no resto.
    Alta só vem dos termos aditivos de verdade (regra R03, com os termos do PNCP)."""
    if contratos_mun.empty:
        return []
    df = contratos_mun.assign(orig=_num(contratos_mun["ValorContratado"]), adit=_num(contratos_mun["Aditivo"]))
    df = df[(df["orig"] >= minimo) & (df["adit"] > ALERTAS["aditivo_pct"] * df["orig"])].copy()
    sem_data = pd.Series(pd.NA, index=df.index, dtype="object")
    ini = pd.to_datetime(df.get("DataInicio", sem_data), dayfirst=True, errors="coerce")
    fim = pd.to_datetime(df.get("DataFinal", sem_data), dayfirst=True, errors="coerce")
    df["anos"] = ((fim - ini).dt.days / 365.25).clip(lower=1).fillna(1).round(1)
    df["total"] = df["orig"] + df["adit"]
    df["explicado"] = df["orig"] * df["anos"].map(_fator_prorrogacao)
    df["teto"] = df["explicado"] * (1 + ALERTAS["aditivo_pct"])
    df["sobra"] = (df["total"] - df["explicado"]).clip(lower=0)
    df["alem_do_teto"] = (df["total"] - df["teto"]).clip(lower=0)
    out = []
    for _, r in df.sort_values(["alem_do_teto", "sobra", "adit"], ascending=False).iterrows():
        sobra_pct = r["sobra"] / r["orig"]
        if r["alem_do_teto"] > 0 or (sobra_pct > ALERTAS["aditivo_pct"] and r["sobra"] >= 1_000_000):
            gravidade = "media"
        else:
            gravidade = "baixa"
        base = (f"Começou em {_brl(r['orig'])}; os aditivos somam {_brl(r['adit'])}. O portal não separa prorrogação, "
                f"reajuste e acréscimo. Supondo 12 meses no valor original e reajuste de até 6% ao ano, os "
                f"{_anos(r['anos'])} anos de vigência explicariam cerca de {_brl(r['explicado'])}")
        if r["alem_do_teto"] > 0:
            leitura = (f"{base}; mesmo com acréscimo máximo de 25% desde o início, o total chegaria a "
                       f"{_brl(r['teto'])}, e ele passa disso em {_brl(r['alem_do_teto'])}.")
        elif r["sobra"] > 0:
            leitura = (f"{base}; o total passa disso em {_brl(r['sobra'])}, dentro do que um acréscimo de até 25% "
                       f"permitiria. Só os termos aditivos dizem se o limite foi respeitado.")
        else:
            leitura = f"{base}, o que cobre o total."
        out.append(Alerta(
            regra="R22",
            gravidade=gravidade,
            titulo=(f"Contrato {r['NumeroContrato']}/{r['AnoContrato']} com {r['Fornecedor']}: valor total de "
                    f"{_brl(r['total'])} ({_vezes(r['total'] / r['orig'])} o original) em {_anos(r['anos'])} anos"),
            detalhe=f"Objeto: {str(r['Objeto'])[:160]}. {leitura}",
            valor=float(r["adit"]),
            fornecedor=r["Fornecedor"], fornecedor_doc=r["CPFCNPJ"],
            referencia=f"contrato {r['NumeroContrato']}/{r['AnoContrato']}",
            link=link_contratos_portal("contratos", r.get("UnidadeGestora"), r["AnoContrato"]),
            data=_iso(r.get("DataAssinatura")),
        ))
    return out


def _vezes(x: float) -> str:
    return f"{x:.1f}".replace(".", ",") + " vezes"


def contratos_emergenciais(emergenciais: pd.DataFrame, minimo: float = 1_000_000) -> list[Alerta]:
    """Contratação emergencial dispensa licitação. Deve ser exceção, por prazo curto."""
    if emergenciais.empty:
        return []
    df = emergenciais.assign(valor=_num(emergenciais["ValorTotal"]))
    out = []
    for _, r in df[df["valor"] >= minimo].sort_values("valor", ascending=False).iterrows():
        out.append(Alerta(
            regra="R23",
            gravidade="alta" if r["valor"] >= 10_000_000 else "media",
            titulo=(f"Contrato emergencial (sem licitação) {r['NumeroContrato']}/{r['AnoContrato']} com "
                    f"{r['Fornecedor']}: {_brl(r['valor'])}"),
            detalhe=f"Objeto: {str(r['Objeto'])[:160]}.",
            valor=float(r["valor"]), fornecedor=r["Fornecedor"], fornecedor_doc=r["CPFCNPJ"],
            referencia=f"contrato {r['NumeroContrato']}/{r['AnoContrato']}",
            link=link_contratos_portal("contratos-emergenciais", r.get("UnidadeGestora"), r["AnoContrato"]),
            data=_iso(r.get("DataAssinatura")),
        ))
    return out


LICITACOES_PNCP = DADOS / "pncp" / "contratacoes.csv"   # compras de Cariacica publicadas no PNCP
JANELA_FIM_EMERGENCIA = 150      # dias: uma licitação leva de 3 a 6 meses
SIMILARIDADE_SUBSTITUTA = 0.4    # mesma régua da R20
RE_OBRA_PONTUAL = re.compile(r"encosta|conten[cç][aã]o|calamidade|enchente|chuva|desabamento|deslizamento", re.I)


def emergencia_sem_substituta(emergenciais: pd.DataFrame, licitacoes: pd.DataFrame, hoje: pd.Timestamp | None = None,
                              minimo: float = 200_000) -> list[Alerta]:
    """R26: contrato emergencial que termina nos próximos meses sem licitação parecida publicada no PNCP depois
    do início da emergência. A lei não deixa prorrogar nem repetir a emergência (art. 75, VIII), então, sem
    licitação a caminho, a próxima emergência já está contratada. É a pergunta antes do problema, não depois."""
    if emergenciais.empty:
        return []
    from ..texto import jaccard, tokens
    from .motor import GENERICOS_CONTRATACAO
    hoje = pd.Timestamp(hoje or pd.Timestamp.today()).normalize()
    df = emergenciais.assign(valor=_num(emergenciais["ValorTotal"]),
                             inicio=pd.to_datetime(emergenciais["DataInicio"], dayfirst=True, errors="coerce"),
                             fim=pd.to_datetime(emergenciais["DataFinal"], dayfirst=True, errors="coerce"))
    df = df[(df["fim"] >= hoje) & (df["fim"] <= hoje + pd.Timedelta(days=JANELA_FIM_EMERGENCIA))
            & (df["valor"] >= minimo) & ~df["Situacao"].astype(str).str.contains("ENCERR|CANCEL|RESCI", case=False)
            & ~df["Objeto"].astype(str).str.contains(RE_OBRA_PONTUAL)]
    if df.empty:
        return []
    lic = licitacoes if licitacoes is not None else pd.DataFrame()
    if not lic.empty:
        lic = lic[~lic["modalidade_nome"].astype(str).str.contains("Dispensa|Inexigibilidade", case=False)]
        lic = lic.assign(pub=pd.to_datetime(lic["data_publicacao"], errors="coerce"),
                         tks=lic["objeto"].map(lambda o: tokens(o) - GENERICOS_CONTRATACAO))
    out = []
    for _, r in df.sort_values("fim").iterrows():
        tks = tokens(r["Objeto"]) - GENERICOS_CONTRATACAO
        depois = lic[lic["pub"] >= r["inicio"]] if not lic.empty and pd.notna(r["inicio"]) else lic
        if not depois.empty and depois["tks"].map(lambda t: jaccard(tks, t)).max() >= SIMILARIDADE_SUBSTITUTA:
            continue
        dias = (r["fim"] - hoje).days
        out.append(Alerta(
            regra="R26",
            gravidade="media" if r["valor"] >= 1_000_000 else "baixa",
            titulo=(f"Emergencial {r['NumeroContrato']}/{r['AnoContrato']} com {r['Fornecedor']} termina em "
                    f"{r['fim']:%d/%m/%Y} sem licitação parecida no PNCP"),
            detalhe=(f"Contrato emergencial de {_brl(r['valor'])}, de {r['inicio']:%d/%m/%Y} a {r['fim']:%d/%m/%Y} "
                     f"(faltam {dias} dias). Objeto: {str(r['Objeto'])[:160]}. O Vigia procurou no PNCP uma "
                     f"licitação ou credenciamento de Cariacica com objeto parecido publicado depois do início da "
                     f"emergência e não achou. Chamamento de organização social pode não aparecer no PNCP."),
            valor=float(r["valor"]), fornecedor=r["Fornecedor"], fornecedor_doc=r["CPFCNPJ"],
            referencia=f"contrato {r['NumeroContrato']}/{r['AnoContrato']} fim {r['fim']:%Y-%m-%d}",
            link=link_contratos_portal("contratos-emergenciais", r.get("UnidadeGestora"), r["AnoContrato"]),
            data=r["fim"].strftime("%Y-%m-%d"),
        ))
    return out


PRAZO_LIMITE_DIAS = 1790          # 60 meses: teto dos serviços contínuos na Lei 8.666 (art. 57, II)
JANELA_LICITACAO_SUBSTITUTA = 540  # dias antes do fim em que uma licitação nova conta como substituta
RE_SERVICO = re.compile(r"servi[cç]o|presta[cç][aã]o|loca[cç][aã]o", re.I)


def contrato_no_limite_sem_substituta(contratos_mun: pd.DataFrame, licitacoes: pd.DataFrame,
                                      hoje: pd.Timestamp | None = None, minimo: float = 5_000_000) -> list[Alerta]:
    """R27: contrato de serviço que chega ao fim depois de 5 anos ou mais (o teto da Lei 8.666 para serviço
    contínuo) sem licitação parecida no PNCP. É o caso da limpeza das ruas em 02/12/2026: sem substituta, a saída
    costuma ser uma emergência. A R26 faz a mesma pergunta para os contratos que já são emergenciais."""
    if contratos_mun.empty:
        return []
    from ..texto import jaccard, tokens
    from .motor import GENERICOS_CONTRATACAO
    hoje = pd.Timestamp(hoje or pd.Timestamp.today()).normalize()
    df = contratos_mun.drop_duplicates(["NumeroContrato", "AnoContrato", "CPFCNPJ"])
    df = df.assign(valor=_num(df["ValorTotal"]),
                   inicio=pd.to_datetime(df["DataInicio"], dayfirst=True, errors="coerce"),
                   fim=pd.to_datetime(df["DataFinal"], dayfirst=True, errors="coerce"))
    df = df[(df["fim"] >= hoje) & (df["fim"] <= hoje + pd.Timedelta(days=JANELA_FIM_EMERGENCIA))
            & (df["valor"] >= minimo) & ((df["fim"] - df["inicio"]).dt.days >= PRAZO_LIMITE_DIAS)
            & df["TipoContrato"].astype(str).str.contains(RE_SERVICO)
            & ~df["Situacao"].astype(str).str.contains("ENCERR|CANCEL|RESCI", case=False)
            & ~df["Objeto"].astype(str).str.contains(RE_OBRA_PONTUAL)]
    if df.empty:
        return []
    lic = licitacoes if licitacoes is not None else pd.DataFrame()
    if not lic.empty:
        lic = lic[~lic["modalidade_nome"].astype(str).str.contains("Dispensa|Inexigibilidade", case=False)]
        lic = lic.assign(pub=pd.to_datetime(lic["data_publicacao"], errors="coerce"),
                         tks=lic["objeto"].map(lambda o: tokens(o) - GENERICOS_CONTRATACAO))
    out = []
    for _, r in df.sort_values("fim").iterrows():
        tks = tokens(r["Objeto"]) - GENERICOS_CONTRATACAO
        recentes = (lic[lic["pub"] >= r["fim"] - pd.Timedelta(days=JANELA_LICITACAO_SUBSTITUTA)]
                    if not lic.empty else lic)
        if not recentes.empty and recentes["tks"].map(lambda t: jaccard(tks, t)).max() >= SIMILARIDADE_SUBSTITUTA:
            continue
        meses = round((r["fim"] - r["inicio"]).days / 30.44)
        anual = r["valor"] / max(meses / 12, 1)
        dias = (r["fim"] - hoje).days
        out.append(Alerta(
            regra="R27",
            gravidade="alta" if anual >= 10_000_000 else "media",
            titulo=(f"Contrato {r['NumeroContrato']}/{r['AnoContrato']} com {r['Fornecedor']} termina em "
                    f"{r['fim']:%d/%m/%Y}, depois de {meses} meses, sem licitação parecida no PNCP"),
            detalhe=(f"Contrato de {_brl(r['valor'])} com aditivos (cerca de {_brl(anual)} por ano), de "
                     f"{r['inicio']:%d/%m/%Y} a {r['fim']:%d/%m/%Y} (faltam {dias} dias). Objeto: "
                     f"{str(r['Objeto'])[:160]}. Serviço contínuo com 60 meses ou mais está no teto de prazo da "
                     f"Lei 8.666 e precisa de licitação nova. O Vigia procurou no PNCP uma licitação de Cariacica "
                     f"com objeto parecido publicada nos 18 meses antes do fim e não achou."),
            valor=float(r["valor"]), fornecedor=r["Fornecedor"], fornecedor_doc=r["CPFCNPJ"],
            referencia=f"contrato {r['NumeroContrato']}/{r['AnoContrato']} fim {r['fim']:%Y-%m-%d}",
            link=link_contratos_portal("contratos", r.get("UnidadeGestora"), r["AnoContrato"]),
            data=r["fim"].strftime("%Y-%m-%d"),
        ))
    return out


def penalizado_recebendo(pagamentos: pd.DataFrame, penalizados: pd.DataFrame) -> list[Alerta]:
    """Pagamento feito a fornecedor durante o período em que estava punido pela própria prefeitura."""
    if pagamentos.empty or penalizados.empty:
        return []
    pen = penalizados.assign(
        ini=pd.to_datetime(penalizados["InicioSuspensao"], dayfirst=True, errors="coerce"),
        fim=pd.to_datetime(penalizados["TerminoSuspensao"], dayfirst=True, errors="coerce"),
    ).dropna(subset=["ini"])
    pag = pagamentos.assign(data=pd.to_datetime(pagamentos["Data"].str[:10], dayfirst=True, errors="coerce"),
                            valor=_num(pagamentos["ValorPago"]))
    out = []
    for _, p in pen.iterrows():
        fim = p["fim"] if pd.notna(p["fim"]) else pd.Timestamp.max
        m = pag[(pag["CpfCnpjFornecedor"] == p["CPFCPNJ"]) & (pag["data"] >= p["ini"]) & (pag["data"] <= fim)]
        if m["valor"].sum() > 0:
            out.append(Alerta(
                regra="R24",
                gravidade="alta",
                titulo=(f"{p['Fornecedor']}: {_brl(m['valor'].sum())} pagos sobre empenhos feitos durante a "
                        f"punição ({p['TipoPenalidade']}) aplicada pela prefeitura"),
                detalhe=(f"Punição de {p['ini']:%d/%m/%Y} "
                         + (f"a {p['fim']:%d/%m/%Y}" if pd.notna(p['fim']) else "sem data de término")
                         + ". Valor pago até hoje sobre esses empenhos."),
                data=f"{p['ini']:%Y-%m-%d}",
                valor=float(m["valor"].sum()), fornecedor=p["Fornecedor"], fornecedor_doc=p["CPFCPNJ"],
                referencia=f"{p['ini']:%Y-%m-%d} a " + (f"{p['fim']:%Y-%m-%d}" if pd.notna(p['fim']) else "sem término"),
                link=link_pagamentos(p["CPFCPNJ"], p["ini"].year),
            ))
    return out


FORNECEDORES_CAMPANHA = DADOS / "tse" / "fornecedores_campanha.csv"   # vigia/coletores/tse.py
# R25 fica de fora quando o VÍNCULO COM A CAMPANHA não indica escolha, porque é obrigação legal ou monopólio:
# - banco: toda campanha é obrigada a ter conta bancária própria (Lei 9.504/1997, art. 22) e paga tarifa;
# - concessionária de energia elétrica, água encanada ou gás canalizado: fornecedor único na cidade;
# - Correios: monopólio postal (Lei 6.538/1978, art. 9º).
# Combustível, telefonia, gráfica, locação etc. têm concorrência: a campanha escolheu o fornecedor, e a
# prefeitura também escolhe (licitação), então a pergunta vale. Decidido em 07/11/2026 (docs/DECISOES.md).
RE_CNAE_SEM_ESCOLHA = re.compile(
    r"distribui[cç][aã]o de energia el[eé]trica|capta[cç][aã]o, tratamento e distribui[cç][aã]o de [aá]gua|"
    r"distribui[cç][aã]o de combust[ií]veis gasosos por redes urbanas|"
    r"bancos? (m[uú]ltiplos|comerciais)|caixas econ[oô]micas|correio", re.I)
# Tipos de despesa de campanha que vêm dessas obrigações (a empresa sai só se TODAS as despesas forem delas)
RE_DESPESA_SEM_ESCOLHA = re.compile(r"^\s*(encargos financeiros.*|.*taxas banc[aá]rias.*|energia el[eé]trica|[aá]gua|"
                                    r"correspond[eê]ncias e despesas postais)\s*$", re.I)


def _numero(v) -> float:
    n = pd.to_numeric(v, errors="coerce")
    return 0.0 if pd.isna(n) else float(n)


def _lista_br(itens: list[str]) -> str:
    return itens[0] if len(itens) == 1 else ", ".join(itens[:-1]) + " e " + itens[-1]


def _periodo(anos: list[int]) -> str:
    return str(anos[0]) if len(anos) == 1 else f"{anos[0]} a {anos[-1]}"


def sem_escolha(cnae: str, tipos: set[str]) -> bool:
    """O vínculo com a campanha veio de obrigação legal ou monopólio (banco, concessionária, Correios)."""
    return bool(RE_CNAE_SEM_ESCOLHA.search(cnae or "")) or (bool(tipos) and all(RE_DESPESA_SEM_ESCOLHA.match(t) for t in tipos))


# Benefício de servidor pago por meio de uma empresa (cartão de auxílio-alimentação, vale-transporte): o dinheiro
# passa pela empresa e vai para os servidores; ela fica só com a taxa de administração do contrato. Em 09/11/2026,
# os R$ 51,5 mi de 2025 pagos a três administradoras de cartão eram todos auxílio-alimentação da folha.
RE_REPASSE_SERVIDOR = re.compile(r"AUX[IÍ]LIO[\s-]*(?:ALIMENTA|REFEI|TRANSPORTE)|VALE[\s-]*(?:TRANSPORTE|ALIMENTA|REFEI)", re.I)


def fornecedor_de_campanha(pagamentos: pd.DataFrame, campanha: pd.DataFrame, minimo: float = 1_000_000,
                           medio: float = 10_000_000, excluidos: list | None = None) -> list[Alerta]:
    """Empresa contratada por candidaturas de Cariacica em eleição municipal (TSE) que, nos anos seguintes à
    (primeira) eleição, recebeu da prefeitura pelo menos `minimo`.

    Um alerta por CNPJ: se a empresa atendeu campanhas em 2020 e 2024, cada ano de pagamento conta uma vez.
    O alerta mostra também o que a empresa já recebia ANTES da eleição (os dados do portal começam em 2019):
    quem já era fornecedora não "passou a receber" depois da campanha. Gravidade média só quando recebeu
    pelo menos `medio` depois e menos de `minimo` antes; senão, baixa. Quando a maior parte do valor é benefício
    de servidor repassado pela empresa (RE_REPASSE_SERVIDOR), o alerta diz isso e fica em baixa: o valor não mede
    o que a empresa recebeu para si.

    Prestar serviço a campanha não é ilegal. A entrada (data/tse/fornecedores_campanha.csv) não tem nome de
    candidato nem de partido, e nenhum alerta cita um. Ficam de fora órgãos e bancos públicos (RE_ENTE_PUBLICO)
    e os vínculos que não indicam escolha (sem_escolha); cada empresa excluída que passaria do mínimo é
    devolvida em `excluidos` (vai para docs/qualidade.md, para que a exclusão fique à vista)."""
    if pagamentos.empty or campanha.empty:
        return []
    camp = campanha.assign(doc=campanha["cnpj"].map(so_digitos),
                           eleicao=pd.to_numeric(campanha["ano_eleicao"], errors="coerce"))
    camp = camp[(camp["doc"].str.len() == 14) & camp["eleicao"].notna()]
    natureza = pagamentos["NaturezaDespesa"] if "NaturezaDespesa" in pagamentos else pd.Series("", index=pagamentos.index)
    pag = pagamentos.assign(doc=pagamentos["CpfCnpjFornecedor"].map(so_digitos),
                            ano=pd.to_numeric(pagamentos["Ano"], errors="coerce"), valor=_num(pagamentos["ValorPago"]),
                            repasse=natureza.astype(str).str.contains(RE_REPASSE_SERVIDOR))
    if pag["ano"].notna().sum() == 0:
        return []
    primeiro_ano_dados = int(pag["ano"].min())        # do portal inteiro, não só destas empresas
    pag = pag[pag["doc"].isin(set(camp["doc"])) & pag["ano"].notna()]
    if pag.empty:
        return []
    soma = pag.groupby(["doc", "ano"])["valor"].sum()
    soma_repasse = pag[pag["repasse"]].groupby(["doc", "ano"])["valor"].sum()
    nomes = pag.groupby("doc")["NomeFornecedor"].agg(lambda s: s.value_counts().index[0])
    out = []
    for doc, linhas in camp.groupby("doc", sort=True):
        if doc not in nomes.index:
            continue
        nome = nomes[doc]
        linhas = linhas.sort_values("eleicao")
        eleicoes = [int(e) for e in linhas["eleicao"]]
        primeira = eleicoes[0]
        cnae = next((str(c).strip() for c in linhas.get("cnae", []) if str(c).strip()), "")
        tipos = {t.strip() for v in linhas.get("tipo_despesa", []) for t in str(v or "").split(";") if t.strip()}
        por_ano = soma.loc[doc]
        depois = por_ano[(por_ano.index > primeira) & (por_ano > 0)]
        total = float(depois.sum())
        if total < minimo:
            continue
        if eh_ente_publico(nome) or any(eh_ente_publico(f) for f in linhas.get("fornecedor", [])) or sem_escolha(cnae, tipos):
            if excluidos is not None:
                excluidos.append((formatar_cnpj(doc), nome, total))
            continue
        antes = por_ano[por_ano.index <= primeira]
        total_antes = float(antes[antes > 0].sum())
        anos = [int(a) for a in depois.index]
        partes_tse = []
        for _, c in linhas.iterrows():
            n = int(_numero(c.get("candidaturas")))
            cargos = _lista_br([x.strip().lower() for x in str(c.get("cargos", "")).split(",") if x.strip()] or ["cargos"])
            partes_tse.append(f"em {int(c['eleicao'])}, por {n} {'candidatura' if n == 1 else 'candidaturas'} a "
                              f"{cargos}, somando {_brl(_numero(c.get('valor_campanha')))}")
        if primeiro_ano_dados > primeira:
            antes_txt = (f"Os dados do portal começam em {primeiro_ano_dados}, depois da eleição: não dá para saber "
                         "se a empresa já recebia antes.")
        else:
            periodo_antes = _periodo(list(range(primeiro_ano_dados, primeira + 1)))
            antes_txt = (f"Antes, de {periodo_antes}, a prefeitura já tinha pago {_brl(total_antes)} à empresa."
                         if total_antes > 0 else
                         f"De {periodo_antes} (os dados do portal começam em {primeiro_ano_dados}), a prefeitura "
                         "não tinha pago nada à empresa.")
        repasse = float(soma_repasse.loc[doc][lambda x: x.index > primeira].sum()) if doc in soma_repasse.index else 0.0
        repasse_txt = ""
        if total and repasse / total >= 0.5:
            repasse_txt = (f" {round(repasse / total * 100)}% desse valor é auxílio-alimentação ou outro benefício de "
                           "servidores pago por meio da empresa (natureza da despesa no portal): o dinheiro passa pela "
                           "empresa e vai para os servidores; o que ela fica é a taxa de administração do contrato.")
        doc_fmt = formatar_cnpj(doc)
        rotulo = _lista_br([str(e) for e in eleicoes])
        out.append(Alerta(
            regra="R25",
            gravidade="media" if total >= medio and total_antes < minimo and not repasse_txt else "baixa",
            titulo=(f"{nome}: fornecedor de campanha eleitoral em Cariacica ({rotulo}) que depois recebeu "
                    f"{_brl(total)} da prefeitura ({_periodo(anos)})"
                    + ("; a maior parte é benefício de servidores repassado pela empresa" if repasse_txt else "")),
            detalhe=("Segundo as prestações de contas entregues ao TSE, a empresa foi contratada por campanhas "
                     "municipais de Cariacica " + "; ".join(partes_tse)
                     + (f" (atividade: {cnae})" if cnae else "") + ". "
                     f"Depois da eleição de {primeira}, a prefeitura pagou {_brl(total)} sobre empenhos de "
                     f"{_periodo(anos)} (" + "; ".join(f"{a}: {_brl(v)}" for a, v in zip(anos, depois.values)) + ")."
                     + repasse_txt + " " + antes_txt + " Prestar serviço a campanha não é ilegal; o cruzamento usa o mesmo critério "
                     "para todas as candidaturas e não cita candidatos nem partidos."),
            valor=total, fornecedor=nome, fornecedor_doc=doc_fmt, referencia="campanhas " + "/".join(map(str, eleicoes)),
            link=link_pagamentos(doc_fmt, int(depois.idxmax())), data=f"{anos[0]}-01-01",
            outros_links=[link_pagamentos(doc_fmt, a) for a in anos if a != int(depois.idxmax())],
        ))
    return out


# ---------------------------------------------------------------- licitações do portal (revisão de 12/11/2026)

RE_SEM_DISPUTA = re.compile(r"DISPENSA|INEXIG|ADES", re.I)
JANELA_PREVISIVEL_ANTES = 120     # dias: o contrato regular acabou até 4 meses antes da emergência...
JANELA_PREVISIVEL_DEPOIS = 60     # ...ou ainda estava valendo até 2 meses depois do início dela
SIMILARIDADE_PREVISIVEL = 0.3     # objeto parecido E mesma secretaria (as duas condições juntas)
DIAS_SELECAO_PARADA = 120         # licitação ou chamamento "em andamento"/"suspenso" há mais que isso
ANTECEDENCIA_MINIMA = 90          # licitação nova publicada a menos de 90 dias do fim do contrato antigo não chega a tempo
# O campo "Situação" do portal nem sempre é atualizado: em 13/11/2026 o chamamento 1/2023 (anulado em jan/2024) e o
# 2/2025 (vencedora declarada em 13/08/2025, revogado em dez/2025) do PA do Trevo ainda apareciam "Em Andamento".
# Cada correção aqui tem a data e o documento oficial que a prova; sem documento, não entra.
SITUACAO_CORRIGIDA = DADOS / "transparencia" / "situacao_corrigida.csv"


ARQUIVOS_PNCP = DADOS / "pncp" / "arquivos_compras.csv"   # títulos dos documentos de cada compra (coletor PNCP)
# Título do documento -> situação que ele prova. A ordem conta: o documento mais recente decide, e "retomada"
# (reabertura, nova data, republicação) desfaz uma suspensão anterior.
SITUACAO_POR_TITULO = [
    (re.compile(r"revoga", re.I), "Revogada"),
    (re.compile(r"anula", re.I), "Anulada"),
    (re.compile(r"suspens", re.I), "Suspensa"),
    (re.compile(r"reabert|retomad|nova data|republica|reagend", re.I), "Em Andamento"),
    (re.compile(r"homologa|adjudica|resultado final|ata de resultado", re.I), "Concluída"),
]


def _proc(v) -> str:
    """'23.790/2026' e '23790/2026' são o mesmo processo (o PNCP às vezes põe ponto de milhar)."""
    return re.sub(r"[^0-9/]", "", str(v))


def situacao_pelos_documentos(contratacoes: pd.DataFrame | None, arquivos: pd.DataFrame | None) -> pd.DataFrame:
    """Situação que os documentos do PNCP provam, por processo: o documento mais recente cujo título casa com
    SITUACAO_POR_TITULO decide. Sai no formato de data/transparencia/situacao_corrigida.csv (sem número: casa
    com o portal pelo processo), com o link da compra no PNCP como fonte."""
    cols = ["numero", "processo", "situacao", "desde", "fonte", "nota", "tipo_data"]
    if contratacoes is None or contratacoes.empty:
        return pd.DataFrame(columns=cols)
    if arquivos is None or arquivos.empty:
        arquivos = pd.DataFrame(columns=["id_pncp", "sequencial", "data_publicacao", "titulo", "ativo"])
    a = arquivos.copy()
    if "ativo" in a.columns:
        a = a[a["ativo"].astype(str).isin(["1", "1.0", "True", "true", ""])]
    a["dt"] = pd.to_datetime(a["data_publicacao"], errors="coerce")
    a = a.sort_values(["id_pncp", "dt", "sequencial"])
    comp = contratacoes.drop_duplicates("id_pncp").set_index("id_pncp")
    docs_por_compra = dict(tuple(a.groupby("id_pncp")))
    out = []
    for idp, c in comp.iterrows():
        sit, desde, titulo = None, None, ""
        por_data: dict = {}
        for _, d in docs_por_compra.get(idp, pd.DataFrame()).iterrows():
            for rx, s in SITUACAO_POR_TITULO:
                if rx.search(str(d["titulo"])):
                    sit, desde, titulo = s, d["dt"], str(d["titulo"])
                    por_data.setdefault(d["dt"], set()).add(s)
                    break
        if sit and len(por_data.get(desde, set())) > 1:
            # documentos que se contradizem na mesma data (ex.: aviso de suspensão e edital republicado enviados
            # juntos ao PNCP): não dá para saber qual vale, então o documento não prova nada
            sit, desde, titulo = None, None, ""
        nota = f"Documento no PNCP: \"{titulo[:80]}\" ({desde:%d/%m/%Y})." if sit and not pd.isna(desde) else ""
        if not sit or sit == "Em Andamento":
            # sem documento que prove: vale a situação que o próprio PNCP registra, sem data
            s_pncp = str(c.get("situacao", ""))
            if not re.search(r"suspens|revogad|anulad", s_pncp, re.I):
                continue
            sit, desde, nota = s_pncp.strip().capitalize(), None, f"Situação registrada no PNCP: {s_pncp}."
        dig = re.sub(r"\D", "", str(c.get("numero_compra", "")))
        ano = str(c.get("ano", "")).split(".")[0]
        out.append({"numero": f"{int(dig)}/{ano}" if dig and ano else "", "processo": _proc(c.get("processo", "")),
                    "situacao": sit,
                    "desde": "" if desde is None or pd.isna(desde) else f"{desde:%Y-%m-%d}",
                    "fonte": f"https://pncp.gov.br/app/editais/{c.get('cnpj_orgao', '')}/{c.get('ano', '')}/"
                             f"{str(c.get('sequencial', '')).split('.')[0]}",
                    "nota": nota,
                    # a data é a do envio do documento ao PNCP, não a do ato (o PNCP às vezes recebe vários
                    # documentos de uma vez, meses depois): o texto do alerta diz isso
                    "tipo_data": "pncp"})
    return pd.DataFrame(out, columns=cols)


def aplicar_correcoes(proc: pd.DataFrame, correcoes: pd.DataFrame | None) -> pd.DataFrame:
    """Troca a situação do portal pela situação provada por documento (numero + processo iguais) e acrescenta
    situacao_desde (AAAA-MM-DD, data do ato) e situacao_fonte. Sem correção, situacao_desde fica vazio."""
    if "situacao_desde" not in proc.columns:
        proc = proc.assign(situacao_desde="", situacao_fonte="", situacao_tipo_data="")
    if correcoes is None or correcoes.empty:
        return proc
    c = correcoes.fillna("").astype(str)
    chave = lambda df: df["numero"].astype(str).str.strip() + "|" + df["processo"].map(_proc)
    mapa = dict(zip(chave(c), c.to_dict("records")))
    # pelo processo sozinho só quando o portal tem uma única licitação com ele (o mesmo processo pode ter uma
    # concorrência anulada e a nova que a substituiu)
    procs = proc["processo"].map(_proc)
    unicos = set(procs[~procs.duplicated(keep=False)])
    mapa_proc = {k: v for k, v in zip(c["processo"].map(_proc), c.to_dict("records")) if k in unicos}
    for i, k in chave(proc).items():
        r = mapa.get(k) or mapa_proc.get(_proc(proc.at[i, "processo"]))
        if r:
            proc.at[i, "situacao"] = r["situacao"]
            proc.at[i, "situacao_desde"] = r.get("desde", "")
            proc.at[i, "situacao_fonte"] = r.get("fonte", "")
            # correção conferida à mão: a data é a do ato; deduzida do PNCP: a do envio do documento
            proc.at[i, "situacao_tipo_data"] = r.get("tipo_data", "") or "ato"
    return proc


def licitacoes_portal(pasta=None) -> pd.DataFrame:
    """data/transparencia/licitacoes_AAAA.csv (um item por linha) -> um processo por linha, com as colunas que as
    regras R26 e R27 já usam para o PNCP (modalidade_nome, data_publicacao, objeto) mais situacao e secretaria.
    O portal tem o que o PNCP não tem: chamamentos de organização social e os processos de antes de 2023."""
    from ..config import DADOS as _D
    pasta = pasta or (_D / "transparencia")
    partes = [armazem.ler(a) for a in sorted(pasta.glob("licitacoes_20*.csv"))]
    partes = [p for p in partes if not p.empty]
    if not partes:
        return pd.DataFrame(columns=["numero", "processo", "modalidade_nome", "data_publicacao", "objeto", "situacao",
                                     "secretaria", "situacao_desde", "situacao_fonte", "situacao_tipo_data"])
    df = pd.concat(partes, ignore_index=True).fillna("")
    proc = df.groupby(["Numero", "Processo", "Modalidade"], as_index=False).agg(
        situacao=("Situacao", "first"), objeto=("Objeto", "first"), secretaria=("Secretaria", "first"),
        data=("DataPublicacao", "first"))
    proc["data_publicacao"] = pd.to_datetime(proc["data"].str[:10], dayfirst=True, errors="coerce").dt.strftime("%Y-%m-%d")
    # dispensa e adesão entram com o nome que as regras do PNCP já excluem
    proc["modalidade_nome"] = proc["Modalidade"].where(~proc["Modalidade"].str.contains(RE_SEM_DISPUTA),
                                                       "Dispensa (portal: " + proc["Modalidade"] + ")")
    proc = proc.rename(columns={"Numero": "numero", "Processo": "processo"})[
        ["numero", "processo", "modalidade_nome", "data_publicacao", "objeto", "situacao", "secretaria"]]
    if pasta != (_D / "transparencia"):
        return aplicar_correcoes(proc, None)
    # primeiro o que os documentos do PNCP provam; por cima, as correções conferidas à mão (mandam mais)
    auto = situacao_pelos_documentos(armazem.ler(LICITACOES_PNCP), armazem.ler(ARQUIVOS_PNCP))
    proc = aplicar_correcoes(proc, auto)
    return aplicar_correcoes(proc, armazem.ler(SITUACAO_CORRIGIDA) if SITUACAO_CORRIGIDA.exists() else None)


# A lista oficial de contratos emergenciais do portal está incompleta: não tem 2023 e só traz um contrato de 2022, mas
# o objeto de contratos dessas épocas diz "em caráter emergencial" (ex.: o 85/2022 e o 153/2023 do PA do Trevo).
# "Urgência e emergência" (tipo de atendimento de saúde) não conta: só a forma da contratação.
RE_OBJETO_EMERGENCIAL = re.compile(
    r"car[aá]ter emerg[eê]ncial|contrata[cç][aã]o emerg[eê]ncial|emerg[eê]ncialmente|dispensa emerg[eê]ncial|"
    r"contrato emerg[eê]ncial|gest[aã]o emerg[eê]ncial|de forma emerg[eê]ncial|em regime emerg[eê]ncial|"
    r"situa[cç][aã]o emerg[eê]ncial", re.I)


def completar_emergenciais(emergenciais: pd.DataFrame, contratos_mun: pd.DataFrame) -> pd.DataFrame:
    """Lista oficial de emergenciais + contratos cujo objeto diz que a contratação foi emergencial e que a lista não
    tem (revisão de 13/11/2026). A coluna OrigemEmergencia diz de onde veio cada linha."""
    base = emergenciais.copy() if emergenciais is not None else pd.DataFrame()
    if not base.empty:
        base["OrigemEmergencia"] = "lista oficial do portal"
    if contratos_mun is None or contratos_mun.empty or "Objeto" not in contratos_mun.columns:
        return base
    m = contratos_mun[contratos_mun["Objeto"].fillna("").astype(str).str.contains(RE_OBJETO_EMERGENCIAL)]
    chave = lambda d: (d["NumeroContrato"].astype(str).str.strip() + "/" + d["AnoContrato"].astype(str).str.strip()
                       + "|" + d["CPFCNPJ"].astype(str).str.strip())
    if not base.empty:
        m = m[~chave(m).isin(set(chave(base)))]
    m = m.drop_duplicates(["NumeroContrato", "AnoContrato", "CPFCNPJ"]).assign(
        OrigemEmergencia="objeto do contrato (fora da lista oficial)")
    return pd.concat([base, m], ignore_index=True) if not base.empty else m.reset_index(drop=True)


def _sec(s) -> str:
    from ..texto import normalizar
    return normalizar(str(s)).replace("secretaria municipal de ", "").replace("secretaria municipal da ", "").strip()


def emergencia_previsivel(contratos_mun: pd.DataFrame, emergenciais: pd.DataFrame,
                          licitacoes: pd.DataFrame | None = None, minimo: float = 1_000_000) -> list[Alerta]:
    """R29: contrato emergencial que entra no lugar de um contrato regular da mesma secretaria, com objeto
    parecido, que acabou pouco antes (ou ainda nem tinha acabado). O fim do contrato regular estava escrito nele
    desde a assinatura: a emergência era previsível. Exemplo que deu origem à regra: a limpeza das escolas
    (contrato regular até 30/08/2026, pregão novo no PNCP em 28/07/2026, só 33 dias antes do fim, e emergência de
    R$ 42,3 mi a partir de 31/07/2026)."""
    if emergenciais.empty or contratos_mun.empty:
        return []
    from ..texto import jaccard, tokens
    from .motor import GENERICOS_CONTRATACAO
    emerg = emergenciais.drop_duplicates(["NumeroContrato", "AnoContrato", "CPFCNPJ"])
    emerg = emerg.assign(valor=_num(emerg["ValorTotal"]),
                         inicio=pd.to_datetime(emerg["DataInicio"], dayfirst=True, errors="coerce"),
                         sec=emerg["Secretaria"].map(_sec),
                         tks=emerg["Objeto"].map(lambda o: tokens(o) - GENERICOS_CONTRATACAO))
    emerg = emerg[(emerg["valor"] >= minimo) & emerg["inicio"].notna()
                  & ~emerg["Objeto"].astype(str).str.contains(RE_OBRA_PONTUAL)]
    chave_emerg = set(zip(emerg["NumeroContrato"], emerg["AnoContrato"]))
    reg = contratos_mun.drop_duplicates(["NumeroContrato", "AnoContrato", "CPFCNPJ"])
    reg = reg[~reg["Objeto"].astype(str).str.contains(r"emerg", case=False)
              & ~pd.Series(list(zip(reg["NumeroContrato"], reg["AnoContrato"])), index=reg.index).isin(chave_emerg)]
    reg = reg.assign(valor=_num(reg["ValorTotal"]),
                     inicio=pd.to_datetime(reg["DataInicio"], dayfirst=True, errors="coerce"),
                     fim=pd.to_datetime(reg["DataFinal"], dayfirst=True, errors="coerce"),
                     sec=reg["Secretaria"].map(_sec),
                     tks=reg["Objeto"].map(lambda o: tokens(o) - GENERICOS_CONTRATACAO))
    reg = reg[reg["fim"].notna() & reg["inicio"].notna()]
    lic = licitacoes if licitacoes is not None else pd.DataFrame()
    if not lic.empty:
        lic = lic[~lic["modalidade_nome"].astype(str).str.contains("Dispensa|Inexigibilidade", case=False)]
        lic = lic.assign(pub=pd.to_datetime(lic["data_publicacao"], errors="coerce"),
                         tks=lic["objeto"].map(lambda o: tokens(o) - GENERICOS_CONTRATACAO))
    out = []
    for _, e in emerg.sort_values("inicio").iterrows():
        cand = reg[(reg["sec"] == e["sec"])
                   & (reg["fim"] >= e["inicio"] - pd.Timedelta(days=JANELA_PREVISIVEL_ANTES))
                   & (reg["fim"] <= e["inicio"] + pd.Timedelta(days=JANELA_PREVISIVEL_DEPOIS))
                   & (reg["inicio"] < e["inicio"] - pd.Timedelta(days=180))]
        if cand.empty:
            continue
        sim = cand["tks"].map(lambda t: jaccard(e["tks"], t))
        if sim.max() < SIMILARIDADE_PREVISIVEL:
            continue
        r = cand.loc[sim.idxmax()]
        nova = ""
        if not lic.empty:
            parecidas = lic[lic["tks"].map(lambda t: jaccard(e["tks"], t)) >= SIMILARIDADE_SUBSTITUTA]
            a_tempo = parecidas[(parecidas["pub"] >= r["inicio"])
                                & (parecidas["pub"] <= r["fim"] - pd.Timedelta(days=ANTECEDENCIA_MINIMA))]
            if not a_tempo.empty:
                continue   # houve licitação nova com tempo: a emergência pode ter outro motivo
            tarde = parecidas[parecidas["pub"] > r["fim"] - pd.Timedelta(days=ANTECEDENCIA_MINIMA)].sort_values("pub")
            nova = (f" A primeira licitação parecida saiu só em {tarde['pub'].iloc[0]:%d/%m/%Y}, "
                    f"{(tarde['pub'].iloc[0] - r['fim']).days:+d} dias em relação ao fim do contrato antigo."
                    if not tarde.empty else " O Vigia não achou licitação parecida publicada depois.")
        anos = (r["fim"] - r["inicio"]).days / 365.25
        out.append(Alerta(
            regra="R29",
            gravidade="alta" if e["valor"] >= 10_000_000 else "media",
            titulo=(f"Emergência previsível: {e['Fornecedor']} ({e['NumeroContrato']}/{e['AnoContrato']}) entrou no "
                    f"lugar do contrato {r['NumeroContrato']}/{r['AnoContrato']}, que vencia em {r['fim']:%d/%m/%Y}"),
            detalhe=(f"Contrato emergencial de {_brl(e['valor'])} a partir de {e['inicio']:%d/%m/%Y}, na mesma "
                     f"secretaria e com objeto parecido ao contrato {r['NumeroContrato']}/{r['AnoContrato']} com "
                     f"{r['Fornecedor']} ({_brl(r['valor'])}, de {r['inicio']:%d/%m/%Y} a {r['fim']:%d/%m/%Y}, "
                     f"{anos:.1f} anos). A data do fim estava no contrato desde a assinatura. Nenhuma licitação "
                     f"parecida foi publicada com pelo menos {ANTECEDENCIA_MINIMA} dias de antecedência.{nova} Objeto da "
                     f"emergência: {str(e['Objeto'])[:150]}."),
            valor=float(e["valor"]), fornecedor=e["Fornecedor"], fornecedor_doc=e["CPFCNPJ"],
            referencia=f"contrato {e['NumeroContrato']}/{e['AnoContrato']} x {r['NumeroContrato']}/{r['AnoContrato']}",
            link=link_contratos_portal("contratos-emergenciais", e.get("UnidadeGestora"), e["AnoContrato"]),
            data=e["inicio"].strftime("%Y-%m-%d"),
            outros_links=[link_contratos_portal("contratos", r.get("UnidadeGestora"), r["AnoContrato"])],
        ))
    return out


def selecao_parada(licitacoes: pd.DataFrame, emergenciais: pd.DataFrame, hoje: pd.Timestamp | None = None,
                   minimo: float = 1_000_000) -> list[Alerta]:
    """R30: licitação ou chamamento do portal "em andamento" ou "suspenso", publicado há mais de DIAS_SELECAO_PARADA
    dias, enquanto um contrato emergencial com objeto parecido está valendo. Origem: o PA do Trevo, que passa de
    emergência em emergência. A situação vem do portal corrigida por documento (aplicar_correcoes): seleção
    anulada ou revogada sai da conta, e a suspensa mostra desde quando está suspensa."""
    if licitacoes is None or licitacoes.empty or emergenciais.empty or "situacao" not in licitacoes.columns:
        return []
    from ..texto import jaccard, tokens
    from .motor import GENERICOS_CONTRATACAO
    hoje = pd.Timestamp(hoje or pd.Timestamp.today()).normalize()
    lic = licitacoes[licitacoes["situacao"].astype(str).str.contains(r"andamento|suspens", case=False)
                     & ~licitacoes["modalidade_nome"].astype(str).str.contains("Dispensa", case=False)].copy()
    lic["pub"] = pd.to_datetime(lic["data_publicacao"], errors="coerce")
    lic = lic[lic["pub"].notna() & ((hoje - lic["pub"]).dt.days > DIAS_SELECAO_PARADA)]
    if lic.empty:
        return []
    lic["tks"] = lic["objeto"].map(lambda o: tokens(o) - GENERICOS_CONTRATACAO)
    emerg = emergenciais.drop_duplicates(["NumeroContrato", "AnoContrato", "CPFCNPJ"])
    emerg = emerg.assign(valor=_num(emerg["ValorTotal"]),
                         inicio=pd.to_datetime(emerg["DataInicio"], dayfirst=True, errors="coerce"),
                         fim=pd.to_datetime(emerg["DataFinal"], dayfirst=True, errors="coerce"),
                         tks=emerg["Objeto"].map(lambda o: tokens(o) - GENERICOS_CONTRATACAO))
    emerg = emerg[(emerg["fim"] >= hoje) & (emerg["inicio"] <= hoje) & (emerg["valor"] >= minimo)]
    lic["sec_n"] = lic["secretaria"].map(_sec) if "secretaria" in lic.columns else ""
    out = []
    for _, e in emerg.iterrows():
        sim = lic["tks"].map(lambda t: jaccard(e["tks"], t))
        # mesma secretaria (quando as duas dizem): a portaria da Administração não é substituída pelo pregão da
        # portaria da Saúde (erro achado na revisão de 13/11/2026)
        sec_e = _sec(e.get("Secretaria", "")) if "Secretaria" in emerg.columns else ""
        mesma_sec = (lic["sec_n"] == sec_e) | (lic["sec_n"] == "") | (sec_e == "")
        paradas = lic[(sim >= SIMILARIDADE_SUBSTITUTA) & mesma_sec].sort_values("pub")
        if paradas.empty:
            continue
        def _desde(p) -> str:
            d = pd.to_datetime(p.get("situacao_desde", ""), errors="coerce")
            if pd.isna(d):
                return ""
            if p.get("situacao_tipo_data", "") == "pncp":
                # data do envio do documento ao PNCP, que pode ser bem depois do ato: não vira "desde"
                return f"; aviso de {p['situacao'].lower().replace('suspensa', 'suspensão')} enviado ao PNCP em {d:%d/%m/%Y}"
            return f", {p['situacao'].lower()} desde {d:%d/%m/%Y} (há {(hoje - d).days} dias)"
        lista = "; ".join(f"{p['modalidade_nome']} {p['numero']} (situação: {p['situacao'].lower()}, publicada em "
                          f"{p['pub']:%d/%m/%Y}, há {(hoje - p['pub']).days} dias{_desde(p)})"
                          for _, p in paradas.iterrows())
        mais_antiga = (hoje - paradas["pub"].iloc[0]).days
        p0 = paradas.iloc[0]
        susp = _desde(p0) if p0.get("situacao_tipo_data", "") != "pncp" else f", {p0['situacao'].lower()}"
        out.append(Alerta(
            regra="R30",
            gravidade="alta" if e["valor"] >= 10_000_000 else "media",
            titulo=(f"Seleção sem conclusão há {mais_antiga} dias{susp.split(' (')[0]} enquanto a emergência com "
                    f"{e['Fornecedor']} ({e['NumeroContrato']}/{e['AnoContrato']}) está valendo"),
            detalhe=(f"Contrato emergencial de {_brl(e['valor'])}, de {e['inicio']:%d/%m/%Y} a {e['fim']:%d/%m/%Y}. "
                     f"No portal, a seleção para o mesmo serviço está assim: {lista}. Objeto: "
                     f"{str(e['Objeto'])[:150]}. A situação no portal pode estar desatualizada: é exatamente isso "
                     f"que a pergunta quer saber."),
            valor=float(e["valor"]), fornecedor=e["Fornecedor"], fornecedor_doc=e["CPFCNPJ"],
            referencia=f"contrato {e['NumeroContrato']}/{e['AnoContrato']}",
            link=link_contratos_portal("contratos-emergenciais", e.get("UnidadeGestora"), e["AnoContrato"]),
            data=hoje.strftime("%Y-%m-%d"),
        ))
    return out


# ---------------------------------------------------------------- R31 contrato sem publicação no PNCP
PNCP_CONTRATOS = DADOS / "pncp" / "contratos.csv"   # contratos de Cariacica publicados no PNCP
R31_DESDE = pd.Timestamp("2025-01-01")    # Lei 14.133 em vigor para tudo (a 8.666 acabou em 30/12/2023)
R31_CARENCIA_DIAS = 30                    # prazo de publicação (art. 94: 20 dias úteis) com folga
R31_MINIMO = 1_000_000
RE_SEM_PNCP = re.compile(r"autoriza[cç][aã]o de uso|permiss[aã]o de uso|concess[aã]o de uso|conv[eê]nio|"
                         r"termo de (?:colabora|fomento)", re.I)


def contrato_sem_pncp(contratos_mun: pd.DataFrame, emergenciais: pd.DataFrame, pncp: pd.DataFrame | None,
                      hoje: pd.Timestamp | None = None, minimo: float = R31_MINIMO) -> list[Alerta]:
    """R31: contrato do portal, assinado desde 2025, acima de R$ 1 mi e com mais de 30 dias, sem correspondente nos
    contratos de Cariacica publicados no PNCP. Correspondente = mesma raiz de CNPJ do fornecedor (8 dígitos: a matriz
    e as filiais) e mesmo número/ano, ou valor inicial ou global a menos de 1%. Pode ser falha da coleta ou número
    diferente no PNCP: por isso a gravidade é média e a pergunta é se foi publicado."""
    if pncp is None or pncp.empty:
        return []
    hoje = pd.Timestamp(hoje or pd.Timestamp.today().normalize())
    partes = [x for x in (contratos_mun, emergenciais) if x is not None and not x.empty]
    if not partes:
        return []
    base = pd.concat(partes, ignore_index=True)
    raiz = lambda s: s.astype(str).map(so_digitos).str[:8]
    pn = pncp.assign(raiz=raiz(pncp["ni_fornecedor"]),
                     num=pd.to_numeric(pncp["numero"].astype(str).str.extract(r"(\d+)")[0], errors="coerce"),
                     vi=_num(pncp["valor_inicial"]), vg=_num(pncp["valor_global"]))
    valor_col = "ValorContratado" if "ValorContratado" in base.columns else "ValorTotal"
    df = base.assign(valor=_num(base[valor_col]), doc=base["CPFCNPJ"].astype(str).map(so_digitos),
                     num=pd.to_numeric(base["NumeroContrato"].astype(str).str.extract(r"(\d+)")[0], errors="coerce"),
                     data=pd.to_datetime(base.get("DataAssinatura", base["DataInicio"]), dayfirst=True,
                                         errors="coerce").fillna(pd.to_datetime(base["DataInicio"], dayfirst=True,
                                                                                errors="coerce")))
    df = df[(df["doc"].str.len() == 14) & (df["valor"] >= minimo) & (df["data"] >= R31_DESDE)
            & (df["data"] <= hoje - pd.Timedelta(days=R31_CARENCIA_DIAS))]
    df = df[~df["Objeto"].astype(str).str.contains(RE_SEM_PNCP) & ~df.get("TipoContrato", pd.Series("", index=df.index))
            .astype(str).str.contains(RE_SEM_PNCP)]
    df = df.drop_duplicates(["AnoContrato", "NumeroContrato", "doc"])
    out = []
    for _, r in df.iterrows():
        q = pn[pn["raiz"] == r["doc"][:8]]
        if not q.empty and (((q["num"] == r["num"]) & (q["ano"].astype(str) == str(r["AnoContrato"]))).any()
                            or ((abs(q["vi"] - r["valor"]) <= 0.01 * r["valor"])
                                | (abs(q["vg"] - r["valor"]) <= 0.01 * r["valor"])).any()):
            continue
        dias = int((hoje - r["data"]).days)
        out.append(Alerta(
            regra="R31", gravidade="media",
            titulo=(f"Contrato {r['NumeroContrato']}/{r['AnoContrato']} com {r['Fornecedor']} "
                    f"({_brl(r['valor'])}) não aparece no PNCP"),
            detalhe=(f"Assinado em {r['data']:%d/%m/%Y}, há {dias} dias, por {r.get('Secretaria') or 'órgão não informado'}. "
                     + ("Nenhum contrato desse fornecedor aparece no PNCP com Cariacica. " if q.empty else
                        "O fornecedor tem outros contratos no PNCP, mas nenhum com este número ou valor. ")
                     + f"Objeto: {str(r['Objeto'])[:150]}. Pode estar publicado com outro número: é isso que a "
                       f"pergunta quer saber."),
            valor=float(r["valor"]), fornecedor=r["Fornecedor"], fornecedor_doc=r["CPFCNPJ"],
            referencia=f"contrato {r['NumeroContrato']}/{r['AnoContrato']}",
            link=link_contratos_portal("contratos", r.get("UnidadeGestora"), r["AnoContrato"]),
            outros_links=["https://pncp.gov.br/app/contratos?q=" + re.sub(r"\s+", "+", str(r["Fornecedor"]).strip())],
            data=f"{r['data']:%Y-%m-%d}",
        ))
    return out


# ---------------------------------------------------------------- R32 licitação presencial
R32_MINIMO = 1_000_000
R32_DESCONTO_BAIXO = 0.05


def licitacao_presencial(contratacoes: pd.DataFrame | None, contratos: pd.DataFrame | None,
                         hoje: pd.Timestamp | None = None, minimo: float = R32_MINIMO) -> list[Alerta]:
    """R32: licitação de Cariacica em forma presencial (PNCP, desde 2024), acima de R$ 1 mi. A Lei 14.133 manda fazer
    a licitação preferencialmente eletrônica; a presencial precisa ser motivada e a sessão gravada em áudio e vídeo
    (art. 17, §2º). A forma presencial limita quem disputa. Alta quando passa de R$ 10 mi e o contrato saiu com
    desconto menor que 5% sobre o estimado. Quando a abertura ainda não aconteceu, a pergunta é preventiva: ainda
    dá para pedir esclarecimento ou impugnar até 3 dias úteis antes (art. 164)."""
    if contratacoes is None or contratacoes.empty or "modalidade_nome" not in contratacoes.columns:
        return []
    hoje = pd.Timestamp(hoje or pd.Timestamp.today().normalize())
    c = contratacoes.assign(e=_num(contratacoes["valor_estimado"]),
                            pub=pd.to_datetime(contratacoes["data_publicacao"], errors="coerce"),
                            abre=pd.to_datetime(contratacoes["data_abertura"], errors="coerce"))
    c = c[c["modalidade_nome"].astype(str).str.contains("Presencial", case=False) & (c["e"] >= minimo)
          & (c["pub"] >= pd.Timestamp("2024-01-01"))].drop_duplicates("id_pncp")
    k = contratos if contratos is not None and not contratos.empty else pd.DataFrame(columns=["id_pncp_compra"])
    out = []
    for _, r in c.iterrows():
        ks = k[k["id_pncp_compra"] == r["id_pncp"]] if "id_pncp_compra" in k.columns else k.iloc[0:0]
        contratado = float(_num(ks["valor_global"]).sum()) if not ks.empty else 0.0
        desconto = 1 - contratado / r["e"] if contratado > 0 else None
        aberta = pd.notna(r["abre"]) and r["abre"] > hoje
        alta = desconto is not None and r["e"] >= 10_000_000 and desconto < R32_DESCONTO_BAIXO
        if aberta:
            situacao = (f"A abertura está marcada para {r['abre']:%d/%m/%Y}: ainda dá para pedir esclarecimento ou "
                        f"impugnar o edital até 3 dias úteis antes (Lei 14.133, art. 164).")
        elif desconto is not None:
            fornecedores = _lista_br(sorted(set(ks["nome_fornecedor"].astype(str))))
            pct = f"{desconto * 100:.1f}".replace(".", ",")
            situacao = f"Contratado com {fornecedores} por {_brl(contratado)}: desconto de {pct}% sobre o estimado."
        else:
            situacao = "O contrato resultante ainda não aparece no PNCP."
        out.append(Alerta(
            regra="R32", gravidade="alta" if alta else "media",
            titulo=(f"{r['modalidade_nome']} {r['numero_compra']}/{r['ano']} de {_brl(r['e'])} feita na forma "
                    f"presencial"),
            detalhe=(f"Publicada no PNCP em {r['pub']:%d/%m/%Y}. {situacao} Objeto: {str(r['objeto'])[:160]}."),
            valor=float(contratado or r["e"]), fornecedor=(ks["nome_fornecedor"].iloc[0] if not ks.empty else ""),
            fornecedor_doc=(ks["ni_fornecedor"].iloc[0] if not ks.empty else ""),
            referencia=f"compra {r['id_pncp']}",
            link=f"https://pncp.gov.br/app/editais/{r['cnpj_orgao']}/{r['ano']}/{int(float(r['sequencial']))}",
            data=f"{r['pub']:%Y-%m-%d}",
        ))
    return out


def todas(pagamentos: pd.DataFrame, contratos_mun: pd.DataFrame, emergenciais: pd.DataFrame,
          penalizados: pd.DataFrame, fornecedores_campanha: pd.DataFrame | None = None,
          licitacoes: pd.DataFrame | None = None) -> list[Alerta]:
    """Roda R21–R27 e R29 a R33 sobre os CSVs do portal. R25 lê data/tse/fornecedores_campanha.csv; R26, R27 e R29
    procuram licitação substituta no PNCP (data/pncp/contratacoes.csv) e, desde 12/11/2026, também nas
    licitações do próprio portal (que têm os chamamentos de organização social); R30 usa só as do portal."""
    if fornecedores_campanha is None:
        fornecedores_campanha = armazem.ler(FORNECEDORES_CAMPANHA)
    portal_lic = licitacoes_portal()
    if licitacoes is None:
        licitacoes = armazem.ler(LICITACOES_PNCP)
    todas_lic = pd.concat([x for x in (licitacoes, portal_lic) if x is not None and not x.empty], ignore_index=True) \
        if (licitacoes is not None and not licitacoes.empty) or not portal_lic.empty else pd.DataFrame()
    return (crescimento_fornecedor(pagos_por_fornecedor(pagamentos))
            + aditivos_municipais(contratos_mun)
            + contratos_emergenciais(emergenciais)
            + penalizado_recebendo(pagamentos, penalizados)
            + _r25_com_registro(pagamentos, fornecedores_campanha)
            + emergencia_sem_substituta(emergenciais, todas_lic)
            + contrato_no_limite_sem_substituta(contratos_mun, todas_lic)
            + emergencia_previsivel(contratos_mun, emergenciais, todas_lic)
            + selecao_parada(portal_lic, emergenciais)
            + contrato_sem_pncp(contratos_mun, emergenciais, armazem.ler(PNCP_CONTRATOS))
            + licitacao_presencial(licitacoes, armazem.ler(PNCP_CONTRATOS))
            + empenho_depois_do_contrato(pagamentos, contratos_mun, emergenciais))


def _r25_com_registro(pagamentos: pd.DataFrame, campanha: pd.DataFrame) -> list[Alerta]:
    from .. import qualidade
    excluidos: list = []
    alertas = fornecedor_de_campanha(pagamentos, campanha, excluidos=excluidos)
    for doc, nome, total in excluidos:
        qualidade.REGISTRO.notas.append(("R25", f"{nome} ({doc}): {_brl(total)} pagos depois da eleição; fora porque "
                                                "o vínculo com a campanha é obrigação legal ou monopólio (banco, "
                                                "concessionária, Correios) ou órgão público"))
    return alertas

# ---------------------------------------------------------------- R33 empenho depois do fim do contrato
R33_MINIMO = 500_000
R33_ALTA = 1_000_000
R33_JANELA_DIAS = 365          # olha só o primeiro ano depois do fim do último contrato
R33_INICIO_PROXIMO_DIAS = 30   # empenho feito pouco antes de um contrato novo começar é reserva para ele
R33_NATUREZA_BENS = r"MATERIA|EQUIP"


def _num_contrato(v) -> str:
    """'153 /2023' -> '153/2023'; 'Não informado' -> ''."""
    m = re.search(r"(\d+)\s*/\s*(\d{4})", str(v))
    return f"{int(m.group(1))}/{m.group(2)}" if m else ""


def empenho_depois_do_contrato(pagamentos: pd.DataFrame, contratos_mun: pd.DataFrame,
                               emergenciais: pd.DataFrame, minimo: float = R33_MINIMO) -> list[Alerta]:
    """R33: empenho com valor pago a um fornecedor, feito quando nenhum contrato dele estava valendo e até um ano
    depois do fim do último. Origem: o PA do Trevo, em que, depois do fim de três contratos de gestão, saíram
    pagamentos por outros processos, quase sempre sem número de contrato no empenho (13/11/2026). A data é a do
    empenho (o compromisso), não a do pagamento: resto a pagar de serviço prestado durante o contrato tem empenho
    de dentro da vigência e não entra."""
    if pagamentos is None or pagamentos.empty or contratos_mun is None or contratos_mun.empty:
        return []
    partes = [x for x in (contratos_mun, emergenciais) if x is not None and not x.empty]
    c = pd.concat(partes, ignore_index=True).drop_duplicates(["NumeroContrato", "AnoContrato", "CPFCNPJ"])
    c = c.assign(ini=pd.to_datetime(c["DataInicio"], dayfirst=True, errors="coerce"),
                 fim=pd.to_datetime(c["DataFinal"], dayfirst=True, errors="coerce"),
                 num=c["NumeroContrato"].astype(str).str.strip() + "/" + c["AnoContrato"].astype(str).str.strip())
    c = c.dropna(subset=["ini", "fim"])
    pag = pagamentos.assign(d=pd.to_datetime(pagamentos["Data"].astype(str).str[:10], dayfirst=True, errors="coerce"),
                            v=_num(pagamentos["ValorPago"]))
    pag = pag[(pag["v"] >= minimo) & pag["d"].notna() & pag["CpfCnpjFornecedor"].isin(set(c["CPFCNPJ"]))]
    # compra de bens pode ser feita só com nota de empenho (Lei 14.133, art. 95, II): fica de fora
    pag = pag[~pag["NaturezaDespesa"].astype(str).str.contains(R33_NATUREZA_BENS, case=False, regex=True)]
    out = []
    por_doc = dict(tuple(c.groupby("CPFCNPJ")))
    for _, r in pag.iterrows():
        cc = por_doc[r["CpfCnpjFornecedor"]]
        if ((cc["ini"] <= r["d"]) & (cc["fim"] >= r["d"])).any():
            continue
        # reserva para um contrato que começa logo depois (o empenho às vezes sai um dia antes)
        if ((cc["ini"] > r["d"]) & (cc["ini"] <= r["d"] + pd.Timedelta(days=R33_INICIO_PROXIMO_DIAS))).any():
            continue
        ant = cc[cc["fim"] < r["d"]]
        if ant.empty:
            continue
        ult = ant.sort_values("fim").iloc[-1]
        dias = (r["d"] - ult["fim"]).days
        if dias > R33_JANELA_DIAS:
            continue
        no_emp = _num_contrato(r.get("NumeroContrato", ""))
        sem_num = not no_emp
        out.append(Alerta(
            regra="R33",
            gravidade="alta" if r["v"] >= R33_ALTA else "media",
            titulo=(f"{r['NomeFornecedor']}: {_brl(r['v'])} pagos em empenho de {r['d']:%d/%m/%Y}, {dias} dias depois "
                    f"do fim do contrato {ult['num']}" + (", sem número de contrato no empenho" if sem_num else "")),
            detalhe=(f"Empenho {r.get('NumeroEmpenho', '')}, processo {r.get('NumeroProcesso', '')}, natureza "
                     f"{str(r.get('NaturezaDespesa', '')).strip().lower()}. O contrato {ult['num']} valeu de "
                     f"{ult['ini']:%d/%m/%Y} a {ult['fim']:%d/%m/%Y}, e nenhum outro contrato do fornecedor no portal "
                     f"cobre a data do empenho." + ("" if sem_num else f" O empenho cita o contrato {no_emp}.")
                     + f" Descrição: {str(r.get('Descricao', ''))[:180]}"),
            valor=float(r["v"]), fornecedor=r["NomeFornecedor"], fornecedor_doc=r["CpfCnpjFornecedor"],
            referencia=f"empenho {r.get('NumeroEmpenho', '')}",
            link=link_pagamentos(r["CpfCnpjFornecedor"], r["d"].year),
            data=f"{r['d']:%Y-%m-%d}",
        ))
    return out
