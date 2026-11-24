"""Regras R21–R27 (portal municipal) e catálogo único de regras."""
import pandas as pd

from vigia.alertas import _detalhe_publico, _titulo_publico, portal
from vigia.coletores.transparencia import proteger_pessoa_fisica
from vigia.texto import mascarar_cpfs
from vigia.regras import REGRAS


def pagamentos(linhas):
    return pd.DataFrame(linhas, columns=["Ano", "CpfCnpjFornecedor", "NomeFornecedor", "ValorPago", "Data"]).astype(str)


def test_catalogo_tem_31_regras_e_toda_regra_faz_uma_pergunta():
    # R28 (plano de contratações) ainda não existe no catálogo; R29 a R32 vieram da revisão de 12/11/2026
    assert sorted(REGRAS) == [f"R{i:02d}" for i in range(1, 28)] + ["R29", "R30", "R31", "R32", "R33"]
    for codigo, r in REGRAS.items():
        assert r["pergunta"].endswith("?"), codigo
        for campo in ("nome", "porque", "base_legal", "verificar", "legitimas"):
            assert r[campo], f"{codigo} sem {campo}"


def test_entes_publicos_ficam_fora_do_ranking():
    p = pagamentos([
        ["2024", "99.999.999/9999-99", "FOLHA DE PAGAMENTO DO MUNICÍPIO DE CARIACICA", "1000", "02/01/2024"],
        ["2024", "29.979.036/0061-81", "INSS INST NACIONAL DO SEG SOCIAL", "500", "02/01/2024"],
        ["2024", "11.111.111/0001-11", "CONSTRUTORA X LTDA", "300", "02/01/2024"],
    ])
    assert list(portal.pagos_por_fornecedor(p).index) == ["11.111.111/0001-11"]


def test_r21_salto_de_pagamentos():
    linhas = []
    for ano, v in (("2021", 1e6), ("2022", 1.2e6), ("2023", 0.9e6), ("2024", 30e6)):
        linhas.append([ano, "22.222.222/0001-22", "ENGENHARIA Y LTDA", str(v), f"10/03/{ano}"])
    for ano in ("2021", "2022", "2023", "2024"):  # fornecedor estável não dispara
        linhas.append([ano, "33.333.333/0001-33", "LIMPEZA Z LTDA", "20000000", f"10/03/{ano}"])
    a = portal.crescimento_fornecedor(portal.pagos_por_fornecedor(pagamentos(linhas)))
    assert len(a) == 1
    assert a[0].regra == "R21" and a[0].fornecedor_doc == "22.222.222/0001-22" and a[0].referencia == "2024"
    assert a[0].gravidade == "alta" and a[0].data == "2024-12-31"
    assert "wstransparencia.cariacica.es.gov.br" in a[0].link


def test_r22_aditivo_acima_de_25pct():
    c = pd.DataFrame([
        {"NumeroContrato": "8", "AnoContrato": "2021", "Fornecedor": "HIMALAIA", "CPFCNPJ": "00.471.823/0001-03",
         "ValorContratado": "13500000", "Aditivo": "100100000", "Objeto": "Manutenção predial"},
        {"NumeroContrato": "9", "AnoContrato": "2021", "Fornecedor": "OK LTDA", "CPFCNPJ": "1",
         "ValorContratado": "1000000", "Aditivo": "200000", "Objeto": "x"},
    ])
    a = portal.aditivos_municipais(c)
    assert [x.fornecedor for x in a] == ["HIMALAIA"] and a[0].regra == "R22"


