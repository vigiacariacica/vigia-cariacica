"""Dossiê de um alerta: reúne tudo o que se sabe, o que perguntar e como encaminhar."""
from __future__ import annotations

import datetime as dt
import html
import json
from pathlib import Path

from .regras import GRAVIDADE_NOME, REGRAS
from .texto import formatar_cnpj, mascarar_cpf, reais

PERGUNTAS_LAI = {
    "R01": ["Cópia integral da pesquisa de preços que fundamentou o valor estimado (art. 23 da Lei 14.133/2021), "
            "com as cotações e fontes consultadas.",
            "Cópia do termo de referência ou especificação do item.",
            "Cópias das notas fiscais e dos termos de recebimento do item.",
            "Relação de empresas que participaram da disputa, com os preços ofertados."],
    "R03": ["Cópia de todos os termos aditivos do contrato, com os pareceres técnico e jurídico de cada um.",
            "Memória de cálculo dos acréscimos e supressões de valor.",
            "Justificativa técnica para cada alteração de quantidade ou de objeto."],
    "R04": ["Cópia integral dos processos de dispensa listados, incluindo justificativa, cotações e razão da escolha do fornecedor.",
            "Plano de Contratações Anual (PCA) do órgão para o ano em questão.",
            "Relação de todas as contratações diretas do órgão no exercício para o mesmo ramo de atividade."],
    "R06": ["Cópia dos processos de contratação emergencial, com a justificativa da situação emergencial.",
            "Informação sobre a licitação aberta para substituir a contratação emergencial e seu andamento."],
    "R07": ["Cópia do estudo que demonstrou a vantagem da adesão à ata de registro de preços (art. 86, §2º, da Lei 14.133/2021).",
            "Cópia da autorização do órgão gerenciador da ata e do aceite do fornecedor.",
            "Cópia da pesquisa de preços realizada antes da adesão.",
            "Quantitativos máximos previstos na ata e quantidades já aderidas por outros órgãos."],
    "R08": ["Ata da sessão pública com a relação de todos os licitantes, lances e propostas.",
            "Motivos de desclassificação ou inabilitação de licitantes."],
    "R09": ["Cópia dos documentos de habilitação apresentados pela empresa (atestados de capacidade técnica, "
            "balanço patrimonial, certidões)."],
    "R14": ["Declarações apresentadas pela empresa sobre inexistência de vínculo com agentes públicos (art. 14 da Lei 14.133/2021).",
            "Relação dos agentes públicos que atuaram na contratação (agente de contratação, pregoeiro, fiscal, gestor)."],
    "R15": ["Relação de todos os participantes das licitações em que as empresas atuaram, com propostas."],
    "R17": ["Relação de todos os contratos e pagamentos ao fornecedor no período."],
}
PERGUNTAS_LAI["R02"] = PERGUNTAS_LAI["R01"]
PERGUNTAS_LAI["R05"] = PERGUNTAS_LAI["R04"]
for _r in ("R10", "R11", "R12", "R13"):
    PERGUNTAS_LAI[_r] = PERGUNTAS_LAI["R09"]
PERGUNTAS_LAI["R16"] = PERGUNTAS_LAI["R15"]
PERGUNTAS_LAI["R18"] = ["Cópia do extrato publicado no Diário Oficial e do processo com as datas de cada ato."]


def _md_tabela(evs: list[dict]) -> str:
    if not evs:
        return "_sem evidências tabuladas_\n"
    chaves = []
    for e in evs:
        for k in e:
            if k not in chaves:
                chaves.append(k)
    linhas = ["| " + " | ".join(chaves) + " |", "|" + "---|" * len(chaves)]
    for e in evs:
        vals = []
        for k in chaves:
            v = e.get(k)
            if isinstance(v, float) and k in ("preco", "valor", "valor_inicial", "valor_global", "valor_acrescido",
                                              "estimado", "homologado", "total_recebido", "capital_social"):
                v = reais(v)
            vals.append(str(v if v is not None else "").replace("|", "/").replace("\n", " "))
        linhas.append("| " + " | ".join(vals) + " |")
    return "\n".join(linhas) + "\n"


