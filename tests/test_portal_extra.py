"""Emendas, obras, diárias e receitas do portal municipal (vigia/coletores/portal_extra.py).

As amostras em tests/amostras/ são respostas reais da API (07/11/2026), colhidas pelo navegador, em
windows-1252 como a prefeitura entrega. Nas diárias, os nomes de servidores foram trocados por fictícios.
Nada aqui acessa a internet: as chamadas passam por tests/sessao_falsa.py.
"""
import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from tests.sessao_falsa import SessaoFalsa
from vigia import qualidade
from vigia.coletores import portal_extra as P
from vigia.coletores import transparencia

AMOSTRAS = Path(__file__).resolve().parent / "amostras"
HOJE = date(2026, 11, 7)
SEM_DADOS = b"Nome\r\nsem dados\r\n"
CSV = {"Content-Type": "text/csv"}


def bruto(nome: str) -> bytes:
    return (AMOSTRAS / nome).read_bytes()


def texto(nome: str) -> str:
    return bruto(nome).decode("windows-1252")


@pytest.fixture
def pasta(tmp_path, monkeypatch):
    destino = tmp_path / "transparencia"
    destino.mkdir()
    monkeypatch.setattr(transparencia, "PASTA", destino)
    monkeypatch.setattr(qualidade, "BRUTOS", tmp_path / "brutos")
    monkeypatch.setattr(qualidade, "PASTA", tmp_path / "qualidade")
    monkeypatch.setattr(qualidade, "REGISTRO", qualidade.Registro())
    monkeypatch.delenv(P.SEGREDO_PSEUDONIMO, raising=False)
    monkeypatch.delenv("VIGIA_COMPLETO", raising=False)
    return destino


def avisos() -> dict[tuple[str, str], str]:
    return {(c.arquivo, c.regra): c.detalhe for c in qualidade.REGISTRO.checagens if not c.ok}


# ---------------------------------------------------------------- emendas

def test_emendas_amostra_real_com_valor_em_reais_e_descricao_em_varias_linhas():
    df = P.ler_emendas(texto("emendas_2024.csv"))
    assert len(df) == 5
    assert list(df.columns) == P.COLUNAS_EMENDAS
    assert df.loc[0, "numero"] == "918257/2021"                    # espaço do fim removido
    assert list(df["valor"]) == ["486104.00", "449950.00", "1051985.00", "200000.00", "249845.00"]
    # a descrição da 3ª emenda tem quebra de linha dentro das aspas
    assert "Nova Rosa da Penha" in df.loc[2, "descricao"] and "perímetro urbano" in df.loc[2, "descricao"]
    assert "\n" not in "".join(df["descricao"])


def test_emendas_quebra_de_linha_fora_de_aspas_nao_cria_registro_fantasma():
    # Um leitor de CSV comum lê 4 registros neste arquivo; são 2 emendas.
    assert len(pd.read_csv(AMOSTRAS / "emendas_2027.csv", encoding="windows-1252", dtype=str)) == 4
    df = P.ler_emendas(texto("emendas_2027.csv"))
    assert len(df) == 2
    assert df.loc[1, "numero"] == "FABIANO CONTARATO"              # defeito da fonte, mantido como veio
    assert df.loc[1, "valor"] == "450000.00"
    assert df.loc[1, "descricao"].startswith("SEMAP Setor Agropecuário")
    assert "caminhão toco caçamba" in df.loc[1, "descricao"]


