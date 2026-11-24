"""Quem são as empresas que recebem dinheiro público: dados da Receita, sócios e punições."""
from __future__ import annotations

import csv
import datetime as dt
import io
import zipfile
from pathlib import Path

from .. import log
from ..db import upsert
from .pncp import g, data, num, booleano
from ..texto import nome_pessoa, so_digitos


# ---------------------------------------------------------------- CNPJ (Receita Federal)
def _mapear_cnpj(d: dict) -> dict:
    """Formato BrasilAPI / Minha Receita (mesmos nomes de campos)."""
    tel = g(d, "ddd_telefone_1") or ""
    return {
        "razao_social": g(d, "razao_social"),
        "nome_fantasia": g(d, "nome_fantasia"),
        "data_abertura": data(g(d, "data_inicio_atividade")),
        "situacao": g(d, "descricao_situacao_cadastral", "situacao_cadastral"),
        "data_situacao": data(g(d, "data_situacao_cadastral")),
        "capital_social": num(g(d, "capital_social")),
        "porte": g(d, "porte", "descricao_porte"),
        "natureza_juridica": g(d, "natureza_juridica"),
        "cnae": str(g(d, "cnae_fiscal", padrao="") or ""),
        "cnae_descricao": g(d, "cnae_fiscal_descricao"),
        "opcao_mei": booleano(g(d, "opcao_pelo_mei")),
        "opcao_simples": booleano(g(d, "opcao_pelo_simples")),
        "logradouro": " ".join(x for x in (g(d, "descricao_tipo_de_logradouro"), g(d, "logradouro")) if x),
        "numero": g(d, "numero"),
        "complemento": g(d, "complemento"),
        "bairro": g(d, "bairro"),
        "cep": so_digitos(g(d, "cep", padrao="")),
        "municipio": g(d, "municipio"),
        "uf": g(d, "uf"),
        "telefone": so_digitos(tel),
        "email": (g(d, "email") or "").lower() or None,
    }


def enriquecer(cli, con, cfg, refazer=False, limite=None, validade_dias=30, renovar_por_vez=40):
    """Consulta dados cadastrais de todo CNPJ que contratou com os órgãos analisados.

    CNPJs novos são consultados sempre. Os já consultados há mais de `validade_dias` são consultados
    de novo, `renovar_por_vez` por execução (situação na Receita e opção pelo MEI mudam)."""
    cnpjs = [r[0] for r in con.execute("""
        SELECT DISTINCT ni FROM (
          SELECT c.ni_fornecedor ni FROM contratos c JOIN orgaos o ON o.cnpj=c.cnpj_orgao WHERE o.alvo=1
          UNION
          SELECT r.ni_fornecedor FROM resultados r JOIN contratacoes k ON k.id_pncp=r.id_pncp WHERE k.alvo=1
        ) WHERE length(ni)=14""")]
    vencidos: list[str] = []
    if not refazer:
        feitos = {r[0] for r in con.execute("SELECT cnpj FROM fornecedores")}
        corte = (dt.datetime.now() - dt.timedelta(days=validade_dias)).strftime("%Y-%m-%d")
        vencidos = [r[0] for r in con.execute(
            "SELECT cnpj FROM fornecedores WHERE COALESCE(consultado_em,'') < ? ORDER BY consultado_em LIMIT ?",
            (corte, renovar_por_vez))]
        cnpjs = [c for c in cnpjs if c not in feitos] + vencidos
    if limite:
        cnpjs = cnpjs[:limite]
    log.info(f"  {len(cnpjs)} empresas para consultar na Receita")
    fontes = cfg["apis"].get("cnpj") or []
    for i, cnpj in enumerate(cnpjs, 1):
        for modelo in fontes:
            st, d = cli.get(modelo.format(cnpj=cnpj), usar_cache=not (refazer or cnpj in vencidos))
            if st == 200 and isinstance(d, dict) and (d.get("razao_social") or d.get("cnpj")):
                linha = {"cnpj": cnpj, **_mapear_cnpj(d), "fonte": modelo.split("/")[2],
                         "consultado_em": dt.datetime.now().strftime("%Y-%m-%d %H:%M")}
                upsert(con, "fornecedores", linha, ["cnpj"])
                con.execute("DELETE FROM socios WHERE cnpj=?", (cnpj,))
                for s in d.get("qsa") or []:
                    con.execute(
                        "INSERT INTO socios(cnpj,nome,qualificacao,documento,data_entrada,faixa_etaria) "
                        "VALUES (?,?,?,?,?,?)",
                        (cnpj, g(s, "nome_socio"), g(s, "qualificacao_socio"),
                         g(s, "cnpj_cpf_do_socio"), data(g(s, "data_entrada_sociedade")),
                         g(s, "faixa_etaria")))
                break
        if i % 20 == 0:
            con.commit()
            log.info(f"  Receita: {i}/{len(cnpjs)}")
    con.commit()


