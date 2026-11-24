"""Emendas Pix (transferências especiais) para Cariacica, no Transferegov do governo federal.

"Emenda Pix" é o apelido da transferência especial (Constituição, art. 166-A, I): o dinheiro da emenda
de um deputado ou senador cai direto na conta da prefeitura, sem convênio. A prefeitura informa no
Transferegov o plano de ação (o que vai fazer com o dinheiro), quem executa, as metas e, depois, os
relatórios de gestão. É aqui que se confere se isso foi feito.

API pública (PostgREST, sem chave): https://api.transferegov.gestao.gov.br/transferenciasespeciais/
    plano_acao_especial?cnpj_beneficiario_plano_acao=eq.<CNPJ>   um plano de ação por emenda
    executor_especial?id_plano_acao=in.(...)                     quem executa e com quanto
    meta_especial?id_executor=in.(...)                           metas de cada executor
    relatorio_gestao_novo_especial?id_plano_acao=in.(...)        relatórios de gestão

Saída (data/transferegov/): emendas_pix_planos.csv, emendas_pix_executores.csv, emendas_pix_metas.csv e
emendas_pix_relatorios.csv. Nenhuma coluna de dado bancário (banco, agência, conta) é gravada.
Roda no semanal. Cada resposta crua é guardada com SHA-256 (qualidade.guardar_bruto), como no portal.
"""
from __future__ import annotations

import logging
import re

import pandas as pd

from .. import qualidade
from ..config import CARIACICA_CNPJS, DADOS
from ..http import sessao
from ..texto import so_digitos
from .portal_extra import gravar_checado

log = logging.getLogger("vigia.transferegov")
BASE = "https://api.transferegov.gestao.gov.br/transferenciasespeciais"
PASTA = DADOS / "transferegov"
CNPJ = CARIACICA_CNPJS[0]           # 27.150.549/0001-19, Município de Cariacica
POR_PAGINA = 1000                   # linhas por chamada (limit)
IDS_POR_CHAMADA = 50                # tamanho de cada lista in.(...)
MAX_PAGINAS = 500                   # trava contra laço infinito (API que ignore o offset)

# Banco, agência, conta e situação da conta nunca vão para o git.
RE_BANCARIO = re.compile(r"banco|agencia|^(?:numero|dv)_conta|dado_bancario", re.I)

# tabela: (colunas que todo registro precisa ter no formato certo, colunas de valor somadas na
# comparação com a coleta anterior)
CHECAGEM = {
    "planos": ({"id_plano_acao": r"\d+", "cnpj_beneficiario_plano_acao": CNPJ},
               ("valor_custeio_plano_acao", "valor_investimento_plano_acao")),
    "executores": ({"id_executor": r"\d+", "id_plano_acao": r"\d+"},
                   ("vl_custeio_executor", "vl_investimento_executor")),
    "metas": ({"id_meta": r"\d+", "id_executor": r"\d+"},
              ("vl_custeio_emenda_especial_meta", "vl_investimento_emenda_especial_meta")),
    "relatorios": ({"id_relatorio_gestao_novo": r"\d+", "id_plano_acao": r"\d+"},
                   ("valor_executado_relatorio_gestao_novo",)),
}


