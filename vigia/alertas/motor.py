"""Regras R01–R20: cruzam PNCP, Receita Federal e CGU e apontam o que merece ser olhado de perto.

O `Lote` junta os alertas de todas as regras (inclusive R21–R27, do portal municipal) e grava no
banco preservando o que foi marcado à mão (status e nota). O id de cada alerta é estável:
sha1("regra|chave")[:12], então o mesmo fato tem o mesmo id em todas as execuções.
"""
from __future__ import annotations

import re

import datetime as dt
import hashlib
import json
import statistics
from collections import defaultdict

from .. import log
from ..config import alerta as A
from ..limites import inciso_art75, limite_dispensa
from ..regras import GRAVIDADE_PONTOS, REGRAS
from ..texto import (endereco, fator as fx, formatar_cnpj, jaccard, nome_pessoa, normalizar, numeros,
                    pct as pc, reais, tokens, unidade)

PNCP_APP = "https://pncp.gov.br/app"


# ---------------------------------------------------------------- utilitários
def _d(s) -> dt.date | None:
    if not s:
        return None
    try:
        return dt.date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def link_compra(id_pncp: str | None) -> str | None:
    from ..coletores.pncp import partes_id
    p = partes_id(id_pncp)
    return f"{PNCP_APP}/editais/{p[0]}/{p[3]}/{p[2]}" if p else None


def link_contrato(id_pncp: str | None) -> str | None:
    from ..coletores.pncp import partes_id
    p = partes_id(id_pncp)
    return f"{PNCP_APP}/contratos/{p[0]}/{p[3]}/{p[2]}" if p else None


class Lote:
    def __init__(self, con):
        self.con = con
        self.itens: dict[str, dict] = {}
        self.orgaos = {r["cnpj"]: (r["razao_social"] or r["cnpj"])
                       for r in con.execute("SELECT cnpj, razao_social FROM orgaos")}

    def add(self, regra, gravidade, titulo, resumo, chave, *, cnpj_orgao=None, ni_fornecedor=None,
            nome_fornecedor=None, valor=None, excesso=None, data=None, id_contratacao=None,
            id_contrato=None, evidencias=None, links=None, pergunta=None):
        ident = hashlib.sha1(f"{regra}|{chave}".encode()).hexdigest()[:12]
        atual = self.itens.get(ident)
        if atual and GRAVIDADE_PONTOS[atual["gravidade"]] >= GRAVIDADE_PONTOS[gravidade]:
            return
        lks = [l for l in (links or []) if l]
        if id_contratacao and link_compra(id_contratacao) not in lks:
            lks.append(link_compra(id_contratacao))
        if id_contrato and link_contrato(id_contrato) not in lks:
            lks.append(link_contrato(id_contrato))
        self.itens[ident] = {
            "id": ident, "regra": regra, "gravidade": gravidade,
            "pontos": GRAVIDADE_PONTOS[gravidade], "titulo": titulo, "resumo": resumo,
            "pergunta": pergunta or REGRAS[regra]["pergunta"],
            "cnpj_orgao": cnpj_orgao, "nome_orgao": self.orgaos.get(cnpj_orgao, cnpj_orgao),
            "ni_fornecedor": ni_fornecedor, "nome_fornecedor": nome_fornecedor,
            "valor_envolvido": valor, "valor_excesso": excesso, "data_referencia": data,
            "id_contratacao": id_contratacao, "id_contrato": id_contrato,
            "evidencias": json.dumps(evidencias or [], ensure_ascii=False, default=str),
            "links": json.dumps(lks, ensure_ascii=False),
        }

    def gravar(self):
        agora = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
        self.con.execute("UPDATE alertas SET ativo=0")
        for a in self.itens.values():
            cols = list(a.keys())
            self.con.execute(
                f"INSERT INTO alertas ({','.join(cols)}, atualizado_em, ativo) "
                f"VALUES ({','.join('?' * len(cols))}, ?, 1) "
                f"ON CONFLICT(id) DO UPDATE SET " + ",".join(f"{c}=excluded.{c}" for c in cols if c != "id")
                + ", atualizado_em=excluded.atualizado_em, ativo=1",
                [a[c] for c in cols] + [agora])
        self.con.commit()


def _alvos(con) -> set[str]:
    return {r[0] for r in con.execute("SELECT cnpj FROM orgaos WHERE alvo=1")}


# ---------------------------------------------------------------- R01 / R02 preços
def _linhas_preco(con, apenas_materiais: bool):
    sql = """
      SELECT r.id_pncp, r.numero_item, r.sequencial, r.valor_unit, r.quantidade, r.ni_fornecedor,
             r.nome_fornecedor, COALESCE(r.data_resultado, c.data_publicacao) AS data,
             i.descricao, i.unidade, i.catalogo_codigo, i.material_servico,
             c.cnpj_orgao, c.alvo, c.municipio_nome, c.objeto, c.modalidade_nome
      FROM resultados r
      JOIN itens i ON i.id_pncp=r.id_pncp AND i.numero_item=r.numero_item
      JOIN contratacoes c ON c.id_pncp=r.id_pncp
      WHERE r.valor_unit > 0 AND r.quantidade > 0"""
    linhas = []
    for r in con.execute(sql):
        if apenas_materiais and (r["material_servico"] or "M").upper() not in ("M", "MATERIAL"):
            continue
        tks = tokens(r["descricao"])
        if not tks:
            continue
        linhas.append({**dict(r), "tks": tks, "nums": numeros(tks), "un": unidade(r["unidade"]),
                       "dt": _d(r["data"])})
    return linhas


class IndicePrecos:
    def __init__(self, refs, sim):
        self.refs = refs
        self.sim = sim
        self.por_token = defaultdict(list)
        self.por_catalogo = defaultdict(list)
        for k, r in enumerate(refs):
            for t in r["tks"]:
                self.por_token[t].append(k)
            if r["catalogo_codigo"]:
                self.por_catalogo[(r["catalogo_codigo"], r["un"])].append(k)
        n = max(len(refs), 1)
        self.comum = {t for t, ks in self.por_token.items() if len(ks) > max(500, n * 0.2)}

    def semelhantes(self, alvo, janela_dias):
        achados = []
        if alvo["catalogo_codigo"] and (alvo["catalogo_codigo"], alvo["un"]) in self.por_catalogo:
            candidatos = self.por_catalogo[(alvo["catalogo_codigo"], alvo["un"])]
            exato = True
        else:
            exato = False
            cont = defaultdict(int)
            for t in alvo["tks"] - self.comum:
                for k in self.por_token.get(t, ()):
                    cont[k] += 1
            minimo = 2 if len(alvo["tks"]) > 2 else 1
            candidatos = [k for k, c in cont.items() if c >= minimo]
        for k in candidatos:
            r = self.refs[k]
            if r["id_pncp"] == alvo["id_pncp"] or r["un"] != alvo["un"]:
                continue
            if alvo["dt"] and r["dt"] and abs((alvo["dt"] - r["dt"]).days) > janela_dias:
                continue
            if not exato:
                if r["nums"] != alvo["nums"]:
                    continue
                if jaccard(r["tks"], alvo["tks"]) < self.sim:
                    continue
            achados.append(r)
        return achados