# ---------------------------------------------------------------- Sanções (CEIS / CNEP)
def sancoes_api(cli, con, cfg):
    chave = (cfg["apis"].get("chave_transparencia") or "").strip()
    if not chave:
        log.aviso("Sem chave da API do Portal da Transparência. Pulei a consulta de empresas punidas. "
                  "Use 'importar-sancoes' com os CSVs do CEIS/CNEP ou cadastre uma chave grátis.")
        return
    base = cfg["apis"]["transparencia"].rstrip("/")
    cnpjs = [r[0] for r in con.execute("SELECT cnpj FROM fornecedores")]
    log.info(f"  Consultando CEIS e CNEP para {len(cnpjs)} empresas")
    for cnpj in cnpjs:
        for cadastro in ("ceis", "cnep"):
            # sem cache: a punição pode ter sido aplicada depois da última consulta
            st, d = cli.get(f"{base}/{cadastro}", {"codigoSancionado": cnpj, "pagina": 1},
                            usar_cache=False, cabecalhos={"chave-api-dados": chave})
            registros = d if (st == 200 and isinstance(d, list)) else []
            for s in registros:
                doc = so_digitos(g(s, "sancionado.codigoFormatado", "pessoa.cnpjFormatado", padrao=""))
                if doc and doc != cnpj:
                    continue
                upsert(con, "sancoes", {
                    "cnpj": cnpj, "cadastro": cadastro.upper(),
                    "tipo": g(s, "tipoSancao.descricaoResumida", "tipoSancao.descricaoPortal"),
                    "orgao_sancionador": g(s, "orgaoSancionador.nome"),
                    "data_inicio": data(g(s, "dataInicioSancao")),
                    "data_fim": data(g(s, "dataFimSancao")),
                    "fundamentacao": "; ".join(
                        x.get("descricao", "") for x in (g(s, "fundamentacao") or []) if isinstance(x, dict)),
                }, ["cnpj", "cadastro", "tipo", "data_inicio"])
    con.commit()


def _ler_csv_flexivel(caminho: Path):
    """Lê CSV do Portal da Transparência (pode vir zipado, em latin-1, separado por ;)."""
    if caminho.suffix.lower() == ".zip":
        with zipfile.ZipFile(caminho) as z:
            for nome in z.namelist():
                if nome.lower().endswith(".csv"):
                    bruto = z.read(nome)
                    break
            else:
                raise ValueError("Nenhum CSV dentro do ZIP")
    else:
        bruto = caminho.read_bytes()
    for cod in ("utf-8-sig", "latin-1"):
        try:
            texto = bruto.decode(cod)
            break
        except UnicodeDecodeError:
            continue
    sep = ";" if texto[:2000].count(";") > texto[:2000].count(",") else ","
    return list(csv.DictReader(io.StringIO(texto), delimiter=sep))


def _coluna(cabecalhos, *pedacos):
    for h in cabecalhos:
        hn = nome_pessoa(h)
        if all(nome_pessoa(p) in hn for p in pedacos):
            return h
    return None