def test_r22_e_triagem_nunca_alta():
    """O portal só dá o total dos aditivos: prorrogação, reajuste e acréscimo legal (até 25%, repetido a cada ano
    prorrogado) podem explicar muito. A regra nunca dá alta; média só quando passa do teto com 25% de acréscimo."""
    c = pd.DataFrame([
        # 5 anos; total 5x: a prorrogação com reajuste explica → baixa
        {"NumeroContrato": "1", "AnoContrato": "2020", "Fornecedor": "COLETA LTDA", "CPFCNPJ": "1",
         "ValorContratado": "1000000", "Aditivo": "4000000", "Objeto": "x",
         "DataInicio": "01/01/2020", "DataFinal": "31/12/2024", "DataAssinatura": "20/12/2019"},
        # 2 anos; total 8x: passa até do teto com 25% de acréscimo → média, com o valor além do teto
        {"NumeroContrato": "2", "AnoContrato": "2023", "Fornecedor": "OBRA LTDA", "CPFCNPJ": "2",
         "ValorContratado": "1000000", "Aditivo": "7000000", "Objeto": "y",
         "DataInicio": "01/01/2023", "DataFinal": "31/12/2024", "DataAssinatura": "15/12/2022"},
        # 4 anos; total 5,3x (caso real parecido): cabe no teto de 25% → baixa, sem alarme no título
        {"NumeroContrato": "3", "AnoContrato": "2023", "Fornecedor": "PAVIMENTO LTDA", "CPFCNPJ": "3",
         "ValorContratado": "48670346.02", "Aditivo": "207472873.93", "Objeto": "z",
         "DataInicio": "29/12/2023", "DataFinal": "28/12/2027", "DataAssinatura": "29/12/2023"},
    ])
    a = {x.fornecedor_doc: x for x in portal.aditivos_municipais(c)}
    assert a["1"].gravidade == "baixa" and "cobre o total" in a["1"].detalhe
    assert a["2"].gravidade == "media" and "passa disso em" in a["2"].detalhe
    assert a["2"].data == "2022-12-15" and "(8,0 vezes o original) em 2" in a["2"].titulo
    assert a["3"].gravidade == "media" and "%" not in a["3"].titulo          # sobra > 25% e > R$ 1 mi, mas no teto
    assert "dentro do que um acréscimo de até 25%" in a["3"].detalhe
    assert all(x.gravidade != "alta" for x in a.values())


def test_r24_pagamento_a_fornecedor_punido():
    p = pagamentos([
        ["2023", "42.336.122/0001-01", "VETORIAL", "5000", "15/06/2023 00:00:00"],
        ["2022", "42.336.122/0001-01", "VETORIAL", "9000", "15/06/2022 00:00:00"],
    ])
    pen = pd.DataFrame([{"Fornecedor": "VETORIAL", "CPFCPNJ": "42.336.122/0001-01", "TipoPenalidade": "Suspensão",
                         "InicioSuspensao": "28/12/2022", "TerminoSuspensao": "28/12/2023"}])
    a = portal.penalizado_recebendo(p, pen)
    assert len(a) == 1 and a[0].valor == 5000 and a[0].regra == "R24"


def campanha(linhas):
    return pd.DataFrame(linhas, columns=["cnpj", "fornecedor", "ano_eleicao", "cargos", "candidaturas",
                                         "valor_campanha", "cnae"]).astype(str)


