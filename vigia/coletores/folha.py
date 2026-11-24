"""Folha da prefeitura, só agregada: quantos servidores, em que cargo e vínculo, e quanto custam.

Fonte: Portal da Transparência de Cariacica, consultas de pessoal (https://wstransparencia.cariacica.es.gov.br/Help)
    pessoal/anos                               anos publicados
    pessoal/mensal?exercicio=AAAA              total da folha em cada mês            -> data/folha/folha_mensal.csv
    pessoal/cargo?exercicio=AAAA&mes=M         por cargo: nº de servidores e valores -> data/folha/cargos_AAAA.csv
    pessoal/lotacao?exercicio=AAAA&mes=M       por lotação e secretaria              -> data/folha/lotacoes_AAAA.csv
    pessoal/csv?exercicio=AAAA&periodo=M       folha nominal (uma linha por rubrica) -> data/folha/vinculos.csv
                                               (lida na memória e somada por vínculo; nada nominal é gravado)

Por que existe: pessoal é o maior gasto da prefeitura (~40%) e o Vigia só via o total. A revisão de 10/11/2026
achou que a contratação por tempo determinado (elemento 319004) foi de R$ 39,7 mi em 2019 para R$ 146,2 mi em
2025. Com esta coleta dá para responder quantos são, em que cargos e há quanto tempo.

LGPD: as consultas por cargo e por lotação já vêm agregadas pela prefeitura (sem nome). A folha nominal traz
nome, CPF e matrícula: é baixada só para ser somada por vínculo (QuadroNome) e por tempo de casa, na memória.
O arquivo cru não é guardado (só o SHA-256 vai para o manifesto) e nenhuma coluna com pessoa vai para o git.

Para não pesar no portal (que às vezes bloqueia o GitHub): cargos e lotações só baixam os meses que faltam e
os dois últimos meses do ano corrente; a folha nominal, no máximo MAX_NOMINAIS_POR_DIA meses por dia, do mais
recente para o mais antigo (o histórico se completa sozinho em poucos dias).
"""
from __future__ import annotations

import csv
import hashlib
import io
import logging
import re
from datetime import date

import pandas as pd

from .. import armazem, qualidade
from ..config import DADOS
from ..http import sessao
from . import transparencia

log = logging.getLogger("vigia.folha")
FONTE = "folha"
PASTA = DADOS / "folha"
ANO_INICIAL = 2019
MAX_NOMINAIS_POR_DIA = 4

CARGO = {"cd_CargoServidor": "cd_cargo", "CargoNome": "cargo", "NumeroServidores": "servidores",
         "VencimentoPadrao": "vencimento_padrao", "OutrosVencimentos": "outros_vencimentos",
         "RemuneracaoBruta": "remuneracao_bruta", "Descontos": "descontos", "RemuneracaoLiquida": "remuneracao_liquida"}
LOTACAO = {"cd_LotacaoServidor": "cd_lotacao", "LotacaoNome": "lotacao", "cd_Secretaria": "cd_secretaria",
           "SecretariaNome": "secretaria", "Nivel": "nivel", "NumeroServidores": "servidores",
           "VencimentoPadrao": "vencimento_padrao", "OutrosVencimentos": "outros_vencimentos",
           "RemuneracaoBruta": "remuneracao_bruta", "Descontos": "descontos", "RemuneracaoLiquida": "remuneracao_liquida"}
NUM = r"-?\d+(\.\d+)?"
OBRIG_MENSAL = {"ano": r"\d{4}", "mes": r"\d{1,2}", "valor": NUM}
OBRIG_CARGO = {"ano": r"\d{4}", "mes": r"\d{1,2}", "cargo": r".+", "servidores": r"\d+"}
OBRIG_LOTACAO = {"ano": r"\d{4}", "mes": r"\d{1,2}", "lotacao": r".+", "servidores": r"\d+"}
OBRIG_VINCULO = {"ano": r"\d{4}", "mes": r"\d{1,2}", "vinculo": r".+", "servidores": r"\d+"}
# Folha nominal: 11 campos fixos à esquerda, 2 à direita (Valor, Tipo); a rubrica fica no meio.
NOMINAL = ["Matricula", "ServidorNome", "ServidorCpf", "QuadroNome", "LotacaoNome", "CargoNome", "DataAdmissao",
           "CargaHoraria", "PlanoCargos", "Mes", "Ano", "Rubrica", "Valor", "Tipo"]