def regra_precos(con, cfg, lote: Lote):
    linhas = _linhas_preco(con, A(cfg, "sobrepreco_apenas_materiais", True))
    alvos = [l for l in linhas if l["alvo"] == 1]
    externas = [l for l in linhas if l["alvo"] != 1]
    if not alvos:
        return
    janela = int(A(cfg, "sobrepreco_janela_meses", 18)) * 30
    f_med, f_alto = A(cfg, "sobrepreco_fator_medio", 1.5), A(cfg, "sobrepreco_fator_alto", 2.0)
    min_ref, min_org = A(cfg, "sobrepreco_min_referencias", 3), A(cfg, "sobrepreco_min_orgaos", 2)
    min_exc = A(cfg, "sobrepreco_min_excesso_reais", 5000)
    sim = A(cfg, "sobrepreco_similaridade", 0.6)

    idx_ext = IndicePrecos(externas, sim)
    idx_int = IndicePrecos(alvos, sim)
    log.info(f"  Comparando {len(alvos)} preços de {len(externas)} referências externas")
    marcados = set()
    for a in alvos:
        refs = idx_ext.semelhantes(a, janela)
        orgs = {r["cnpj_orgao"] for r in refs}
        if len(refs) >= min_ref and len(orgs) >= min_org:
            med = statistics.median(r["valor_unit"] for r in refs)
            if med > 0:
                fator = a["valor_unit"] / med
                exc = (a["valor_unit"] - med) * a["quantidade"]
                if fator >= f_med and exc >= min_exc:
                    grav = "alta" if fator >= f_alto and exc >= 5 * min_exc else "media"
                    marcados.add((a["id_pncp"], a["numero_item"]))
                    lote.add("R01", grav,
                             f"{a['descricao'][:90]}: {fx(fator)} a mediana dos vizinhos",
                             f"Pago {reais(a['valor_unit'])}/{a['un']} contra mediana de {reais(med)} em "
                             f"{len(refs)} compras de {len(orgs)} outros órgãos. Excesso estimado: {reais(exc)} "
                             f"em {a['quantidade']:g} {a['un']}.",
                             f"{a['id_pncp']}|{a['numero_item']}|{a['sequencial']}",
                             cnpj_orgao=a["cnpj_orgao"], ni_fornecedor=a["ni_fornecedor"],
                             nome_fornecedor=a["nome_fornecedor"], valor=a["valor_unit"] * a["quantidade"],
                             excesso=exc, data=a["data"], id_contratacao=a["id_pncp"],
                             evidencias=[{"tipo": "preco_pago", "descricao": a["descricao"],
                                          "unidade": a["un"], "preco": a["valor_unit"],
                                          "quantidade": a["quantidade"], "data": a["data"]}] + [
                                 {"tipo": "referencia", "orgao": lote.orgaos.get(r["cnpj_orgao"], r["cnpj_orgao"]),
                                  "municipio": r["municipio_nome"], "data": r["data"],
                                  "descricao": r["descricao"], "unidade": r["un"], "preco": r["valor_unit"],
                                  "quantidade": r["quantidade"], "link": link_compra(r["id_pncp"])}
                                 for r in sorted(refs, key=lambda x: x["valor_unit"])[:15]])
                    continue
        # R02 - comparação interna
        if (a["id_pncp"], a["numero_item"]) in marcados:
            continue
        internos = idx_int.semelhantes(a, 365)
        if len(internos) >= 2:
            med = statistics.median(r["valor_unit"] for r in internos)
            if med > 0:
                fator = a["valor_unit"] / med
                exc = (a["valor_unit"] - med) * a["quantidade"]
                if fator >= f_alto and exc >= min_exc:
                    lote.add("R02", "media",
                             f"{a['descricao'][:90]}: {fx(fator)} o que o próprio município pagou",
                             f"Pago {reais(a['valor_unit'])}/{a['un']}; nas outras {len(internos)} compras "
                             f"do município a mediana foi {reais(med)}. Excesso estimado: {reais(exc)}.",
                             f"{a['id_pncp']}|{a['numero_item']}|{a['sequencial']}",
                             cnpj_orgao=a["cnpj_orgao"], ni_fornecedor=a["ni_fornecedor"],
                             nome_fornecedor=a["nome_fornecedor"], valor=a["valor_unit"] * a["quantidade"],
                             excesso=exc, data=a["data"], id_contratacao=a["id_pncp"],
                             evidencias=[{"tipo": "preco_pago", "descricao": a["descricao"], "unidade": a["un"],
                                          "preco": a["valor_unit"], "quantidade": a["quantidade"],
                                          "data": a["data"]}] + [
                                 {"tipo": "referencia", "orgao": lote.orgaos.get(r["cnpj_orgao"], r["cnpj_orgao"]),
                                  "data": r["data"], "descricao": r["descricao"], "unidade": r["un"],
                                  "preco": r["valor_unit"], "quantidade": r["quantidade"],
                                  "fornecedor": r["nome_fornecedor"], "link": link_compra(r["id_pncp"])}
                                 for r in sorted(internos, key=lambda x: x["valor_unit"])[:15]])


# ---------------------------------------------------------------- R03 aditivos / R19 emergência prorrogada
def classificar_termo(t) -> str:
    """renovacao (só prorroga prazo), misto (prorroga e acrescenta), apostila (reajuste, dotação...) ou acrescimo."""
    tipo, obj = normalizar(t["tipo"]), normalizar(t["objeto"])
    if "apostil" in tipo:
        return "apostila"
    prorroga = (t["prazo_aditado_dias"] or 0) > 0 or "prorrog" in obj
    acresce = "acresc" in obj
    if prorroga:
        return "misto" if acresce else "renovacao"
    return "acrescimo"