def montar(con, id_alerta: str) -> str:
    a = con.execute("SELECT * FROM alertas WHERE id=?", (id_alerta,)).fetchone()
    if not a:
        raise SystemExit(f"Alerta {id_alerta} não encontrado.")
    a = dict(a)
    r = REGRAS[a["regra"]]
    evs = json.loads(a["evidencias"] or "[]")
    links = json.loads(a["links"] or "[]")
    doc = a["ni_fornecedor"] or ""
    doc_fmt = mascarar_cpf(doc) if len(doc) == 11 else formatar_cnpj(doc)

    md = [f"# Dossiê {a['id']} — {a['titulo']}", "",
          f"_Gerado em {dt.datetime.now():%d/%m/%Y %H:%M} pelo Vigia Cariacica a partir de dados públicos. "
          f"Este documento reúne INDÍCIOS para verificação. Não afirma a ocorrência de irregularidade._", "",
          "## Resumo", "",
          f"- **Tipo de alerta:** {a['regra']} — {r['nome']}",
          f"- **Gravidade calculada:** {GRAVIDADE_NOME.get(a['gravidade'], a['gravidade'])}",
          f"- **Órgão:** {a['nome_orgao'] or '-'} ({formatar_cnpj(a['cnpj_orgao'])})" if a["cnpj_orgao"] else "- **Órgão:** -",
          f"- **Fornecedor:** {a['nome_fornecedor'] or '-'} {f'({doc_fmt})' if doc else ''}",
          f"- **Valor envolvido:** {reais(a['valor_envolvido'])}",
          f"- **Excesso estimado:** {reais(a['valor_excesso'])}" if a["valor_excesso"] else None,
          f"- **Data de referência:** {a['data_referencia'] or '-'}",
          f"- **Status:** {a['status']}" + (f" — {a['nota']}" if a["nota"] else ""), "",
          "## O que os dados mostram", "", a["resumo"], "",
          "## Por que isso importa", "", r["porque"], "", f"**Base legal:** {r['base_legal']}", "",
          "## Evidências (dados públicos)", "", _md_tabela(evs), "",
          "## Fontes oficiais", ""] + [f"- {l}" for l in links] + [""]

    if doc and len(doc) == 14:
        f = con.execute("SELECT * FROM fornecedores WHERE cnpj=?", (doc,)).fetchone()
        if f:
            md += ["## Dados cadastrais do fornecedor (Receita Federal)", "",
                   f"- Razão social: {f['razao_social']}", f"- Nome fantasia: {f['nome_fantasia'] or '-'}",
                   f"- Abertura: {f['data_abertura']} · Situação: {f['situacao']} ({f['data_situacao'] or '-'})",
                   f"- Capital social: {reais(f['capital_social'])} · Porte: {f['porte'] or '-'} · "
                   f"MEI: {'sim' if f['opcao_mei'] else 'não'}",
                   f"- Atividade principal: {f['cnae']} — {f['cnae_descricao']}",
                   f"- Endereço: {f['logradouro']} {f['numero'] or ''} {f['complemento'] or ''} — {f['bairro']}, "
                   f"{f['municipio']}/{f['uf']} — CEP {f['cep']}", ""]
            socios = con.execute("SELECT nome, qualificacao, data_entrada FROM socios WHERE cnpj=?", (doc,)).fetchall()
            if socios:
                md += ["**Quadro de sócios:**", ""] + [
                    f"- {s['nome']} — {s['qualificacao'] or '-'} (desde {s['data_entrada'] or '-'})" for s in socios] + [""]
            contratos = con.execute("""SELECT c.id_pncp, c.objeto, c.valor_global, c.data_assinatura, o.razao_social
                                       FROM contratos c JOIN orgaos o ON o.cnpj=c.cnpj_orgao
                                       WHERE c.ni_fornecedor=? AND o.alvo=1 ORDER BY c.data_assinatura""", (doc,)).fetchall()
            if contratos:
                md += [f"**Contratos com o município ({len(contratos)}, total "
                       f"{reais(sum(c['valor_global'] or 0 for c in contratos))}):**", ""] + [
                    f"- {c['data_assinatura']} · {c['razao_social']} · {reais(c['valor_global'])} · {(c['objeto'] or '')[:120]}"
                    for c in contratos[:40]] + [""]

    md += ["## Antes de concluir qualquer coisa: como verificar", ""] + [f"- [ ] {v}" for v in r["verificar"]] + [
        "- [ ] Conferir cada número no link oficial (o PNCP pode ter erro de lançamento).",
        "- [ ] Pedir os documentos abaixo por LAI e ler o processo completo.",
        "- [ ] Registrar no sistema o resultado: `python -m vigia marcar " + a["id"] + " confirmado|descartado \"nota\"`", "",
        "## Explicações legítimas possíveis", ""] + [f"- {x}" for x in r["legitimas"]] + ["",
        "## Pedido pela Lei de Acesso à Informação (copiar no e-SIC)", "",
        "> Com fundamento na Lei nº 12.527/2011, solicito, em formato digital:", ">"] + [
        f"> {i}. {p}" for i, p in enumerate(PERGUNTAS_LAI.get(a["regra"], []), 1)] + [">",
        f"> Referência: {', '.join(links[:3]) or a['id_contratacao'] or a['id_contrato'] or ''}", ">",
        "> Peço que as informações sejam enviadas em até 20 dias, conforme o art. 11 da Lei 12.527/2011.", "",
        "## Se, DEPOIS de verificar, o indício se confirmar", "",
        "Qualquer cidadão pode denunciar irregularidades ao Tribunal de Contas (Constituição Federal, art. 74, §2º, "
        "aplicado aos estados pelo art. 75). Canais:",
        "- **TCE-ES** — Ouvidoria / denúncia (www.tcees.tc.br)",
        "- **Ministério Público do ES** — Ouvidoria (www.mpes.mp.br)",
        "- **Controladoria do Município** e **Câmara Municipal** (vereadores podem fazer representação)",
        "- Recursos federais (SUS, FUNDEB, FNDE): **CGU** via Fala.BR (falabr.cgu.gov.br) e **MPF**", "",
        "Estrutura sugerida para a denúncia: (1) fatos objetivos com datas, valores e links; "
        "(2) por que configuram possível irregularidade, citando a lei; (3) documentos anexos; "
        "(4) pedido de apuração. Use linguagem de indício (\"há indícios\", \"solicita-se apuração\") "
        "e nunca atribua crime a uma pessoa: quem apura é o órgão de controle.", ""]
    return "\n".join(x for x in md if x is not None)


