"""A camada refinada traduz códigos do portal em categorias e soma sem inventar número."""
import pandas as pd
import pytest

from vigia import refino


def test_origem_muda_de_plano_em_2023():
    # plano antigo (ES, até 2022)
    assert refino.origem_da_fonte("1.001.0000.0000", 2022) == "livres"
    assert refino.origem_da_fonte("1.112.0000.0000", 2021) == "fundeb"
    assert refino.origem_da_fonte("1.214.0003.0000", 2022) == "saude_vinc"
    assert refino.origem_da_fonte("1.540.0000.0000", 2022) == "royalties"   # 540 antigo = royalties dos estados
    assert refino.origem_da_fonte("1.920.0013.0000", 2020) == "emprestimos"
    # plano da STN (desde 2023)
    assert refino.origem_da_fonte("1.500.0025.0000", 2025) == "livres"
    assert refino.origem_da_fonte("1.540.0070.0000", 2025) == "fundeb"      # 540 novo = FUNDEB
    assert refino.origem_da_fonte("1.600.0003.0000", 2024) == "saude_vinc"
    assert refino.origem_da_fonte("1.706.0000.0000", 2024) == "emendas_pix"
    assert refino.origem_da_fonte("1.751.0000.0000", 2023) == "cosip"
    assert refino.origem_da_fonte("1.754.0000.0000", 2023) == "emprestimos"
    assert refino.origem_da_fonte("1.801.0000.0000", 2023) == "rpps"
    assert refino.origem_da_fonte("1.701.2153.0000", 2025) == "convenios"
    assert refino.origem_da_fonte("", 2025) == "nao_classificada"
    assert refino.origem_da_fonte("1.123.0000", 2020) == "educacao_vinc"    # formato curto de 2019-2020


def test_exercicio_anterior_e_tipo_e_modalidade():
    assert refino.exercicio_anterior("2.500.0000.0000")
    assert not refino.exercicio_anterior("1.500.0000.0000")
    assert refino.tipo_gasto("31901100") == "Pessoal e encargos"
    assert refino.tipo_gasto("44905100").startswith("Investimentos")
    assert refino.tipo_gasto("46907100").startswith("Amortização")
    assert refino.modalidade("33903900").startswith("Aplicação direta")
    assert refino.modalidade("33508500").startswith("Entidade sem fins")
    assert refino.modalidade("33933000").startswith("Consórcio")


def test_tipo_recebedor():
    assert refino.tipo_recebedor("FOLHA DE PAGAMENTO DO MUNICÍPIO", "99.999.999/9999-99").startswith("Servidores")
    # até 2022 a folha era lançada em nome da prefeitura: a natureza (31 = pessoal) decide
    assert refino.tipo_recebedor("PREFEITURA MUNICIPAL DE CARIACICA", "27.150.549/0001-19", "", "31901100").startswith("Servidores")
    assert refino.tipo_recebedor("INSS", "29.979.036/0001-40", "", "31901300").startswith("Servidores")
    assert refino.tipo_recebedor("CAIXA ECONOMICA FEDERAL", "00.360.305/0001-04", "", "46907100").startswith("Dívida")
    assert refino.tipo_recebedor("JOAO DA SILVA", "***.212.345-**") == "Pessoa física"
    assert refino.tipo_recebedor("INSS INST NACIONAL DO SEG SOCIAL", "29.979.036/0001-40").startswith("Órgão público")
    assert refino.tipo_recebedor("CIM POLINORTE", "02.618.132/0001-07").startswith("Órgão público")
    assert refino.tipo_recebedor("INSTITUTO ESPERANCA", "10.779.749/0001-32") == "Entidade sem fins lucrativos"
    assert refino.tipo_recebedor("XYZ LTDA", "11.111.111/0001-11", "Associação Privada") == "Entidade sem fins lucrativos"
    assert refino.tipo_recebedor("EDP ESPIRITO SANTO DISTRIBUICAO", "28.152.650/0001-71").startswith("Concessionária")
    assert refino.tipo_recebedor("CONSORCIO S3 ILUMINACAO", "43.663.727/0001-61") == "Consórcio de empresas"
    assert refino.tipo_recebedor("FORTE AMBIENTAL LTDA", "27.320.787/0001-25") == "Empresa"
    assert refino.tipo_recebedor("BANCO QUALQUER SA", "00.000.000/0001-91", "Sociedade de Economia Mista").startswith("Órgão público")


def _pagamento(ano, fonte, natureza, doc, nome, pago, funcao="12", funcao_nome="EDUCAÇÃO", orgao="SEME", contrato="1/2024"):
    return {"Ano": str(ano), "Data": f"02/01/{ano} 00:00:00", "IdEmpenho": "1", "NumeroEmpenho": "1/2024",
            "ValorEmpenhado": f"{pago:.2f}", "ValorLiquidado": f"{pago:.2f}", "ValorPago": f"{pago:.2f}",
            "CpfCnpjFornecedor": doc, "NomeFornecedor": nome, "CodOrgao": "020800", "Orgao": orgao,
            "CodUnidadeGestora": "208", "UnidadeGestora": orgao, "CodFuncao": funcao, "Funcao": funcao_nome,
            "CodSubFuncao": "361", "SubFuncao": "ENSINO", "CodPrograma": "0020", "Programa": "P", "CodAcao": "2",
            "Acao": "A", "CodFonte": fonte, "Fonte": "F", "CodNaturezaDespesa": natureza, "NaturezaDespesa": "N",
            "NumeroProcesso": "1/2024", "NumeroContrato": contrato, "Licitacao": "", "Descricao": "d"}


