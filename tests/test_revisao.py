"""Coletores da revisão de 10/11/2026: folha agregada, dívida, Estado, licitações, ISP e CAUC.

Amostras reais da sonda (tests/amostras/ e data/sonda/) ou textos no formato conferido nelas. Nenhum teste
acessa a internet nem escreve nas pastas reais de data/.
"""
import json
import re
from pathlib import Path

import pandas as pd
import pytest

from vigia.coletores import divida, estado, externos, folha, licitacoes, siconfi, transparencia

AMOSTRAS = Path(__file__).parent / "amostras"
SONDA = Path(__file__).parent.parent / "data" / "sonda"


# ---------------------------------------------------------------- licitações

LIC = ("Numero,Processo,Modalidade,Situacao,DataPublicacao,DataAberturaProposta,DataHomologacao,DataInicioSessao,"
       "DataLimiteProposta,DataInicioEntrega,DataAdjudicacao,Comissao,Secretaria,Coronavirus,Objeto,Item,Unidade,"
       "Quantidade,ValorReferencia,ValorTotal,ValorTotalHomologado\n"
       "9/2026,42845/2025,PREGÃO ELETRONICO,Homologação,16/03/2026 00:00:00,,,,,,,AGENTE,Secretaria Municipal de Saúde,"
       "Não,Aquisição de balanças,BALANÇA PLATAFORMA,Unidade,50.0000,9708.6000,485430.000000,218000.00\n"
       "9/2026,42845/2025,PREGÃO ELETRONICO,Homologação,16/03/2026 00:00:00,,,,,,,AGENTE,Secretaria Municipal de Saúde,"
       "Não,Aquisição de balanças,BALANÇA INFANTIL,Unidade,10.0000,1457.0000,14570.000000,218000.00\n"
       "3/2026,100/2026,PREGÃO ELETRONICO,Deserta,,,,,,,,AGENTE,Secretaria Municipal de Obras,Não,Objeto, com vírgula,"
       "ITEM X,Unidade,1.0000,10.0000,10.000000,0\n"
       "9/2026,34178/2025,DISPENSA DE LICITAÇÃO (OUTROS ARTIGOS),Ratificação,,,,,,,,AGENTE,Finanças,Não,CIGA,"
       "CIGA,Unidade,12.0000,3404.7200,40856.640000,182395.80\n"
       "8/2026,5608/2026,ADESAO A ATA,Homologação,,,,,,,,AGENTE,Educação,Não,Ata,ITEM,Unidade,1,5,5,5\n")


def test_licitacoes_quebra_de_linha_no_objeto():
    texto = LIC.replace("Aquisição de balanças,BALANÇA INFANTIL", "Aquisição\r\nde balanças,BALANÇA INFANTIL")
    df = licitacoes.ler(texto)
    assert len(df) == 5 and df.loc[1, "Objeto"] == "Aquisição de balanças"


def test_licitacoes_le_e_resume(tmp_path, monkeypatch):
    df = licitacoes.ler(LIC)
    assert len(df) == 5
    assert df.loc[0, "ValorTotal"] == "485430.00"
    assert df.loc[2, "Objeto"].startswith("Objeto") and df.loc[2, "Item"] == ""   # vírgula a mais: tudo no objeto
    monkeypatch.setattr(transparencia, "PASTA", tmp_path)
    df.to_csv(tmp_path / "licitacoes_2026.csv", index=False)
    r = licitacoes.resumo().iloc[0]
    assert r["processos"] == 4 and r["desertas"] == 1 and r["dispensas_inexigibilidades"] == 1
    assert r["adesoes_a_ata"] == 1
    # estimado do pregão = 485.430 + 14.570 = 500.000; homologado 218.000 -> desconto 56,4%
    assert r["desconto_homologado"] == pytest.approx(1 - 218000 / 500000)
    assert "Licitações da prefeitura" in licitacoes.secao_markdown()


# ---------------------------------------------------------------- folha

NOMINAL = ("Matricula,ServidorNome,ServidorCpf,QuadroNome,LotacaoNome,CargoNome,DataAdmissao,CargaHoraria,PlanoCargos,"
           "Mes,Ano,Rubrica,Valor,Tipo\n"
           "1,PESSOA A,,EFETIVO,ESCOLA,PROFESSOR,01/02/2010,40,PCCS,9,2026,VENCIMENTO,3000.00,Provento\n"
           "1,PESSOA A,,EFETIVO,ESCOLA,PROFESSOR,01/02/2010,40,PCCS,9,2026,INSS, 11%,330.00,Desconto\n"
           "2,PESSOA B,,DESIGNAÇÃO TEMPORÁRIA,ESCOLA,PROFESSOR,15/03/2025,25,DT,9,2026,VENCIMENTO,2000.00,Provento\n"
           "3,PESSOA C,,DESIGNAÇÃO TEMPORÁRIA,ESCOLA,PROFESSOR,10/01/2023,25,DT,9,2026,VENCIMENTO,2100.00,Provento\n")


def test_folha_soma_por_vinculo_sem_pessoa():
    df = folha.somar_nominal(NOMINAL, 2026, 9)
    assert set(df.columns).isdisjoint({"ServidorNome", "ServidorCpf", "Matricula"})
    dt = df[df["vinculo"] == "DESIGNAÇÃO TEMPORÁRIA"].iloc[0]
    assert dt["servidores"] == 2 and dt["tempo_ate_1_ano"] == 0 and dt["tempo_de_1_a_2_anos"] == 1
    assert dt["tempo_de_2_a_5_anos"] == 1 and dt["valor_provento"] == "4100.00"
    ef = df[df["vinculo"] == "EFETIVO"].iloc[0]
    assert ef["servidores"] == 1 and ef["valor_desconto"] == "330.00"   # rubrica com vírgula lida certo
    assert "PESSOA" not in df.to_csv()


