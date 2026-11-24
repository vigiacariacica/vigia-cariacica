"""Todas as regras de alerta num lugar só.

    R01–R20  PNCP, Receita Federal e CGU ............ vigia/alertas/motor.py
    R21–R27, R29–R33  portal, TSE e PNCP ... vigia/alertas/portal.py
    Catálogo (nome, pergunta, base legal, como conferir) ... vigia/regras.py

Fluxo de `rodar`:
1. roda as 32 regras e grava no banco (tabela `alertas`), preservando status e nota;
2. aplica as marcações humanas de data/casos.csv (quem marcou, quando e por quê fica no git);
3. exporta data/alertas.csv, a lista pública: cada linha é uma PERGUNTA com link oficial.
"""
from __future__ import annotations

import datetime as dt
import json
import re

import pandas as pd

from .. import log
from ..config import DADOS
from ..regras import REGRAS
from ..texto import formatar_cnpj, mascarar_cpf, mascarar_cpfs, so_digitos
from . import portal
from .motor import Lote, link_compra, link_contrato, regras_pncp  # noqa: F401  (usados pelo painel)

STATUS_VALIDOS = ("novo", "em_analise", "confirmado", "denunciado", "descartado")
REGRAS_RECEITA = {"R09", "R10", "R11", "R12", "R15", "R16"}  # usam o cadastro da Receita
CASOS = DADOS / "casos.csv"
COLUNAS_CASOS = ["id", "status", "nota", "atualizado_em"]
# Regras que rodam e ficam no banco, mas não saem na lista pública até a revisão jurídica (docs/DECISOES.md,
# 24/11/2026). R25 diz quantas candidaturas a prefeito a empresa atendeu; com 1 ou 2 por eleição, isso aponta
# para uma campanha só. Para voltar a publicar, tire a regra daqui e registre a decisão.
EM_REVISAO = {"R25"}
COLUNAS_PUBLICAS = ["id", "regra", "nome_regra", "gravidade", "titulo", "pergunta", "detalhe", "valor",
                    "valor_excesso", "orgao", "fornecedor", "fornecedor_doc", "referencia", "data_referencia",
                    "link", "outros_links", "primeira_vez", "status", "nota"]


def rodar(con, cfg, *, pagamentos: pd.DataFrame, contratos_mun: pd.DataFrame, emergenciais: pd.DataFrame,
          penalizados: pd.DataFrame, campanha: pd.DataFrame | None = None) -> pd.DataFrame:
    lote = Lote(con)
    regras_pncp(con, cfg, lote)
    antes = len(lote.itens)
    for a in portal.todas(pagamentos, contratos_mun, emergenciais, penalizados, campanha):
        lote.add(a.regra, a.gravidade, a.titulo, a.detalhe, f"{a.fornecedor_doc}|{a.referencia}",
                 ni_fornecedor=a.fornecedor_doc, nome_fornecedor=a.fornecedor, valor=a.valor,
                 data=a.data or None, links=[a.link, *a.outros_links])
    log.info(f"  Portal municipal, TSE e PNCP (R21-R27, R29-R33): {len(lote.itens) - antes} alertas")
    lote.gravar()
    aplicar_casos(con)
    return exportar(con)


# ---------------------------------------------------------------- marcações humanas

def ler_casos() -> pd.DataFrame:
    if CASOS.exists():
        return pd.read_csv(CASOS, dtype=str, keep_default_na=False)
    return pd.DataFrame(columns=COLUNAS_CASOS)


def marcar(con, id_alerta: str, status: str, nota: str = "") -> None:
    """Registra a marcação em data/casos.csv (auditável no git) e aplica no banco."""
    if status not in STATUS_VALIDOS:
        raise ValueError(f"Status inválido. Use: {', '.join(STATUS_VALIDOS)}")
    no_banco = con.execute("SELECT 1 FROM alertas WHERE id=?", (id_alerta,)).fetchone()
    publicos = DADOS / "alertas.csv"
    na_lista = publicos.exists() and id_alerta in set(pd.read_csv(publicos, dtype=str, usecols=["id"])["id"])
    if not (no_banco or na_lista):
        raise KeyError(f"Alerta {id_alerta} não encontrado em data/alertas.csv")
    casos = ler_casos()
    casos = casos[casos["id"] != id_alerta]
    nova = pd.DataFrame([{"id": id_alerta, "status": status, "nota": nota,
                          "atualizado_em": dt.date.today().isoformat()}])
    pd.concat([casos, nova], ignore_index=True).sort_values("id").to_csv(CASOS, index=False)
    aplicar_casos(con)