def _md_para_html(md: str, titulo: str) -> str:
    """Conversão simples de Markdown para HTML imprimível (sem dependências)."""
    linhas, out, em_lista, em_tabela, em_citacao = md.split("\n"), [], False, False, False
    def fecha():
        nonlocal em_lista, em_tabela, em_citacao
        if em_lista: out.append("</ul>"); em_lista = False
        if em_tabela: out.append("</table>"); em_tabela = False
        if em_citacao: out.append("</blockquote>"); em_citacao = False
    def inline(t):
        t = html.escape(t)
        import re
        t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
        t = re.sub(r"`(.+?)`", r"<code>\1</code>", t)
        t = re.sub(r"(?<![\w/])_(.+?)_(?![\w])", r"<em>\1</em>", t)
        t = re.sub(r"(https?://[^\s<|]+)", r'<a href="\1">\1</a>', t)
        return t
    for l in linhas:
        if l.startswith("|"):
            if not em_tabela:
                fecha(); out.append("<table>"); em_tabela = True
            if set(l.replace("|", "").strip()) <= {"-"}:
                continue
            cel = [c.strip() for c in l.strip("|").split("|")]
            tag = "th" if len(out) and out[-1] == "<table>" else "td"
            out.append("<tr>" + "".join(f"<{tag}>{inline(c)}</{tag}>" for c in cel) + "</tr>")
            continue
        if l.startswith("- "):
            if not em_lista:
                fecha(); out.append("<ul>"); em_lista = True
            item = l[2:].replace("[ ] ", "☐ ")
            out.append(f"<li>{inline(item)}</li>")
            continue
        if l.startswith(">"):
            if not em_citacao:
                fecha(); out.append("<blockquote>"); em_citacao = True
            out.append(inline(l[1:].strip()) + "<br>")
            continue
        fecha()
        if l.startswith("# "):
            out.append(f"<h1>{inline(l[2:])}</h1>")
        elif l.startswith("## "):
            out.append(f"<h2>{inline(l[3:])}</h2>")
        elif l.strip():
            out.append(f"<p>{inline(l)}</p>")
    fecha()
    estilo = """body{font:15px/1.55 system-ui,'Segoe UI',sans-serif;max-width:900px;margin:32px auto;padding:0 16px;color:#0b0b0b}
    h1{font-size:22px}h2{font-size:17px;margin-top:28px;border-bottom:1px solid #e1e0d9;padding-bottom:4px}
    table{border-collapse:collapse;width:100%;font-size:12.5px}td,th{border:1px solid #e1e0d9;padding:4px 6px;vertical-align:top}
    th{background:#f3f2ee}blockquote{background:#f3f2ee;margin:0;padding:12px 16px;border-left:4px solid #2a78d6}
    code{background:#f3f2ee;padding:1px 5px;border-radius:4px}a{color:#1c5cab;word-break:break-all}
    @media print{a{color:#000}}"""
    return (f"<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><title>{html.escape(titulo)}</title>"
            f"<style>{estilo}</style></head><body>{''.join(out)}</body></html>")


def gerar(con, cfg, id_alerta: str) -> tuple[Path, Path]:
    md = montar(con, id_alerta)
    pasta = Path(cfg["_pasta_dados"]).parent / "saida" / "dossies"
    pasta.mkdir(parents=True, exist_ok=True)
    p_md = pasta / f"dossie_{id_alerta}.md"
    p_html = pasta / f"dossie_{id_alerta}.html"
    p_md.write_text(md, encoding="utf-8")
    p_html.write_text(_md_para_html(md, f"Dossiê {id_alerta}"), encoding="utf-8")
    return p_md, p_html