def importar_sancoes(con, caminho: str, cadastro: str | None = None):
    caminho = Path(caminho)
    linhas = _ler_csv_flexivel(caminho)
    if not linhas:
        log.aviso("Arquivo vazio")
        return 0
    cab = list(linhas[0].keys())
    c_doc = _coluna(cab, "CPF OU CNPJ") or _coluna(cab, "CNPJ")
    c_tipo = _coluna(cab, "CATEGORIA") or _coluna(cab, "TIPO", "SANCAO")
    c_org = _coluna(cab, "ORGAO SANCIONADOR") or _coluna(cab, "ORGAO")
    c_ini = _coluna(cab, "INICIO", "SANCAO")
    c_fim = _coluna(cab, "FINAL", "SANCAO") or _coluna(cab, "FIM", "SANCAO")
    c_fund = _coluna(cab, "FUNDAMENTACAO")
    cadastro = (cadastro or ("CNEP" if "cnep" in caminho.name.lower() else "CEIS")).upper()
    if not c_doc:
        raise ValueError(f"Não achei a coluna de CPF/CNPJ. Colunas: {cab}")

    def dt_br(v):
        v = (v or "").strip()
        if len(v) == 10 and v[2] == "/":
            return f"{v[6:]}-{v[3:5]}-{v[:2]}"
        return v[:10] or None

    n = 0
    for l in linhas:
        doc = so_digitos(l.get(c_doc))
        if len(doc) != 14:
            continue
        upsert(con, "sancoes", {
            "cnpj": doc, "cadastro": cadastro,
            "tipo": (l.get(c_tipo) or "").strip() if c_tipo else None,
            "orgao_sancionador": (l.get(c_org) or "").strip() if c_org else None,
            "data_inicio": dt_br(l.get(c_ini)) if c_ini else None,
            "data_fim": dt_br(l.get(c_fim)) if c_fim else None,
            "fundamentacao": (l.get(c_fund) or "").strip() if c_fund else None,
        }, ["cnpj", "cadastro", "tipo", "data_inicio"])
        n += 1
    con.commit()
    log.info(f"  {n} sanções de empresas importadas ({cadastro})")
    return n


# ---------------------------------------------------------------- Servidores (via LAI / portal)
def importar_servidores(con, caminho: str, fonte: str | None = None, substituir=False):
    """Aceita CSV ou XLSX com uma coluna de nome (e opcionalmente cargo e lotação)."""
    caminho = Path(caminho)
    if caminho.suffix.lower() in (".xlsx", ".xlsm"):
        import openpyxl
        wb = openpyxl.load_workbook(caminho, read_only=True, data_only=True)
        ws = wb.active
        linhas_brutas = list(ws.iter_rows(values_only=True))
        idx = 0
        for idx, linha in enumerate(linhas_brutas[:30]):
            if any(isinstance(v, str) and "nome" in v.lower() for v in linha):
                break
        cab = [str(v or "").strip() for v in linhas_brutas[idx]]
        linhas = [dict(zip(cab, [str(v or "") for v in l])) for l in linhas_brutas[idx + 1:]]
    else:
        linhas = _ler_csv_flexivel(caminho)
    if not linhas:
        return 0
    cab = list(linhas[0].keys())
    c_nome = _coluna(cab, "NOME")
    c_cargo = _coluna(cab, "CARGO") or _coluna(cab, "FUNCAO")
    c_lot = _coluna(cab, "LOTACAO") or _coluna(cab, "SECRETARIA") or _coluna(cab, "ORGAO")
    if not c_nome:
        raise ValueError(f"Não achei a coluna de nome. Colunas: {cab}")
    if substituir:
        con.execute("DELETE FROM servidores")
    n = 0
    for l in linhas:
        nome = (l.get(c_nome) or "").strip()
        if len(nome.split()) < 2:
            continue
        con.execute("INSERT INTO servidores(nome,nome_normalizado,cargo,lotacao,fonte) VALUES (?,?,?,?,?)",
                    (nome, nome_pessoa(nome), l.get(c_cargo) if c_cargo else None,
                     l.get(c_lot) if c_lot else None, fonte or caminho.name))
        n += 1
    con.commit()
    log.info(f"  {n} servidores importados de {caminho.name}")
    return n