def test_r25_fornecedor_de_campanha_que_depois_recebeu():
    p = pagamentos([
        ["2020", "11.111.111/0001-11", "GRAFICA A LTDA", "5000000", "10/03/2020"],      # antes (ano da eleição)
        ["2021", "11.111.111/0001-11", "GRAFICA A LTDA", "600000", "10/03/2021"],
        ["2022", "11.111.111/0001-11", "GRAFICA A LTDA", "500000", "10/03/2022"],
        ["2025", "22.222.222/0001-22", "LOCADORA B LTDA", "12000000", "10/03/2025"],
        ["2021", "33.333.333/0001-33", "POSTO C LTDA", "900000", "10/03/2021"],         # abaixo de R$ 1 mi
        ["2021", "00.000.000/0001-91", "BANCO DO BRASIL SA", "9000000", "10/03/2021"],  # banco público
        ["2025", "44.444.444/0001-44", "EDP ESPIRITO SANTO", "30000000", "10/03/2025"], # concessionária de energia
        ["2021", "55.555.555/0001-55", "SEM CAMPANHA LTDA", "50000000", "10/03/2021"],  # não atendeu campanha
    ])
    c = campanha([
        ["11111111000111", "GRAFICA A LTDA", "2020", "Prefeito, Vereador", "3", "4460.0", "Impressão"],
        ["22222222000122", "LOCADORA B LTDA", "2024", "Vereador", "1", "900.0", "Aluguel de estruturas"],
        ["33333333000133", "POSTO C LTDA", "2020", "Vereador", "2", "100.0", "Combustíveis"],
        ["00000000000191", "BANCO DO BRASIL SA", "2020", "Vereador", "1", "10.45", "Bancos múltiplos"],
        ["44444444000144", "EDP ESPIRITO SANTO", "2024", "Prefeito", "1", "177.1", "Distribuição de energia elétrica"],
    ])
    excluidos = []
    a = {x.fornecedor_doc: x for x in portal.fornecedor_de_campanha(p, c, excluidos=excluidos)}
    assert set(a) == {"11.111.111/0001-11", "22.222.222/0001-22"}
    assert {doc for doc, _, _ in excluidos} == {"00.000.000/0001-91", "44.444.444/0001-44"}   # à vista no relatório
    g = a["11.111.111/0001-11"]
    assert (g.regra, g.valor, g.referencia) == ("R25", 1_100_000, "campanhas 2020")
    assert g.gravidade == "baixa"                                    # já recebia antes da eleição
    assert "(2020) que depois recebeu R$ 1.100.000,00 da prefeitura (2021 a 2022)" in g.titulo
    assert "3 candidaturas a prefeito e vereador" in g.detalhe and "R$ 4.460,00" in g.detalhe
    assert "já tinha pago R$ 5.000.000,00" in g.detalhe            # não "passou a receber"
    assert g.link.endswith("exercicio=2021&nomeCPFCNPJ=11.111.111/0001-11")        # ano de maior pagamento
    assert [x[-35:] for x in g.outros_links] == ["exercicio=2022&nomeCPFCNPJ=11.111.111/0001-11"[-35:]]
    b = a["22.222.222/0001-22"]
    assert b.gravidade == "media" and "não tinha pago nada" in b.detalhe            # >= R$ 10 mi e nada antes
    assert "por 1 candidatura a vereador" in b.detalhe                              # singular
    assert "(2025)" in b.titulo and "2025 a 2025" not in b.titulo


def test_r25_beneficio_de_servidor_repassado_pela_empresa_fica_em_baixa():
    """09/11/2026: os pagamentos a administradoras de cartão eram auxílio-alimentação dos servidores. O valor não
    é o que a empresa recebeu para si; o alerta continua (a escolha da empresa é a pergunta), mas diz isso."""
    p = pagamentos([[str(a), "06.175.892/0001-48", "CARTOES Y LTDA", "20000000", f"01/02/{a}"] for a in (2021, 2022)])
    p["NaturezaDespesa"] = "AUXÍLIO ALIMENTAÇÃO"
    c = campanha([["06175892000148", "CARTOES Y LTDA", "2020", "Vereador", "1", "300.0", "Administração de cartões"]])
    a = portal.fornecedor_de_campanha(p, c)
    assert [(x.regra, x.gravidade, x.valor) for x in a] == [("R25", "baixa", 40_000_000)]
    assert "100% desse valor é auxílio-alimentação" in a[0].detalhe
    assert a[0].titulo.endswith("a maior parte é benefício de servidores repassado pela empresa")


def test_r25_um_alerta_por_cnpj_mesmo_com_duas_eleicoes():
    p = pagamentos([[str(a), "11.111.111/0001-11", "EMPRESA X LTDA", "1000000", f"01/02/{a}"] for a in range(2021, 2027)])
    c = campanha([["11111111000111", "EMPRESA X LTDA", "2020", "Prefeito", "1", "100.0", "Serviços"],
                  ["11111111000111", "EMPRESA X LTDA", "2024", "Vereador", "2", "50.0", "Serviços"]])
    a = portal.fornecedor_de_campanha(p, c)
    assert [(x.referencia, x.valor, x.data) for x in a] == [("campanhas 2020/2024", 6_000_000, "2021-01-01")]
    assert "(2020 e 2024)" in a[0].titulo                         # cada ano de pagamento conta uma vez
    assert "em 2020, por 1 candidatura a prefeito" in a[0].detalhe and "em 2024, por 2 candidaturas a vereador" in a[0].detalhe


