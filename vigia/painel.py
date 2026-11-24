"""Gera o painel (HTML que abre no navegador, sem internet) e a planilha Excel."""
from __future__ import annotations

import datetime as dt
import json
from collections import defaultdict
from pathlib import Path

from . import log
from .regras import GRAVIDADE_PONTOS, REGRAS
from .texto import formatar_cnpj, mascarar_cpf

PASTA_SAIDA = "saida"


def _doc(ni: str | None) -> str:
    d = ni or ""
    return mascarar_cpf(d) if len(d) == 11 else formatar_cnpj(d)


def coletar_dados(con, cfg) -> dict:
    alertas = []
    for a in con.execute("SELECT * FROM alertas WHERE ativo=1"):
        a = dict(a)
        a["evidencias"] = json.loads(a["evidencias"] or "[]")
        a["links"] = json.loads(a["links"] or "[]")
        a["doc_fornecedor"] = _doc(a["ni_fornecedor"])
        alertas.append(a)
    alertas.sort(key=lambda a: (-GRAVIDADE_PONTOS.get(a["gravidade"], 0), -(a["valor_excesso"] or 0),
                                -(a["valor_envolvido"] or 0)))

    alertas_por_forn = defaultdict(lambda: [0, 0])
    for a in alertas:
        if a["ni_fornecedor"]:
            alertas_por_forn[a["ni_fornecedor"]][0] += 1
            alertas_por_forn[a["ni_fornecedor"]][1] += a["pontos"] or 0

    fornecedores = []
    for f in con.execute("""
        SELECT c.ni_fornecedor ni, MAX(c.nome_fornecedor) nome, COUNT(*) n, SUM(c.valor_global) total,
               MIN(c.data_assinatura) primeiro, MAX(c.data_assinatura) ultimo,
               fo.data_abertura, fo.capital_social, fo.situacao, fo.municipio, fo.uf, fo.cnae_descricao
        FROM contratos c JOIN orgaos o ON o.cnpj=c.cnpj_orgao
        LEFT JOIN fornecedores fo ON fo.cnpj=c.ni_fornecedor
        WHERE o.alvo=1 GROUP BY c.ni_fornecedor"""):
        f = dict(f)
        f["doc"] = _doc(f["ni"])
        f["alertas"], f["pontos"] = alertas_por_forn.get(f["ni"], [0, 0])
        fornecedores.append(f)
    fornecedores.sort(key=lambda f: (-f["pontos"], -(f["total"] or 0)))

    orgaos = [dict(r) for r in con.execute("""
        SELECT o.cnpj, o.razao_social,
               (SELECT COUNT(*) FROM contratacoes k WHERE k.cnpj_orgao=o.cnpj) n_compras,
               (SELECT COUNT(*) FROM contratos c WHERE c.cnpj_orgao=o.cnpj) n_contratos,
               (SELECT SUM(valor_global) FROM contratos c WHERE c.cnpj_orgao=o.cnpj) total
        FROM orgaos o WHERE o.alvo=1 ORDER BY total DESC""")]

    est = {
        "contratacoes": con.execute("SELECT COUNT(*) FROM contratacoes WHERE alvo=1").fetchone()[0],
        "contratos": con.execute("SELECT COUNT(*) FROM contratos c JOIN orgaos o ON o.cnpj=c.cnpj_orgao "
                                 "WHERE o.alvo=1").fetchone()[0],
        "valor_contratos": con.execute("SELECT COALESCE(SUM(valor_global),0) FROM contratos c JOIN orgaos o "
                                       "ON o.cnpj=c.cnpj_orgao WHERE o.alvo=1").fetchone()[0],
        "fornecedores": len(fornecedores),
        "itens": con.execute("SELECT COUNT(*) FROM itens i JOIN contratacoes c ON c.id_pncp=i.id_pncp "
                             "WHERE c.alvo=1").fetchone()[0],
        "referencias": con.execute("SELECT COUNT(*) FROM resultados r JOIN contratacoes c ON c.id_pncp=r.id_pncp "
                                   "WHERE c.alvo=0").fetchone()[0],
        "periodo": con.execute("SELECT MIN(data_publicacao), MAX(data_publicacao) FROM contratacoes "
                               "WHERE alvo=1").fetchone()[:],
        "ultima_coleta": con.execute("SELECT MAX(baixado_em) FROM bruto").fetchone()[0],
        "gerado_em": dt.datetime.now().strftime("%d/%m/%Y %H:%M"),
        "excesso_estimado": sum((a["valor_excesso"] or 0) for a in alertas
                                if a["regra"] in ("R01", "R02") and a["gravidade"] in ("alta", "media")),
    }
    return {"municipio": cfg["projeto"]["municipio_nome"], "estatisticas": est, "alertas": alertas,
            "fornecedores": fornecedores[:3000], "orgaos": orgaos, "regras": REGRAS}


