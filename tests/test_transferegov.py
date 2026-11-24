"""Emendas Pix (transferências especiais) do Transferegov (vigia/coletores/transferegov.py).

Amostras reais da API (07/11/2026) em tests/amostras/transferegov_*.json, com os valores das colunas
bancárias trocados por fictícios (nenhum número de conta vai para o repositório). Nada aqui acessa a
internet: um simulador do PostgREST responde pelas chamadas.
"""
import copy
import json
from pathlib import Path

import pandas as pd
import pytest

from tests.sessao_falsa import SessaoFalsa
from vigia import qualidade
from vigia.coletores import transferegov as T

AMOSTRAS = Path(__file__).resolve().parent / "amostras"
BANCARIAS = ["codigo_banco_plano_acao", "nome_banco_plano_acao", "numero_agencia_plano_acao", "dv_agencia_plano_acao",
             "numero_conta_plano_acao", "dv_conta_plano_acao", "codigo_situacao_dado_bancario_plano_acao",
             "codigo_banco_executor", "nome_banco_executor", "numero_agencia_executor", "dv_agencia_executor",
             "nome_agencia_executor", "numero_conta_executor", "dv_conta_executor",
             "codigo_situacao_dado_bancario_executor", "descricao_situacao_dado_bancario_executor"]


def amostra(nome: str) -> list[dict]:
    return json.loads((AMOSTRAS / f"transferegov_{nome}.json").read_text(encoding="utf-8"))


@pytest.fixture
def pasta(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "PASTA", tmp_path / "transferegov")
    monkeypatch.setattr(qualidade, "BRUTOS", tmp_path / "brutos")
    monkeypatch.setattr(qualidade, "PASTA", tmp_path / "qualidade")
    monkeypatch.setattr(qualidade, "REGISTRO", qualidade.Registro())
    return tmp_path / "transferegov"


def postgrest(dados: dict, maximo_por_pagina=None, contar=True, ignora_offset=False, ignora_filtro=False):
    """Simula o PostgREST: filtros eq./in.(), order, limit/offset, Content-Range e 416 além do fim."""
    def rotas(caminho, params, cab):
        linhas = list(dados.get(caminho.rsplit("/", 1)[-1], []))
        if not ignora_filtro:
            for col, cond in params.items():
                if col in ("order", "limit", "offset"):
                    continue
                op, _, valor = cond.partition(".")
                aceitos = {valor} if op == "eq" else set(valor.strip("()").split(","))
                linhas = [x for x in linhas if str(x.get(col)) in aceitos]
        for campo in reversed([c for c in params.get("order", "").split(",") if c]):
            nome = campo.split(".")[0]
            linhas.sort(key=lambda x: (x.get(nome) is None, x.get(nome) or 0))
        conta = contar and "count=exact" in cab.get("Prefer", "")
        total, offset = len(linhas), 0 if ignora_offset else int(params.get("offset", 0))
        limite = min(int(params.get("limit", total or 1)), maximo_por_pagina or 10**9)
        if conta and 0 < total <= offset:
            return 416, {"message": "Requested range not satisfiable"}, {"Content-Range": f"*/{total}"}
        pagina = linhas[offset:offset + limite]
        faixa = f"{offset}-{offset + len(pagina) - 1}" if pagina else "*"
        return (206 if conta and len(pagina) < total else 200), pagina, {"Content-Range": f"{faixa}/{total if conta else '*'}"}
    return rotas


def offsets(s, tabela):
    return [p["offset"] for c, p, _ in s.chamadas if c.endswith("/" + tabela)]


def test_colunas_bancarias_nunca_saem():
    assert all(T.RE_BANCARIO.search(c) for c in BANCARIAS)
    planos = T.tabela(amostra("plano_acao_especial"), ["id_plano_acao"])
    executores = T.tabela(amostra("executor_especial"), ["id_executor"])
    for df in (planos, executores):
        assert not [c for c in df.columns if T.RE_BANCARIO.search(c)]
        assert "FICTICIO" not in df.to_csv(index=False)
    assert "ind_recursos_gerenciados_conta_especifica_executor" in executores.columns   # não é dado bancário
    assert list(planos["id_plano_acao"]) == ["90328", "91493"]                           # ordem numérica
    assert planos.loc[1, "valor_custeio_plano_acao"] == "199000"
    assert planos.loc[0, "descricao_programacao_orcamentaria_plano_acao"] == ""          # null vira vazio


def test_lotes_de_ids():
    lotes = T.em_lotes([*range(120, 0, -1), 5, None, "x"])
    assert [len(x) for x in lotes] == [50, 50, 20] and lotes[0][0] == 1
    assert T.filtro_em([1, 2, 3]) == "in.(1,2,3)"


def tabela_grande(n):
    return [{"id_plano_acao": i, "cnpj_beneficiario_plano_acao": T.CNPJ, "valor_custeio_plano_acao": i}
            for i in range(1, n + 1)]