def test_r25_le_a_entrada_do_repositorio_e_funciona_sem_ela(tmp_path, monkeypatch):
    p = pagamentos([["2021", "11.111.111/0001-11", "EMPRESA X LTDA", "2000000", "01/02/2021"]])
    vazio = pd.DataFrame()
    monkeypatch.setattr(portal, "FORNECEDORES_CAMPANHA", tmp_path / "nao_existe.csv")
    assert not [x for x in portal.todas(p, vazio, vazio, vazio) if x.regra == "R25"]
    entrada = tmp_path / "fornecedores_campanha.csv"
    campanha([["11111111000111", "EMPRESA X LTDA", "2020", "Prefeito", "1", "100.0", "Serviços"]]).to_csv(entrada, index=False)
    monkeypatch.setattr(portal, "FORNECEDORES_CAMPANHA", entrada)
    # R32 olha só o PNCP gravado no repositório (não depende das entradas do teste)
    assert [x.regra for x in portal.todas(p, vazio, vazio, vazio) if x.regra != "R32"] == ["R25"]


def test_lista_publica_nao_traz_nome_de_pessoa_fisica():
    assert "MARIA" not in _titulo_publico("R14", "Sócio MARIA SOUZA tem o nome de servidora")
    assert "MARIA" not in _detalhe_publico("R14", "Sócio: MARIA SOUZA. Servidor(es): MARIA SOUZA - Assessora")


def test_mascara_cpf_em_texto_livre():
    t = "MEI JOAO 52998224725; restituição a 529.982.247-25; CNPJ 27.150.549/0001-19; tel 27999998888"
    m = mascarar_cpfs(t)
    assert "52998224725" not in m and "529.982.247-25" not in m
    assert "27.150.549/0001-19" in m and "27999998888" in m


def test_pagamento_a_pessoa_fisica_sai_sem_nome_e_descricao():
    df = pd.DataFrame([
        {"CpfCnpjFornecedor": "****47.207**", "NomeFornecedor": "FULANA", "Descricao": "Pensão alimentícia de X"},
        {"CpfCnpjFornecedor": "27.320.787/0001-25", "NomeFornecedor": "FORTE", "Descricao": "Coleta de lixo"},
    ])
    out = proteger_pessoa_fisica(df)
    assert list(out["NomeFornecedor"]) == ["PESSOA FÍSICA", "FORTE"]
    assert "Pensão" not in out.loc[0, "Descricao"] and out.loc[1, "Descricao"] == "Coleta de lixo"


def test_r25_so_exclui_vinculo_obrigatorio_ou_monopolio():
    """Combustível e telefonia têm concorrência: entram. Banco (conta obrigatória) e tarifa bancária: saem."""
    docs = {"66": "CARTAO COMBUSTIVEL LTDA", "77": "TELEFONIA X SA", "88": "BANCO PRIVADO SA", "99": "PAGAMENTOS Y LTDA"}
    p = pagamentos([["2021", f"{d}.{d}{d[0]}.{d}{d[0]}/0001-{d}", n, "9000000", "10/03/2021"] for d, n in docs.items()])
    def linha(d, cnae, tipo):
        return {"cnpj": f"{d}{d}{d[0]}{d}{d[0]}0001{d}", "fornecedor": docs[d], "ano_eleicao": "2020", "cargos": "Prefeito",
                "candidaturas": "1", "valor_campanha": "100", "cnae": cnae, "tipo_despesa": tipo}
    c = pd.DataFrame([linha("66", "Serviços prestados às empresas", "Combustíveis e lubrificantes"),
                      linha("77", "Telefonia móvel celular", "Diversas a especificar"),
                      linha("88", "Bancos múltiplos, com carteira comercial", "Diversas a especificar"),
                      linha("99", "Serviços financeiros", "Encargos financeiros, taxas bancárias e/ou op. cartão de crédito")])
    excluidos = []
    a = portal.fornecedor_de_campanha(p, c, excluidos=excluidos)
    assert sorted(x.fornecedor for x in a) == ["CARTAO COMBUSTIVEL LTDA", "TELEFONIA X SA"]
    assert sorted(n for _, n, _ in excluidos) == ["BANCO PRIVADO SA", "PAGAMENTOS Y LTDA"]