def gerar_html(dados: dict, destino: Path) -> Path:
    modelo = (Path(__file__).parent / "painel_modelo.html").read_text(encoding="utf-8")
    js = json.dumps(dados, ensure_ascii=False, default=str).replace("</", "<\\/")
    destino.write_text(modelo.replace("/*__DADOS__*/null", js)
                       .replace("__MUNICIPIO__", dados["municipio"]), encoding="utf-8")
    return destino


def gerar_excel(dados: dict, con, destino: Path) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    cab_font = Font(bold=True, color="FFFFFF")
    cab_fill = PatternFill("solid", fgColor="1C5CAB")
    cores = {"alta": "F6D3D3", "media": "FBE3D7", "baixa": "FEF2D1"}

    def aba(ws, cabecalho, linhas, larguras, formatos=None, link_col=None, grav_col=None):
        ws.append(cabecalho)
        for c in ws[1]:
            c.font, c.fill = cab_font, cab_fill
            c.alignment = Alignment(vertical="center", wrap_text=True)
        for linha in linhas:
            # textos do PNCP às vezes trazem caracteres de controle que o Excel não aceita
            ws.append([ILLEGAL_CHARACTERS_RE.sub(" ", v) if isinstance(v, str) else v for v in linha])
        for i, w in enumerate(larguras, 1):
            ws.column_dimensions[get_column_letter(i)].width = w
        for col, fmt in (formatos or {}).items():
            for cel in ws[get_column_letter(col)][1:]:
                cel.number_format = fmt
        if link_col:
            for cel in ws[get_column_letter(link_col)][1:]:
                if cel.value and str(cel.value).startswith("http"):
                    cel.hyperlink = cel.value
                    cel.font = Font(color="1C5CAB", underline="single")
        if grav_col:
            for linha in ws.iter_rows(min_row=2):
                g = linha[grav_col - 1].value
                if g in cores:
                    linha[grav_col - 1].fill = PatternFill("solid", fgColor=cores[g])
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions

    moeda = '"R$" #,##0.00'
    ws = wb.active
    ws.title = "Alertas"
    aba(ws, ["ID", "Gravidade", "Regra", "Tipo de alerta", "Título", "Resumo", "Órgão", "Fornecedor",
             "CNPJ/CPF", "Valor envolvido", "Excesso estimado", "Data", "Status", "Nota", "Link"],
        [[a["id"], a["gravidade"], a["regra"], REGRAS[a["regra"]]["nome"], a["titulo"], a["resumo"],
          a["nome_orgao"], a["nome_fornecedor"], a["doc_fornecedor"], a["valor_envolvido"], a["valor_excesso"],
          a["data_referencia"], a["status"], a["nota"], (a["links"] or [None])[0]] for a in dados["alertas"]],
        [14, 10, 7, 34, 50, 70, 30, 34, 20, 16, 16, 12, 12, 30, 45], {10: moeda, 11: moeda}, 15, 2)

    ws = wb.create_sheet("Fornecedores")
    aba(ws, ["CNPJ/CPF", "Nome", "Contratos", "Total contratado", "Primeiro", "Último", "Abertura",
             "Capital social", "Situação", "Cidade", "UF", "Atividade", "Alertas", "Pontos"],
        [[f["doc"], f["nome"], f["n"], f["total"], f["primeiro"], f["ultimo"], f["data_abertura"],
          f["capital_social"], f["situacao"], f["municipio"], f["uf"], f["cnae_descricao"], f["alertas"],
          f["pontos"]] for f in dados["fornecedores"]],
        [20, 40, 10, 18, 12, 12, 12, 16, 12, 18, 5, 40, 9, 9], {4: moeda, 8: moeda})

    ws = wb.create_sheet("Contratos")
    linhas = []
    for c in con.execute("""SELECT c.*, o.razao_social orgao,
                            (SELECT COUNT(*) FROM termos t WHERE t.id_contrato=c.id_pncp) n_termos
                            FROM contratos c JOIN orgaos o ON o.cnpj=c.cnpj_orgao WHERE o.alvo=1
                            ORDER BY c.valor_global DESC"""):
        p = c["id_pncp"]
        from .alertas import link_contrato
        linhas.append([p, c["orgao"], c["numero"], c["objeto"], c["nome_fornecedor"], _doc(c["ni_fornecedor"]),
                       c["valor_inicial"], c["valor_global"], c["data_assinatura"], c["vigencia_inicio"],
                       c["vigencia_fim"], c["n_termos"],
                       "Adesão" if c["cnpj_orgao_compra"] and c["cnpj_orgao_compra"] != c["cnpj_orgao"] else "",
                       link_contrato(p)])
    aba(ws, ["ID PNCP", "Órgão", "Número", "Objeto", "Fornecedor", "CNPJ/CPF", "Valor inicial", "Valor global",
             "Assinatura", "Início", "Fim", "Termos", "Adesão?", "Link"], linhas,
        [30, 30, 14, 60, 34, 20, 16, 16, 12, 12, 12, 8, 9, 45], {7: moeda, 8: moeda}, 14)

    ws = wb.create_sheet("Contratações")
    from .alertas import link_compra
    aba(ws, ["ID PNCP", "Órgão", "Modalidade", "Objeto", "Estimado", "Homologado", "Publicação", "Situação",
             "Amparo legal", "Link"],
        [[k["id_pncp"], k["razao_social"], k["modalidade_nome"], k["objeto"], k["valor_estimado"],
          k["valor_homologado"], k["data_publicacao"], k["situacao"], k["amparo_legal"], link_compra(k["id_pncp"])]
         for k in con.execute("""SELECT k.*, o.razao_social FROM contratacoes k LEFT JOIN orgaos o
                                 ON o.cnpj=k.cnpj_orgao WHERE k.alvo=1 ORDER BY k.data_publicacao DESC""")],
        [30, 30, 18, 70, 16, 16, 12, 16, 40, 45], {5: moeda, 6: moeda}, 10)

    ws = wb.create_sheet("Comparações de preço")
    linhas = []
    for a in dados["alertas"]:
        if a["regra"] not in ("R01", "R02"):
            continue
        for e in a["evidencias"]:
            linhas.append([a["id"], a["gravidade"], "PAGO" if e.get("tipo") == "preco_pago" else "Referência",
                           e.get("orgao") or a["nome_orgao"], e.get("data"), e.get("descricao"), e.get("unidade"),
                           e.get("quantidade"), e.get("preco"), e.get("link")])
    aba(ws, ["Alerta", "Gravidade", "Tipo", "Órgão", "Data", "Descrição", "Unidade", "Quantidade",
             "Preço unitário", "Link"], linhas, [14, 10, 11, 34, 12, 70, 8, 12, 16, 45], {9: moeda}, 10, 2)

    ws = wb.create_sheet("Leia-me")
    ws.column_dimensions["A"].width = 120
    for t in ["VIGIA CARIACICA - relatório gerado em " + dados["estatisticas"]["gerado_em"], "",
              "IMPORTANTE: cada alerta é um INDÍCIO calculado automaticamente a partir de dados públicos.",
              "Nenhum alerta é prova de irregularidade. Antes de qualquer conclusão, siga o PROTOCOLO_DE_VERIFICACAO.",
              "", "Fontes: PNCP (pncp.gov.br), Receita Federal (via BrasilAPI/Minha Receita), CEIS/CNEP (CGU).",
              "Cada número pode ser conferido no link da linha correspondente.", "",
              "CPFs de pessoas físicas aparecem mascarados (LGPD)."]:
        ws.append([t])
    ws["A1"].font = Font(bold=True, size=14)
    wb.move_sheet("Leia-me", offset=-5)
    wb.save(destino)
    return destino


def gerar(con, cfg) -> tuple[Path, Path]:
    pasta = Path(cfg["_pasta_dados"]).parent / PASTA_SAIDA
    pasta.mkdir(parents=True, exist_ok=True)
    dados = coletar_dados(con, cfg)
    html = gerar_html(dados, pasta / "painel.html")
    xlsx = gerar_excel(dados, con, pasta / "relatorio.xlsx")
    log.info(f"  Painel:   {html}")
    log.info(f"  Planilha: {xlsx}")
    return html, xlsx
