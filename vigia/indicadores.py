"""Indicadores do orçamento a partir dos dados mensais do TCE-ES (data/tcees/).

Arrecadação x previsão: compara o arrecadado no ano até o último mês disponível com o mesmo período
do ano anterior, projeta o ano no ritmo do ano anterior e mede a distância da previsão da LOA.
Aumento líquido da dotação (créditos adicionais menos cancelamentos): quanto o orçamento de despesa
cresceu desde a LOA, por fonte, SÓ quando o cálculo confere com o RREO do Tesouro (Siconfi).

Fonte 500 = "recursos não vinculados de impostos e transferências de impostos": o dinheiro livre
da prefeitura, que paga a maior parte dos créditos adicionais. É onde se mede o excesso de arrecadação.

Cuidados (revisão de 07/11/2026):
- As duas colunas do relatório usam o MESMO mês: o último que tem dado na fonte livre e no total.
- "Todas as fontes" exclui as receitas intraorçamentárias (classificação começando por 7 ou 8, ex.: a
  contribuição patronal paga ao IPC), que contariam o mesmo dinheiro duas vezes; o RREO faz o mesmo.
- O significado mês a mês de "PrevisaoAtualizada" no arquivo de despesas não é documentado. O código
  testa as leituras possíveis (valor do último mês ou soma dos meses) contra a "DOTAÇÃO ATUALIZADA" do
  RREO Anexo 01 do mesmo bimestre e só mostra o número se uma delas bater (tolerância de 2%).
- Nada aqui pode derrubar a execução: sem dado ou com dado estranho, a seção some e fica um aviso.
"""
from __future__ import annotations

import logging

import pandas as pd

from . import armazem
from .config import DADOS

log = logging.getLogger("vigia.indicadores")
FONTE_LIVRE = "500"
TOLERANCIA_RREO = 0.02
VALORES = ("Previsao", "Arrecadada", "Empenhada", "Liquidada", "Paga")


def _ler(conjunto: str, ano: int) -> pd.DataFrame:
    df = armazem.ler(DADOS / "tcees" / f"{conjunto}_{ano}.csv")
    if df.empty or "Mes" not in df.columns:
        return pd.DataFrame()
    df = df.copy()
    df["Mes"] = pd.to_numeric(df["Mes"], errors="coerce")
    df = df[df["Mes"].between(1, 12)]
    for c in df.columns:
        if c.startswith(VALORES):
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    return df


def _receitas(ano: int, fonte: str | None) -> pd.DataFrame:
    df = _ler("receitas", ano)
    if df.empty:
        return df
    if fonte:
        return df[df["CodigoFonteReduzida"] == fonte]
    return df[~df["ClassificacaoReceita"].astype(str).str.match(r"^[78]")]     # sem intraorçamentárias


def _ultimo_mes(df: pd.DataFrame) -> int | None:
    if df.empty:
        return None
    m = df.loc[df["Arrecadada"] != 0, "Mes"].max()
    return int(m) if pd.notna(m) else None


def mes_comum(ano: int) -> int | None:
    """Último mês com arrecadação na fonte livre E no total (as duas colunas comparam o mesmo período)."""
    meses = [_ultimo_mes(_receitas(ano, f)) for f in (FONTE_LIVRE, None)]
    return min(meses) if all(meses) else None


def arrecadacao(ano: int, fonte: str | None = FONTE_LIVRE, mes: int | None = None) -> dict | None:
    """Retorna os números do indicador, ou None se faltar o ano, o anterior ou o mês."""
    atual, anterior = _receitas(ano, fonte), _receitas(ano - 1, fonte)
    mes = mes or _ultimo_mes(atual)
    if atual.empty or anterior.empty or not mes:
        return None
    acum = atual.loc[atual["Mes"] <= mes, "Arrecadada"].sum()
    acum_ant = anterior.loc[anterior["Mes"] <= mes, "Arrecadada"].sum()
    total_ant = anterior["Arrecadada"].sum()
    previsao = atual["PrevisaoInicial"].sum()
    projecao = acum * (total_ant / acum_ant) if acum_ant else None
    return {
        "ano": ano, "fonte": fonte or "todas", "ate_mes": mes, "arrecadado": acum,
        "arrecadado_ano_anterior_mesmo_periodo": acum_ant,
        "variacao": (acum / acum_ant - 1) if acum_ant else None,
        "previsao_inicial": previsao, "projecao_no_ritmo_do_ano_anterior": projecao,
        "excesso_projetado": (projecao - previsao) if projecao is not None else None,
        "aumento_dotacao": aumento_dotacao(ano, fonte),
    }