def test_emendas_casos_dificeis():
    cab = "numero,partido,sigla,Parlamentar,data,destino,beneficiario,valor,Situacao,descricao\r\n"

    def emenda(numero, beneficiario, valor, descricao):
        return f"{numero},PARTIDO X,PX,FULANO,10/03/2024,Prefeitura,{beneficiario},{valor},Paga,{descricao}\r\n"

    df = P.ler_emendas(
        cab
        + emenda("1/2024", "SEMUS", '"R$ 1.000,00"', "Linha um\r\nlinha dois sem vírgula")       # CRLF fora de aspas
        + emenda("2/2024", '"SEMOB - Obras, Habitação"', '"R$ 2.500,50"', '"Praça "Central", Itacibá"')
        + emenda("3/2024", "SEMED", '"R$ 450.000"', "Sem centavos"))
    assert list(df["numero"]) == ["1/2024", "2/2024", "3/2024"]
    assert df.loc[0, "descricao"] == "Linha um linha dois sem vírgula"
    assert df.loc[1, "beneficiario"] == "SEMOB - Obras, Habitação"
    assert df.loc[1, "descricao"] == 'Praça "Central", Itacibá'
    assert list(df["valor"]) == ["1000.00", "2500.50", "450000.00"]


def test_emendas_formato_novo_e_barrado_e_registro_grudado_vira_aviso(pasta):
    with pytest.raises(ValueError, match="colunas diferentes"):
        P.ler_emendas("numero,valor\r\n1,\"R$ 1,00\"\r\n")
    # Campo fixo com quebra de linha: a 2ª emenda gruda na 1ª. A conferência independente avisa.
    t = ("numero,partido,sigla,Parlamentar,data,destino,beneficiario,valor,Situacao,descricao\r\n"
         '1,P,P,FULANO,01/01/2024,Pref,SEMUS,"R$ 1,00",Paga,x\r\n'
         '2,P,P,"BELTRANO\r\nDE TAL",01/01/2024,Pref,SEMUS,"R$ 2,00",Paga,y\r\n')
    df = P.ler_emendas(t)
    P.conferir_contagem_emendas(t, df, "emendas_2024.csv")
    assert len(df) == 1 and ("emendas_2024.csv", "conferencia_de_registros") in avisos()


def test_valor_em_reais():
    assert P.valor_reais("R$ 486.104,00") == "486104.00"
    assert P.valor_reais("R$ 1.051.985") == "1051985.00"
    assert P.valor_reais("R$ -10,50") == "-10.50" == P.valor_reais("-R$ 10,50")
    assert P.valor_reais("") == "" and P.valor_reais("R$ abc") == ""


def rotas_emendas(caminho, params, cab):
    if caminho.endswith("/emendas/anos"):
        return 200, json.loads(bruto("emendas_anos.json")), {}
    ano = int(params["exercicio"])
    if ano in (2024, 2027):
        return 200, bruto(f"emendas_{ano}.csv"), CSV
    if ano in (2025, 2026):
        return 500, bruto("emendas_2025_erro.json"), {"Content-Type": "application/json"}
    return 200, SEM_DADOS, CSV


def test_coleta_de_emendas_registra_defeitos_da_fonte_sem_parar(pasta):
    anterior = pasta / "emendas_2025.csv"
    anterior.write_text("numero,valor\nA,1.00\n", encoding="utf-8")
    s = SessaoFalsa(rotas_emendas)
    P.coletar_emendas(HOJE, s)

    pedidos = sorted(int(p["exercicio"]) for c, p, _ in s.chamadas if c.endswith("/emendas/csv"))
    assert pedidos == [2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026, 2027, 2031]   # 2025/2026 fora da lista
    assert sorted(p.name for p in pasta.glob("emendas_*.csv")) == ["emendas_2024.csv", "emendas_2025.csv",
                                                                   "emendas_2027.csv"]
    assert anterior.read_text(encoding="utf-8") == "numero,valor\nA,1.00\n"      # ano com erro: arquivo intocado
    gravado = pd.read_csv(pasta / "emendas_2024.csv", dtype=str)
    assert len(gravado) == 5 and pd.to_numeric(gravado["valor"]).sum() == pytest.approx(2437884.0)

    a = avisos()
    assert "HTTP 500" in a[("emendas_2025.csv", "erro_na_fonte")] and "An error has occurred" in a[("emendas_2025.csv", "erro_na_fonte")]
    assert "arquivo anterior mantido" in a[("emendas_2025.csv", "erro_na_fonte")]
    assert "nada gravado" in a[("emendas_2026.csv", "erro_na_fonte")]
    assert "2025, 2026" in a[("emendas/anos", "ano_fora_da_lista")]
    assert ("emendas_2027.csv", "ano_no_futuro") in a and ("emendas_2031.csv", "ano_no_futuro") in a
    assert ("emendas_2019.csv", "sem_dados") in a
    assert not qualidade.REGISTRO.bloqueios                       # defeito da fonte é aviso, não bloqueio
    assert (qualidade.BRUTOS / "emendas_2024.csv").read_bytes() == bruto("emendas_2024.csv")   # cru guardado


