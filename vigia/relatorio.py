"""Gera docs/relatorio.md a partir dos dados coletados.

O relatório é refeito a cada coleta e fica versionado: o histórico do git
mostra como os números evoluíram.
"""
import re
from datetime import datetime

import pandas as pd

from . import armazem, indicadores, pedidos, refino
from .alertas.portal import _brl, _num, pagos_por_fornecedor
from .config import CARIACICA_IBGE, DADOS, DOCS, GRANDE_VITORIA

RE_FUNCAO = re.compile(r"^\d{2} - ")


def _coluna_liquidada(df: pd.DataFrame) -> str | None:
    cols = [c for c in df["coluna"].unique() if "liquidad" in c.lower()]
    return cols[0] if cols else None


def despesa_por_funcao() -> pd.DataFrame:
    """Linhas: (ano, município, função, valor liquidado)."""
    df = armazem.ler(DADOS / "siconfi" / "dca_despesa_funcao.csv")
    if df.empty:
        return df
    col = _coluna_liquidada(df)
    if not col:
        return pd.DataFrame()
    df = df[(df["coluna"] == col) & df["conta"].str.match(RE_FUNCAO)].copy()
    df["valor"] = _num(df["valor"])
    df["funcao"] = df["conta"].str.replace(RE_FUNCAO, "", regex=True)
    return df[["exercicio", "cod_ibge", "funcao", "valor"]]


def populacao() -> dict[int, float]:
    entes = armazem.ler(DADOS / "siconfi" / "entes.csv")
    if entes.empty or "populacao" not in entes.columns:
        return {}
    return {int(r["cod_ibge"]): float(r["populacao"] or 0) for _, r in entes.iterrows()}


def tabela(df: pd.DataFrame) -> str:
    if df.empty:
        return "_Sem dados ainda._\n"
    linhas = ["| " + " | ".join(map(str, df.columns)) + " |", "|" + "---|" * len(df.columns)]
    linhas += ["| " + " | ".join(map(str, r)) + " |" for r in df.itertuples(index=False)]
    return "\n".join(linhas) + "\n"


def secao_grande_vitoria(fun: pd.DataFrame, pop: dict) -> str:
    if fun.empty:
        return "## Gasto por habitante na Grande Vitória\n\n_Sem dados do Siconfi ainda._\n"
    ano = fun["exercicio"].max()
    tot = fun[fun["exercicio"] == ano].groupby("cod_ibge")["valor"].sum().reset_index()
    tot["cidade"] = tot["cod_ibge"].astype(int).map(GRANDE_VITORIA)
    tot["habitantes"] = tot["cod_ibge"].astype(int).map(pop)
    tot["por_habitante"] = tot["valor"] / tot["habitantes"]
    tot = tot.sort_values("por_habitante", ascending=False)
    t = pd.DataFrame({
        "Cidade": tot["cidade"],
        "Despesa liquidada": tot["valor"].map(_brl),
        "Habitantes": tot["habitantes"].map(lambda x: f"{x:,.0f}".replace(",", ".")),
        "Por habitante": tot["por_habitante"].map(_brl),
    })
    return f"## Gasto por habitante na Grande Vitória ({ano})\n\nFonte: Siconfi/Tesouro Nacional, DCA Anexo I-E.\n\n" + tabela(t)


def secao_funcoes_cariacica(fun: pd.DataFrame) -> str:
    c = fun[fun["cod_ibge"] == str(CARIACICA_IBGE)] if not fun.empty else fun
    if c.empty:
        return "## Para onde vai o dinheiro de Cariacica\n\n_Sem dados ainda._\n"
    piv = c.pivot_table(index="funcao", columns="exercicio", values="valor", aggfunc="sum").fillna(0)
    ultimo = piv.columns.max()
    piv = piv.sort_values(ultimo, ascending=False).head(12)
    total_ultimo = c[c["exercicio"] == ultimo]["valor"].sum()
    t = piv.map(lambda v: f"{v / 1e6:,.1f}".replace(",", "X").replace(".", ",").replace("X", "."))
    t.insert(0, "Área", piv.index)
    t[f"% em {ultimo}"] = (piv[ultimo] / total_ultimo).map(lambda x: f"{x:.1%}")
    return ("## Para onde vai o dinheiro de Cariacica (R$ milhões, despesa liquidada)\n\n"
            "Fonte: Siconfi/Tesouro Nacional, DCA Anexo I-E.\n\n" + tabela(t.reset_index(drop=True)))