# ---------------------------------------------------------------- dotação (créditos adicionais)

def _dotacao_tcees(d: pd.DataFrame, mes: int, leitura: str) -> float:
    if leitura == "ultimo_mes":
        return float(d.loc[d["Mes"] == mes, "PrevisaoAtualizada"].sum())
    return float(d.loc[d["Mes"] <= mes, "PrevisaoAtualizada"].sum())          # "soma"


def _rreo_dotacao(ano: int) -> dict[int, tuple[float, float]]:
    """{bimestre: (dotação inicial, dotação atualizada)} de Cariacica no RREO Anexo 01: subtotal das despesas
    (com intra) mais a reserva do RPPS, que o arquivo do TCE-ES inclui na dotação (conferido em 07/11/2026: a
    diferença entre as duas bases era exatamente a reserva do RPPS, R$ 104,9 mi em 2025)."""
    r = armazem.ler(DADOS / "siconfi" / "rreo_balanco_orcamentario.csv")
    if r.empty:
        return {}
    r = r[(r["exercicio"] == str(ano)) & (r["cod_ibge"] == "3201308") & (r["anexo"] == "RREO-Anexo 01")
          & (r["cod_conta"].isin(["SubtotalDasDespesas", "ReservaDoRPPS"]))]
    saida = {}
    for b, g in r.groupby("periodo"):
        ini = pd.to_numeric(g.loc[g["coluna"].str.startswith("DOTAÇÃO INICIAL"), "valor"], errors="coerce").sum()
        atu = pd.to_numeric(g.loc[g["coluna"].str.startswith("DOTAÇÃO ATUALIZADA"), "valor"], errors="coerce").sum()
        if ini and atu:
            saida[int(b)] = (float(ini), float(atu))
    return saida


def leitura_validada(ano: int) -> tuple[str, int] | None:
    """Qual leitura de PrevisaoAtualizada bate com o RREO, e em que mês. None se nenhuma bater."""
    d = _ler("despesas", ano)
    rreo = _rreo_dotacao(ano)
    if d.empty or not rreo:
        return None
    ultimo = int(d["Mes"].max())
    bimestres = [b for b in rreo if 2 * b <= ultimo]
    if not bimestres:
        return None
    b = max(bimestres)
    ini_rreo, atu_rreo = rreo[b]
    if abs(float(d["PrevisaoInicial"].sum()) / ini_rreo - 1) > TOLERANCIA_RREO:
        log.warning("Dotação inicial do TCE-ES não confere com o RREO de %s", ano)
        return None
    for leitura in ("ultimo_mes", "soma"):
        if abs(_dotacao_tcees(d, 2 * b, leitura) / atu_rreo - 1) <= TOLERANCIA_RREO:
            return leitura, ultimo
    log.warning("Dotação atualizada do TCE-ES não confere com o RREO de %s (bimestre %s)", ano, b)
    return None


def aumento_dotacao(ano: int, fonte: str | None = FONTE_LIVRE) -> float | None:
    """Dotação atualizada menos dotação inicial (LOA): créditos adicionais líquidos de cancelamentos.
    None quando o cálculo não confere com o RREO (melhor não mostrar do que mostrar errado)."""
    validada = leitura_validada(ano)
    if not validada:
        return None
    leitura, mes = validada
    d = _ler("despesas", ano)
    if fonte:
        d = d[d["CodigoFonteReduzida"] == fonte]
    return _dotacao_tcees(d, mes, leitura) - float(d["PrevisaoInicial"].sum())


def conferencia_receita(ano: int) -> dict | None:
    """Receita do TCE-ES (todas as fontes, sem intra) até o fim do último bimestre do RREO x "Até o Bimestre"
    do RREO Anexo 01 (RECEITAS EXCETO INTRA-ORÇAMENTÁRIAS). As duas vêm da prefeitura por caminhos
    diferentes (Tribunal e Tesouro); em 07/11/2026 bateram ao centavo em 2025 e 2026."""
    r = armazem.ler(DADOS / "siconfi" / "rreo_balanco_orcamentario.csv")
    rec = _receitas(ano, None)
    if r.empty or rec.empty:
        return None
    r = r[(r["exercicio"] == str(ano)) & (r["cod_ibge"] == "3201308") & (r["anexo"] == "RREO-Anexo 01")
          & (r["cod_conta"] == "ReceitasExcetoIntraOrcamentarias") & r["coluna"].str.startswith("Até o Bimestre")]
    ultimo = int(rec["Mes"].max())
    bimestres = [int(b) for b in r["periodo"] if 2 * int(b) <= ultimo]
    if not bimestres:
        return None
    b = max(bimestres)
    rreo = float(pd.to_numeric(r.loc[r["periodo"] == str(b), "valor"], errors="coerce").sum())
    tce = float(rec.loc[rec["Mes"] <= 2 * b, "Arrecadada"].sum())
    dif = (tce / rreo - 1) if rreo else None
    return {"bimestre": b, "tcees": tce, "rreo": rreo, "diferenca": dif,
            "ok": dif is not None and abs(dif) <= TOLERANCIA_RREO}