def test_emendas_sem_nenhum_ano_com_dados_derruba_a_fonte(pasta):
    def rotas(caminho, params, cab):
        if caminho.endswith("/anos"):
            return 200, [{"Valor": 2024, "Nome": 2024}], {}
        return 500, bruto("emendas_2025_erro.json"), {}
    with pytest.raises(RuntimeError, match="nenhum ano"):
        P.coletar_emendas(HOJE, SessaoFalsa(rotas))


# ---------------------------------------------------------------- obras

def test_obras_amostra_real_separa_contrato_e_empresa():
    df = P.ler_obras(texto("obras_2024.csv"))
    assert len(df) == 3
    assert df.loc[0, "ValorContratado"] == "3841444.42" and df.loc[1, "ValorPago"] == "6986556.01"
    assert df.loc[2, "Nome"].endswith("RUA GABINO RIOS, BAIRRO PORTO DE SANTANTA")   # vírgula dentro de aspas
    assert list(df["NumeroContrato"]) == ["083/2023", "037/2024", "023/2024"]
    assert list(df["Empresa"]) == ["EXATA CONSTRUTORA LTDA", "MATIX CONSTRUTORA LTDA - ME", "ARTT ENGENHARIA LTDA."]
    assert df.loc[0, "Contratos"] == "083/2023 - EXATA CONSTRUTORA LTDA"             # original fica
    cols = list(df.columns)
    assert cols.index("NumeroContrato") == cols.index("Contratos") + 1


def test_separar_contrato_so_quando_ha_um_contrato():
    assert P.separar_contrato("083/2023 - EXATA LTDA") == ("083/2023", "EXATA LTDA")
    assert P.separar_contrato("083/2023-EXATA LTDA") == ("083/2023", "EXATA LTDA")
    assert P.separar_contrato("083/2023 - EXATA LTDA; 090/2024 - OUTRA LTDA") == ("", "")
    assert P.separar_contrato("") == ("", "") and P.separar_contrato("Sem contrato") == ("", "")


def test_obras_sem_dados_nunca_apaga_o_arquivo_anterior(pasta):
    assert P.resposta_sem_dados(texto("obras_2026.csv")) and not P.resposta_sem_dados(texto("obras_2024.csv"))
    anterior = pasta / "obras_2026.csv"
    anterior.write_text("Id,Nome,ValorContratado\n1926,OBRA BOA,10.00\n", encoding="utf-8")

    def rotas(caminho, params, cab):
        if caminho.endswith("/obras/anos"):
            return 200, [{"Valor": 2024, "Nome": 2024}, {"Valor": 2026, "Nome": 2026}], {}
        return 200, bruto("obras_2024.csv") if params["exercicio"] == 2024 else bruto("obras_2026.csv"), CSV

    P.coletar_obras(HOJE, SessaoFalsa(rotas))
    assert anterior.read_text(encoding="utf-8") == "Id,Nome,ValorContratado\n1926,OBRA BOA,10.00\n"
    assert "arquivo anterior mantido" in avisos()[("obras_2026.csv", "sem_dados")]
    assert ("obras_2025.csv", "sem_dados") in avisos()
    assert not (pasta / "obras_2025.csv").exists()                # "sem dados" nunca vira tabela vazia
    assert "Empresa" in pd.read_csv(pasta / "obras_2024.csv", dtype=str).columns