def secao_fornecedores(contratos: pd.DataFrame) -> str:
    if contratos.empty:
        return "## Quem mais recebe contratos\n\n_Sem dados do PNCP ainda._\n"
    c = contratos.assign(valor=_num(contratos["valor_global"]))
    g = (c.groupby(["nome_fornecedor", "ni_fornecedor"], as_index=False)
         .agg(contratos=("id_pncp", "count"), valor=("valor", "sum"))
         .sort_values("valor", ascending=False).head(20))
    total = c["valor"].sum()
    t = pd.DataFrame({
        "Fornecedor": g["nome_fornecedor"], "CNPJ/CPF": g["ni_fornecedor"],
        "Contratos": g["contratos"], "Valor": g["valor"].map(_brl),
        "% do total": (g["valor"] / total).map(lambda x: f"{x:.1%}"),
    })
    periodo = f"{c['data_publicacao'].min()[:10]} a {c['data_publicacao'].max()[:10]}"
    return (f"## Quem mais recebe contratos ({periodo})\n\nFonte: PNCP. Total no período: {_brl(total)} "
            f"em {len(c)} contratos.\n\n" + tabela(t))


def secao_alertas(alertas: pd.DataFrame) -> str:
    if alertas.empty:
        return "## Alertas\n\n_Nenhum alerta gerado ainda._\n"
    resumo = (alertas.groupby(["regra", "nome_regra", "gravidade"]).size().reset_index(name="quantidade"))
    top = alertas.head(25).copy()
    top["fonte"] = top["link"].map(lambda l: f"[ver]({l})" if l else "")
    t = top[["id", "gravidade", "regra", "titulo", "pergunta", "fonte"]]
    return ("## Alertas (perguntas que merecem resposta)\n\n"
            "Um alerta não é acusação: é um padrão que pede explicação. Confira sempre a fonte.\n\n"
            + tabela(resumo) + "\n### Principais\n\n" + tabela(t))


def _mi(v: float) -> str:
    return f"{v / 1e6:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")


def secao_pagamentos(pagamentos: pd.DataFrame) -> str:
    """Quem mais recebeu dinheiro de fato (pagamentos), por ano. Fonte mais completa que o PNCP."""
    piv = pagos_por_fornecedor(pagamentos)
    if piv.empty:
        return "## Quem mais recebe dinheiro da prefeitura\n\n_Sem dados do portal municipal ainda._\n"
    anos = sorted(c for c in piv.columns if c != "fornecedor" and c >= "2021")
    piv["total"] = piv[anos].sum(axis=1)
    top = piv.sort_values("total", ascending=False).head(25)
    t = pd.DataFrame({"Fornecedor": top["fornecedor"], "CNPJ/CPF": top.index})
    for a in anos:
        t[a] = top[a].map(_mi)
    t["Total"] = top["total"].map(_mi)
    total_geral = piv["total"].sum()
    return (f"## Quem mais recebe dinheiro da prefeitura (R$ milhões pagos, {anos[0]}–{anos[-1]})\n\n"
            "Fonte: Portal da Transparência de Cariacica (pagamentos por empenho). Exclui folha de pagamento, "
            f"previdência, tributos e outros órgãos públicos. Total pago a empresas e pessoas no período: "
            f"R$ {_mi(total_geral)} mi; os 25 abaixo somam {top['total'].sum() / total_geral:.0%}.\n\n"
            + tabela(t.reset_index(drop=True)))


def secao_emergenciais(emergenciais: pd.DataFrame) -> str:
    if emergenciais.empty:
        return ""
    e = emergenciais.assign(valor=_num(emergenciais["ValorTotal"]))
    g = e.groupby("AnoContrato").agg(contratos=("valor", "size"), valor=("valor", "sum")).reset_index()
    t = pd.DataFrame({"Ano": g["AnoContrato"], "Contratos emergenciais": g["contratos"], "Valor (R$ mi)": g["valor"].map(_mi)})
    return ("## Contratos emergenciais (sem licitação)\n\n"
            "Fonte: Portal da Transparência de Cariacica. Emergência deve ser exceção e por prazo curto.\n\n" + tabela(t))