def regra_aditivos(con, cfg, lote: Lote):
    lim, lim_ref = A(cfg, "aditivo_limite", 0.25), A(cfg, "aditivo_limite_reforma", 0.50)
    atencao, muitos = A(cfg, "aditivo_atencao", 0.20), A(cfg, "aditivo_muitos_termos", 4)
    sql = """
      SELECT c.*, k.amparo_legal amparo_compra, COUNT(t.sequencial) n_termos
      FROM contratos c JOIN orgaos o ON o.cnpj=c.cnpj_orgao
      LEFT JOIN contratacoes k ON k.id_pncp=c.id_pncp_compra
      LEFT JOIN termos t ON t.id_contrato=c.id_pncp
      WHERE o.alvo=1 GROUP BY c.id_pncp"""
    for c in con.execute(sql):
        vi = c["valor_inicial"] or 0
        if vi <= 0 or not c["n_termos"]:
            continue
        reforma = "reforma" in normalizar(c["objeto"])
        limite = lim_ref if reforma else lim
        termos = [dict(t) for t in con.execute(
            "SELECT numero, tipo, data_assinatura, valor_acrescido, valor_global, prazo_aditado_dias, objeto, "
            "qualifica_acrescimo FROM termos WHERE id_contrato=? ORDER BY data_assinatura, sequencial", (c["id_pncp"],))]
        soma = defaultdict(float)
        for t in termos:
            t["classe"] = classificar_termo(t)
            v = t["valor_acrescido"] or 0
            if v > 0 and (t["classe"] != "acrescimo" or t["qualifica_acrescimo"] in (None, 1)):
                soma[t["classe"]] += v
        acresc = soma["acrescimo"]
        pct = acresc / vi
        comum = dict(cnpj_orgao=c["cnpj_orgao"], ni_fornecedor=c["ni_fornecedor"],
                     nome_fornecedor=c["nome_fornecedor"], data=c["data_assinatura"], id_contrato=c["id_pncp"],
                     id_contratacao=c["id_pncp_compra"],
                     evidencias=[{"tipo": "contrato", "objeto": c["objeto"], "valor_inicial": vi,
                                  "valor_global": c["valor_global"], "data_assinatura": c["data_assinatura"],
                                  "vigencia": f"{c['vigencia_inicio']} a {c['vigencia_fim']}",
                                  "amparo_da_compra": c["amparo_compra"]}]
                     + [{"tipo": "termo", **{k: v for k, v in t.items() if k != "qualifica_acrescimo"}} for t in termos])
        nota_renov = (f" Prorrogações sem acréscimo (renovação do período, que não conta no limite): "
                      f"{reais(soma['renovacao'])}." if soma["renovacao"] else "")
        if pct > limite:
            lote.add("R03", "alta", f"Acréscimos de {pc(pct)} no contrato com {c['nome_fornecedor']}",
                     f"Valor inicial {reais(vi)}; acréscimos de valor somados {reais(acresc)} "
                     f"({pc(pct)}), acima do limite de {pc(limite)}{' (reforma)' if reforma else ''}.{nota_renov}",
                     c["id_pncp"], valor=vi + acresc, excesso=(pct - limite) * vi, **comum)
        elif pct >= atencao:
            lote.add("R03", "media", f"Acréscimos de {pc(pct)} (perto do limite) com {c['nome_fornecedor']}",
                     f"Valor inicial {reais(vi)}; acréscimos {reais(acresc)} ({pc(pct)}). "
                     f"Limite legal: {pc(limite)}.{nota_renov}", c["id_pncp"], valor=vi + acresc, **comum)
        if soma["misto"] > 0:
            lote.add("R03", "media", f"Prorrogação junto com acréscimo de valor no contrato com {c['nome_fornecedor']}",
                     f"Valor inicial {reais(vi)}; termo(s) que prorrogam o prazo e também acrescentam valor somam "
                     f"{reais(soma['misto'])}. É preciso separar quanto é renovação e quanto é acréscimo.",
                     c["id_pncp"] + "|misto", valor=vi + soma["misto"], **comum)
        if soma["apostila"] > limite * vi:
            lote.add("R03", "media", f"Apostilamento de {pc(soma['apostila'] / vi)} do valor no contrato com {c['nome_fornecedor']}",
                     f"Apostilamento serve para reajuste, repactuação ou dotação, não para aumentar o contrato. "
                     f"Aqui somam {reais(soma['apostila'])} sobre {reais(vi)}.",
                     c["id_pncp"] + "|apostila", valor=vi + soma["apostila"], **comum)
        if pct < atencao and not soma["misto"] and c["n_termos"] >= muitos:
            lote.add("R03", "baixa", f"{c['n_termos']} termos no contrato com {c['nome_fornecedor']}",
                     f"Contrato de {reais(vi)} com {c['n_termos']} termos aditivos ou apostilamentos.",
                     c["id_pncp"], valor=vi, **comum)
        # R19: contrato emergencial (art. 75, VIII) que foi prorrogado
        prorrogs = [t for t in termos if t["classe"] in ("renovacao", "misto")]
        if inciso_art75(c["amparo_compra"]) == "VIII" and prorrogs:
            dias = sum(t["prazo_aditado_dias"] or 0 for t in prorrogs)
            v = sum(t["valor_acrescido"] or 0 for t in prorrogs)
            # Prazo total = vigência original + dias aditados. A lei põe o teto de 1 ano para a emergência;
            # há entendimentos que aceitam prorrogar dentro desse ano. Passou de 1 ano: alta; dentro: média.
            ini, fim = _d(c["vigencia_inicio"]), _d(c["vigencia_fim"])
            total = ((fim - ini).days + dias) if ini and fim else None
            passou = total is not None and total > 365
            prazo = (f" Prazo total: {total} dias" + (", mais de 1 ano." if passou else
                     ", dentro de 1 ano (há quem entenda que a prorrogação é aceitável dentro desse limite; a lei "
                     "diz \"vedada a prorrogação\").") if total is not None else "")
            lote.add("R19", "alta" if passou or total is None else "media",
                     f"Contrato emergencial prorrogado: {c['nome_fornecedor']}",
                     f"Contratado por emergência (art. 75, VIII) em {_fmt_data(c['data_assinatura'])} por {reais(vi)} "
                     f"e prorrogado {len(prorrogs)} vez(es)" + (f", +{dias} dias" if dias else "")
                     + (f", +{reais(v)}" if v else "") + " (termos registrados no PNCP)." + prazo
                     + " A Lei 14.133, art. 75, VIII, veda prorrogar contrato emergencial; o alerta pergunta se foi o caso.",
                     c["id_pncp"] + "|R19", valor=vi + v, **comum)