@pytest.fixture
def pagamentos():
    return pd.DataFrame([
        _pagamento(2024, "1.500.0000.0000", "33903900", "27.320.787/0001-25", "FORTE AMBIENTAL EIRELI", 100.0),
        _pagamento(2024, "1.540.0070.0000", "31901100", "99.999.999/9999-99", "FOLHA DE PAGAMENTO", 300.0),
        _pagamento(2024, "1.600.0003.0000", "44905100", "27.320.787/0002-06", "FORTE AMBIENTAL LTDA", 50.0,
                   funcao="10", funcao_nome="SAUDE", orgao="FMS"),
        _pagamento(2025, "1.500.0000.0000", "33903900", "27.320.787/0001-25", "FORTE AMBIENTAL LTDA", 200.0),
        _pagamento(2025, "1.500.0000.0000", "33903600", "***.212.345-**", "PESSOA", 10.0),
        _pagamento(2025, "1.500.0000.0000", "33903900", "27.320.787/0001-25", "FORTE AMBIENTAL LTDA", 0.0,
                   funcao="10", funcao_nome="SAÚDE"),
    ])


def test_refinar_soma_sem_inventar(pagamentos, tmp_path, monkeypatch):
    monkeypatch.setattr(refino, "DADOS", tmp_path)
    monkeypatch.setattr(refino, "PASTA", tmp_path / "refinado")
    monkeypatch.setattr(refino.armazem, "ler", lambda caminho: pd.DataFrame())
    tabelas = refino.refinar(pagamentos, empresas=pd.DataFrame())
    resumo = tabelas["resumo_ano"].set_index("ano")
    assert resumo.loc[2024, "pago"] == 450.0 and resumo.loc[2025, "pago"] == 210.0
    origem = tabelas["origem_ano"]
    o24 = origem[origem["ano"] == 2024].set_index("origem")["pago"]
    assert o24["livres"] == 100.0 and o24["fundeb"] == 300.0 and o24["saude_vinc"] == 50.0
    assert abs(origem[origem["ano"] == 2024]["pct_do_ano"].sum() - 1.0) < 1e-6
    tipo = tabelas["tipo_ano"]
    assert tipo[(tipo["ano"] == 2024) & (tipo["tipo"] == "Pessoal e encargos")]["pago"].iloc[0] == 300.0
    # matriz e filial viram uma só empresa (raiz do CNPJ); pessoa física fica de fora da lista
    f = tabelas["fornecedores"]
    forte = f[f["raiz_cnpj"] == "27320787"].iloc[0]
    assert forte["total_pago"] == 350.0 and forte["pago_2024"] == 150.0 and forte["pago_2025"] == 200.0
    assert forte["primeiro_ano"] == 2024 and forte["nome"] == "FORTE AMBIENTAL LTDA" and forte["orgaos"] == 2
    assert not f["nome"].str.contains("PESSOA").any()
    # o nome da função fica único mesmo quando o portal escreve SAUDE/SAÚDE
    fun = tabelas["funcao_ano"]
    assert fun[fun["CodFuncao"] == "10"]["funcao"].nunique() == 1
    assert "deflator" not in tabelas   # sem IPCA: só valores nominais, sem coluna real
    assert "pago_real" not in resumo.columns


def test_deflator_leva_a_precos_do_ultimo_ano_fechado(tmp_path, monkeypatch):
    monkeypatch.setattr(refino, "DADOS", tmp_path)
    (tmp_path / "ibge").mkdir()
    linhas = [{"ano": 2024, "mes": m, "indice": 100.0} for m in range(1, 13)]
    linhas += [{"ano": 2025, "mes": m, "indice": 110.0} for m in range(1, 13)]
    linhas += [{"ano": 2026, "mes": m, "indice": 120.0} for m in range(1, 7)]   # ano corrente, parcial
    pd.DataFrame(linhas).to_csv(tmp_path / "ibge" / "ipca.csv", index=False)
    d = refino.deflator([2024, 2025, 2026]).set_index("ano")
    assert d.loc[2024, "ano_base"] == 2025 and d.loc[2024, "fator_para_ano_base"] == pytest.approx(1.1)
    assert d.loc[2025, "fator_para_ano_base"] == pytest.approx(1.0)
    assert d.loc[2026, "fator_para_ano_base"] == pytest.approx(110 / 120)
    assert d.loc[2026, "meses"] == 6


def test_origem_pelo_nome_so_avisa_quando_difere():
    assert refino.origem_pelo_nome("RECEITA DE IMPOSTOS E TRANSF IMPOSTOS - SAÚDE") == "livres"
    assert refino.origem_pelo_nome("TRANSFERÊNCIA ESPECIAL DA UNIÃO") == "emendas_pix"
    assert refino.origem_pelo_nome("TRANSFERÊNCIAS DO FUNDEB [70%]") == "fundeb"
    assert refino.origem_pelo_nome("XYZ") == ""