def _int(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _total(content_range: str) -> int | None:
    """Content-Range do PostgREST: '0-999/1234' -> 1234; '*/0' -> 0; sem total ('0-999/*') -> None."""
    m = re.search(r"/(\d+)\s*$", content_range or "")
    return int(m.group(1)) if m else None


def baixar_tabela(s, tabela: str, filtros: dict, ordem: str, rotulo: str, confere=None) -> list[dict]:
    """Todas as linhas de uma consulta, página por página (limit/offset, em ordem estável).
    Pede a contagem exata (cabeçalho Content-Range); se ela não vier, segue até uma página vazia, para que
    um servidor que devolva menos linhas que o pedido nunca faça a coleta parar no meio.
    confere(linha) -> bool: a API às vezes ignora filtros sem avisar; linha fora do filtro aborta."""
    linhas: list[dict] = []
    primeira_anterior = None
    for pagina in range(1, MAX_PAGINAS + 1):
        params = {**filtros, "order": ordem, "limit": POR_PAGINA, "offset": len(linhas)}
        r = s.get(f"{BASE}/{tabela}", params=params, headers={"Prefer": "count=exact"}, timeout=120)
        if r.status_code == 416:            # pediu além do fim (PostgREST): acabou
            break
        r.raise_for_status()
        qualidade.guardar_bruto(f"transferegov_{rotulo}_p{pagina:03d}.json", r.content, r.url)
        dados = r.json()
        if not isinstance(dados, list):
            raise ValueError(f"{tabela}: resposta inesperada: {str(dados)[:150]}")
        if not dados:
            break
        if confere and not all(confere(d) for d in dados):
            raise ValueError(f"{tabela}: a API devolveu linhas fora do filtro {filtros} (filtro ignorado?)")
        if dados[0] == primeira_anterior:
            raise ValueError(f"{tabela}: a API repetiu a mesma página (offset ignorado?)")
        primeira_anterior = dados[0]
        linhas += dados
        total = _total(r.headers.get("Content-Range", ""))
        if total is not None and len(linhas) >= total:
            break
    else:
        raise ValueError(f"{tabela}: mais de {MAX_PAGINAS} páginas; parando por segurança")
    return linhas


def em_lotes(ids, n: int = IDS_POR_CHAMADA) -> list[list[int]]:
    unicos = sorted({i for i in (_int(x) for x in ids) if i is not None})
    return [unicos[k:k + n] for k in range(0, len(unicos), n)]


def filtro_em(ids) -> str:
    return "in.(" + ",".join(str(i) for i in ids) + ")"


def _dentro(campo: str, ids):
    """Confere se a linha devolvida pertence ao lote pedido (filtro in.(...) respeitado)."""
    ids = set(ids)
    return lambda d: _int(d.get(campo)) in ids


def sem_dados_bancarios(df: pd.DataFrame) -> pd.DataFrame:
    return df.drop(columns=[c for c in df.columns if RE_BANCARIO.search(str(c))])


def _texto(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return re.sub(r"\s+", " ", str(v)).strip()


def tabela(linhas: list[dict], chave: list[str]) -> pd.DataFrame:
    """Linhas da API -> tabela de texto sem colunas bancárias, sem repetidos e em ordem estável."""
    if not linhas:
        return pd.DataFrame()
    colunas = list(dict.fromkeys(k for linha in linhas for k in linha))
    df = sem_dados_bancarios(pd.DataFrame([{c: _texto(linha.get(c)) for c in colunas} for linha in linhas],
                                          columns=colunas)).drop_duplicates()
    ordem = [c for c in chave if c in df.columns]
    if ordem:
        df = df.sort_values(ordem, key=lambda col: pd.to_numeric(col, errors="coerce"), kind="stable")
    return df.reset_index(drop=True)


def baixar(s) -> dict[str, pd.DataFrame]:
    """Baixa as quatro tabelas antes de gravar qualquer uma: uma falha no meio não deixa arquivos
    de datas diferentes."""
    planos = baixar_tabela(s, "plano_acao_especial", {"cnpj_beneficiario_plano_acao": f"eq.{CNPJ}"},
                           "id_plano_acao.asc", "planos",
                           confere=lambda d: so_digitos(d.get("cnpj_beneficiario_plano_acao")) == CNPJ)
    executores: list[dict] = []
    relatorios: list[dict] = []
    for k, lote in enumerate(em_lotes(p.get("id_plano_acao") for p in planos), 1):
        executores += baixar_tabela(s, "executor_especial", {"id_plano_acao": filtro_em(lote)}, "id_executor.asc",
                                    f"executores_{k:02d}", confere=_dentro("id_plano_acao", lote))
        relatorios += baixar_tabela(s, "relatorio_gestao_novo_especial", {"id_plano_acao": filtro_em(lote)},
                                    "id_relatorio_gestao_novo.asc", f"relatorios_{k:02d}",
                                    confere=_dentro("id_plano_acao", lote))
    metas: list[dict] = []
    for k, lote in enumerate(em_lotes(e.get("id_executor") for e in executores), 1):
        metas += baixar_tabela(s, "meta_especial", {"id_executor": filtro_em(lote)}, "id_executor.asc,id_meta.asc",
                               f"metas_{k:02d}", confere=_dentro("id_executor", lote))
    return {
        "planos": tabela(planos, ["id_plano_acao"]),
        "executores": tabela(executores, ["id_plano_acao", "id_executor"]),
        "metas": tabela(metas, ["id_executor", "id_meta"]),
        "relatorios": tabela(relatorios, ["id_plano_acao", "id_relatorio_gestao_novo"]),
    }


def _soma(df: pd.DataFrame, colunas) -> pd.Series | int:
    presentes = [c for c in colunas if c in df.columns]
    if not presentes:
        return 0
    return sum(pd.to_numeric(df[c], errors="coerce").fillna(0.0) for c in presentes)


def coletar(s=None) -> None:
    s = s or sessao()
    tabelas = baixar(s)
    for nome, df in tabelas.items():
        obrigatorias, valores = CHECAGEM[nome]
        if gravar_checado(df, PASTA / f"emendas_pix_{nome}.csv", fonte="transferegov", obrigatorias=obrigatorias,
                          coluna_total=lambda d, valores=valores: _soma(d, valores)):
            log.info("transferegov %s: %d linhas", nome, len(df))