RE_NATUREZA_COM_CAPITAL = re.compile(r"sociedade (empres[aá]ria|simples|an[oô]nima)|empres[aá]rio|eireli|"
                                     r"individual de responsabilidade|cooperativa", re.I)

GENERICOS_CONTRATACAO = {normalizar(w) for w in """
contratacao empresa especializada prestacao servico servicos forma continua municipio cariacica fornecimento
execucao executados unidades administrativas municipalidade desta carater emergencial emergencia emergencial
pessoa juridica atender necessidades secretaria municipal""".split()}


def _fmt_data(s):
    d = _d(s)
    return f"{d:%d/%m/%Y}" if d else "data não informada"


# ---------------------------------------------------------------- R04 / R05 / R06 dispensas
def _dispensas(con):
    sql = """
      SELECT c.id_pncp, c.cnpj_orgao, c.objeto, c.amparo_legal, c.data_publicacao, c.processo, c.numero_compra,
             COALESCE(c.valor_homologado, c.valor_estimado) valor_compra
      FROM contratacoes c WHERE c.alvo=1 AND c.modalidade_id=8 ORDER BY c.id_pncp"""
    saida, vistos = [], set()
    for c in con.execute(sql):
        # A mesma dispensa às vezes é publicada duas vezes no PNCP (mesmo processo, número e valor)
        chave = (c["cnpj_orgao"], (c["processo"] or "").strip(), (c["numero_compra"] or "").strip(), c["valor_compra"])
        if chave[1] and chave[2]:
            if chave in vistos:
                continue
            vistos.add(chave)
        inc = inciso_art75(c["amparo_legal"])
        d = _d(c["data_publicacao"])
        forn = {}
        for r in con.execute("SELECT ni_fornecedor, MAX(nome_fornecedor) nome, SUM(valor_total) v "
                             "FROM resultados WHERE id_pncp=? GROUP BY ni_fornecedor", (c["id_pncp"],)):
            if r["ni_fornecedor"]:
                forn[r["ni_fornecedor"]] = (r["nome"], r["v"] or 0)
        if not forn:
            for r in con.execute("SELECT ni_fornecedor, MAX(nome_fornecedor) nome, SUM(valor_global) v "
                                 "FROM contratos WHERE id_pncp_compra=? GROUP BY ni_fornecedor", (c["id_pncp"],)):
                if r["ni_fornecedor"]:
                    forn[r["ni_fornecedor"]] = (r["nome"], r["v"] or 0)
        saida.append({**dict(c), "inciso": inc, "dt": d, "fornecedores": forn,
                      "valor": sum(v for _, v in forn.values()) or (c["valor_compra"] or 0),
                      "tks": tokens(c["objeto"])})
    return saida


