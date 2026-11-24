"""Coletor do TSE (vigia/coletores/tse.py): data/tse/fornecedores_campanha.csv, a entrada da regra R25."""
from pathlib import Path

import pandas as pd

from vigia.coletores import tse as G
from vigia.texto import tem_cpf

RAIZ = Path(__file__).resolve().parent.parent

CABECALHO = ["DT_GERACAO", "ANO_ELEICAO", "NM_UE", "DS_CARGO", "SQ_CANDIDATO", "NM_CANDIDATO", "SG_PARTIDO",
             "NR_CPF_CNPJ_FORNECEDOR", "NM_FORNECEDOR", "NM_FORNECEDOR_RFB", "DS_CNAE_FORNECEDOR",
             "VR_DESPESA_CONTRATADA", "DS_ORIGEM_DESPESA"]


def arquivo_tse(caminho: Path, linhas, codificacao: str) -> Path:
    texto = "\n".join(";".join(f'"{v}"' for v in linha) for linha in [CABECALHO, *linhas]) + "\n"
    caminho.write_bytes(texto.encode(codificacao))
    return caminho


def test_so_empresas_de_cariacica_sem_candidato_nem_partido(tmp_path):
    a2020 = arquivo_tse(tmp_path / "despesas_contratadas_candidatos_2020_ES.csv", [
        ["x", "2020", "CARIACICA", "Prefeito", "1", "FULANO CANDIDATO", "PXX", "11.222.333/0001-81", "POSTO X",
         "POSTO X LTDA", "Comércio varejista de combustíveis", "1.000,50", "Combustíveis e lubrificantes"],
        ["x", "2020", "CARIACICA", "Vereador", "2", "BELTRANO", "PYY", "11222333000181", "POSTO X",
         "POSTO X LTDA", "Comércio varejista de combustíveis", "99,50", "Combustíveis e lubrificantes"],
        ["x", "2020", "CARIACICA", "Vereador", "2", "BELTRANO", "PYY", "529.982.247-25", "JOÃO", "#NULO", "#NULO",
         "50,00", "Serviços prestados por terceiros"],                          # pessoa física: fica de fora
        ["x", "2020", "VITÓRIA", "Prefeito", "3", "CICLANO", "PZZ", "44.555.666/0001-00", "GRÁFICA",
         "GRÁFICA Z LTDA", "Impressão", "10,00", "Publicidade por materiais impressos"],   # outra cidade
        ["x", "2020", "CARIACICA", "Vereador", "4", "D", "P", "12.345.678/0001-95", "MEI",
         "MARIA SOUZA 52998224725", "Serviços", "200,00", "Serviços prestados por terceiros"],  # MEI: nome omitido
        ["x", "2020", "CARIACICA", "Prefeito", "1", "FULANO CANDIDATO", "PXX", "39.111.222/0001-10",
         "ELEICAO 2020 SICRANO DA SILVA VEREADOR", "ELEICAO 2020 SICRANO DA SILVA VEREADOR",
         "Atividades de organizações políticas", "5.000,00", "Doações financeiras a outros candidatos/partidos"],
    ], "latin-1")
    a2024 = arquivo_tse(tmp_path / "despesas_contratadas_candidatos_2024_ES.csv", [
        ["x", "2024", "CARIACICA", "Vereador", "9", "E", "P", "11.222.333/0001-81", "POSTO X", "#NULO",
         "Comércio varejista de combustíveis", "10,00", "Combustíveis e lubrificantes"],
    ], "utf-8")

    df = pd.concat([G.processar(G._ler_csv_tse(a2020.read_bytes()), 2020),
                    G.processar(G._ler_csv_tse(a2024.read_bytes()), 2024)], ignore_index=True)
    assert list(df.columns) == G.COLUNAS
    assert [(r.ano_eleicao, r.cnpj) for r in df.itertuples()] == [
        ("2020", "11222333000181"), ("2020", "12345678000195"), ("2024", "11222333000181")]
    posto = df.iloc[0]
    assert (posto["cargos"], posto["candidaturas"], posto["valor_campanha"]) == ("Prefeito, Vereador", 2, "1100.00")
    assert posto["fornecedor"] == "POSTO X LTDA" and df.iloc[2]["fornecedor"] == "POSTO X"   # sem nome na Receita
    texto = df.to_csv(index=False)
    for proibido in ("CANDIDATO", "BELTRANO", "CICLANO", "PXX", "PYY", "GRÁFICA", "JOÃO", "SICRANO", "ELEICAO",
                     "MARIA", "982.247"):
        assert proibido not in texto
    assert not tem_cpf(texto) and df.iloc[1]["fornecedor"] == G.NOME_MEI


def test_mei_com_comeco_do_cnpj_no_nome_fica_sem_nome():
    df = pd.DataFrame({"cnpj": ["12345678000190"], "fornecedor": ["12.345.678 FULANO DE TAL"], "ano_eleicao": ["2024"],
                       "cargos": ["Vereador"], "candidaturas": ["1"], "valor_campanha": ["10"], "cnae": ["x"],
                       "tipo_despesa": ["Publicidade"]})
    assert G.limpar(df).iloc[0]["fornecedor"] == G.NOME_MEI


def test_arquivo_do_repositorio_tem_o_formato_do_coletor():
    import pytest
    arquivo = RAIZ / "data" / "tse" / "fornecedores_campanha.csv"
    if not arquivo.exists():
        pytest.skip("fora do repositório público enquanto a R25 está em revisão jurídica (docs/DECISOES.md)")
    df = pd.read_csv(arquivo, dtype=str, keep_default_na=False)
    assert list(df.columns) == G.COLUNAS
    assert df["cnpj"].str.fullmatch(r"\d{14}").all() and set(df["ano_eleicao"]) == {"2020", "2024"}
    assert not df.duplicated(["cnpj", "ano_eleicao"]).any()
    assert G.limpar(df).equals(df)                       # as regras de publicação já valem no arquivo
    assert not df["cnae"].str.contains("organizações políticas", case=False).any()
    assert not df["fornecedor"].str.contains(r"ELEI[CÇ][AÃ]O \d{4}|\*\*\*\.", regex=True).any()
