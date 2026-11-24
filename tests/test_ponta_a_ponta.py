"""Teste de ponta a ponta: o comando real (`python -m vigia ...`) contra uma API falsa do PNCP e
da Receita, com dados FICTÍCIOS, numa pasta temporária. Confere que as 20 regras do PNCP disparam
com a gravidade certa, que o cache evita baixar de novo, que a marcação humana sobrevive a uma
nova rodada e que a lista pública não vaza CPF.
"""
from __future__ import annotations

import csv
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from tests import dados_ficticios as F
from tests import servidor_falso

RAIZ = Path(__file__).resolve().parent.parent
ESPERADOS = {
    "R01": "alta", "R02": "media", "R03": "alta", "R04": "media", "R05": "media", "R06": "alta",
    "R07": "alta", "R08": "media", "R09": "alta", "R10": "media", "R11": "media", "R12": "alta",
    "R13": "alta", "R14": "media", "R15": "baixa", "R16": "media", "R17": "baixa", "R18": "baixa",
    "R19": "alta", "R20": "alta",
}
ORDEM = {"baixa": 1, "media": 2, "alta": 3}


@pytest.fixture(scope="module")
def ambiente(tmp_path_factory):
    srv, base = servidor_falso.iniciar()
    pasta = tmp_path_factory.mktemp("vigia")
    cfg = pasta / "config.toml"
    cfg.write_text(f"""
[projeto]
municipio_nome = "Município Exemplo"
municipio_ibge = "{F.IBGE}"
esferas = ["M"]
cnpjs_extras = ["{F.PREF}"]
data_inicial = "2025-01-01"
data_final = "2026-10-31"
[vizinhos]
ativo = true
meses = 24
modalidades = [6, 8]
municipios = {{ "{F.IBGE_A}" = "Vizinho A", "{F.IBGE_B}" = "Vizinho B" }}
[coleta]
pausa_segundos = 0
espera_inicial_segundos = 0.05
modalidades = [4, 6, 8]
[apis]
pncp_consulta = "{base}/consulta"
pncp = "{base}/pncp"
cnpj = ["{base}/cnpj/{{cnpj}}"]
""", encoding="utf-8")
    (pasta / "ceis.csv").write_text(F.CSV_CEIS, encoding="latin-1")
    (pasta / "servidores.csv").write_text(F.CSV_SERVIDORES, encoding="utf-8")
    env = {**os.environ, "VIGIA_DADOS": str(pasta / "data"), "VIGIA_DOCS": str(pasta / "docs"),
           "VIGIA_BANCO": str(pasta / "banco"), "PYTHONPATH": str(RAIZ)}

    def vigia(*args, ok=(0,)):
        r = subprocess.run([sys.executable, "-m", "vigia", "--config", str(cfg), *args],
                           cwd=pasta, env=env, capture_output=True, text=True, timeout=300)
        assert r.returncode in ok, f"vigia {' '.join(args)} falhou:\n{r.stdout[-3000:]}\n{r.stderr[-3000:]}"
        return r

    vigia("coletar", "pncp", "vizinhos")
    chamadas_1 = servidor_falso.ESTADO["chamadas"]
    vigia("coletar", "pncp", "vizinhos")
    chamadas_2 = servidor_falso.ESTADO["chamadas"] - chamadas_1
    vigia("coletar", "empresas")
    vigia("importar-sancoes", str(pasta / "ceis.csv"))
    vigia("importar-servidores", str(pasta / "servidores.csv"))
    vigia("alertas")
    yield {"pasta": pasta, "vigia": vigia, "chamadas": (chamadas_1, chamadas_2)}
    srv.shutdown()


def _alertas(pasta):
    with open(pasta / "data" / "alertas.csv", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_as_20_regras_do_pncp_disparam_com_a_gravidade_certa(ambiente):
    achados = {}
    for a in _alertas(ambiente["pasta"]):
        if ORDEM[a["gravidade"]] > ORDEM.get(achados.get(a["regra"]), 0):
            achados[a["regra"]] = a["gravidade"]
    erradas = {r: (g, achados.get(r)) for r, g in ESPERADOS.items() if achados.get(r) != g}
    assert not erradas, f"esperado x obtido: {erradas}"


def test_preco_normal_nao_gera_alerta(ambiente):
    assert not any("FEIJAO" in a["titulo"].upper() for a in _alertas(ambiente["pasta"]))


def test_toda_linha_publica_e_pergunta_com_link(ambiente):
    for a in _alertas(ambiente["pasta"]):
        assert a["pergunta"].endswith("?"), a["id"]
        assert a["id"] and a["primeira_vez"]
        assert a["link"].startswith("http"), f"{a['id']} ({a['regra']}) sem link oficial"


def test_lista_publica_nao_vaza_cpf(ambiente):
    for a in _alertas(ambiente["pasta"]):
        digitos = "".join(c for c in a["fornecedor_doc"] if c.isdigit())
        assert len(digitos) != 11, f"CPF completo em {a['id']}"
    for arq in (ambiente["pasta"] / "data" / "pncp").glob("*.csv"):
        with open(arq, encoding="utf-8") as f:
            for linha in csv.DictReader(f):
                d = "".join(c for c in linha.get("ni_fornecedor", "") if c.isdigit())
                assert len(d) != 11, f"CPF completo em {arq.name}"


def test_cache_evita_baixar_de_novo(ambiente):
    c1, c2 = ambiente["chamadas"]
    assert c2 < c1 / 2, f"1ª coleta {c1} chamadas, 2ª {c2}"


def test_exporta_csvs_do_pncp(ambiente):
    pncp = ambiente["pasta"] / "data" / "pncp"
    for nome in ("contratacoes", "itens", "resultados", "contratos", "termos", "orgaos"):
        assert (pncp / f"{nome}.csv").stat().st_size > 50, nome
    assert not (ambiente["pasta"] / "data" / "receita" / "socios.csv").exists()


def test_marcacao_humana_fica_no_git_e_sobrevive(ambiente):
    pasta, vigia = ambiente["pasta"], ambiente["vigia"]
    aid = next(a["id"] for a in _alertas(pasta) if a["regra"] == "R01")
    vigia("marcar", aid, "em_analise", "pedi a pesquisa de preços por LAI")
    vigia("alertas")
    casos = (pasta / "data" / "casos.csv").read_text(encoding="utf-8")
    assert aid in casos and "em_analise" in casos
    linha = next(a for a in _alertas(pasta) if a["id"] == aid)
    assert (linha["status"], linha["nota"]) == ("em_analise", "pedi a pesquisa de preços por LAI")
    con = sqlite3.connect(pasta / "banco" / "vigia.db")
    assert con.execute("SELECT status FROM alertas WHERE id=?", (aid,)).fetchone()[0] == "em_analise"


def test_painel_e_dossie(ambiente):
    pasta, vigia = ambiente["pasta"], ambiente["vigia"]
    vigia("painel")
    vigia("dossie", "--top", "2")
    assert (pasta / "saida" / "painel.html").exists()
    assert list((pasta / "saida" / "dossies").glob("dossie_*.html"))


def test_r19_dentro_de_um_ano_e_media(ambiente):
    r19 = [a for a in _alertas(ambiente["pasta"]) if a["regra"] == "R19"]
    assert {a["gravidade"] for a in r19} == {"alta", "media"}
    assert any("dentro de 1 ano" in a["detalhe"] for a in r19 if a["gravidade"] == "media")
    assert any("mais de 1 ano" in a["detalhe"] for a in r19 if a["gravidade"] == "alta")