def regra_dispensas(con, cfg, lote: Lote):
    disp = _dispensas(con)
    sim = A(cfg, "fracionamento_similaridade", 0.5)
    # R04: mesmo fornecedor, mesmo órgão, mesmo ano, mesmo inciso
    grupos = defaultdict(list)
    for d in disp:
        if d["inciso"] in ("I", "II") and d["dt"]:
            for ni, (nome, v) in d["fornecedores"].items():
                grupos[(d["cnpj_orgao"], d["dt"].year, d["inciso"], ni)].append((d, nome, v))
    for (org, ano, inc, ni), itens in grupos.items():
        if len(itens) < 2:
            continue
        soma = sum(v for _, _, v in itens)
        lim = limite_dispensa(ano, inc)
        if lim and soma > lim:
            nome = itens[0][1]
            lote.add("R04", "alta" if soma > 2 * lim else "media",
                     f"{len(itens)} dispensas para {nome} em {ano} somam {reais(soma)}",
                     f"Limite da dispensa (art. 75, {inc}) em {ano}: {reais(lim)}. "
                     f"Soma para o mesmo fornecedor no mesmo órgão: {reais(soma)}.",
                     f"{org}|{ano}|{inc}|{ni}", cnpj_orgao=org, ni_fornecedor=ni, nome_fornecedor=nome,
                     valor=soma, excesso=soma - lim, data=f"{ano}-12-31",
                     evidencias=[{"tipo": "dispensa", "objeto": d["objeto"], "data": d["data_publicacao"],
                                  "valor": v, "amparo": d["amparo_legal"], "link": link_compra(d["id_pncp"])}
                                 for d, _, v in sorted(itens, key=lambda x: x[0]["data_publicacao"] or "")],
                     links=[link_compra(d["id_pncp"]) for d, _, _ in itens][:10])

    # R05: objetos parecidos (agrupamento simples)
    por_org = defaultdict(list)
    for d in disp:
        if d["inciso"] in ("I", "II") and d["dt"] and d["tks"]:
            por_org[(d["cnpj_orgao"], d["dt"].year, d["inciso"])].append(d)
    for (org, ano, inc), lista in por_org.items():
        lim = limite_dispensa(ano, inc)
        usados = set()
        for i, base in enumerate(lista):
            if i in usados:
                continue
            grupo = [base]
            for j in range(i + 1, len(lista)):
                if j not in usados and jaccard(base["tks"], lista[j]["tks"]) >= sim:
                    grupo.append(lista[j])
                    usados.add(j)
            soma = sum(g["valor"] for g in grupo)
            if len(grupo) >= 2 and lim and soma > lim:
                lote.add("R05", "alta" if soma > 2 * lim else "media",
                         f"{len(grupo)} dispensas parecidas em {ano}: \"{base['objeto'][:70]}\"",
                         f"Somam {reais(soma)}; limite da dispensa (art. 75, {inc}) em {ano}: {reais(lim)}.",
                         f"{org}|{ano}|{inc}|" + "|".join(sorted(g["id_pncp"] for g in grupo)),
                         cnpj_orgao=org, valor=soma, excesso=soma - lim, data=f"{ano}-12-31",
                         evidencias=[{"tipo": "dispensa", "objeto": g["objeto"], "data": g["data_publicacao"],
                                      "valor": g["valor"], "fornecedores": ", ".join(n for n, _ in g["fornecedores"].values()),
                                      "link": link_compra(g["id_pncp"])} for g in grupo],
                         links=[link_compra(g["id_pncp"]) for g in grupo][:10])

    # R06: emergências repetidas (art. 75, VIII)
    emerg = [d for d in disp if d["inciso"] == "VIII" and d["dt"]]
    por_forn = defaultdict(list)
    for d in emerg:
        for ni, (nome, v) in d["fornecedores"].items():
            por_forn[(d["cnpj_orgao"], ni)].append((d, nome, v))
    for (org, ni), itens in por_forn.items():
        itens.sort(key=lambda x: x[0]["dt"])
        if len(itens) >= 2 and (itens[-1][0]["dt"] - itens[0][0]["dt"]).days <= 730:
            soma = sum(v for _, _, v in itens)
            lote.add("R06", "alta", f"{len(itens)} contratações emergenciais com {itens[0][1]}",
                     f"Emergências (art. 75, VIII) com o mesmo fornecedor em menos de 2 anos, somando {reais(soma)}. "
                     f"A Lei 14.133, art. 75, VIII, veda recontratar por emergência a empresa já contratada por "
                     f"emergência; o alerta pergunta se foi o caso.",
                     f"{org}|{ni}", cnpj_orgao=org, ni_fornecedor=ni, nome_fornecedor=itens[0][1],
                     valor=soma, data=itens[-1][0]["data_publicacao"],
                     evidencias=[{"tipo": "emergencia", "objeto": d["objeto"], "data": d["data_publicacao"],
                                  "valor": v, "link": link_compra(d["id_pncp"])} for d, _, v in itens])

    # R20: o mesmo serviço contratado por emergência de novo (qualquer fornecedor).
    # Compara o objeto SEM o texto padrão de contratação ("empresa especializada para prestação de serviços
    # ... de forma contínua"), que fazia limpeza e portaria parecerem o mesmo serviço (revisão de 08/11/2026).
    sim20 = A(cfg, "emergencia_repetida_similaridade", 0.4)
    por_org = defaultdict(list)
    for d in emerg:
        tks20 = d["tks"] - GENERICOS_CONTRATACAO
        if tks20:
            por_org[d["cnpj_orgao"]].append({**d, "tks": tks20})
    for org, lista in por_org.items():
        lista.sort(key=lambda x: x["dt"])
        usados = set()
        for i, base in enumerate(lista):
            if i in usados:
                continue
            grupo = [base]
            for j in range(i + 1, len(lista)):
                if j not in usados and max(jaccard(g["tks"], lista[j]["tks"]) for g in grupo) >= sim20:
                    grupo.append(lista[j])
                    usados.add(j)
            if len(grupo) < 2 or (grupo[-1]["dt"] - grupo[0]["dt"]).days < 150:
                continue
            soma = sum(g["valor"] for g in grupo)
            forns = {n for g in grupo for n, _ in g["fornecedores"].values()}
            obra = any(w in normalizar(base["objeto"]) for w in ("encosta", "contencao", "calamidade", "enchente", "chuva"))
            grav = "media" if obra else "alta"
            lote.add("R20", grav, f"{len(grupo)} emergências para o mesmo serviço: \"{base['objeto'].strip()[:70]}\"",
                     f"De {_fmt_data(grupo[0]['data_publicacao'])} a {_fmt_data(grupo[-1]['data_publicacao'])}, "
                     f"{len(grupo)} contratações emergenciais parecidas somando {reais(soma)}, com {len(forns) or 'nenhum'} "
                     f"fornecedor(es) diferente(s).",
                     f"{org}|R20|" + "|".join(sorted(g["id_pncp"] for g in grupo)), cnpj_orgao=org, valor=soma,
                     data=grupo[-1]["data_publicacao"],
                     evidencias=[{"tipo": "emergencia", "objeto": g["objeto"], "data": g["data_publicacao"],
                                  "valor": g["valor"], "fornecedores": ", ".join(n.strip() for n, _ in g["fornecedores"].values()),
                                  "link": link_compra(g["id_pncp"])} for g in grupo],
                     links=[link_compra(g["id_pncp"]) for g in grupo][:10])