def test_folha_cargo_e_meses(tmp_path):
    itens = json.loads((SONDA / "portal_pessoal_cargo_2025_12.json").read_text(encoding="utf-8")) \
        if (SONDA / "portal_pessoal_cargo_2025_12.json").exists() else \
        [{"CargoNome": "PROFESSOR", "cd_CargoServidor": 1, "NumeroServidores": 10, "VencimentoPadrao": 1.5,
          "OutrosVencimentos": 0, "RemuneracaoBruta": 2, "Descontos": 0.5, "RemuneracaoLiquida": 1.5}]
    df = folha.tabela_agregada(itens, folha.CARGO, 2025, 12)
    assert len(df) == len(itens) and df["servidores"].str.fullmatch(r"\d+").all()
    existente = pd.DataFrame({"ano": ["2026", "2026"], "mes": ["1", "2"]})
    from datetime import date
    assert folha.meses_que_faltam(existente, 2026, [1, 2, 3, 4], date(2026, 11, 10)) == [3, 4]
    assert folha.meses_que_faltam(existente, 2025, [1, 2, 3], date(2026, 11, 10)) == [1, 2, 3]


# ---------------------------------------------------------------- dívida

def test_divida_pvl_filtra_cariacica():
    itens = json.loads((AMOSTRAS / "sadipem_pvl_es.json").read_text(encoding="utf-8"))
    df = divida.filtrar_pvl(itens)
    assert len(df) == 2 and set(df["cod_ibge"].astype(str)) == {"3201308"}
    assert df["valor"].str.fullmatch(r"\d+\.\d{2}").all()
    with pytest.raises(ValueError):
        divida.filtrar_pvl(itens + [{"uf": "SC", "cod_ibge": 4211504}])   # filtro de UF ignorado = erro


