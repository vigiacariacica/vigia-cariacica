"""Coleta de dados do PNCP (Portal Nacional de Contratações Públicas).

Fontes (todas públicas, sem cadastro):
  API de consulta:   https://pncp.gov.br/api/consulta   (contratações, contratos, atas)
  API de integração: https://pncp.gov.br/api/pncp       (itens, resultados, termos aditivos)

A API às vezes ignora filtros sem avisar, então todo registro é conferido aqui
(município, CNPJ) antes de ser gravado.
"""
from __future__ import annotations

import datetime as dt
import re

from .. import log, qualidade
from ..db import upsert
from ..http import LimiteDeTentativas
from ..texto import so_digitos

RE_ID = re.compile(r"^(\d{14})-(\d+)-(\d+)/(\d{4})")


# ---------------------------------------------------------------- utilitários
def g(obj, *caminhos, padrao=None):
    """Busca o primeiro caminho existente (ex.: 'orgaoEntidade.razaoSocial')."""
    for caminho in caminhos:
        atual, ok = obj, True
        for parte in caminho.split("."):
            if isinstance(atual, dict) and atual.get(parte) is not None:
                atual = atual[parte]
            else:
                ok = False
                break
        if ok:
            return atual
    return padrao


def data(v) -> str | None:
    return str(v)[:10] if v else None


def num(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        try:
            return float(str(v).replace(".", "").replace(",", "."))
        except ValueError:
            return None


def nome_de(v) -> str | None:
    if isinstance(v, dict):
        return v.get("nome") or v.get("descricao") or v.get("tipoTermoContratoNome")
    return v


def booleano(v) -> int | None:
    if v is None:
        return None
    if isinstance(v, str):
        return 1 if v.strip().lower() in {"true", "1", "s", "sim"} else 0
    return 1 if v else 0


def partes_id(id_pncp: str | None):
    """'27150549000119-1-000214/2026' -> ('27150549000119', 1, 214, 2026)"""
    m = RE_ID.match(id_pncp or "")
    if not m:
        return None
    return m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4))