def aplicar_casos(con) -> None:
    for _, c in ler_casos().iterrows():
        if c["status"] in STATUS_VALIDOS:
            con.execute("UPDATE alertas SET status=?, nota=? WHERE id=?", (c["status"], c["nota"], c["id"]))
    con.commit()


# ---------------------------------------------------------------- lista pública

def _titulo_publico(regra: str, titulo: str) -> str:
    """Nome de pessoa física não vai para a lista pública (LGPD). O dossiê local mantém o detalhe.
    (R15 já escreve "pessoa física" no título quando o sócio não tem CNPJ: ver motor.py.)"""
    if regra == "R14":
        return "Sócio de fornecedor com o mesmo nome de um servidor municipal (pode ser homônimo)"
    return titulo


def _detalhe_publico(regra: str, detalhe: str) -> str:
    if regra == "R14":
        return ("Um sócio da empresa tem o mesmo nome completo de um servidor da lista obtida por LAI. "
                "PODE SER HOMÔNIMO. Os nomes não são publicados; a conferência é feita pelo dossiê.")
    return detalhe


_CPF_NO_NOME = re.compile(r"\*{3}\.\d{3}\.\d{3}-\*{2}|\b\d{3}\.\d{3}\.\d{3}-\d{2}\b|\b\d{11}\b")
_MEI_NO_NOME = re.compile(r"^\d{2}\.?\d{3}\.?\d{3}\s")


def _dono_e_pessoa(con, ni: str | None, nome: str) -> bool:
    """Empresário individual e MEI usam o nome do dono como razão social (às vezes com o CPF ou o começo do CNPJ
    junto). Na lista pública eles viram "empresa individual" com o CNPJ: o README promete nenhum nome de pessoa
    física nos alertas (LGPD; docs/DECISOES.md, 24/11/2026). O banco e o dossiê local mantêm o nome."""
    if not nome:
        return False
    if _CPF_NO_NOME.search(nome) or _MEI_NO_NOME.match(nome):
        return True
    d = so_digitos(ni or "")
    if len(d) == 11 or "*" in (ni or ""):        # documento é CPF: pessoa física
        return True
    if len(d) != 14:
        return False
    r = con.execute("SELECT natureza_juridica, opcao_mei FROM fornecedores WHERE cnpj=?", (d,)).fetchone()
    return bool(r and ((r[0] or "").strip().lower().startswith("empresário") or r[1] == 1))


def _sem_nome_do_dono(texto: str, nome: str, troca: str) -> str:
    if not texto or not nome:
        return texto
    base = _CPF_NO_NOME.sub("", _MEI_NO_NOME.sub("", nome)).strip(" -–")
    for n in sorted({nome, nome.strip(), base}, key=len, reverse=True):
        if len(n) >= 4:
            texto = re.sub(re.escape(n), troca, texto, flags=re.I)
    return texto


def _doc_publico(doc: str | None) -> str:
    if not doc:
        return ""
    d = so_digitos(doc)
    if len(d) == 14:
        return formatar_cnpj(d)
    return mascarar_cpf(doc)


def _links_do_fornecedor(con, ni: str | None) -> list[str]:
    """Alerta sobre a empresa (R09–R17) não aponta para um contrato específico. Para que toda
    pergunta tenha fonte oficial, usa o maior contrato dela com o município no PNCP (ou a compra
    que ela venceu). Empresa punida ganha também o link da consulta oficial do CEIS/CNEP."""
    if not ni:
        return []
    links = []
    k = con.execute("""SELECT c.id_pncp FROM contratos c JOIN orgaos o ON o.cnpj=c.cnpj_orgao
                       WHERE o.alvo=1 AND c.ni_fornecedor=? ORDER BY c.valor_global DESC LIMIT 1""", (ni,)).fetchone()
    if k:
        links.append(link_contrato(k[0]))
    else:
        r = con.execute("""SELECT r.id_pncp FROM resultados r JOIN contratacoes c ON c.id_pncp=r.id_pncp
                           WHERE c.alvo=1 AND r.ni_fornecedor=? ORDER BY r.valor_total DESC LIMIT 1""", (ni,)).fetchone()
        if r:
            links.append(link_compra(r[0]))
    return [x for x in links if x]