def test_ano_com_erro_nao_impede_os_outros_mas_a_fonte_fica_vermelha(pasta):
    def rotas(caminho, params, cab):
        if caminho.endswith("/obras/anos"):
            return 200, [{"Valor": 2024, "Nome": 2024}], {}
        if params["exercicio"] == 2025:
            return 500, b'{"Message": "An error has occurred."}', {}
        return 200, bruto("obras_2024.csv") if params["exercicio"] == 2024 else SEM_DADOS, CSV

    with pytest.raises(RuntimeError, match="obras: falha em 2025"):
        P.coletar_obras(HOJE, SessaoFalsa(rotas))
    assert (pasta / "obras_2024.csv").exists()
    assert "HTTP 500" in avisos()[("obras_2025.csv", "erro_na_fonte")]


# ---------------------------------------------------------------- diárias

def test_diarias_saem_sem_nome_e_sem_cpf():
    df = P.ler_diarias(texto("diarias_2026_ug6.csv"))
    assert "Beneficiario" not in df.columns and "CPFCNPJ" not in df.columns
    assert list(df["IdBeneficiario"]) == ["", "", "", ""]          # sem segredo, sem pseudônimo
    csv_texto = df.to_csv(index=False)
    for pessoal in ("FICTICI", "60.007", "77.317", "00.337"):
        assert pessoal not in csv_texto
    assert list(df["ValorEmpenhado"]) == ["-477.60", "430.00", "430.00", "1910.40"]
    assert df.loc[0, "ValorPago"] == "" and df.loc[0, "Natureza"] == "DIARIAS-PESSOAL CIVIL"


def test_pseudonimo_estavel_com_o_segredo():
    ids = list(P.ler_diarias(texto("diarias_2026_ug6.csv"), sal="segredo-de-teste")["IdBeneficiario"])
    assert all(len(i) == 10 and int(i, 16) >= 0 for i in ids)
    assert ids[2] == ids[3]                                         # a mesma pessoa em duas viagens
    assert len({ids[0], ids[1], ids[2]}) == 3                       # pessoas diferentes
    assert ids == list(P.ler_diarias(texto("diarias_2026_ug6.csv"), sal="segredo-de-teste")["IdBeneficiario"])
    assert ids != list(P.ler_diarias(texto("diarias_2026_ug6.csv"), sal="outro")["IdBeneficiario"])
    s = "segredo"
    assert P.pseudonimo("****00.337**", "Servidor  Fictício C", s) == P.pseudonimo("****00.337**", "SERVIDOR FICTICIO C", s)
    assert P.pseudonimo("12345678901", "FULANO", s) == P.pseudonimo("****56.789**", "FULANO", s)   # CPF inteiro ou não
    assert P.pseudonimo("****00.337**", "FULANO", "") == ""


def rotas_diarias(caminho, params, cab):
    if caminho.endswith("/diarias/anos"):
        return 200, [{"Valor": 2026, "Nome": 2026}], {}
    if params["exercicio"] == 2026 and params["unidadeGestoraId"] == 6:
        return 200, bruto("diarias_2026_ug6.csv"), CSV
    return 200, SEM_DADOS, CSV


def test_coleta_de_diarias_com_o_segredo(pasta, monkeypatch):
    monkeypatch.setenv(P.SEGREDO_PSEUDONIMO, "segredo-de-teste")
    s = SessaoFalsa(rotas_diarias)
    P.coletar_diarias(HOJE, s)
    pedidos = sorted({(p["exercicio"], p["unidadeGestoraId"]) for c, p, _ in s.chamadas if c.endswith("/csv")})
    assert pedidos == [(a, ug) for a in (2025, 2026) for ug in (3, 6, 26)]   # 2019–2024 não estão na lista
    gravado = (pasta / "diarias_2026.csv").read_text(encoding="utf-8")
    assert "FICTICI" not in gravado and "00.337" not in gravado
    assert pd.read_csv(pasta / "diarias_2026.csv", dtype=str, keep_default_na=False)["IdBeneficiario"].str.len().eq(10).all()
    assert ("diarias_2025.csv", "sem_dados") in avisos()
    assert ("diarias", "pseudonimo_sem_segredo") not in avisos()