def test_paginacao_com_contagem(monkeypatch):
    monkeypatch.setattr(T, "POR_PAGINA", 1000)
    monkeypatch.setattr(qualidade, "REGISTRO", qualidade.Registro())
    monkeypatch.setattr(qualidade, "guardar_bruto", lambda *a: None)
    s = SessaoFalsa(postgrest({"plano_acao_especial": tabela_grande(2500)}))
    linhas = T.baixar_tabela(s, "plano_acao_especial", {}, "id_plano_acao.asc", "planos")
    assert len(linhas) == 2500 and len({x["id_plano_acao"] for x in linhas}) == 2500
    assert offsets(s, "plano_acao_especial") == [0, 1000, 2000]          # parou pela contagem, sem chamada extra
    assert all(h.get("Prefer") == "count=exact" for _, _, h in s.chamadas)


def test_paginacao_quando_o_servidor_limita_e_nao_conta(monkeypatch):
    monkeypatch.setattr(T, "POR_PAGINA", 1000)
    monkeypatch.setattr(qualidade, "guardar_bruto", lambda *a: None)
    s = SessaoFalsa(postgrest({"plano_acao_especial": tabela_grande(2500)}, maximo_por_pagina=300, contar=False))
    linhas = T.baixar_tabela(s, "plano_acao_especial", {}, "id_plano_acao.asc", "planos")
    assert len(linhas) == 2500                                           # página curta não encerra antes da hora
    assert offsets(s, "plano_acao_especial") == [*range(0, 2500, 300), 2500]   # até a página vazia


def test_paginacao_aborta_se_a_api_ignora_o_offset(monkeypatch):
    monkeypatch.setattr(T, "POR_PAGINA", 100)
    monkeypatch.setattr(qualidade, "guardar_bruto", lambda *a: None)
    s = SessaoFalsa(postgrest({"plano_acao_especial": tabela_grande(500)}, contar=False, ignora_offset=True))
    with pytest.raises(ValueError, match="repetiu"):
        T.baixar_tabela(s, "plano_acao_especial", {}, "id_plano_acao.asc", "planos")


def dados_cariacica(n_extras=118):
    planos = amostra("plano_acao_especial")
    for i in range(1, n_extras + 1):
        extra = copy.deepcopy(planos[0])
        extra.update(id_plano_acao=i, codigo_plano_acao=f"x-{i}", valor_custeio_plano_acao=1000, valor_investimento_plano_acao=0)
        planos.append(extra)
    return {"plano_acao_especial": planos, "executor_especial": amostra("executor_especial"),
            "meta_especial": amostra("meta_especial"),
            "relatorio_gestao_novo_especial": amostra("relatorio_gestao_novo_especial")}


def test_filtro_ignorado_aborta(pasta):
    dados = dados_cariacica(0)
    dados["plano_acao_especial"][1]["cnpj_beneficiario_plano_acao"] = "11111111000111"
    with pytest.raises(ValueError, match="fora do filtro"):
        T.baixar(SessaoFalsa(postgrest(dados, ignora_filtro=True)))


def test_coleta_grava_as_quatro_tabelas_sem_dado_bancario_e_em_lotes(pasta):
    s = SessaoFalsa(postgrest(dados_cariacica()))
    T.coletar(s)
    planos = pd.read_csv(pasta / "emendas_pix_planos.csv", dtype=str, keep_default_na=False)
    assert len(planos) == 120
    for nome in ("planos", "executores", "metas", "relatorios"):
        arq = pasta / f"emendas_pix_{nome}.csv"
        conteudo = arq.read_text(encoding="utf-8")
        assert len(pd.read_csv(arq, dtype=str)) >= 1
        assert "FICTICIO" not in conteudo and not [c for c in conteudo.splitlines()[0].split(",") if T.RE_BANCARIO.search(c)]
    lotes = [p["id_plano_acao"] for c, p, _ in s.chamadas if c.endswith("/executor_especial")]
    assert len(lotes) == 3 and all(x.startswith("in.(") and x.count(",") < T.IDS_POR_CHAMADA for x in lotes)
    assert (qualidade.BRUTOS / "transferegov_planos_p001.json").exists()
    assert (qualidade.BRUTOS / "transferegov_metas_01_p001.json").exists()
    assert not qualidade.REGISTRO.bloqueios

    # Download "pela metade" (a API passa a devolver só parte dos planos): nada é substituído.
    pela_metade = dados_cariacica(30)
    T.coletar(SessaoFalsa(postgrest(pela_metade)))
    assert len(pd.read_csv(pasta / "emendas_pix_planos.csv", dtype=str)) == 120
    assert any(c.arquivo == "emendas_pix_planos.csv" and c.regra == "sem_queda_de_linhas"
               for c in qualidade.REGISTRO.bloqueios)


def test_transferegov_no_comando_semanal(monkeypatch):
    from vigia import __main__ as cli
    assert "transferegov" in cli.FONTES
    chamadas = []
    monkeypatch.setattr(T, "coletar", lambda: chamadas.append("ok"))

    class Con:
        def commit(self):
            pass

    cli._coletar_fonte("transferegov", {}, Con(), None)
    assert chamadas == ["ok"]