# ---------------------------------------------------------------- R07 carona / R08 desconto / R18 datas
def regra_compras(con, cfg, lote: Lote):
    sql = """
      SELECT c.*, k.objeto k_objeto, k.valor_estimado k_est, k.valor_homologado k_hom, k.srp k_srp,
             k.municipio_ibge k_ibge, k.municipio_nome k_mun, k.data_publicacao k_pub,
             ok.razao_social k_orgao
      FROM contratos c JOIN orgaos o ON o.cnpj=c.cnpj_orgao
      LEFT JOIN contratacoes k ON k.id_pncp=c.id_pncp_compra
      LEFT JOIN orgaos ok ON ok.cnpj=c.cnpj_orgao_compra
      WHERE o.alvo=1"""
    for c in con.execute(sql):
        # R18 - datas
        assin, pub = _d(c["data_assinatura"]), _d(c["k_pub"])
        vi, vf = _d(c["vigencia_inicio"]), _d(c["vigencia_fim"])
        if c["cnpj_orgao_compra"] == c["cnpj_orgao"] and assin and pub and (pub - assin).days > 1:
            lote.add("R18", "baixa", f"Contrato com {c['nome_fornecedor']} assinado antes da compra ser publicada",
                     f"Assinatura em {assin:%d/%m/%Y}; publicação da contratação no PNCP em {pub:%d/%m/%Y}.",
                     f"assin|{c['id_pncp']}", cnpj_orgao=c["cnpj_orgao"], ni_fornecedor=c["ni_fornecedor"],
                     nome_fornecedor=c["nome_fornecedor"], valor=c["valor_global"], data=c["data_assinatura"],
                     id_contrato=c["id_pncp"], id_contratacao=c["id_pncp_compra"])
        if vi and vf and vf < vi:
            lote.add("R18", "baixa", f"Vigência inválida no contrato com {c['nome_fornecedor']}",
                     f"Vigência termina ({vf:%d/%m/%Y}) antes de começar ({vi:%d/%m/%Y}).",
                     f"vig|{c['id_pncp']}", cnpj_orgao=c["cnpj_orgao"], ni_fornecedor=c["ni_fornecedor"],
                     nome_fornecedor=c["nome_fornecedor"], valor=c["valor_global"], data=c["data_assinatura"],
                     id_contrato=c["id_pncp"])

        # R07 - adesão a compra de outro órgão
        if not c["cnpj_orgao_compra"] or c["cnpj_orgao_compra"] == c["cnpj_orgao"]:
            continue
        agravantes = []
        nome_ext = c["k_orgao"] or formatar_cnpj(c["cnpj_orgao_compra"])
        if "CONSORCIO" in normalizar(nome_ext).upper():
            agravantes.append("ata de consórcio público")
        if c["k_ibge"] and not str(c["k_ibge"]).startswith("32"):
            agravantes.append(f"órgão de fora do ES ({c['k_mun'] or c['k_ibge']})")
        itens = con.execute("SELECT quantidade FROM itens WHERE id_pncp=?", (c["id_pncp_compra"],)).fetchall()
        if c["k_objeto"] is not None:
            if not itens or all((i["quantidade"] or 0) <= 1 for i in itens):
                agravantes.append("compra de origem sem quantitativos definidos")
            if c["k_est"] and c["k_hom"] and c["k_est"] > 0:
                desc = 1 - c["k_hom"] / c["k_est"]
                if desc < 0.05:
                    agravantes.append(f"desconto de apenas {pc(desc, 1)} na licitação de origem")
        grav = "alta" if len(agravantes) >= 2 else "media" if agravantes else "baixa"
        lote.add("R07", grav, f"Adesão a compra de {nome_ext[:60]} - {c['nome_fornecedor']}",
                 f"Contrato de {reais(c['valor_global'])} feito sobre licitação de outro órgão."
                 + (f" Agravantes: {'; '.join(agravantes)}." if agravantes else
                    " Sem agravantes detectados (informativo)."),
                 c["id_pncp"], cnpj_orgao=c["cnpj_orgao"], ni_fornecedor=c["ni_fornecedor"],
                 nome_fornecedor=c["nome_fornecedor"], valor=c["valor_global"], data=c["data_assinatura"],
                 id_contrato=c["id_pncp"], id_contratacao=c["id_pncp_compra"],
                 evidencias=[{"tipo": "contrato", "objeto": c["objeto"], "valor": c["valor_global"],
                              "data_assinatura": c["data_assinatura"]},
                             {"tipo": "compra_origem", "orgao": nome_ext, "objeto": c["k_objeto"],
                              "estimado": c["k_est"], "homologado": c["k_hom"],
                              "itens": len(itens)}])

    # R08 - desconto quase zero
    dmin, dcrit = A(cfg, "desconto_minimo", 0.03), A(cfg, "desconto_critico", 0.01)
    vmin = A(cfg, "desconto_valor_minimo", 100000)
    for k in con.execute("""SELECT * FROM contratacoes WHERE alvo=1 AND modalidade_id IN (4,5,6,7)
                            AND valor_estimado >= ? AND valor_homologado > 0""", (vmin,)):
        desc = 1 - k["valor_homologado"] / k["valor_estimado"]
        if 0 <= desc < dmin:  # homologado acima do estimado é outro fenômeno; não entra aqui
            lote.add("R08", "media" if desc < dcrit else "baixa",
                     f"Desconto de {pc(desc, 1)} em \"{(k['objeto'] or '')[:80]}\"",
                     f"Estimado {reais(k['valor_estimado'])}, homologado {reais(k['valor_homologado'])}.",
                     k["id_pncp"], cnpj_orgao=k["cnpj_orgao"], valor=k["valor_homologado"],
                     data=k["data_publicacao"], id_contratacao=k["id_pncp"],
                     evidencias=[{"tipo": "compra", "modalidade": k["modalidade_nome"], "objeto": k["objeto"],
                                  "estimado": k["valor_estimado"], "homologado": k["valor_homologado"]}])


# ---------------------------------------------------------------- fornecedores
def _ganhos_por_fornecedor(con):
    """Lista (data, valor, orgão, id) por CNPJ: contratos, ou resultados quando não há contrato."""
    ganhos = defaultdict(list)
    com_contrato = set()
    for c in con.execute("""SELECT c.ni_fornecedor, c.data_assinatura, c.valor_global, c.cnpj_orgao,
                            c.id_pncp, c.id_pncp_compra FROM contratos c JOIN orgaos o ON o.cnpj=c.cnpj_orgao
                            WHERE o.alvo=1 AND length(c.ni_fornecedor)=14""").fetchall():
        ganhos[c["ni_fornecedor"]].append((_d(c["data_assinatura"]), c["valor_global"] or 0, c["cnpj_orgao"],
                                           c["id_pncp"], "contrato"))
        com_contrato.add((c["ni_fornecedor"], c["id_pncp_compra"]))
    for r in con.execute("""SELECT r.ni_fornecedor, MIN(COALESCE(r.data_resultado, k.data_publicacao)) d,
                            SUM(r.valor_total) v, k.cnpj_orgao, r.id_pncp FROM resultados r
                            JOIN contratacoes k ON k.id_pncp=r.id_pncp WHERE k.alvo=1 AND length(r.ni_fornecedor)=14
                            GROUP BY r.ni_fornecedor, r.id_pncp""").fetchall():
        if (r["ni_fornecedor"], r["id_pncp"]) not in com_contrato:
            ganhos[r["ni_fornecedor"]].append((_d(r["d"]), r["v"] or 0, r["cnpj_orgao"], r["id_pncp"], "resultado"))
    return ganhos