def test_sem_o_segredo_o_arquivo_com_pseudonimos_nao_e_trocado(pasta):
    anterior = pasta / "diarias_2026.csv"
    anterior.write_text("Ano,Data,ValorEmpenhado,IdBeneficiario\n2026,05/01/2026,1.00,abc123def0\n", encoding="utf-8")
    P.coletar_diarias(HOJE, SessaoFalsa(rotas_diarias))
    assert "abc123def0" in anterior.read_text(encoding="utf-8")
    assert ("diarias", "pseudonimo_sem_segredo") in avisos()
    assert "mantido" in avisos()[("diarias_2026.csv", "pseudonimo_sem_segredo")]


# ---------------------------------------------------------------- receitas

def test_receitas_amostra_real():
    df = P.ler_receitas(texto("receitas_2026_ug6.csv"))
    assert len(df) == 7
    assert df.loc[1, "Nome"] == "IMPOSTOS, TAXAS E CONTRIBUIÇÕES DE MELHORIA"
    assert df.loc[0, "ValorPrevisto"] == "1677734660.00" and df.loc[0, "ValorRealizado"] == "1565129274.63"
    assert df.loc[6, "ValorLancado"] == "0.00"


def receitas(realizado_correntes="900.00"):
    linhas = [("1000000000", "RECEITAS CORRENTES", "1000.00", realizado_correntes),
              ("1100000000", "IMPOSTOS", "500.00", "450.00"),
              ("2000000000", "RECEITAS DE CAPITAL", "200.00", "10.00"),
              ("9000000000", "DEDUÇÕES DA RECEITA", "-100.00", "-80.00")]
    return pd.DataFrame([{"Numero": n, "Nome": nome, "Exercicio": "2026", "ValorPrevisto": p, "ValorLancado": "0.00",
                          "ValorRealizado": r, "UnidadeGestora": "PREFEITURA"} for n, nome, p, r in linhas])


def test_acompanhamento_da_receita_so_topo_e_sem_duplicar_no_mesmo_dia(pasta):
    P.registrar_acompanhamento(receitas(), HOJE)
    df = pd.read_csv(pasta / P.ACOMPANHAMENTO, dtype=str)
    assert list(df["codigo"]) == ["1000000000", "2000000000", "9000000000"]       # 1100000000 não é topo
    linha = df.iloc[0]
    assert linha["fracao_do_ano"] == "0.8521"                                    # 311/365
    assert (linha["previsto"], linha["realizado"]) == ("1000.00", "900.00")
    assert (linha["esperado_pro_rata"], linha["diferenca"]) == ("852.05", "47.95")
    assert list(df.columns) == ["data_coleta", "ano", "unidade", "codigo", "nome", "previsto", "realizado",
                                "fracao_do_ano", "esperado_pro_rata", "diferenca"]

    P.registrar_acompanhamento(receitas("950.00"), HOJE)                         # de novo no mesmo dia
    df = pd.read_csv(pasta / P.ACOMPANHAMENTO, dtype=str)
    assert len(df) == 3 and df.iloc[0]["realizado"] == "950.00"

    P.registrar_acompanhamento(receitas("960.00"), date(2026, 11, 8))           # dia seguinte: linha nova
    df = pd.read_csv(pasta / P.ACOMPANHAMENTO, dtype=str)
    assert len(df) == 6 and sorted(set(df["data_coleta"])) == ["2026-11-07", "2026-11-08"]


def test_coleta_de_receitas_grava_o_ano_e_o_acompanhamento(pasta):
    def rotas(caminho, params, cab):
        if params["exercicio"] == 2026 and params["unidadeGestoraId"] == 6:
            return 200, bruto("receitas_2026_ug6.csv"), CSV
        return 200, SEM_DADOS, CSV

    for _ in range(2):                                            # duas coletas no mesmo dia
        P.coletar_receitas(HOJE, SessaoFalsa(rotas))
    df = pd.read_csv(pasta / "receitas_2026.csv", dtype=str)
    assert len(df) == 7 and set(df["UnidadeGestora"]) == {"PREFEITURA"}
    acomp = pd.read_csv(pasta / P.ACOMPANHAMENTO, dtype=str)
    assert len(acomp) == 1 and acomp.loc[0, "codigo"] == "1000000000" and acomp.loc[0, "data_coleta"] == "2026-11-07"
    assert ("receitas_2019.csv", "sem_dados") in avisos()
    assert not qualidade.REGISTRO.bloqueios