def test_divida_rgf_por_ano(tmp_path, monkeypatch):
    linhas = json.loads((AMOSTRAS / "rgf_anexo02_cariacica_2025.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(siconfi, "PASTA", tmp_path)
    pd.DataFrame(linhas).to_csv(tmp_path / "rgf_divida.csv", index=False)
    d = divida.divida_por_ano().loc[2025]
    assert d["divida_consolidada"] == pytest.approx(195585130.22)
    assert d["dc_sobre_rcl"] == pytest.approx(195585130.22 / 1589449184.73)
    assert d["divida_liquida"] < 0


# ---------------------------------------------------------------- Estado

def test_estado_transferencias_so_cariacica():
    df = estado.ler_csv((AMOSTRAS / "es_transferencias_2025.csv").read_bytes())
    out = estado.filtrar_transferencias(df)
    assert len(out) == 2 and set(out["NomeMunicipio"]) == {"CARIACICA"}
    assert out.iloc[0]["IcmsTotal"] == "38939082.27"


def test_estado_convenios_sem_banco_e_sem_pessoa_fisica():
    conv = pd.DataFrame([
        {"cod": "1", "nome": "C1", "pessoaBanco": "021", "pessoaAgencia": "0675", "responsavelConvenente": "FULANO",
         "codConcedenteConvenente": "27150549000119", "cnpjConcedenteConvenente": "27150549000119",
         "codIBGEMunicipio": "3201308", "valorConcessao": "100000,00", "valorTotalAditivos": "0,00", "valorContrapartida": "0,00"},
        {"cod": "2", "nome": "C2", "pessoaBanco": "001", "pessoaAgencia": "1", "responsavelConvenente": "X",
         "codConcedenteConvenente": "11111111000191", "cnpjConcedenteConvenente": "11111111000191",
         "codIBGEMunicipio": "3205309", "valorConcessao": "5,00", "valorTotalAditivos": "0,00", "valorContrapartida": "0,00"},
    ])
    out = estado.filtrar_convenios(conv)
    assert list(out["cod"]) == ["1"] and out.iloc[0]["valorConcessao"] == "100000.00"
    assert not any("Banco" in c or "Agencia" in c or "responsavel" in c for c in out.columns)
    pag = pd.DataFrame([
        {"CodigoConvenioConcedido": "1", "Ano": "2025", "ValorPago": "10,00", "ValorRap": "0,00",
         "CpfCnpjNis": "27150549000119", "Favorecido": "PREFEITURA MUNICIPAL DE CARIACICA"},
        {"CodigoConvenioConcedido": "1", "Ano": "2025", "ValorPago": "5,00", "ValorRap": "0,00",
         "CpfCnpjNis": "12345678909", "Favorecido": "PESSOA"},
    ])
    p = estado.filtrar_pagamentos(pag, {"1"})
    assert len(p) == 1 and p.iloc[0]["ValorPago"] == "10.00"


# ---------------------------------------------------------------- ISP e CAUC

def test_cauc_le_situacao():
    texto = ('"Data da Pesquisa: 10/11/2026"\n"Tipo de Ente: Municípios"\n"Abrangência: CNPJ principal"\n'
             '"UF";"Nome do Ente Federado";"Código IBGE";"Código SIAFI";"Região";"População";"Fonte";"1.1";"2.1.1";"3.2.1"\n'
             '"ES";"Cariacica";"3201308";"5663";"SE";"376200";;"30/01/27";"!";"Desabilitado"\n'
             '"ES";"Afonso Cláudio";"3200102";"5601";"SE";"30000";;"!";"!";"!"\n')
    df = externos.ler_cauc(texto)
    assert set(df["cod_ibge"]) == {"3201308"} and df["data_pesquisa"].iloc[0] == "2026-11-10"
    assert df.set_index("item").loc["2.1.1", "pendente"] == "sim"
    assert df.set_index("item").loc["1.1", "pendente"] == "não"


def test_isp_link_e_planilha():
    html = ('<a href="https://x/arquivos/ISP_2024_resultado_final_Revisado.xlsx">a</a>'
            '<a href="https://x/arquivos/resultado-final-isp-2025-_-publicado-em-04_12_2025-1.xlsx">b</a>')
    assert externos.link_isp(html) == (2025, "https://x/arquivos/resultado-final-isp-2025-_-publicado-em-04_12_2025-1.xlsx")
    arq = SONDA / "isp_2025_planilha.xlsx"
    if not arq.exists():
        pytest.skip("planilha da sonda ausente")
    df = externos.ler_isp(arq.read_bytes(), 2025)
    c = df[(df["cod_ibge"] == 3201308) & (df["planilha"] == "RESULTADO")].set_index("indicador")["valor"]
    assert c["INDICADOR DE SITUAÇÃO PREVIDENCIÁRIA"] == "B"
    assert c["CLASSIFICAÇÃO EM FINANÇAS E LIQUIDEZ"] == "C"


# ---------------------------------------------------------------- R29 e R30 (revisão de 12/11/2026)

def _contrato(num, ano, forn, sec, obj, ini, fim, valor, doc="11111111000191"):
    return {"NumeroContrato": num, "AnoContrato": ano, "Fornecedor": forn, "CPFCNPJ": doc, "Secretaria": sec,
            "Objeto": obj, "DataInicio": ini, "DataFinal": fim, "ValorTotal": str(valor), "Situacao": "",
            "TipoContrato": "Serviço", "UnidadeGestora": "6"}


def test_r29_emergencia_previsivel_e_r30_selecao_parada():
    from vigia.alertas import portal as P
    regular = _contrato("126", "2023", "LIMPA SA", "Secretaria Municipal de Educação",
                        "Prestação de serviços contínuos de conservação e limpeza nas escolas",
                        "31/08/2023", "30/08/2026", 83_700_000)
    emerg = _contrato("134", "2026", "NOVA LIMPEZA", "Secretaria Municipal de Educação",
                      "Contratação emergencial de serviços contínuos de limpeza e conservação nas escolas",
                      "31/07/2026", "30/07/2027", 42_250_488, "22222222000191")
    contratos = pd.DataFrame([regular, emerg])
    emergenciais = pd.DataFrame([emerg])
    tarde = pd.DataFrame([{"numero": "46/2026", "modalidade_nome": "PREGÃO", "data_publicacao": "2026-10-13",
                           "objeto": "Serviços contínuos de limpeza e conservação nas escolas",
                           "situacao": "Em Andamento", "secretaria": "Secretaria Municipal de Educação"}])
    a = P.emergencia_previsivel(contratos, emergenciais, tarde)
    assert len(a) == 1 and a[0].regra == "R29" and a[0].gravidade == "alta" and "13/10/2026" in a[0].detalhe
    a_tempo = tarde.assign(data_publicacao="2026-01-10")
    assert P.emergencia_previsivel(contratos, emergenciais, a_tempo) == []        # licitação com 7 meses: sem alerta
    b = P.selecao_parada(tarde, emergenciais, hoje=pd.Timestamp("2027-03-01"))
    assert len(b) == 1 and b[0].regra == "R30" and "46/2026" in b[0].detalhe
    assert P.selecao_parada(tarde, emergenciais, hoje=pd.Timestamp("2026-11-12")) == []   # só 30 dias: cedo
    from vigia.regras import REGRAS
    assert {"R29", "R30"} <= set(REGRAS)


def test_r30_usa_a_situacao_corrigida_por_documento():
    """13/11/2026: o portal mostrava 'Em Andamento' em chamamentos já anulados ou revogados do PA do Trevo."""
    from vigia.alertas import portal as P
    emerg = _contrato("184", "2026", "SANTA CASA X", "Secretaria Municipal de Saúde",
                      "Contratação emergencial de organização social para gerenciamento do pronto atendimento do trevo",
                      "29/10/2026", "28/10/2027", 54_334_515, "33333333000191")
    obj = "Organização social para gerenciamento e operacionalização do pronto atendimento do trevo"
    lic = pd.DataFrame([
        {"numero": "2/2025", "processo": "38654/2024", "modalidade_nome": "CHAMAMENTO PUBLICO",
         "data_publicacao": "2025-03-14", "objeto": obj, "situacao": "Em Andamento", "secretaria": "Saúde"},
        {"numero": "2/2026", "processo": "4830/2026", "modalidade_nome": "CHAMAMENTO PUBLICO",
         "data_publicacao": "2026-07-07", "objeto": obj, "situacao": "Suspensa", "secretaria": "Saúde"}])
    corr = pd.DataFrame([
        {"numero": "2/2025", "processo": "38654/2024", "situacao": "Revogada", "desde": "2025-12-08", "fonte": "x"},
        {"numero": "2/2026", "processo": "4830/2026", "situacao": "Suspensa", "desde": "2026-08-25", "fonte": "y"}])
    hoje = pd.Timestamp("2026-11-13")
    sem = P.selecao_parada(P.aplicar_correcoes(lic, None), pd.DataFrame([emerg]), hoje=hoje)
    assert len(sem) == 1 and "609 dias" in sem[0].titulo          # sem correção: conta a partir de 2025
    com = P.selecao_parada(P.aplicar_correcoes(lic, corr), pd.DataFrame([emerg]), hoje=hoje)
    assert len(com) == 1 and "2/2025" not in com[0].detalhe        # revogada sai da conta
    assert "129 dias" in com[0].titulo and "suspensa desde 25/08/2026" in com[0].titulo
    assert "há 80 dias" in com[0].detalhe


def test_correcoes_de_situacao_tem_fonte_e_data():
    from vigia.alertas.portal import SITUACAO_CORRIGIDA
    c = pd.read_csv(SITUACAO_CORRIGIDA, dtype=str).fillna("")
    assert set(["numero", "processo", "situacao", "desde", "fonte"]) <= set(c.columns)
    assert (c["fonte"].str.startswith("https://")).all() and (c["desde"].str.match(r"\d{4}-\d{2}-\d{2}$")).all()


def test_r31_contrato_sem_pncp():
    from vigia.alertas import portal as P
    c = _contrato("161", "2026", "CARTOES SA", "Secretaria Municipal de Governo", "Gerenciamento de cartões",
                  "22/09/2026", "21/09/2027", 33_600_000, "33333333000144")
    c["ValorContratado"] = "33600000"; c["DataAssinatura"] = "22/09/2026"
    publicado = dict(c, NumeroContrato="70", CPFCNPJ="44444444000155", Fornecedor="OUTRA SA")
    uso = dict(c, NumeroContrato="103", CPFCNPJ="55555555000166", Objeto="Autorização de uso do imóvel")
    contratos = pd.DataFrame([c, publicado, uso])
    pncp = pd.DataFrame([{"ni_fornecedor": "44444444000270", "numero": "70", "ano": "2026",   # filial: mesma raiz
                          "valor_inicial": "1", "valor_global": "1"}])
    a = P.contrato_sem_pncp(contratos, pd.DataFrame(), pncp, hoje=pd.Timestamp("2026-11-12"))
    assert [(x.regra, x.referencia) for x in a] == [("R31", "contrato 161/2026")]
    assert "Nenhum contrato desse fornecedor" in a[0].detalhe
    assert P.contrato_sem_pncp(contratos, pd.DataFrame(), pncp, hoje=pd.Timestamp("2026-10-01")) == []  # < 30 dias


# ---------------------------------------------------------------- fila de espera (sem dado pessoal)

def _planilha_fila(titulo, datas):
    import io
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = titulo
    ws.append(["Procedimentos a serem realizados", "Tempo médio de espera (em dias)"])
    ws.append(["Consultas Especializadas", 74])
    ws.append(["* nota da prefeitura"])
    ws.append([])
    ws.append(["Código de Solicitação", "Data da solicitação", "Unidade solicitante", "Data Nascimento",
               "Idade do paciente", "Nome do cidadão", "Sexo dos incritos", "ITEM AGENDAMENTO *2/*3",
               "Canal de contato e esclarecimento", "Prioridade", "Orgão executor "])
    itens = ["CONSULTA EM NEUROLOGIA PEDIATRIA METROPOLITANA", "GRUPO TOMOGRAFIA COMPUTADORIZADA METROPOLITANA"]
    for i, d in enumerate(datas):
        # pares: criança nascida em 2018 (a planilha diz 70 anos: coluna de idade embaralhada, como a oficial)
        # ímpares: idosa nascida em 1950 (a planilha diz 8). As linhas 0 e 2 são a mesma pessoa.
        crianca = i % 2 == 0
        ws.append([1000 + i, d, "CARIACICA - US ALTO LAGE", "15/03/2018" if crianca else "01/01/1950",
                   70 if crianca else 8, "FULANA DE TESTE DA SILVA" if crianca else "BELTRANA DE TESTE", "F",
                   itens[i % 2], "Ouvidoria", "MUITO ALTA" if i == 0 else "MEDIA", "SESA"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_fila_soma_sem_nome_e_detecta_formato_de_data(tmp_path, monkeypatch):
    import datetime as dt
    from vigia.coletores import fila
    # setembro: datas de verdade (Excel); julho: texto mês/dia/ano (como as planilhas do Google)
    mes, df = fila.ler_planilha(_planilha_fila("SETEMBRO 2026", [dt.datetime(2025, 9, 30), dt.datetime(2026, 9, 1),
                                                                 dt.datetime(2024, 9, 30)]))
    assert mes == "2026-09" and list(df.columns) == ["data", "unidade", "idade", "idade_planilha", "item",
                                                     "prioridade", "pessoa"]
    assert list(df["idade"]) == [8, 76, 8]                            # pela data de nascimento, não pela coluna
    resumo, esp, uni = fila.resumir(df, mes)
    assert resumo["pedidos"] == 3 and resumo["pessoas"] == 2 and resumo["procedimentos"] == 2
    assert resumo["mais_de_1_ano"] == 1 and resumo["criancas_ate_12"] == 2 and resumo["idosos_60_mais"] == 1
    assert resumo["idade_planilha_confere_pct"] == 0 and resumo["sem_idade"] == 0
    assert resumo["neuro_pediatria_pedidos"] == 2 and resumo["neuro_pediatria_pessoas"] == 1
    assert resumo["neuro_pediatria_ate_5_anos"] == 0 and resumo["muito_alta_pedidos"] == 1
    assert set(esp["procedimento"]) == {"CONSULTA EM NEUROLOGIA PEDIATRIA", "GRUPO TOMOGRAFIA COMPUTADORIZADA"}
    assert list(uni["unidade_solicitante"]) == ["US ALTO LAGE"]
    texto = df.drop(columns="pessoa").to_csv() + esp.to_csv() + uni.to_csv() + str(resumo)
    for pessoal in ("FULANA", "BELTRANA", "1950", "2018", *df["pessoa"]):
        assert pessoal not in texto                                   # nome, nascimento e impressão digital não saem
    mes2, df2 = fila.ler_planilha(_planilha_fila("Planilha1", ["6/30/2026", "7/15/2026", "1/2/2025"]))
    assert mes2 == "2026-07" and df2["data"].max() == pd.Timestamp(2026, 7, 15)   # 7/15 só pode ser mês/dia

    html = ('<a href="https://cariacica.es.gov.br/uploads/files/x/fila-de-consultas/set/Transparencia-SET-2026.xlsx">'
            'Setembro</a><a href="https://docs.google.com/spreadsheets/d/AbC-1_x/edit?usp=sharing&amp;x=1">Agosto</a>'
            '<a href="https://drive.google.com/file/d/ZzZ9/view?usp=sharing">Maio</a><a href="/x.pdf">PDF</a>')
    assert fila.links(html) == [
        "https://cariacica.es.gov.br/uploads/files/x/fila-de-consultas/set/Transparencia-SET-2026.xlsx",
        "https://docs.google.com/spreadsheets/d/AbC-1_x/export?format=xlsx",
        "https://drive.google.com/uc?export=download&id=ZzZ9"]

    conteudo = _planilha_fila("SETEMBRO 2026", [dt.datetime(2026, 9, 1)] * 4)

    class R:
        def __init__(self, c, t=""):
            self.content, self.text = c, t
        def raise_for_status(self):
            pass

    class S:
        def get(self, url, **_):
            return R(b"", html) if "pagina" in url else (R(b"%PDF") if url.endswith("ZzZ9") else R(conteudo))

    monkeypatch.setattr(fila, "PASTA", tmp_path)
    monkeypatch.setattr(fila, "RESUMO", tmp_path / "fila_resumo_mensal.csv")
    monkeypatch.setattr(fila, "ARQUIVOS", tmp_path / "arquivos.csv")
    monkeypatch.setattr(fila, "LINKS", tmp_path / "links.csv")
    # um mês antigo, ainda da conta velha (idade pela coluna embaralhada): perde crianças e idosos
    pd.DataFrame([{"mes": "2026-08", "pedidos": 9, "criancas_ate_12": 5, "idosos_60_mais": 2}]).to_csv(
        tmp_path / "fila_resumo_mensal.csv", index=False)
    fila.coletar(hoje=dt.date(2026, 11, 12), s=S())
    res = pd.read_csv(tmp_path / "fila_resumo_mensal.csv", dtype=str, keep_default_na=False).set_index("mes")
    assert res.loc["2026-08", "criancas_ate_12"] == "" and res.loc["2026-09", "pessoas"] == "2"
    assert "Transparencia-SET-2026.xlsx" in (tmp_path / "links.csv").read_text()

    class Bloqueado(S):                                   # o site da prefeitura recusa o GitHub: usa os links salvos
        def get(self, url, **kw):
            if "pagina" in url:
                raise RuntimeError("403 Client Error: Forbidden")
            return super().get(url, **kw)
    (tmp_path / "arquivos.csv").unlink()
    fila.coletar(hoje=dt.date(2026, 11, 13), s=Bloqueado())
    assert (tmp_path / "arquivos.csv").exists()
    tudo = "".join(p.read_text() for p in tmp_path.glob("*.csv"))
    # a impressão digital (sha256) do arquivo muda a cada execução e às vezes contém "1950" ou "2018" por acaso
    # (falhou assim no GitHub em 13/11/2026): tira os hashes antes de procurar ano de nascimento
    tudo = re.sub(r"\b[0-9a-f]{64}\b", "", tudo)
    assert "FULANA" not in tudo and "BELTRANA" not in tudo and "1950" not in tudo and "2018" not in tudo
    assert "pessoa," not in tudo.split("\n")[0]                      # a impressão digital não vira coluna
    assert (tmp_path / "fila_especialidade_2026-09.csv").exists() and "2026-09" in fila.secao_markdown()

    # crescimento comparável: procedimento novo no último mês não infla a conta
    base = pd.read_csv(tmp_path / "fila_resumo_mensal.csv").iloc[0]
    pd.DataFrame([{**base, "mes": "2026-05", "pedidos": 100}, {**base, "mes": "2026-09", "pedidos": 150}]).to_csv(
        tmp_path / "fila_resumo_mensal.csv", index=False)
    for m, linhas in {"2026-05": [("A", 60), ("B", 40)], "2026-09": [("A", 70), ("B", 50), ("NOVO", 30)]}.items():
        pd.DataFrame([{"mes": m, "procedimento": a, "pedidos": q, "mediana_dias_espera": 1, "mais_de_1_ano": 0}
                      for a, q in linhas]).to_csv(tmp_path / f"fila_especialidade_{m}.csv", index=False)
    c = fila.comparavel()
    assert c["procedimentos_comuns"] == 2 and (c["comum_de"], c["comum_ate"]) == (100, 120)
    assert round(c["cresc_total"], 2) == 0.5 and round(c["cresc_comum"], 2) == 0.2
    assert "+20,0%" in fila.secao_markdown() and "+50,0%" in fila.secao_markdown()


def test_placar_de_resultados(tmp_path, monkeypatch):
    from vigia import pedidos
    monkeypatch.setattr(pedidos, "RESULTADOS", tmp_path / "resultados.csv")
    assert "Nenhum resultado ainda" in pedidos.secao_resultados()
    pd.DataFrame([{"data": "2026-12-05", "campanha": "fila", "tipo": "correção da prefeitura",
                   "o_que_mudou": "Planilha da fila republicada sem nome", "fonte": "https://cariacica.es.gov.br",
                   "pedido": ""}]).to_csv(tmp_path / "resultados.csv", index=False)
    assert "1 resultado(s)" in pedidos.secao_resultados()


def test_r32_licitacao_presencial():
    from vigia.alertas import portal as P
    lic = pd.DataFrame([
        {"id_pncp": "27150549000119-1-000128/2026", "cnpj_orgao": "27150549000119", "ano": "2026", "sequencial": "128",
         "numero_compra": "22", "modalidade_nome": "Concorrência - Presencial", "valor_estimado": "163270000",
         "data_publicacao": "2026-06-09", "data_abertura": "2026-06-10", "objeto": "Contratação integrada de obras"},
        {"id_pncp": "27150549000119-1-000234/2026", "cnpj_orgao": "27150549000119", "ano": "2026", "sequencial": "234",
         "numero_compra": "26", "modalidade_nome": "Concorrência - Presencial", "valor_estimado": "27557157",
         "data_publicacao": "2026-11-03", "data_abertura": "2027-02-12", "objeto": "Contratação integrada"},
        {"id_pncp": "x", "cnpj_orgao": "27150549000119", "ano": "2026", "sequencial": "9", "numero_compra": "9",
         "modalidade_nome": "Concorrência - Eletrônica", "valor_estimado": "9000000", "data_publicacao": "2026-03-01",
         "data_abertura": "2026-03-02", "objeto": "Obra"}])
    k = pd.DataFrame([{"id_pncp_compra": "27150549000119-1-000128/2026", "valor_global": "161308707.84",
                       "nome_fornecedor": "CONSORCIO TESTE", "ni_fornecedor": "11111111000191"}])
    a = P.licitacao_presencial(lic, k, hoje=pd.Timestamp("2026-11-12"))
    assert [(x.regra, x.gravidade) for x in a] == [("R32", "alta"), ("R32", "media")]
    assert "1,2%" in a[0].detalhe and "art. 164" in a[1].detalhe


def test_links_da_fila_sem_endereco_de_teste():
    """os links de exemplo dos testes não podem vazar para a lista real que o robô baixa."""
    from pathlib import Path
    arquivo = Path("data/fila/links.csv")   # fora do git público desde 24/11/2026; só existe durante a coleta
    texto = arquivo.read_text() if arquivo.exists() else ""
    for falso in ("/files/x/", "AbC-1_x", "id=ZzZ9"):
        assert falso not in texto


def test_situacao_pelos_documentos_do_pncp():
    """O aviso de suspensão do chamamento 2/2026 estava anexado no PNCP com a compra ainda 'Divulgada'."""
    from vigia.alertas import portal as P
    comp = pd.DataFrame([
        {"id_pncp": "27150549000119-1-000176/2026", "cnpj_orgao": "27150549000119", "ano": "2026",
         "sequencial": "176", "processo": "4830/2026"},
        {"id_pncp": "27150549000119-1-000061/2025", "cnpj_orgao": "27150549000119", "ano": "2025",
         "sequencial": "61", "processo": "38654/2024"},
        {"id_pncp": "27150549000119-1-000099/2025", "cnpj_orgao": "27150549000119", "ano": "2025",
         "sequencial": "99", "processo": "1/2025"}])
    arq = pd.DataFrame([
        {"id_pncp": "27150549000119-1-000176/2026", "sequencial": "1", "data_publicacao": "2026-07-17",
         "titulo": "Edital de Chamamento Publico 0022026", "ativo": "1"},
        {"id_pncp": "27150549000119-1-000176/2026", "sequencial": "4", "data_publicacao": "2026-08-27",
         "titulo": "Publicacao do Aviso de Suspensao", "ativo": "1"},
        {"id_pncp": "27150549000119-1-000061/2025", "sequencial": "2", "data_publicacao": "2025-05-12",
         "titulo": "EDITAL DE CHAMAMENTO PUBLICO", "ativo": "1"},
        {"id_pncp": "27150549000119-1-000099/2025", "sequencial": "1", "data_publicacao": "2025-03-01",
         "titulo": "Aviso de suspensão", "ativo": "1"},
        {"id_pncp": "27150549000119-1-000099/2025", "sequencial": "2", "data_publicacao": "2025-04-01",
         "titulo": "Republicação do edital com nova data", "ativo": "1"}])
    s = P.situacao_pelos_documentos(comp, arq)
    assert list(s["processo"]) == ["4830/2026"]                     # retomada desfaz a suspensão; edital não prova nada
    r = s.iloc[0]
    assert r["situacao"] == "Suspensa" and r["desde"] == "2026-08-27"
    assert r["fonte"] == "https://pncp.gov.br/app/editais/27150549000119/2026/176"
    lic = pd.DataFrame([{"numero": "2/2026", "processo": "4830/2026", "modalidade_nome": "CHAMAMENTO PUBLICO",
                         "data_publicacao": "2026-07-07", "objeto": "x", "situacao": "Em Andamento", "secretaria": "S"}])
    out = P.aplicar_correcoes(lic, s)
    assert out.iloc[0]["situacao"] == "Suspensa" and out.iloc[0]["situacao_desde"] == "2026-08-27"
    manual = pd.DataFrame([{"numero": "2/2026", "processo": "4830/2026", "situacao": "Suspensa",
                            "desde": "2026-08-25", "fonte": "https://x"}])
    assert P.aplicar_correcoes(out, manual).iloc[0]["situacao_desde"] == "2026-08-25"   # a conferida manda


def test_data_do_pncp_nao_vira_data_do_ato_e_documentos_contraditorios_nao_provam():
    """Em 26/03/2026 o PNCP recebeu de uma vez o aviso de suspensão e o edital republicado de vários pregões. A data
    de envio não é a data do ato, e suspensão + republicação no mesmo dia não provam situação nenhuma."""
    from vigia.alertas import portal as P
    comp = pd.DataFrame([
        {"id_pncp": "A", "cnpj_orgao": "27150549000119", "ano": "2026", "sequencial": "33", "processo": "10/2026",
         "numero_compra": "005", "situacao": "Divulgada no PNCP"},
        {"id_pncp": "B", "cnpj_orgao": "27150549000119", "ano": "2026", "sequencial": "50", "processo": "11/2026",
         "numero_compra": "008", "situacao": "Divulgada no PNCP"}])
    arq = pd.DataFrame([
        {"id_pncp": "A", "sequencial": "1", "data_publicacao": "2026-03-26", "titulo": "AVISO_DE_SUSPENS_O.pdf", "ativo": "1"},
        {"id_pncp": "B", "sequencial": "1", "data_publicacao": "2026-03-26", "titulo": "AVISO SUSPENSAO PE 0082026", "ativo": "1"},
        {"id_pncp": "B", "sequencial": "2", "data_publicacao": "2026-03-26", "titulo": "EDITAL REPUBLICADO", "ativo": "1"}])
    s = P.situacao_pelos_documentos(comp, arq)
    assert list(s["processo"]) == ["10/2026"] and s.iloc[0]["tipo_data"] == "pncp"
    lic = pd.DataFrame([{"numero": "5/2026", "processo": "10/2026", "modalidade_nome": "PREGAO ELETRONICO",
                         "data_publicacao": "2026-03-26", "objeto": "limpeza e higienizacao das unidades de saude",
                         "situacao": "Em Andamento", "secretaria": "Saude"}])
    lic = P.aplicar_correcoes(lic, s)
    assert lic.iloc[0]["situacao_tipo_data"] == "pncp"
    emerg = pd.DataFrame([{"NumeroContrato": "62", "AnoContrato": "2026", "CPFCNPJ": "1", "Fornecedor": "EMPRESA X",
                           "ValorTotal": "13500000", "DataInicio": "24/03/2026", "DataFinal": "23/03/2027",
                           "Objeto": "limpeza e higienizacao das unidades de saude", "UnidadeGestora": "Saude"}])
    a = P.selecao_parada(lic, emerg, hoje=pd.Timestamp("2026-11-13"))
    assert len(a) == 1
    assert "aviso de suspensão enviado ao PNCP em 26/03/2026" in a[0].detalhe
    assert "desde 26/03/2026" not in a[0].titulo + a[0].detalhe
    # a correção conferida à mão continua dizendo "desde" (data do ato)
    manual = pd.DataFrame([{"numero": "5/2026", "processo": "10/2026", "situacao": "Suspensa", "desde": "2026-04-02",
                            "fonte": "https://x"}])
    b = P.selecao_parada(P.aplicar_correcoes(lic, manual), emerg, hoje=pd.Timestamp("2026-11-13"))
    assert "suspensa desde 02/04/2026" in b[0].titulo


def test_coletor_guarda_os_documentos_das_compras_sem_resultado():
    import sqlite3
    from vigia import db as DB
    from vigia.coletores import pncp
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript(DB.ESQUEMA)
    hoje = pd.Timestamp.today()
    for idp, mod, hom in (("27150549000119-1-000176/2026", 12, None),     # chamamento sem resultado: entra
                          ("27150549000119-1-000227/2026", 8, None),      # dispensa: fica de fora
                          ("27150549000119-1-000010/2026", 6, 1000.0)):   # pregão homologado: fica de fora
        con.execute("INSERT INTO contratacoes (id_pncp, modalidade_id, valor_homologado, data_publicacao, alvo) "
                    "VALUES (?,?,?,?,1)", (idp, mod, hom, f"{hoje - pd.Timedelta(days=100):%Y-%m-%d}"))
    urls = []
    class Cli:
        def get(self, url, **kw):
            urls.append((url, kw.get("usar_cache")))
            return 200, [{"sequencialDocumento": 4, "dataPublicacaoPncp": "2026-08-27T10:00:00",
                          "titulo": "Publicacao do Aviso de Suspensao", "tipoDocumentoNome": "Outros Documentos",
                          "statusAtivo": True}]
    n = pncp.coletar_arquivos_compras(Cli(), con, {"apis": {"pncp": "https://pncp.gov.br/api/pncp"}})
    assert n == 1 and urls == [("https://pncp.gov.br/api/pncp/v1/orgaos/27150549000119/compras/2026/176/arquivos",
                                False)]
    r = con.execute("SELECT * FROM arquivos_compra").fetchone()
    assert r["titulo"] == "Publicacao do Aviso de Suspensao" and r["data_publicacao"] == "2026-08-27"


def test_processo_com_ponto_e_situacao_do_proprio_pncp():
    from vigia.alertas import portal as P
    comp = pd.DataFrame([{"id_pncp": "27150549000119-1-000184/2026", "cnpj_orgao": "27150549000119", "ano": "2026",
                          "sequencial": "184", "processo": "23.790/2026", "situacao": "Suspensa"}])
    s = P.situacao_pelos_documentos(comp, None)                     # sem documento: vale a situação do PNCP, sem data
    assert s.iloc[0]["situacao"] == "Suspensa" and s.iloc[0]["desde"] == "" and s.iloc[0]["processo"] == "23790/2026"
    lic = pd.DataFrame([{"numero": "46/2026", "processo": "23790/2026", "modalidade_nome": "PREGÃO ELETRONICO",
                         "data_publicacao": "2026-10-13", "objeto": "x", "situacao": "Em Andamento", "secretaria": "E"}])
    assert P.aplicar_correcoes(lic, s).iloc[0]["situacao"] == "Suspensa"


def test_r30_nao_junta_secretarias_diferentes():
    """A emergência da portaria da Administração (119/2025) não é substituída pelo pregão da portaria da Saúde (39/2025)."""
    from vigia.alertas import portal as P
    lic = pd.DataFrame([{"numero": "39/2025", "processo": "31112/2025", "modalidade_nome": "PREGÃO ELETRONICO",
                         "data_publicacao": "2025-10-17", "objeto": "servicos de portaria com fornecimento de mao de obra",
                         "situacao": "Suspensa", "secretaria": "Secretaria Municipal de Saúde",
                         "situacao_desde": "", "situacao_fonte": "", "situacao_tipo_data": ""}])
    emerg = pd.DataFrame([{"NumeroContrato": "119", "AnoContrato": "2025", "CPFCNPJ": "1", "Fornecedor": "EMPRESA X",
                           "ValorTotal": "1590074.88", "DataInicio": "01/12/2025", "DataFinal": "30/11/2026",
                           "Objeto": "servicos de portaria com fornecimento de mao de obra",
                           "Secretaria": "Secretaria Municipal de Administração", "UnidadeGestora": "Adm"}])
    assert P.selecao_parada(lic, emerg, hoje=pd.Timestamp("2026-11-13")) == []
    emerg.loc[0, "Secretaria"] = "Secretaria Municipal de Saúde"
    assert len(P.selecao_parada(lic, emerg, hoje=pd.Timestamp("2026-11-13"))) == 1


def test_emergenciais_completados_pelo_objeto_do_contrato():
    """A lista oficial não tem 2023; o 153/2023 do PA do Trevo diz "em caráter emergencial" no objeto."""
    from vigia.alertas import portal as P
    of = pd.DataFrame([{"NumeroContrato": "116", "AnoContrato": "2024", "CPFCNPJ": "10.779.749/0001-32",
                        "Objeto": "Contratação emergencial de entidade"}])
    contr = pd.DataFrame([
        {"NumeroContrato": "116", "AnoContrato": "2024", "CPFCNPJ": "10.779.749/0001-32", "Objeto": "Contratação emergencial de entidade"},
        {"NumeroContrato": "153", "AnoContrato": "2023", "CPFCNPJ": "10.779.749/0001-32",
         "Objeto": "contratação em caráter emergencial de entidade para o PA do Trevo"},
        {"NumeroContrato": "10", "AnoContrato": "2023", "CPFCNPJ": "1", "Objeto": "atendimento de urgência e emergência (SAMU)"}])
    t = P.completar_emergenciais(of, contr)
    assert sorted(t["NumeroContrato"]) == ["116", "153"]
    assert t.set_index("NumeroContrato").loc["153", "OrigemEmergencia"].startswith("objeto do contrato")


def test_r33_empenho_depois_do_fim_do_contrato():
    """Pagamento depois do fim (PA do Trevo, 5066/2026) alerta; reserva para contrato que começa no dia seguinte e
    resto a pagar de empenho feito dentro da vigência não alertam."""
    from vigia.alertas import portal as P
    contr = pd.DataFrame([
        {"NumeroContrato": "99", "AnoContrato": "2025", "CPFCNPJ": "73.027.690/0001-46", "DataInicio": "28/10/2025",
         "DataFinal": "27/10/2026", "Objeto": "x"},
        {"NumeroContrato": "85", "AnoContrato": "2022", "CPFCNPJ": "10.779.749/0001-32", "DataInicio": "13/05/2022",
         "DataFinal": "02/11/2023", "Objeto": "x"},
        {"NumeroContrato": "153", "AnoContrato": "2023", "CPFCNPJ": "10.779.749/0001-32", "DataInicio": "09/11/2023",
         "DataFinal": "27/10/2024", "Objeto": "x"}])
    base = {"NomeFornecedor": "ENTIDADE", "NumeroProcesso": "1/2026", "NaturezaDespesa": "CONTRATO DE GESTÃO",
            "Descricao": "x"}
    pag = pd.DataFrame([
        {**base, "CpfCnpjFornecedor": "73.027.690/0001-46", "Data": "10/11/2026 00:00:00", "NumeroEmpenho": "5066/2026",
         "ValorPago": "2208655.16", "NumeroContrato": "Não informado"},
        {**base, "CpfCnpjFornecedor": "73.027.690/0001-46", "Data": "02/10/2026 00:00:00", "NumeroEmpenho": "131/2026",
         "ValorPago": "3915389.03", "NumeroContrato": "99 /2025"},
        {**base, "CpfCnpjFornecedor": "10.779.749/0001-32", "Data": "08/11/2023 00:00:00", "NumeroEmpenho": "3270/2023",
         "ValorPago": "3700000", "NumeroContrato": "153 /2023"}])
    a = P.empenho_depois_do_contrato(pag, contr, pd.DataFrame())
    assert [(x.regra, x.gravidade, x.referencia) for x in a] == [("R33", "alta", "empenho 5066/2026")]
    assert "14 dias depois do fim do contrato 99/2025, sem número de contrato" in a[0].titulo


def test_todo_csv_publicado_abre_no_pandas():
    """A guarda final da coleta lê o CSV do último commit; um CSV malformado derruba a coleta inteira (13/11/2026:
    vírgula sem aspas num CSV de caso)."""
    raiz = Path(__file__).resolve().parents[1] / "data"
    ruins = []
    for p in sorted(raiz.rglob("*.csv")):
        if "sonda" in p.parts:
            continue
        try:
            pd.read_csv(p, dtype=str, keep_default_na=False)
        except Exception as e:  # noqa: BLE001
            ruins.append(f"{p.relative_to(raiz)}: {e}")
    assert not ruins, ruins