# ---------------------------------------------------------------- leitura

def numero(texto) -> float:
    """'1.234,56' -> 1234.56; '1234.56' -> 1234.56; vazio -> 0."""
    t = str(texto if texto is not None else "").strip()
    if not t:
        return 0.0
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return 0.0


def tabela_agregada(itens: list[dict], colunas: dict, ano: int, mes: int) -> pd.DataFrame:
    """Lista JSON da prefeitura (cargo ou lotação) -> tabela com nomes de coluna do Vigia."""
    linhas = []
    for it in itens or []:
        linha = {"ano": ano, "mes": mes}
        for origem, destino in colunas.items():
            v = it.get(origem)
            if destino in ("servidores", "nivel", "cd_cargo", "cd_lotacao", "cd_secretaria"):
                linha[destino] = "" if v is None else str(int(numero(v)))
            elif destino.startswith(("vencimento", "outros", "remuneracao", "descontos")):
                linha[destino] = f"{numero(v):.2f}"
            else:
                linha[destino] = re.sub(r"\s+", " ", str(v or "")).strip()
        linhas.append(linha)
    return pd.DataFrame(linhas)


def _data(texto: str) -> date | None:
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", str(texto or "").strip()) or \
        re.match(r"(\d{4})-(\d{2})-(\d{2})", str(texto or "").strip())
    if not m:
        return None
    a, b, c = m.groups()
    try:
        return date(int(c), int(b), int(a)) if len(a) <= 2 else date(int(a), int(b), int(c))
    except ValueError:
        return None


def _slug(texto: str) -> str:
    t = re.sub(r"[^a-z0-9]+", "_", str(texto or "sem_tipo").lower()).strip("_")
    return t or "sem_tipo"


def somar_nominal(texto: str, ano: int, mes: int) -> pd.DataFrame:
    """Folha nominal (texto do CSV) -> uma linha por vínculo, sem nenhuma informação de pessoa.

    servidores: matrículas distintas; tempo de casa contado até o último dia do mês; valores somados por Tipo
    (coluna valor_<tipo>, do jeito que a prefeitura escreve o tipo)."""
    leitor = csv.reader(io.StringIO(texto.lstrip("﻿")))
    cab = next(leitor, None)
    if not cab or [c.strip() for c in cab[:4]] != NOMINAL[:4]:
        raise ValueError(f"folha nominal: cabeçalho inesperado {cab[:6] if cab else cab}")
    fim_mes = date(ano, 12, 31) if mes == 12 else date(ano, mes + 1, 1).replace(day=1)
    acc: dict[str, dict] = {}
    for campos in leitor:
        if len(campos) < len(NOMINAL):
            continue
        esq, dir_ = campos[:11], campos[-2:]
        matricula, vinculo, admissao = esq[0].strip(), (esq[3].strip() or "NÃO INFORMADO"), _data(esq[6])
        valor, tipo = numero(dir_[0]), _slug(dir_[1])
        a = acc.setdefault(vinculo, {"matriculas": {}, "valores": {}})
        a["matriculas"].setdefault(matricula, admissao)
        a["valores"][tipo] = a["valores"].get(tipo, 0.0) + valor
    linhas = []
    for vinculo, a in acc.items():
        faixas = {"ate_1_ano": 0, "de_1_a_2_anos": 0, "de_2_a_5_anos": 0, "mais_de_5_anos": 0, "sem_data": 0}
        for adm in a["matriculas"].values():
            if adm is None:
                faixas["sem_data"] += 1
                continue
            anos = (fim_mes - adm).days / 365.25
            chave = ("ate_1_ano" if anos < 1 else "de_1_a_2_anos" if anos < 2 else
                     "de_2_a_5_anos" if anos < 5 else "mais_de_5_anos")
            faixas[chave] += 1
        linha = {"ano": ano, "mes": mes, "vinculo": vinculo, "servidores": len(a["matriculas"]),
                 **{f"tempo_{k}": v for k, v in faixas.items()}}
        linha.update({f"valor_{t}": f"{v:.2f}" for t, v in sorted(a["valores"].items())})
        linhas.append(linha)
    if not linhas:
        raise ValueError("folha nominal sem nenhuma linha válida")
    return pd.DataFrame(linhas).sort_values("servidores", ascending=False)