# ---------------------------------------------------------------- relatório

MESES = ["", "janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro",
         "outubro", "novembro", "dezembro"]


def _mi(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v / 1e6:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")


def secao_markdown(ano: int) -> str:
    """Seção do relatório. Sem dado do ano (ex.: janeiro), usa o ano anterior."""
    for a in (ano, ano - 1):
        mes = mes_comum(a)
        if mes:
            return _secao(a, mes)
    return ""


def _secao(ano: int, mes: int) -> str:
    livre, total = arrecadacao(ano, mes=mes), arrecadacao(ano, fonte=None, mes=mes)
    if not livre:
        return ""
    linhas = [
        f"## Arrecadação de {ano} x previsão do orçamento (R$ milhões)", "",
        f"Fonte: TCE-ES, receita e despesa mensal dos municípios (dados enviados pela prefeitura), até "
        f"{MESES[mes]}. \"Todas as fontes\" sem as receitas intraorçamentárias. Projeção = arrecadado até o "
        f"mês × (total do ano anterior ÷ arrecadado no mesmo período do ano anterior). É uma estimativa, não "
        f"um dado oficial.", "",
        "| | Impostos e transferências (fonte livre) | Todas as fontes |", "|---|---|---|",
    ]
    def linha(rotulo, chave, pct=False):
        def v(d):
            if not d or d.get(chave) is None:
                return "—"
            return f"{d[chave]:+.1%}".replace(".", ",") if pct else _mi(d[chave])
        linhas.append(f"| {rotulo} | {v(livre)} | {v(total)} |")
    linha(f"Arrecadado jan–{MESES[mes][:3]}/{ano}", "arrecadado")
    linha(f"Mesmo período de {ano - 1}", "arrecadado_ano_anterior_mesmo_periodo")
    linha("Variação", "variacao", pct=True)
    linha(f"Previsão da LOA {ano}", "previsao_inicial")
    linha("Projeção do ano no ritmo do anterior", "projecao_no_ritmo_do_ano_anterior")
    linha("Distância projetada da previsão", "excesso_projetado")
    linha("Aumento líquido da dotação (créditos adicionais menos cancelamentos)", "aumento_dotacao")
    conf = conferencia_receita(ano)
    if conf and conf["ok"]:
        linhas += ["", f"_Receita conferida com o RREO do Tesouro até o {conf['bimestre']}º bimestre: TCE-ES R$ "
                   f"{_mi(conf['tcees'])} mi, RREO R$ {_mi(conf['rreo'])} mi._"]
    elif conf:
        from . import qualidade
        qualidade.REGISTRO.add(qualidade.Checagem("tcees", f"receitas_{ano}.csv", "confere_rreo", False, False,
                                                  f"receita até o {conf['bimestre']}º bimestre: TCE-ES {_mi(conf['tcees'])}"
                                                  f" x RREO {_mi(conf['rreo'])} (R$ mi)"))
        linhas += ["", f"**Atenção:** a receita do TCE-ES não bate com o RREO do Tesouro até o {conf['bimestre']}º "
                   f"bimestre (TCE-ES R$ {_mi(conf['tcees'])} mi, RREO R$ {_mi(conf['rreo'])} mi). Confira antes de "
                   "usar estes números."]
    if livre.get("aumento_dotacao") is None:
        linhas += ["", "_Aumento da dotação: não mostrado porque o cálculo com o TCE-ES não conferiu com o RREO "
                   "do Tesouro no mesmo bimestre._"]
    else:
        linhas += ["", "_Aumento da dotação conferido com o RREO (Anexo 01) do Tesouro no mesmo bimestre._"]
    linhas += ["", "**Pergunta:** se a arrecadação passa da previsão, quais prioridades a prefeitura deu ao "
               "dinheiro extra nos créditos adicionais?", ""]
    return "\n".join(linhas)