# ---------------------------------------------------------------- integração com o comando

def test_fontes_novas_no_comando_e_falha_isolada(monkeypatch):
    from vigia import __main__ as cli
    assert set(cli.PORTAL_EXTRA) <= set(cli.FONTES)
    assert all(callable(getattr(P, f"coletar_{nome}")) for nome in cli.PORTAL_EXTRA)
    monkeypatch.setattr(qualidade, "REGISTRO", qualidade.Registro())
    monkeypatch.setattr(cli, "ESPERA_SEGUNDA_CHANCE", 0)
    chamadas = []

    def quebra():
        chamadas.append("emendas")
        qualidade.REGISTRO.add(qualidade.Checagem("emendas", "emendas_2026.csv", "erro_na_fonte", False, False, "403"))
        raise RuntimeError("fora do ar")

    monkeypatch.setattr(P, "coletar_emendas", quebra)
    monkeypatch.setattr(P, "coletar_obras", lambda: chamadas.append("obras"))

    class Con:
        def commit(self):
            pass

    falhas = cli.coletar(["emendas", "obras"], {}, Con(), None)
    assert falhas == 1                                            # a falha de uma não derruba a outra
    assert chamadas == ["emendas", "obras", "emendas"]            # e ganha uma segunda tentativa no fim
    assert qualidade.REGISTRO.falhas_fonte == ["emendas"]         # e aparece no relatório de qualidade
    erros = [c for c in qualidade.REGISTRO.checagens if c.regra == "erro_na_fonte"]
    assert len(erros) == 1                                        # sem a checagem repetida da 1ª tentativa


def test_bloqueio_passageiro_do_portal_some_na_segunda_tentativa(monkeypatch):
    """09/11/2026: o portal respondeu 403 a tudo às 7h18 e estava normal à tarde. Uma fonte que funciona
    na segunda tentativa não deixa a execução vermelha nem rastro de erro no relatório de qualidade."""
    from vigia import __main__ as cli
    monkeypatch.setattr(qualidade, "REGISTRO", qualidade.Registro())
    monkeypatch.setattr(cli, "ESPERA_SEGUNDA_CHANCE", 0)
    tentativas = []

    def receitas():
        tentativas.append(1)
        if len(tentativas) == 1:
            qualidade.REGISTRO.add(qualidade.Checagem("receitas", "receitas_2026.csv", "erro_na_fonte", False,
                                                      False, "HTTP 403"))
            raise RuntimeError("receitas: falha em 2026")
        qualidade.REGISTRO.add(qualidade.Checagem("receitas", "receitas_2026.csv", "colunas", True, True, ""))

    monkeypatch.setattr(P, "coletar_receitas", receitas)

    class Con:
        def commit(self):
            pass

    assert cli.coletar(["receitas"], {}, Con(), None) == 0
    assert qualidade.REGISTRO.falhas_fonte == []
    assert not [c for c in qualidade.REGISTRO.checagens if not c.ok]
    assert any(c.regra == "segunda_tentativa" for c in qualidade.REGISTRO.checagens)


def test_fontes_longas_nao_ganham_segunda_tentativa(monkeypatch):
    from vigia import __main__ as cli
    monkeypatch.setattr(qualidade, "REGISTRO", qualidade.Registro())
    monkeypatch.setattr(cli, "ESPERA_SEGUNDA_CHANCE", 0)
    chamadas = []

    def falha(nome, cfg, con, args):
        chamadas.append(nome)
        raise RuntimeError("fora do ar")

    monkeypatch.setattr(cli, "_coletar_fonte", falha)

    class Con:
        def commit(self):
            pass

    assert cli.coletar(["pncp", "tse"], {}, Con(), None) == 2
    assert chamadas == ["pncp", "tse"]