def exportar(con) -> pd.DataFrame:
    linhas = con.execute("""
        SELECT id, regra, gravidade, titulo, pergunta, resumo, valor_envolvido, valor_excesso, nome_orgao,
               nome_fornecedor, ni_fornecedor, id_contratacao, id_contrato, data_referencia, links,
               criado_em, status, nota
        FROM alertas WHERE ativo=1""").fetchall()
    anteriores = {}
    destino = DADOS / "alertas.csv"
    if destino.exists():
        prev = pd.read_csv(destino, dtype=str, keep_default_na=False)
        if {"id", "primeira_vez"} <= set(prev.columns):
            anteriores = dict(zip(prev["id"], prev["primeira_vez"]))
    saida = []
    guardados = 0
    for r in linhas:
        if r["regra"] in EM_REVISAO:
            guardados += 1
            continue
        links = [x for x in json.loads(r["links"] or "[]") if x]
        if not links:
            links = _links_do_fornecedor(con, r["ni_fornecedor"])
        detalhe = _detalhe_publico(r["regra"], r["resumo"] or "")
        if r["regra"] in REGRAS_RECEITA and r["ni_fornecedor"] and len(so_digitos(r["ni_fornecedor"])) == 14:
            ni = so_digitos(r["ni_fornecedor"])
            links.append(f"https://solucoes.receita.fazenda.gov.br/Servicos/cnpjreva/Cnpj_Solicitacao.asp?cnpj={ni}")
            consulta = con.execute("SELECT consultado_em FROM fornecedores WHERE cnpj=?", (ni,)).fetchone()
            if consulta and consulta[0]:
                c = consulta[0][:10]
                detalhe += f" Dados da Receita Federal consultados em {c[8:10]}/{c[5:7]}/{c[:4]}."
        if r["regra"] == "R13" and r["ni_fornecedor"]:
            links.append(f"https://portaldatransparencia.gov.br/sancoes/consulta?cpfCnpj={so_digitos(r['ni_fornecedor'])}")
        criado = (r["criado_em"] or dt.date.today().isoformat())[:10]
        titulo = _titulo_publico(r["regra"], r["titulo"] or "")
        pergunta = r["pergunta"] or REGRAS[r["regra"]]["pergunta"]
        fornecedor = r["nome_fornecedor"] or ""
        if _dono_e_pessoa(con, r["ni_fornecedor"], fornecedor):
            d = so_digitos(r["ni_fornecedor"] or "")
            troca = f"empresa individual (CNPJ {formatar_cnpj(d)})" if len(d) == 14 else "pessoa física"
            titulo, pergunta, detalhe = (_sem_nome_do_dono(x, fornecedor, troca) for x in (titulo, pergunta, detalhe))
            fornecedor = "empresa individual (nome do titular omitido)" if len(d) == 14 else "pessoa física"
        saida.append({
            "id": r["id"], "regra": r["regra"], "nome_regra": REGRAS[r["regra"]]["nome"],
            "gravidade": r["gravidade"], "titulo": titulo,
            "pergunta": pergunta,
            "detalhe": detalhe,
            "valor": round(r["valor_envolvido"], 2) if r["valor_envolvido"] is not None else "",
            "valor_excesso": round(r["valor_excesso"], 2) if r["valor_excesso"] is not None else "",
            "orgao": r["nome_orgao"] or "", "fornecedor": fornecedor,
            "fornecedor_doc": _doc_publico(r["ni_fornecedor"]),
            "referencia": r["id_contrato"] or r["id_contratacao"] or "",
            "data_referencia": r["data_referencia"] or "",
            "link": links[0] if links else "", "outros_links": " | ".join(links[1:]),
            "primeira_vez": min(filter(None, [anteriores.get(r["id"]), criado])),
            "status": r["status"] or "novo", "nota": r["nota"] or "",
        })
    if guardados:
        log.info(f"{guardados} alerta(s) de regra em revisão jurídica ({', '.join(sorted(EM_REVISAO))}) fora da lista pública")
    df = pd.DataFrame(saida, columns=COLUNAS_PUBLICAS)
    for col in ("titulo", "pergunta", "detalhe", "fornecedor", "orgao", "nota"):
        df[col] = df[col].astype(str).str.replace(r"\s+", " ", regex=True).str.strip().map(mascarar_cpfs)
    ordem = {"alta": 0, "media": 1, "baixa": 2}
    df = df.assign(_g=df["gravidade"].map(ordem), _v=pd.to_numeric(df["valor"], errors="coerce").fillna(0))
    df = df.sort_values(["_g", "_v", "id"], ascending=[True, False, True]).drop(columns=["_g", "_v"])
    df.to_csv(destino, index=False)
    return df