def secao_emendas_pix() -> str:
    """Emendas parlamentares Pix (transferências especiais) para Cariacica, por ano (Transferegov)."""
    e = armazem.ler(DADOS / "transferegov" / "emendas_pix_planos.csv")
    if e.empty or "ano_plano_acao" not in e.columns:
        return ""
    e = e.assign(valor=_num(e.get("valor_custeio_plano_acao", pd.Series(0, index=e.index)))
                 + _num(e.get("valor_investimento_plano_acao", pd.Series(0, index=e.index))))
    situacao = e.get("situacao_plano_acao", pd.Series("", index=e.index)).astype(str)
    e = e.assign(impedido=situacao.str.upper().str.contains("IMPEDID"))
    e = e.assign(valor_ok=e["valor"].where(~e["impedido"], 0.0))
    g = e.groupby("ano_plano_acao").agg(planos=("valor", "size"), valor=("valor_ok", "sum"),
                                        impedidos=("impedido", "sum")).reset_index()
    t = pd.DataFrame({"Ano": g["ano_plano_acao"], "Planos de ação": g["planos"],
                      "Valor (R$ mi, sem os impedidos)": g["valor"].map(_mi), "Impedidos": g["impedidos"].astype(int)})
    return ("## Emendas parlamentares \"Pix\" para Cariacica\n\n"
            "Fonte: Transferegov (transferências especiais, que caem direto no caixa da prefeitura). Plano "
            "\"impedido\" (com impedimento técnico registrado) não entra no valor. Lista completa, com parlamentar, "
            "área, situação, executores, metas e relatórios de gestão, em `data/transferegov/`.\n\n" + tabela(t))


def _secao_fundeb() -> str:
    from .coletores import tesouro
    return tesouro.secao_markdown()


def _secao_de(modulo: str) -> str:
    """Seção escrita pelo próprio coletor (vigia/coletores/<modulo>.py, função secao_markdown)."""
    import importlib
    return importlib.import_module(f".coletores.{modulo}", __package__).secao_markdown()


def _secao_segura(nome: str, funcao, *args) -> str:
    """Seção nova não derruba o relatório (nem os alertas do dia): erro vira aviso em docs/qualidade.md."""
    try:
        return funcao(*args)
    except Exception as e:
        from . import qualidade
        qualidade.REGISTRO.add(qualidade.Checagem("relatorio", "relatorio.md", f"secao_{nome}", False, False,
                                                  f"seção omitida: {type(e).__name__}: {str(e)[:150]}"))
        return ""


def gerar(alertas: pd.DataFrame, pagamentos: pd.DataFrame | None = None,
          emergenciais: pd.DataFrame | None = None) -> str:
    fun = despesa_por_funcao()
    contratos = armazem.ler(DADOS / "pncp" / "contratos.csv")
    vazio = pd.DataFrame()
    partes = [
        "# Vigia Cariacica: relatório automático\n",
        f"_Gerado em {datetime.now():%d/%m/%Y %H:%M} (UTC). Dados públicos oficiais; "
        "como cada dado é obtido em [METODOLOGIA.md](METODOLOGIA.md)._\n",
        _secao_segura("resultados", pedidos.secao_resultados),
        secao_funcoes_cariacica(fun),
        _secao_segura("mapa_do_dinheiro", refino.secoes_markdown),
        _secao_segura("indicadores", indicadores.secao_markdown, datetime.now().year),
        _secao_segura("fundeb", _secao_fundeb),
        _secao_segura("emendas_pix", secao_emendas_pix),
        _secao_segura("divida", _secao_de, "divida"),
        _secao_segura("folha", _secao_de, "folha"),
        _secao_segura("previdencia_cauc", _secao_de, "externos"),
        _secao_segura("estado", _secao_de, "estado"),
        _secao_segura("licitacoes", _secao_de, "licitacoes"),
        _secao_segura("fila", _secao_de, "fila"),
        secao_pagamentos(vazio if pagamentos is None else pagamentos),
        secao_emergenciais(vazio if emergenciais is None else emergenciais),
        secao_grande_vitoria(fun, populacao()),
        secao_fornecedores(contratos),
        _secao_segura("pedidos", pedidos.secao_markdown),
        secao_alertas(alertas),
        "## Limitações conhecidas\n\n"
        "- PNCP é obrigatório para municípios só desde abr/2023; antes disso a cobertura é parcial.\n"
        "- Comparação de preços (R01) depende de as descrições dos itens serem parecidas; serviços ficam de fora.\n"
        "- \"Aditivo\" no portal municipal soma prorrogações de prazo (legais em serviços contínuos) e acréscimos "
        "de objeto (limitados a 25%); o alerta pede que a prefeitura diga qual foi o caso.\n"
        "- O ano corrente é parcial. Pagamentos de um ano podem incluir restos a pagar de anos anteriores.\n"
        "- Valores são declarados pela prefeitura; divergências devem ser checadas com o TCE-ES.\n",
    ]
    texto = "\n".join(partes)
    DOCS.mkdir(exist_ok=True)
    (DOCS / "relatorio.md").write_text(texto, encoding="utf-8")
    return texto