# ---------------------------------------------------------------- download

def _get(s, rota: str, params: dict, nome_bruto: str | None, guardar: bool = True):
    r = s.get(f"{transparencia.BASE}/{rota}", params=params, timeout=300)
    r.raise_for_status()
    if "html" in r.headers.get("Content-Type", "").lower():
        raise ValueError(f"{rota} devolveu HTML (bloqueio do portal ou página de erro)")
    if nome_bruto:
        if guardar:
            qualidade.guardar_bruto(nome_bruto, r.content, r.url)
        else:   # folha nominal: só o hash (tem nome e CPF)
            qualidade.registrar_bruto(nome_bruto, hashlib.sha256(r.content).hexdigest(), len(r.content), r.url)
    return r


def _gravar(df: pd.DataFrame, nome: str, obrigatorias: dict, total: str, chave: list[str]) -> bool:
    caminho = PASTA / nome
    antigo = armazem.ler(caminho)
    junto = armazem.juntar(antigo, df) if not antigo.empty else df
    chs = qualidade.validar_tabela(junto.astype(str).drop_duplicates(subset=chave, keep="last"), antigo,
                                   fonte=FONTE, arquivo=nome, obrigatorias=obrigatorias, coluna_total=total)
    if not qualidade.aprovado(chs):
        log.error("%s NÃO gravado: falhou na checagem; mantida a versão anterior", nome)
        return False
    armazem.gravar(junto, caminho, chave=chave, ordenar=chave)
    return True


def meses_que_faltam(existente: pd.DataFrame, ano: int, meses: list[int], hoje: date) -> list[int]:
    """Meses publicados que ainda não temos; no ano corrente, os dois últimos sempre de novo (a prefeitura
    fecha a folha depois)."""
    tem = set()
    if not existente.empty and "mes" in existente.columns:
        tem = {int(m) for m in pd.to_numeric(existente.loc[existente["ano"].astype(str) == str(ano), "mes"],
                                             errors="coerce").dropna()}
    faltam = [m for m in meses if m not in tem]
    if ano == hoje.year:
        faltam = sorted(set(faltam) | set(sorted(meses)[-2:]))
    return sorted(faltam)