def regra_fornecedores(con, cfg, lote: Lote):
    ganhos = _ganhos_por_fornecedor(con)
    forn = {r["cnpj"]: dict(r) for r in con.execute("SELECT * FROM fornecedores")}
    dias_n, dias_g = A(cfg, "empresa_nova_dias", 180), A(cfg, "empresa_nova_dias_grave", 90)
    v_grave = A(cfg, "empresa_nova_valor_grave", 200000)
    cap_pct, cap_min = A(cfg, "capital_minimo_pct", 0.05), A(cfg, "capital_valor_minimo", 200000)
    mei_lim = A(cfg, "mei_limite_anual", 81000)

    def ev(lista, limite=12):
        return [{"tipo": t, "data": str(d) if d else None, "valor": v,
                 "orgao": lote.orgaos.get(o, o), "link": link_contrato(i) if t == "contrato" else link_compra(i)}
                for d, v, o, i, t in sorted(lista, key=lambda x: x[0] or dt.date.min)[:limite]]

    for ni, lista in ganhos.items():
        f = forn.get(ni)
        if not f:
            continue
        nome = f["razao_social"] or ni
        datados = [x for x in lista if x[0]]
        total = sum(x[1] for x in lista)
        # R09 empresa nova
        abertura = _d(f["data_abertura"])
        if abertura and datados:
            primeiro = min(datados, key=lambda x: x[0])
            dias = (primeiro[0] - abertura).days
            v12 = sum(x[1] for x in datados if (x[0] - primeiro[0]).days <= 365)
            consorcio = normalizar(nome).startswith("consorcio") or "consorcio" in normalizar(f["natureza_juridica"])
            if 0 <= dias < dias_n:
                grav = "alta" if dias < dias_g and v12 >= v_grave else "media"
                if consorcio:  # consórcio de empresas costuma ser criado para a própria licitação (art. 15)
                    grav = "baixa"
                lote.add("R09", grav, f"{nome}: aberta {dias} dias antes do primeiro contrato",
                         f"CNPJ aberto em {abertura:%d/%m/%Y}; primeiro ganho em {primeiro[0]:%d/%m/%Y}. "
                         f"Valor contratado/homologado nos primeiros 12 meses: {reais(v12)}.",
                         ni, cnpj_orgao=primeiro[2], ni_fornecedor=ni, nome_fornecedor=nome, valor=v12,
                         data=str(primeiro[0]), evidencias=[{"tipo": "cadastro", "abertura": f["data_abertura"],
                                                             "capital_social": f["capital_social"],
                                                             "cnae": f["cnae_descricao"],
                                                             "endereco": f"{f['logradouro']} {f['numero']} - {f['bairro']}, {f['municipio']}/{f['uf']}"}]
                         + ev(lista))
        # por ano
        por_ano = defaultdict(float)
        for d, v, *_ in datados:
            por_ano[d.year] += v
        # R10 capital: só para empresa com capital social de verdade. Associação, fundação, organização
        # social, sindicato, consórcio público ou de sociedades e serviço social autônomo não têm capital
        # (a Receita mostra R$ 0), então ficavam como falso positivo (revisão de 09/11/2026: 10 de 20).
        cap = f["capital_social"]
        natureza = f["natureza_juridica"] or ""
        tem_capital = not natureza or bool(RE_NATUREZA_COM_CAPITAL.search(natureza))
        if cap is not None and por_ano and tem_capital:
            ano, maior = max(por_ano.items(), key=lambda x: x[1])
            if maior >= cap_min and cap < cap_pct * maior:
                lote.add("R10", "media", f"{nome}: capital de {reais(cap)} para {reais(maior)} contratados em {ano}",
                         f"Capital social equivale a {pc(cap / maior, 1)} do valor contratado no ano.",
                         ni, ni_fornecedor=ni, nome_fornecedor=nome, valor=maior, data=f"{ano}-12-31",
                         evidencias=ev(lista))
        # R11 MEI
        if f["opcao_mei"] == 1:
            for ano, v in por_ano.items():
                if v > mei_lim:
                    lote.add("R11", "media", f"{nome} (MEI) teve {reais(v)} contratados com o município em {ano}",
                             f"Limite anual de faturamento do MEI: {reais(mei_lim)}. Valor contratado/homologado só "
                             f"neste município: {reais(v)}.",
                             f"{ni}|{ano}", ni_fornecedor=ni, nome_fornecedor=nome, valor=v, data=f"{ano}-12-31",
                             evidencias=ev([x for x in lista if x[0] and x[0].year == ano]))
        # R12 situação
        sit = (f["situacao"] or "").upper()
        if sit and sit != "ATIVA":
            dsit = _d(f["data_situacao"])
            depois = [x for x in datados if dsit and x[0] >= dsit]
            texto_sit = (f"Situação cadastral {sit} desde {dsit:%d/%m/%Y}." if dsit
                         else f"Situação cadastral {sit}.")
            if depois:
                texto_sit += f" Houve {len(depois)} contratação(ões) depois disso."
            lote.add("R12", "alta" if depois else "baixa", f"{nome}: situação '{sit}' na Receita",
                     texto_sit,
                     ni, ni_fornecedor=ni, nome_fornecedor=nome, valor=total,
                     data=f["data_situacao"], evidencias=ev(depois or lista))
        # R13 sanções
        for s in con.execute("SELECT * FROM sancoes WHERE cnpj=?", (ni,)):
            ini_s, fim_s = _d(s["data_inicio"]), _d(s["data_fim"]) or dt.date(9999, 1, 1)
            durante = [x for x in datados if ini_s and ini_s <= x[0] <= fim_s]
            lote.add("R13", "alta" if durante else "baixa",
                     f"{nome}: {s['cadastro']} - {s['tipo'] or 'sanção'}",
                     f"Sanção aplicada por {s['orgao_sancionador'] or '?'} de {s['data_inicio'] or '?'} a "
                     f"{s['data_fim'] or 'indeterminado'}." + (f" {len(durante)} contratação(ões) dentro do período."
                                                              if durante else " Nenhuma contratação dentro do período."),
                     f"{ni}|{s['cadastro']}|{s['data_inicio']}", ni_fornecedor=ni, nome_fornecedor=nome,
                     valor=sum(x[1] for x in durante) or total, data=s["data_inicio"],
                     evidencias=[{"tipo": "sancao", **dict(s)}] + ev(durante or lista))

    # R14 sócio = servidor
    if con.execute("SELECT 1 FROM servidores LIMIT 1").fetchone():
        servidores = defaultdict(list)
        for s in con.execute("SELECT nome, nome_normalizado, cargo, lotacao FROM servidores"):
            if len(s["nome_normalizado"].split()) >= 3:
                servidores[s["nome_normalizado"]].append(dict(s))
        for s in con.execute("SELECT cnpj, nome, qualificacao FROM socios"):
            nn = nome_pessoa(s["nome"])
            if nn in servidores and s["cnpj"] in ganhos:
                f = forn.get(s["cnpj"], {})
                lote.add("R14", "media", f"Sócio de {f.get('razao_social') or s['cnpj']} tem nome igual ao de servidor",
                         f"Sócio: {s['nome']} ({s['qualificacao']}). Servidor(es): "
                         + "; ".join(f"{x['nome']} - {x['cargo'] or '?'} / {x['lotacao'] or '?'}" for x in servidores[nn])
                         + ". PODE SER HOMÔNIMO: confirme antes de qualquer conclusão.",
                         f"{s['cnpj']}|{nn}", ni_fornecedor=s["cnpj"], nome_fornecedor=f.get("razao_social"),
                         valor=sum(x[1] for x in ganhos[s["cnpj"]]),
                         evidencias=[{"tipo": "socio", "nome": s["nome"], "qualificacao": s["qualificacao"]}]
                         + [{"tipo": "servidor", **x} for x in servidores[nn]] + ev(ganhos[s["cnpj"]]))

    # R15 sócios em comum / R16 contatos em comum
    ativos = set(ganhos) & set(forn)
    orgaos_de = {ni: {x[2] for x in ganhos[ni]} for ni in ativos}
    compras_de = {ni: {x[3] for x in ganhos[ni]} for ni in ativos}
    por_socio = defaultdict(set)
    socio_pj = {}
    for s in con.execute("SELECT cnpj, nome, documento FROM socios"):
        nn = nome_pessoa(s["nome"])
        if s["cnpj"] in ativos and len(nn.split()) >= 3:
            por_socio[nn].add(s["cnpj"])
            socio_pj[nn] = len("".join(ch for ch in (s["documento"] or "") if ch.isdigit())) == 14
    for socio, cnpjs in por_socio.items():
        if len(cnpjs) < 2:
            continue
        lista = sorted(cnpjs)
        comuns = set.intersection(*(orgaos_de[c] for c in lista)) or set.union(*(orgaos_de[c] for c in lista))
        mesma_compra = any(len({c for c in lista if k in compras_de[c]}) >= 2
                           for k in set.union(*(compras_de[c] for c in lista)))
        nomes = [forn[c]["razao_social"] for c in lista]
        lote.add("R15", "media" if mesma_compra else "baixa",
                 (f"{len(lista)} fornecedores com o mesmo sócio: {socio.title()}" if socio_pj.get(socio)
                  else f"{len(lista)} fornecedores com o mesmo sócio (pessoa física)"),
                 f"Empresas: {'; '.join(nomes)}. Todas contratam com o município"
                 + (" e ganharam itens na MESMA contratação." if mesma_compra else "."),
                 f"{socio}|{'|'.join(lista)}", ni_fornecedor=lista[0], nome_fornecedor=" / ".join(nomes)[:200],
                 valor=sum(sum(x[1] for x in ganhos[c]) for c in lista), cnpj_orgao=sorted(comuns)[0],
                 evidencias=[{"tipo": "empresa", "cnpj": formatar_cnpj(c), "nome": forn[c]["razao_social"],
                              "total_recebido": sum(x[1] for x in ganhos[c])} for c in lista])

    for campo, rotulo, grav in (("telefone", "telefone", "media"), ("email", "e-mail", "media"),
                                ("endereco", "endereço", "baixa")):
        por_valor = defaultdict(set)
        for ni in ativos:
            f = forn[ni]
            chave = endereco(f["logradouro"], f["numero"], f["cep"]) if campo == "endereco" else (f[campo] or "")
            if chave and len(chave) >= 8:
                por_valor[chave].add(ni)
        for chave, cnpjs in por_valor.items():
            if len(cnpjs) < 2:
                continue
            lista = sorted(cnpjs)
            nomes = [forn[c]["razao_social"] for c in lista]
            if len(lista) > 6:   # muitos CNPJs no mesmo dado = provavelmente contador/escritório
                grav_f = "baixa"
            else:
                grav_f = grav
            lote.add("R16", grav_f, f"{len(lista)} fornecedores com o mesmo {rotulo}",
                     f"Empresas: {'; '.join(nomes)}.", f"{campo}|{chave}", ni_fornecedor=lista[0],
                     nome_fornecedor=" / ".join(nomes)[:200],
                     valor=sum(sum(x[1] for x in ganhos[c]) for c in lista),
                     evidencias=[{"tipo": "empresa", "cnpj": formatar_cnpj(c), "nome": forn[c]["razao_social"],
                                  rotulo: chave.split("|")[0]} for c in lista])