def test_r20_compara_sem_o_texto_padrao_de_contratacao():
    """Caso real (PNCP 2024/46, 2025/72, 2025/277): limpeza e portaria pareciam o mesmo serviço pelo texto padrão."""
    from vigia.alertas.motor import GENERICOS_CONTRATACAO as G
    from vigia.texto import jaccard, tokens
    limpeza = ("Contratação de empresa especializada para prestação dos serviços de limpeza, higienização e desinfecção "
               "nas instalações físicas das Unidades Administrativas desta municipalidade, com fornecimento de material")
    limpeza2 = ("Prestação dos serviços de limpeza, higienização e desinfecção nas instalações físicas das Unidades "
                "Administrativas desta municipalidade, com fornecimento de material")
    portaria = ("Contratação de empresa especializada para prestação de serviços de portaria, com fornecimento de mão de "
                "obra, equipamentos e insumos, a serem executados de forma contínua, nas dependências das Unidades "
                "Administrativas")
    assert jaccard(tokens(limpeza) - G, tokens(limpeza2) - G) >= 0.4
    assert jaccard(tokens(limpeza) - G, tokens(portaria) - G) < 0.4


# ---------------------------------------------------------------- R26 emergencial perto do fim

def _emerg(numero, objeto, inicio, fim, valor="13547427.36", situacao="Normal"):
    return {"NumeroContrato": numero, "AnoContrato": "2026", "ValorTotal": valor, "CPFCNPJ": "27.436.815/0001-74",
            "Fornecedor": "EMPRESA X LTDA", "DataInicio": inicio, "DataFinal": fim, "Situacao": situacao,
            "Objeto": objeto, "UnidadeGestora": "PREFEITURA"}


def _lic(objeto, publicada, modalidade="Pregão - Eletrônico"):
    return {"objeto": objeto, "data_publicacao": publicada, "modalidade_nome": modalidade}


LIMPEZA = ("Contratação emergencial de empresa para execução de serviços contínuos de limpeza, conservação, asseio "
           "e higienização dos estabelecimentos de saúde")


def test_r26_pergunta_quando_emergencial_acaba_sem_licitacao_depois_do_inicio():
    e = pd.DataFrame([_emerg("62", LIMPEZA, "01/04/2026", "23/03/2027")])
    # a licitação parecida é de ANTES da emergência (provavelmente a que falhou): não conta como substituta
    lic = pd.DataFrame([_lic("Contratação de empresa para execução de serviços contínuos de limpeza, conservação, "
                             "asseio e higienização dos estabelecimentos de saúde", "2026-03-11")])
    a = portal.emergencia_sem_substituta(e, lic, hoje=pd.Timestamp("2026-11-09"))
    assert [(x.regra, x.gravidade, x.data) for x in a] == [("R26", "media", "2027-03-23")]
    assert "23/03/2027" in a[0].titulo and "faltam 134 dias" in a[0].detalhe
    assert "contratos-emergenciais/csv" in a[0].link


def test_r26_cala_quando_ha_licitacao_parecida_depois_do_inicio():
    e = pd.DataFrame([_emerg("62", LIMPEZA, "01/04/2026", "23/03/2027")])
    lic = pd.DataFrame([_lic("Serviços contínuos de limpeza, conservação, asseio e higienização dos "
                             "estabelecimentos de saúde do município", "2026-09-28")])
    assert portal.emergencia_sem_substituta(e, lic, hoje=pd.Timestamp("2026-11-09")) == []