def coletar(hoje: date | None = None, s=None) -> None:
    hoje = hoje or date.today()
    s = s or sessao()
    r = _get(s, "pessoal/anos", {}, "folha_anos.json")
    anos = sorted({int(i["Valor"]) for i in r.json() if str(i.get("Valor", "")).isdigit()
                   and ANO_INICIAL <= int(i["Valor"]) <= hoje.year})
    if not anos:
        raise ValueError("pessoal/anos não trouxe nenhum ano")

    # 1) total por mês (barato: uma chamada por ano)
    mensal, meses_por_ano = [], {}
    for ano in anos:
        r = _get(s, "pessoal/mensal", {"exercicio": ano}, f"folha_mensal_{ano}.json")
        meses = []
        for it in r.json() or []:
            mes, valor = int(numero(it.get("mes"))), numero(it.get("valor"))
            if 1 <= mes <= 12 and valor > 0:
                meses.append(mes)
                mensal.append({"ano": ano, "mes": mes, "valor": f"{valor:.2f}"})
        meses_por_ano[ano] = sorted(meses)
    _gravar(pd.DataFrame(mensal), "folha_mensal.csv", OBRIG_MENSAL, "valor", ["ano", "mes"])

    # 2) por cargo e por lotação (agregado pela prefeitura)
    erros = []
    for ano in anos:
        for rota, colunas, nome, obrig in (("pessoal/cargo", CARGO, f"cargos_{ano}.csv", OBRIG_CARGO),
                                           ("pessoal/lotacao", LOTACAO, f"lotacoes_{ano}.csv", OBRIG_LOTACAO)):
            faltam = meses_que_faltam(armazem.ler(PASTA / nome), ano, meses_por_ano.get(ano, []), hoje)
            partes = []
            for mes in faltam:
                try:
                    itens = _get(s, rota, {"exercicio": ano, "mes": mes}, f"folha_{rota.split('/')[1]}_{ano}_{mes:02d}.json").json()
                    partes.append(tabela_agregada(itens, colunas, ano, mes))
                except Exception as e:  # noqa: BLE001
                    erros.append(f"{rota} {ano}/{mes}: {type(e).__name__}")
            partes = [p for p in partes if not p.empty]
            if partes:
                chave = ["ano", "mes", "cd_cargo" if "cargo" in rota else "cd_lotacao"]
                _gravar(pd.concat(partes, ignore_index=True), nome, obrig, "servidores", chave)

    # 3) vínculos (folha nominal somada na memória), do mês mais recente para trás, com limite por dia
    vinc = armazem.ler(PASTA / "vinculos.csv")
    tem = set() if vinc.empty else set(zip(vinc["ano"].astype(str), vinc["mes"].astype(str)))
    pedidos = []
    for ano in sorted(anos, reverse=True):
        meses = meses_por_ano.get(ano, [])
        if not meses:
            continue
        # ano corrente: todos os meses; anos fechados: só dezembro (ou o último publicado)
        alvo = meses if ano == hoje.year else [max(meses)]
        for mes in sorted(alvo, reverse=True):
            refazer = ano == hoje.year and mes == max(meses)
            if refazer or (str(ano), str(mes)) not in tem:
                pedidos.append((ano, mes))
    novos = []
    for ano, mes in pedidos[:MAX_NOMINAIS_POR_DIA]:
        try:
            r = _get(s, "pessoal/csv", {"exercicio": ano, "periodo": mes}, f"folha_nominal_{ano}_{mes:02d}.csv",
                     guardar=False)
            novos.append(somar_nominal(r.content.decode("windows-1252", errors="replace"), ano, mes))
        except Exception as e:  # noqa: BLE001
            # folha nominal é grande e o portal às vezes estoura o tempo (HTTP 524): o mês fica para amanhã,
            # sem deixar a coleta vermelha (cargos e lotações, se falharem, deixam)
            qualidade.REGISTRO.add(qualidade.Checagem(FONTE, "vinculos.csv", "folha_nominal_adiada", False, False,
                                                      f"{ano}/{mes}: {type(e).__name__}: {str(e)[:80]}; tenta de novo amanhã"))
    if novos:
        df = pd.concat(novos, ignore_index=True).fillna("0")
        _gravar(df, "vinculos.csv", OBRIG_VINCULO, "servidores", ["ano", "mes", "vinculo"])
        conferir_totais(df)
    if len(pedidos) > MAX_NOMINAIS_POR_DIA:
        log.info("folha: %d meses da folha nominal ficam para os próximos dias", len(pedidos) - MAX_NOMINAIS_POR_DIA)
    if erros:
        raise RuntimeError("folha: " + "; ".join(erros[:6]) + (f" (+{len(erros) - 6})" if len(erros) > 6 else ""))
    log.info("folha: %d anos; vínculos de %d meses atualizados", len(anos), len(novos))


def conferir_totais(vinculos: pd.DataFrame) -> None:
    """Servidores somados na folha nominal x soma da consulta por cargo do mesmo mês (devem bater)."""
    for (ano, mes), g in vinculos.groupby(["ano", "mes"]):
        cargos = armazem.ler(PASTA / f"cargos_{ano}.csv")
        if cargos.empty:
            continue
        c = cargos[(cargos["ano"].astype(str) == str(ano)) & (cargos["mes"].astype(str) == str(mes))]
        if c.empty:
            continue
        n_cargo = int(pd.to_numeric(c["servidores"], errors="coerce").sum())
        n_vinc = int(pd.to_numeric(g["servidores"], errors="coerce").sum())
        dif = (n_vinc - n_cargo) / n_cargo if n_cargo else 0
        qualidade.REGISTRO.add(qualidade.Checagem(
            FONTE, "vinculos.csv", "folha_nominal_x_cargos", abs(dif) <= 0.02, False,
            f"{ano}/{mes}: {n_vinc} matrículas na folha nominal x {n_cargo} na consulta por cargo ({dif:+.1%})"))


