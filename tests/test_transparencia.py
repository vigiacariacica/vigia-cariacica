"""Testes do leitor do portal municipal, com o formato real (e malformado) dos CSVs."""
from vigia.coletores.transparencia import INICIO_CONTRATO, INICIO_DESPESA, decimal_br, ler_csv_malformado

CABECALHO = (
    "Ano,ValorOrcado,ValorAutorizado,ValorReservado,ValorEmpenhado,ValorLiquidado,ValorPago,"
    "CodUnidadeOrcamentaria,UnidadeOrcamentaria,CodUnidadeGestora,UnidadeGestora,CodOrgao,Orgao,"
    "CodFuncao,Funcao,CodSubFuncao,SubFuncao,CodPrograma,Programa,CodAcao,Acao,CodFonte,Fonte,"
    "CpfCnpjFornecedor,NumeroProcesso,NumeroContrato,CodNaturezaDespesa,NaturezaDespesa,NomeFornecedor,"
    "Data,IdEmpenho,Licitacao,Descricao,NumeroEmpenho"
)
FIXOS = (',,,,"{v}","{v}","{v}",,,204,SECRETARIA MUNICIPAL DE ADMINISTRAÇÃO,020400,SEMAD,04,ADMINISTRAÇÃO,122,'
         'ADMINISTRAÇÃO GERAL,0027,Apoio Administrativo PMC,20156,Manutenção de Unidade,1.500.0000.0000,'
         'RECURSOS ORDINÁRIOS,{doc},35109/2013,Não informado,33903600 ,OUTROS SERV DE TERC-PES.FISICA   ,'
         '{nome},02/01/2025 00:00:00,{id},Não informado,')

# Linha 2 tem aspas soltas e quebra de linha na descrição: é o que quebra leitores comuns.
CSV_DESPESAS = (
    CABECALHO + "\r\n"
    + "2025" + FIXOS.format(v="21165,44", doc="****47.207**", nome="SEBASTIÃO JARETTA", id=389503)
    + '"Contrato 016/2014, locação do imóvel, Cariacica-ES.",1/2025\r\n'
    + "2025" + FIXOS.format(v="1234567,89", doc="27.320.787/0001-25", nome="FORTE AMBIENTAL EIRELI", id=389504)
    + '"Coleta de lixo "lote 2\r\nreferente a jan, fev",2/2025\r\n'
    + "2025" + FIXOS.format(v="10,00", doc="08.583.394/0001-60", nome="GLOBO LTDA", id=389505)
    + 'Sem aspas, com vírgula,3/2025\r\n'
    # Descrição com quebra de linha seguida de "2025, ...": já gerou registro fantasma em 2023
    + "2025" + FIXOS.format(v="99,00", doc="11.111.111/0001-11", nome="X LTDA", id=389506)
    + '"Pagamento referente ao exercício de\r\n2025, segunda parcela",4/2025\r\n'
)

CSV_CONTRATOS = (
    "NumeroContrato,AnoContrato,TipoContrato,Processo,AnoProcesso,ValorContratado,Aditivo,ValorTotal,CPFCNPJ,"
    "Fornecedor,Secretaria,Fiscal,DataInicio,DataFinal,DataPublicacao,DataAssinatura,Situacao,Coronavirus,Objeto,"
    "Prioritario\r\n"
    '135,2025,Serviço,41708,2025,"729712,50",0,"729712,50",03.354.844/0001-29,MINDWORKS INFORMATICA LTDA,'
    'Secretaria Municipal de Finanças,,23/12/2025,22/12/2026,30/12/2025,23/12/2025,Normal,False,'
    '"Contratação emergencial de antivírus.\r\n",Sim\r\n'
    '119,2025,Serviço,35978,2025,"1482238,32","107836,56","1590074,88",52.592.357/0001-00,FORTH VIX LTDA,'
    'Secretaria Municipal de Administração,,01/12/2025,30/11/2026,01/12/2025,28/11/2025,Normal,False,'
    '"Contratação de "vigilância",Não\r\n'
)


def test_decimal_br():
    assert decimal_br("21165,44") == "21165.44"
    assert decimal_br("1.234,50") == "1234.50"
    assert decimal_br("0") == "0.00"
    assert decimal_br("") == "" and decimal_br("-") == ""


def test_despesas_malformadas_viram_um_registro_por_empenho():
    df = ler_csv_malformado(CSV_DESPESAS, INICIO_DESPESA)
    assert len(df) == 4
    assert list(df["IdEmpenho"]) == ["389503", "389504", "389505", "389506"]
    assert list(df["ValorPago"]) == ["21165.44", "1234567.89", "10.00", "99.00"]
    assert "segunda parcela" in df.loc[3, "Descricao"] and df.loc[3, "NumeroEmpenho"] == "4/2025"
    assert df.loc[1, "NomeFornecedor"] == "FORTE AMBIENTAL EIRELI"
    assert "lote 2" in df.loc[1, "Descricao"] and "jan, fev" in df.loc[1, "Descricao"]
    assert df.loc[2, "Descricao"] == "Sem aspas, com vírgula"
    assert list(df["NumeroEmpenho"]) == ["1/2025", "2/2025", "3/2025", "4/2025"]
    assert df.loc[0, "NaturezaDespesa"] == "OUTROS SERV DE TERC-PES.FISICA"


def test_contratos_com_objeto_quebrado():
    df = ler_csv_malformado(CSV_CONTRATOS, INICIO_CONTRATO)
    assert len(df) == 2
    assert df.loc[1, "ValorContratado"] == "1482238.32"
    assert df.loc[1, "Aditivo"] == "107836.56"
    assert df.loc[1, "Prioritario"] == "Não"
    assert df.loc[0, "Objeto"].startswith("Contratação emergencial")