def test_r26_ignora_dispensa_obra_pontual_fim_distante_e_contrato_encerrado():
    hoje = pd.Timestamp("2026-11-09")
    e = pd.DataFrame([
        _emerg("40", "Contratação emergencial para obras de contenção de encosta na Rua Mato Grosso", "28/01/2026",
               "27/01/2027"),
        _emerg("184", "Gestão do pronto atendimento do Trevo", "29/10/2026", "28/10/2027"),   # fim distante
        _emerg("70", LIMPEZA, "01/02/2026", "20/12/2026", situacao="Encerrado"),
    ])
    assert portal.emergencia_sem_substituta(e, pd.DataFrame(), hoje=hoje) == []
    # uma nova DISPENSA para o mesmo serviço não é licitação substituta
    e2 = pd.DataFrame([_emerg("62", LIMPEZA, "01/04/2026", "23/03/2027")])
    lic = pd.DataFrame([_lic(LIMPEZA, "2026-10-01", "Dispensa")])
    assert [x.regra for x in portal.emergencia_sem_substituta(e2, lic, hoje=hoje)] == ["R26"]


# ---------------------------------------------------------------- R27 contrato no teto de prazo

def _contrato(numero, objeto, inicio, fim, valor="150622873.61", tipo="Serviço", situacao="Normal"):
    return {"NumeroContrato": numero, "AnoContrato": "2020", "TipoContrato": tipo, "ValorTotal": valor,
            "CPFCNPJ": "04.411.461/0001-61", "Fornecedor": "LIMPA TUDO LTDA", "DataInicio": inicio, "DataFinal": fim,
            "Situacao": situacao, "Objeto": objeto, "UnidadeGestora": "PREFEITURA"}


LOGRADOUROS = ("O presente contrato tem por objeto a execução de serviços de limpeza de logradouros públicos nas "
               "regiões administrativas 01 a 12, no Município de Cariacica/ES.")


def test_r27_pergunta_quando_contrato_de_6_anos_acaba_sem_licitacao():
    c = pd.DataFrame([_contrato("164", LOGRADOUROS, "03/12/2020", "02/12/2026")])
    a = portal.contrato_no_limite_sem_substituta(c, pd.DataFrame(), hoje=pd.Timestamp("2026-11-10"))
    assert [(x.regra, x.gravidade, x.data) for x in a] == [("R27", "alta", "2026-12-02")]
    assert "72 meses" in a[0].titulo and "faltam 22 dias" in a[0].detalhe
    assert "/api/contratos/csv" in a[0].link


def test_r27_cala_com_licitacao_parecida_recente_e_ignora_contrato_curto_obra_ou_pequeno():
    hoje = pd.Timestamp("2026-11-10")
    c = pd.DataFrame([_contrato("164", LOGRADOUROS, "03/12/2020", "02/12/2026")])
    lic = pd.DataFrame([_lic("Contratação de empresa para execução de serviços de limpeza de logradouros públicos "
                             "nas regiões administrativas 01 a 12", "2026-06-01")])
    assert portal.contrato_no_limite_sem_substituta(c, lic, hoje=hoje) == []
    # licitação parecida, mas antiga (a que deu origem ao contrato), não conta
    lic_antiga = pd.DataFrame([_lic(LOGRADOUROS, "2020-08-01")])
    assert [x.regra for x in portal.contrato_no_limite_sem_substituta(c, lic_antiga, hoje=hoje)] == ["R27"]
    outros = pd.DataFrame([
        _contrato("26", "Manutenção e recuperação de vias", "12/03/2025", "02/12/2026"),            # 21 meses
        _contrato("76", "Implantação de passagem em dois níveis", "03/12/2020", "02/12/2026", tipo="OBRAS"),
        _contrato("9", "Poda de árvores", "03/12/2020", "02/12/2026", valor="900000"),               # abaixo do mínimo
        _contrato("8", LOGRADOUROS, "03/12/2020", "02/12/2026", situacao="Encerrado"),
    ])
    assert portal.contrato_no_limite_sem_substituta(outros, pd.DataFrame(), hoje=hoje) == []