def fatias(ini: dt.date, fim: dt.date, meses: int = 1):
    atual = ini
    while atual <= fim:
        m = atual.month - 1 + meses
        prox = dt.date(atual.year + m // 12, m % 12 + 1, 1)
        yield atual, min(prox - dt.timedelta(days=1), fim)
        atual = prox


def _ymd(d: dt.date) -> str:
    return d.strftime("%Y%m%d")


def _pode_cache(cfg, fim_fatia: dt.date) -> bool:
    dias = int(cfg["coleta"].get("recoletar_ultimos_dias", 60))
    return fim_fatia < dt.date.today() - dt.timedelta(days=dias)


def _registros(dados):
    if dados is None:
        return []
    if isinstance(dados, list):
        return dados
    for chave in ("data", "itens", "listaResultados", "resultados", "termos", "content"):
        if isinstance(dados.get(chave), list):
            return dados[chave]
    return [dados] if dados else []


def paginar(cli, url, params, usar_cache=True, tamanho=50, maximo_paginas=2000):
    pagina = 1
    while pagina <= maximo_paginas:
        st, dados = cli.get(url, {**params, "pagina": pagina, "tamanhoPagina": tamanho}, usar_cache)
        if st == 204 or dados is None:
            return
        if st != 200:
            log.aviso(f"HTTP {st} em {url} {params}")
            _registrar_falha(url, st)
            return
        regs = _registros(dados)
        if not regs:
            return
        yield from regs
        if isinstance(dados, dict):
            if dados.get("paginasRestantes") is not None:
                if int(dados["paginasRestantes"]) <= 0:
                    return
            elif dados.get("totalPaginas") is not None:
                if pagina >= int(dados["totalPaginas"]):
                    return
            elif len(regs) < tamanho:
                return
        elif len(regs) < tamanho:
            return
        pagina += 1


def _registrar_falha(url: str, status: int) -> None:
    """Resposta inesperada do PNCP fica visível em docs/qualidade.md (não some como "sem dados")."""
    qualidade.REGISTRO.add(qualidade.Checagem("pncp", url[:120], "resposta_http", False, False, f"HTTP {status}"))


def _recente(cfg) -> str:
    dias = int(cfg["coleta"].get("recoletar_ultimos_dias", 60))
    return (dt.date.today() - dt.timedelta(days=dias)).isoformat()


# ---------------------------------------------------------------- gravação
def salvar_orgao(con, cnpj, reg, alvo: bool):
    upsert(con, "orgaos", {
        "cnpj": cnpj,
        "razao_social": g(reg, "orgaoEntidade.razaoSocial", "orgaoEntidade.razaosocial", "nomeOrgao"),
        "esfera": g(reg, "orgaoEntidade.esferaId"),
        "poder": g(reg, "orgaoEntidade.poderId"),
        "municipio_ibge": str(g(reg, "unidadeOrgao.codigoIbge", padrao="") or ""),
        "municipio_nome": g(reg, "unidadeOrgao.municipioNome"),
        "alvo": 1 if alvo else 0,
    }, ["cnpj"], preservar=("alvo",))
    if alvo:
        con.execute("UPDATE orgaos SET alvo=1 WHERE cnpj=?", (cnpj,))


def salvar_contratacao(con, reg, alvo: bool) -> str | None:
    id_pncp = g(reg, "numeroControlePNCP")
    if not id_pncp:
        return None
    cnpj = so_digitos(g(reg, "orgaoEntidade.cnpj", padrao=""))
    partes = partes_id(id_pncp)
    salvar_orgao(con, cnpj, reg, alvo)
    amparo = " - ".join(x for x in (g(reg, "amparoLegal.nome"), g(reg, "amparoLegal.descricao")) if x)
    upsert(con, "contratacoes", {
        "id_pncp": id_pncp,
        "cnpj_orgao": cnpj,
        "ano": g(reg, "anoCompra") or (partes[3] if partes else None),
        "sequencial": g(reg, "sequencialCompra") or (partes[2] if partes else None),
        "numero_compra": g(reg, "numeroCompra"),
        "processo": g(reg, "processo"),
        "modalidade_id": g(reg, "modalidadeId"),
        "modalidade_nome": g(reg, "modalidadeNome"),
        "modo_disputa": g(reg, "modoDisputaNome"),
        "situacao": g(reg, "situacaoCompraNome"),
        "objeto": g(reg, "objetoCompra"),
        "info_complementar": g(reg, "informacaoComplementar"),
        "srp": booleano(g(reg, "srp")),
        "amparo_legal": amparo or None,
        "valor_estimado": num(g(reg, "valorTotalEstimado")),
        "valor_homologado": num(g(reg, "valorTotalHomologado")),
        "data_publicacao": data(g(reg, "dataPublicacaoPncp", "dataInclusao")),
        "data_abertura": data(g(reg, "dataAberturaProposta")),
        "data_encerramento": data(g(reg, "dataEncerramentoProposta")),
        "unidade_nome": g(reg, "unidadeOrgao.nomeUnidade"),
        "municipio_ibge": str(g(reg, "unidadeOrgao.codigoIbge", padrao="") or ""),
        "municipio_nome": g(reg, "unidadeOrgao.municipioNome"),
        "link_origem": g(reg, "linkSistemaOrigem"),
        "alvo": 1 if alvo else 0,
    }, ["id_pncp"], preservar=("itens_coletados", "alvo"))
    if alvo:
        con.execute("UPDATE contratacoes SET alvo=1 WHERE id_pncp=?", (id_pncp,))
    return id_pncp


def salvar_contrato(con, reg) -> str | None:
    id_pncp = g(reg, "numeroControlePNCP")
    if not id_pncp:
        return None
    partes = partes_id(id_pncp)
    id_compra = g(reg, "numeroControlePNCPCompra", "numeroControlePncpCompra")
    pc = partes_id(id_compra)
    cnpj = so_digitos(g(reg, "orgaoEntidade.cnpj", padrao=""))
    upsert(con, "contratos", {
        "id_pncp": id_pncp,
        "id_pncp_compra": id_compra,
        "cnpj_orgao": cnpj,
        "cnpj_orgao_compra": pc[0] if pc else None,
        "ano": g(reg, "anoContrato") or (partes[3] if partes else None),
        "sequencial": g(reg, "sequencialContrato") or (partes[2] if partes else None),
        "numero": g(reg, "numeroContratoEmpenho"),
        "processo": g(reg, "processo"),
        "tipo_contrato": nome_de(g(reg, "tipoContrato")),
        "categoria": nome_de(g(reg, "categoriaProcesso")),
        "objeto": g(reg, "objetoContrato"),
        "info_complementar": g(reg, "informacaoComplementar"),
        "tipo_pessoa": g(reg, "tipoPessoa"),
        "ni_fornecedor": so_digitos(g(reg, "niFornecedor", padrao="")),
        "nome_fornecedor": g(reg, "nomeRazaoSocialFornecedor"),
        "valor_inicial": num(g(reg, "valorInicial")),
        "valor_global": num(g(reg, "valorGlobal")),
        "valor_acumulado": num(g(reg, "valorAcumulado")),
        "data_assinatura": data(g(reg, "dataAssinatura")),
        "vigencia_inicio": data(g(reg, "dataVigenciaInicio")),
        "vigencia_fim": data(g(reg, "dataVigenciaFim")),
        "data_publicacao": data(g(reg, "dataPublicacaoPncp")),
        "unidade_nome": g(reg, "unidadeOrgao.nomeUnidade"),
        "municipio_ibge": str(g(reg, "unidadeOrgao.codigoIbge", padrao="") or ""),
    }, ["id_pncp"], preservar=("termos_coletados",))
    return id_pncp


# ---------------------------------------------------------------- coletas
def coletar_contratacoes(cli, con, cfg, ibge, ini, fim, modalidades, alvo: bool,
                         cnpjs_alternativos=()):
    base = cfg["apis"]["pncp_consulta"].rstrip("/") + "/v1/contratacoes/publicacao"
    esferas = set(cfg["projeto"].get("esferas") or [])
    total = 0
    for a, b in fatias(ini, fim, 1):
        cache = _pode_cache(cfg, b)
        for mod in modalidades:
            params = {"dataInicial": _ymd(a), "dataFinal": _ymd(b),
                      "codigoModalidadeContratacao": mod, "codigoMunicipioIbge": ibge}
            dentro = fora = 0
            filtro_ignorado = False
            for reg in paginar(cli, base, params, cache, tamanho=50):
                if str(g(reg, "unidadeOrgao.codigoIbge", padrao="")) != str(ibge):
                    fora += 1
                    if fora >= 50 and dentro == 0:
                        filtro_ignorado = True
                        break
                    continue
                eh_alvo = alvo and (not esferas or g(reg, "orgaoEntidade.esferaId") in esferas)
                salvar_contratacao(con, reg, eh_alvo)
                dentro += 1
            if filtro_ignorado:
                log.aviso("A API ignorou o filtro de município. Consultando por CNPJ dos órgãos conhecidos.")
                for cnpj in cnpjs_alternativos:
                    for reg in paginar(cli, base, {**params, "codigoMunicipioIbge": None, "cnpj": cnpj},
                                       cache, tamanho=50):
                        if so_digitos(g(reg, "orgaoEntidade.cnpj", padrao="")) == cnpj:
                            salvar_contratacao(con, reg, alvo)
                            dentro += 1
            total += dentro
        con.commit()
        log.info(f"  {a:%m/%Y}: {total} contratações acumuladas ({cli.chamadas} chamadas, "
                 f"{cli.do_cache} do cache)")
    return total


def coletar_contratos(cli, con, cfg, cnpj, ini, fim):
    base = cfg["apis"]["pncp_consulta"].rstrip("/") + "/v1/contratos"
    total = 0
    for a, b in fatias(ini, fim, 3):
        cache = _pode_cache(cfg, b)
        params = {"dataInicial": _ymd(a), "dataFinal": _ymd(b), "cnpjOrgao": cnpj}
        errados = 0
        for reg in paginar(cli, base, params, cache, tamanho=500):
            if so_digitos(g(reg, "orgaoEntidade.cnpj", padrao="")) != cnpj:
                errados += 1
                if errados >= 200:
                    log.aviso(f"Filtro de CNPJ ignorado na consulta de contratos de {cnpj}; abortando fatia.")
                    break
                continue
            salvar_contrato(con, reg)
            total += 1
        con.commit()
    log.info(f"  {cnpj}: {total} contratos")
    return total


def coletar_atas(cli, con, cfg, cnpj, ini, fim):
    base = cfg["apis"]["pncp_consulta"].rstrip("/") + "/v1/atas"
    total = 0
    for a, b in fatias(ini, fim, 6):
        cache = _pode_cache(cfg, b)
        params = {"dataInicial": _ymd(a), "dataFinal": _ymd(b), "cnpj": cnpj, "cnpjOrgao": cnpj}
        errados = 0
        for reg in paginar(cli, base, params, cache, tamanho=500):
            if so_digitos(g(reg, "cnpjOrgao", "orgaoEntidade.cnpj", padrao="")) != cnpj:
                errados += 1
                if errados >= 200:
                    break
                continue
            id_ata = g(reg, "numeroControlePNCPAta", "numeroControlePncpAta")
            if not id_ata:
                continue
            upsert(con, "atas", {
                "id_ata": id_ata,
                "id_pncp_compra": g(reg, "numeroControlePNCPCompra", "numeroControlePncpCompra"),
                "cnpj_orgao": cnpj,
                "nome_orgao": g(reg, "nomeOrgao"),
                "numero": g(reg, "numeroAtaRegistroPreco"),
                "objeto": g(reg, "objetoContratacao"),
                "data_assinatura": data(g(reg, "dataAssinatura")),
                "vigencia_inicio": data(g(reg, "vigenciaInicio")),
                "vigencia_fim": data(g(reg, "vigenciaFim")),
                "cancelada": booleano(g(reg, "cancelado")),
            }, ["id_ata"])
            total += 1
        con.commit()
    return total


def coletar_compras_externas(cli, con, cfg):
    """Compras de OUTROS órgãos usadas por Cariacica (adesão a ata / 'carona')."""
    base = cfg["apis"]["pncp"].rstrip("/")
    linhas = con.execute("""
        SELECT DISTINCT c.id_pncp_compra FROM contratos c JOIN orgaos o ON o.cnpj=c.cnpj_orgao
        WHERE o.alvo=1 AND c.id_pncp_compra IS NOT NULL
          AND c.id_pncp_compra NOT IN (SELECT id_pncp FROM contratacoes)""").fetchall()
    # Uma compra externa que o PNCP não entrega (fora do ar, 504) não pode derrubar o resto da coleta
    # (08/11/2026: uma só compra derrubou o PNCP inteiro depois de 40 min de tentativas). Fica registrada,
    # e a próxima execução tenta de novo (a consulta acima só pega o que ainda falta). Três falhas seguidas
    # = PNCP fora do ar: para aqui e segue com o resto.
    # Cada compra externa tenta no máximo 3 vezes (cerca de 2 min), não 6 (cerca de 15 min): em 09/11/2026,
    # duas compras fora do ar custaram 30 min de espera. O que faltar volta na próxima execução.
    tentativas_antes = cli.tentativas
    cli.tentativas = min(cli.tentativas, 3)
    try:
        n, faltaram = _baixar_compras_externas(cli, con, base, linhas)
    finally:
        cli.tentativas = tentativas_antes
    con.commit()
    if faltaram:
        qualidade.REGISTRO.falhas_fonte.append(f"pncp (compras externas: {len(faltaram)} sem resposta)")
    log.info(f"  {n} compras externas (de outros órgãos) baixadas")
    return n


def _baixar_compras_externas(cli, con, base, linhas):
    n, falhas_seguidas, faltaram = 0, 0, []
    for (id_compra,) in linhas:
        p = partes_id(id_compra)
        if not p:
            continue
        url = f"{base}/v1/orgaos/{p[0]}/compras/{p[3]}/{p[2]}"
        try:
            st, dados = cli.get(url)
        except LimiteDeTentativas:
            faltaram.append(id_compra)
            falhas_seguidas += 1
            _registrar_falha(url, 0)
            if falhas_seguidas >= 3:
                log.aviso("PNCP sem responder em 3 compras externas seguidas; o resto fica para a próxima execução")
                break
            continue
        falhas_seguidas = 0
        if st == 200 and isinstance(dados, dict):
            dados.setdefault("numeroControlePNCP", id_compra)
            salvar_contratacao(con, dados, alvo=False)
            n += 1
    return n, faltaram


def salvar_item(con, id_pncp, it):
    upsert(con, "itens", {
        "id_pncp": id_pncp,
        "numero_item": g(it, "numeroItem"),
        "descricao": g(it, "descricao"),
        "material_servico": g(it, "materialOuServico"),
        "quantidade": num(g(it, "quantidade")),
        "unidade": g(it, "unidadeMedida"),
        "valor_unit_estimado": num(g(it, "valorUnitarioEstimado")),
        "valor_total_estimado": num(g(it, "valorTotal")),
        "situacao": g(it, "situacaoCompraItemNome"),
        "criterio": g(it, "criterioJulgamentoNome"),
        "tem_resultado": booleano(g(it, "temResultado")),
        "catalogo_codigo": str(g(it, "catalogoCodigoItem", padrao="") or "") or None,
        "ncm": g(it, "ncmNbsCodigo"),
        "orcamento_sigiloso": booleano(g(it, "orcamentoSigiloso")),
    }, ["id_pncp", "numero_item"], preservar=("resultados_coletados",))


def coletar_itens(cli, con, cfg, filtro_sql: str, params_sql=(), revisitar: bool = False,
                  refazer_recentes: bool = True):
    """Itens de cada contratação. Além das que nunca foram baixadas, baixa de novo (sem cache) as
    publicadas na janela de recoleta e, se `revisitar`, as do último ano que ainda não têm nenhum
    item com resultado: assim o resultado homologado depois da primeira visita não se perde."""
    base = cfg["apis"]["pncp"].rstrip("/")
    recente = _recente(cfg)
    dias_rev = int(cfg["coleta"].get("revisitar_sem_resultado_dias", 365))
    limite_rev = (dt.date.today() - dt.timedelta(days=dias_rev)).isoformat()
    compras = con.execute(f"""
        SELECT id_pncp, cnpj_orgao, ano, sequencial, itens_coletados, data_publicacao FROM contratacoes c
        WHERE ({filtro_sql}) AND (
            itens_coletados=0
            OR (? AND data_publicacao >= ?)
            OR (? AND data_publicacao >= ? AND COALESCE(situacao,'') NOT IN ('Anulada','Revogada')
                AND NOT EXISTS (SELECT 1 FROM itens i WHERE i.id_pncp=c.id_pncp AND i.tem_resultado=1)))""",
        (*params_sql, 1 if refazer_recentes else 0, recente, 1 if revisitar else 0, limite_rev)).fetchall()
    log.info(f"  {len(compras)} contratações para baixar ou atualizar itens")
    for i, c in enumerate(compras, 1):
        p = partes_id(c["id_pncp"])
        cnpj, ano, seq = (p[0], p[3], p[2]) if p else (c["cnpj_orgao"], c["ano"], c["sequencial"])
        url = f"{base}/v1/orgaos/{cnpj}/compras/{ano}/{seq}/itens"
        # primeira visita a compra antiga: pode usar a resposta guardada; o resto é baixado de novo
        usar_cache = bool(c["itens_coletados"] == 0 and (c["data_publicacao"] or "") < recente)
        vistos = set()
        pagina = 1
        ok = True
        while pagina <= 100:
            st, dados = cli.get(url, {"pagina": pagina, "tamanhoPagina": 100}, usar_cache)
            if pagina == 1 and st in (400, 422):
                # alguns servidores do PNCP recusam a paginação: tenta a lista completa
                st, dados = cli.get(url, usar_cache=usar_cache)
                for it in _registros(dados) if st == 200 else []:
                    salvar_item(con, c["id_pncp"], it)
                ok = st in (200, 204)
                break
            if st not in (200, 204):
                ok = False
                _registrar_falha(url, st)
                break
            regs = _registros(dados) if st == 200 else []
            novos = [it for it in regs if g(it, "numeroItem") not in vistos]
            for it in novos:
                vistos.add(g(it, "numeroItem"))
                salvar_item(con, c["id_pncp"], it)
            if not novos or len(regs) < 100:
                break
            pagina += 1
        if ok:  # só marca como baixado se a API respondeu de verdade
            con.execute("UPDATE contratacoes SET itens_coletados=1 WHERE id_pncp=?", (c["id_pncp"],))
        if i % 25 == 0:
            con.commit()
            log.info(f"  itens: {i}/{len(compras)} contratações")
    con.commit()


def coletar_resultados(cli, con, cfg, filtro_sql: str, params_sql=(), refazer_recentes: bool = True):
    base = cfg["apis"]["pncp"].rstrip("/")
    recente = _recente(cfg)
    itens = con.execute(f"""
        SELECT i.id_pncp, i.numero_item, i.resultados_coletados, c.data_publicacao
        FROM itens i JOIN contratacoes c ON c.id_pncp=i.id_pncp
        WHERE i.tem_resultado=1 AND (i.resultados_coletados=0 OR (? AND c.data_publicacao >= ?)) AND ({filtro_sql})""",
        (1 if refazer_recentes else 0, recente, *params_sql)).fetchall()
    log.info(f"  {len(itens)} itens com resultado a baixar ou atualizar")
    for k, it in enumerate(itens, 1):
        p = partes_id(it["id_pncp"])
        if not p:
            continue
        url = f"{base}/v1/orgaos/{p[0]}/compras/{p[3]}/{p[2]}/itens/{it['numero_item']}/resultados"
        st, dados = cli.get(url, usar_cache=(it["data_publicacao"] or "") < recente)
        if st not in (200, 204):
            _registrar_falha(url, st)
            continue
        for r in _registros(dados) if st == 200 else []:
            qtd = num(g(r, "quantidadeHomologada"))
            vu = num(g(r, "valorUnitarioHomologado"))
            upsert(con, "resultados", {
                "id_pncp": it["id_pncp"],
                "numero_item": it["numero_item"],
                "sequencial": g(r, "sequencialResultado", padrao=1),
                "ni_fornecedor": so_digitos(g(r, "niFornecedor", padrao="")),
                "nome_fornecedor": g(r, "nomeRazaoSocialFornecedor"),
                "tipo_pessoa": g(r, "tipoPessoa"),
                "porte": g(r, "porteFornecedorNome"),
                "quantidade": qtd,
                "valor_unit": vu,
                "valor_total": num(g(r, "valorTotalHomologado")) or ((qtd or 0) * (vu or 0)),
                "percentual_desconto": num(g(r, "percentualDesconto")),
                "data_resultado": data(g(r, "dataResultado", "dataInclusao")),
                "situacao": g(r, "situacaoCompraItemResultadoNome"),
            }, ["id_pncp", "numero_item", "sequencial"])
        con.execute("UPDATE itens SET resultados_coletados=1 WHERE id_pncp=? AND numero_item=?",
                    (it["id_pncp"], it["numero_item"]))
        if k % 50 == 0:
            con.commit()
            log.info(f"  resultados: {k}/{len(itens)} itens")
    con.commit()


def coletar_termos(cli, con, cfg):
    base = cfg["apis"]["pncp"].rstrip("/")
    contratos = con.execute("""
        SELECT c.id_pncp, c.termos_coletados FROM contratos c JOIN orgaos o ON o.cnpj=c.cnpj_orgao
        WHERE o.alvo=1 AND (c.termos_coletados=0 OR c.vigencia_fim >= date('now','-30 day'))""").fetchall()
    log.info(f"  {len(contratos)} contratos para checar termos aditivos")
    for k, c in enumerate(contratos, 1):
        p = partes_id(c["id_pncp"])
        if not p:
            continue
        url_t = f"{base}/v1/orgaos/{p[0]}/contratos/{p[3]}/{p[2]}/termos"
        st, dados = cli.get(url_t, usar_cache=bool(c["termos_coletados"] == 0))
        if st not in (200, 204):
            _registrar_falha(url_t, st)
            continue
        for t in _registros(dados) if st == 200 else []:
            if booleano(g(t, "excluido")):
                continue
            upsert(con, "termos", {
                "id_contrato": c["id_pncp"],
                "sequencial": g(t, "sequencialTermoContrato", padrao=0),
                "numero": g(t, "numeroTermoContrato"),
                "tipo": nome_de(g(t, "tipoTermoContrato", "tipoTermoContratoNome")),
                "objeto": g(t, "objetoTermoContrato"),
                "fundamento": g(t, "fundamentoLegal"),
                "valor_acrescido": num(g(t, "valorAcrescido")),
                "valor_global": num(g(t, "valorGlobal")),
                "prazo_aditado_dias": g(t, "prazoAditadoDias"),
                "qualifica_acrescimo": booleano(g(t, "qualificacaoAcrescimoSupressao")),
                "qualifica_vigencia": booleano(g(t, "qualificacaoVigencia")),
                "qualifica_fornecedor": booleano(g(t, "qualificacaoFornecedor")),
                "data_assinatura": data(g(t, "dataAssinatura")),
            }, ["id_contrato", "sequencial"])
        con.execute("UPDATE contratos SET termos_coletados=1 WHERE id_pncp=?", (c["id_pncp"],))
        if k % 50 == 0:
            con.commit()
            log.info(f"  termos: {k}/{len(contratos)}")
    con.commit()


ARQUIVOS_SEM_DISPUTA = (8, 9)     # dispensa e inexigibilidade: não têm seleção para ficar parada


def coletar_arquivos_compras(cli, con, cfg, anos: int = 3) -> int:
    """Lista de documentos (só título, tipo e data, nunca o PDF) das contratações sem resultado homologado:
    é onde aparecem o aviso de suspensão, a revogação e a anulação que o campo "situação" nem sempre mostra
    (o chamamento 2/2026 do PA do Trevo estava "Divulgada no PNCP" com o aviso de suspensão anexado).
    Sem cache: documentos novos entram a qualquer hora. Para depois de 3 falhas seguidas."""
    base = cfg["apis"]["pncp"].rstrip("/")
    marc = ",".join(str(m) for m in ARQUIVOS_SEM_DISPUTA)
    compras = con.execute(f"""
        SELECT id_pncp FROM contratacoes
        WHERE alvo=1 AND COALESCE(modalidade_id, 0) NOT IN ({marc})
          AND COALESCE(valor_homologado, 0) = 0
          AND data_publicacao >= date('now', ?)""", (f"-{int(anos)} year",)).fetchall()
    log.info(f"  {len(compras)} contratações sem resultado: conferindo os documentos")
    gravados, falhas = 0, 0
    for c in compras:
        p = partes_id(c["id_pncp"])
        if not p:
            continue
        url = f"{base}/v1/orgaos/{p[0]}/compras/{p[3]}/{p[2]}/arquivos"
        try:
            st, dados = cli.get(url, usar_cache=False)
        except LimiteDeTentativas:
            st, dados = 0, None
        if st not in (200, 204):
            _registrar_falha(url, st)
            falhas += 1
            if falhas >= 3:
                qualidade.REGISTRO.falhas_fonte.append("PNCP arquivos das compras: 3 sem resposta seguidas")
                break
            continue
        falhas = 0
        for a in _registros(dados) if st == 200 else []:
            upsert(con, "arquivos_compra", {
                "id_pncp": c["id_pncp"],
                "sequencial": g(a, "sequencialDocumento", padrao=0),
                "data_publicacao": data(g(a, "dataPublicacaoPncp")),
                "titulo": (g(a, "titulo") or "").strip(),
                "tipo": g(a, "tipoDocumentoNome", "tipoDocumentoDescricao"),
                "ativo": booleano(g(a, "statusAtivo")),
            }, ["id_pncp", "sequencial"])
            gravados += 1
    con.commit()
    return gravados


# ---------------------------------------------------------------- orquestração
def coletar_tudo(cli, con, cfg, ini, fim, so_vizinhos=False, sem_vizinhos=False):
    p, c = cfg["projeto"], cfg["coleta"]
    ibge = p["municipio_ibge"]
    extras = [so_digitos(x) for x in p.get("cnpjs_extras", [])]
    for cnpj in extras:
        con.execute("INSERT OR IGNORE INTO orgaos(cnpj, alvo, municipio_ibge) VALUES (?,1,?)", (cnpj, ibge))
        con.execute("UPDATE orgaos SET alvo=1 WHERE cnpj=?", (cnpj,))
    con.commit()

    if not so_vizinhos:
        log.etapa(f"1/7 Contratações publicadas por órgãos de {p['municipio_nome']}")
        coletar_contratacoes(cli, con, cfg, ibge, ini, fim, c["modalidades"], alvo=True,
                             cnpjs_alternativos=extras)

        orgaos = [r["cnpj"] for r in con.execute("SELECT cnpj, razao_social FROM orgaos WHERE alvo=1")]
        log.etapa(f"2/7 Contratos de {len(orgaos)} órgãos municipais")
        for cnpj in orgaos:
            coletar_contratos(cli, con, cfg, cnpj, ini, fim)

        if c.get("coletar_atas", True):
            log.etapa("3/7 Atas de registro de preço")
            for cnpj in orgaos:
                coletar_atas(cli, con, cfg, cnpj, ini, fim)

        if c.get("coletar_compras_externas", True):
            log.etapa("4/7 Compras de outros órgãos usadas por adesão ('carona')")
            coletar_compras_externas(cli, con, cfg)

        externas = ("SELECT k.id_pncp_compra FROM contratos k JOIN orgaos o ON o.cnpj=k.cnpj_orgao "
                    "WHERE o.alvo=1 AND k.id_pncp_compra IS NOT NULL")
        if c.get("coletar_itens", True):
            log.etapa("5/7 Itens das contratações")
            coletar_itens(cli, con, cfg, f"alvo=1 OR id_pncp IN ({externas})",
                          revisitar=bool(c.get("revisitar_sem_resultado")))
        if c.get("coletar_resultados", True):
            log.etapa("6/7 Resultados (quem ganhou e por quanto)")
            coletar_resultados(cli, con, cfg, f"c.alvo=1 OR c.id_pncp IN ({externas})")
        if c.get("coletar_termos", True):
            log.etapa("7/7 Termos aditivos dos contratos")
            coletar_termos(cli, con, cfg)
        if c.get("coletar_arquivos", True):
            log.etapa("Extra: documentos das contratações sem resultado (suspensão, revogação, anulação)")
            coletar_arquivos_compras(cli, con, cfg)

    v = cfg.get("vizinhos", {})
    if v.get("ativo") and not sem_vizinhos and v.get("municipios"):
        ini_v = max(ini, fim - dt.timedelta(days=int(v.get("meses", 12)) * 31))
        log.etapa(f"Referências de preço: {len(v['municipios'])} municípios vizinhos desde {ini_v:%m/%Y}")
        for ibge_v, nome in v["municipios"].items():
            log.info(f"Vizinho: {nome}")
            coletar_contratacoes(cli, con, cfg, ibge_v, ini_v, fim, v.get("modalidades", [6, 8]), alvo=False)
        marc = ",".join("?" * len(v["municipios"]))
        mods = ",".join(str(int(m)) for m in v.get("modalidades", [6, 8]))
        params = tuple(v["municipios"].keys())
        log.info("Itens dos vizinhos")
        coletar_itens(cli, con, cfg, f"alvo=0 AND municipio_ibge IN ({marc}) AND modalidade_id IN ({mods})", params,
                      refazer_recentes=False)
        log.info("Resultados dos vizinhos (só materiais, que são os comparáveis)")
        coletar_resultados(cli, con, cfg,
                           f"c.alvo=0 AND c.municipio_ibge IN ({marc}) AND c.modalidade_id IN ({mods}) "
                           f"AND COALESCE(i.material_servico,'M') IN ('M','Material')", params,
                           refazer_recentes=False)