def regra_concentracao(con, cfg, lote: Lote):
    pct, vmin = A(cfg, "concentracao_pct", 0.30), A(cfg, "concentracao_valor_minimo", 1000000)
    linhas = con.execute("""SELECT c.cnpj_orgao, substr(c.data_assinatura,1,4) ano, c.ni_fornecedor,
                            MAX(c.nome_fornecedor) nome, SUM(c.valor_global) v
                            FROM contratos c JOIN orgaos o ON o.cnpj=c.cnpj_orgao
                            WHERE o.alvo=1 AND c.data_assinatura IS NOT NULL
                            GROUP BY c.cnpj_orgao, ano, c.ni_fornecedor""").fetchall()
    totais = defaultdict(float)
    for l in linhas:
        totais[(l["cnpj_orgao"], l["ano"])] += l["v"] or 0
    for l in linhas:
        tot = totais[(l["cnpj_orgao"], l["ano"])]
        if tot >= vmin and (l["v"] or 0) / tot >= pct:
            lote.add("R17", "baixa", f"{l['nome']} ficou com {pc((l['v'] or 0) / tot)} do que o órgão contratou em {l['ano']}",
                     f"{reais(l['v'])} de {reais(tot)} contratados pelo órgão no ano.",
                     f"{l['cnpj_orgao']}|{l['ano']}|{l['ni_fornecedor']}", cnpj_orgao=l["cnpj_orgao"],
                     ni_fornecedor=l["ni_fornecedor"], nome_fornecedor=l["nome"], valor=l["v"],
                     data=f"{l['ano']}-12-31")


# ---------------------------------------------------------------- execução
ETAPAS_PNCP = [("Preços (R01/R02)", regra_precos), ("Aditivos (R03, R19)", regra_aditivos),
              ("Dispensas (R04-R06, R20)", regra_dispensas), ("Compras e contratos (R07, R08, R18)", regra_compras),
              ("Fornecedores (R09-R16)", regra_fornecedores), ("Concentração (R17)", regra_concentracao)]


def regras_pncp(con, cfg, lote: Lote) -> None:
    for nome, f in ETAPAS_PNCP:
        antes = len(lote.itens)
        f(con, cfg, lote)
        log.info(f"  {nome}: {len(lote.itens) - antes} alertas")


def nomes_regras():
    return {k: v["nome"] for k, v in REGRAS.items()}
