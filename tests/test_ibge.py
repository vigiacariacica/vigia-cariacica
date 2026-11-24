"""IPCA do IBGE (vigia/coletores/ibge.py): leitura do formato do SIDRA, sem internet."""
import pandas as pd
import pytest

from tests.sessao_falsa import SessaoFalsa
from vigia import qualidade
from vigia.coletores import ibge

CABECALHO = {"NC": "Nível Territorial (Código)", "NN": "Nível Territorial", "MC": "Unidade de Medida (Código)",
             "MN": "Unidade de Medida", "V": "Valor", "D1C": "Brasil (Código)", "D1N": "Brasil",
             "D2C": "Variável (Código)", "D2N": "Variável", "D3C": "Mês (Código)", "D3N": "Mês"}


def linha(periodo, valor, nome):
    return {"NC": "1", "NN": "Brasil", "MC": "30", "MN": "Número-índice", "V": valor, "D1C": "1", "D1N": "Brasil",
            "D2C": "2266", "D2N": "IPCA - Número-índice (base: dezembro de 1993 = 100)", "D3C": periodo, "D3N": nome}


def resposta():
    return [CABECALHO, linha("201412", "4000.10", "dezembro 2014"), linha("202501", "7000.50", "janeiro 2025"),
            linha("202502", "7100.25", "fevereiro 2025"), linha("202503", "...", "março 2025")]


def test_le_formato_do_sidra():
    df = ibge.ler_sidra(resposta())
    assert list(df.columns) == ["ano", "mes", "indice", "referencia"]
    assert len(df) == 2                      # 2014 fica fora (antes do ano inicial); "..." é ignorado
    assert df.iloc[0]["ano"] == 2025 and df.iloc[0]["mes"] == "01" and df.iloc[0]["indice"] == "7000.50"


def test_formato_inesperado_derruba_a_fonte():
    with pytest.raises(ValueError):
        ibge.ler_sidra([CABECALHO, {"X": "1"}])
    with pytest.raises(ValueError):
        ibge.ler_sidra([])


def test_coletar_grava_csv(tmp_path, monkeypatch):
    monkeypatch.setattr(ibge, "PASTA", tmp_path / "ibge")
    monkeypatch.setattr(qualidade, "BRUTOS", tmp_path / "brutos")
    monkeypatch.setattr(qualidade, "PASTA", tmp_path / "qualidade")
    monkeypatch.setattr(qualidade, "REGISTRO", qualidade.Registro())
    monkeypatch.setattr(ibge, "sessao", lambda: SessaoFalsa(lambda caminho, params, cab: (200, resposta(), {})))
    ibge.coletar()
    df = pd.read_csv(tmp_path / "ibge" / "ipca.csv", dtype=str)
    assert len(df) == 2 and df["indice"].tolist() == ["7000.50", "7100.25"]
    assert (tmp_path / "brutos" / "ibge_ipca.json").exists()