# ---------------------------------------------------------------- relatório

def _br(v: float, casas: int = 1) -> str:
    return f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def secao_markdown() -> str:
    vinc = armazem.ler(PASTA / "vinculos.csv")
    mensal = armazem.ler(PASTA / "folha_mensal.csv")
    if vinc.empty and mensal.empty:
        return ""
    partes = ["## Quem trabalha na prefeitura (folha, só números)\n",
              "Fonte: Portal da Transparência de Cariacica, consultas de pessoal. Nenhum nome é guardado: a folha "
              "nominal é somada por vínculo na hora da coleta (valor_v = vencimentos e vantagens, valor_d = descontos, "
              "como a prefeitura marca o tipo da rubrica). **Em conferência:** o número de contratos temporários varia "
              "muito de um mês para outro e a soma das "
              "matrículas fica 2% a 5% abaixo da consulta por cargo; não publicar antes de entender o porquê.\n"]
    if not vinc.empty:
        v = vinc.copy()
        v["ano"], v["mes"] = v["ano"].astype(int), v["mes"].astype(int)
        v["servidores"] = pd.to_numeric(v["servidores"], errors="coerce").fillna(0).astype(int)
        ult = v.sort_values(["ano", "mes"]).iloc[-1]
        atual = v[(v["ano"] == ult["ano"]) & (v["mes"] == ult["mes"])].sort_values("servidores", ascending=False)
        total = atual["servidores"].sum()
        linhas = ["| Vínculo | Matrículas | % | Admitidos há mais de 2 anos |", "|---|---:|---:|---:|"]
        for _, r in atual.iterrows():
            mais2 = int(pd.to_numeric(r.get("tempo_de_2_a_5_anos", 0), errors="coerce") or 0) + \
                int(pd.to_numeric(r.get("tempo_mais_de_5_anos", 0), errors="coerce") or 0)
            pct = f"{r['servidores'] / total:.1%}".replace(".", ",")
            linhas.append(f"| {r['vinculo']} | {r['servidores']:,} | ".replace(",", ".") + pct + f" | {mais2:,} |".replace(",", "."))
        partes.append(f"### Por vínculo ({int(ult['mes']):02d}/{int(ult['ano'])}): {total:,} matrículas\n".replace(",", "."))
        partes.append("\n".join(linhas) + "\n")
        dez = v[v["mes"] == v.groupby("ano")["mes"].transform("max")]
        if dez["ano"].nunique() > 1:
            piv = dez.pivot_table(index="vinculo", columns="ano", values="servidores", aggfunc="sum").fillna(0).astype(int)
            piv = piv.loc[piv.sum(axis=1).sort_values(ascending=False).index]
            cab = "| Vínculo | " + " | ".join(str(a) for a in piv.columns) + " |"
            sep = "|---|" + "---:|" * len(piv.columns)
            corpo = [f"| {i} | " + " | ".join(f"{x:,}".replace(",", ".") for x in row) + " |" for i, row in piv.iterrows()]
            partes.append("### Servidores por vínculo no último mês de cada ano\n\n" + "\n".join([cab, sep, *corpo]) + "\n")
    if not mensal.empty:
        m = mensal.copy()
        m["valor"] = pd.to_numeric(m["valor"], errors="coerce")
        por_ano = m.groupby("ano")["valor"].agg(["sum", "count"])
        linhas = ["| Ano | Folha (R$ mi) | Meses |", "|---|---:|---:|"]
        for ano, r in por_ano.iterrows():
            linhas.append(f"| {ano} | {_br(r['sum'] / 1e6)} | {int(r['count'])} |")
        partes.append("### Total da folha por ano (soma dos meses publicados)\n\n" + "\n".join(linhas) + "\n")
    return "\n".join(partes)
