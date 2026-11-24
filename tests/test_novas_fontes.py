"""TCE-ES (receita/despesa mensal) e indicador de arrecadação, com dados no formato real."""
import io
import zipfile

import pandas as pd
import pytest

from vigia import indicadores, qualidade
from vigia.coletores import tcees
from tests.sessao_falsa import SessaoFalsa

CAB_REC = ("Ano;Mes;CodigoUnidadeGestora;UnidadeGestora;EsferaAdministrativa;ClassificacaoReceita;CodigoCategoria;"
           "NomeCategoria;CodigoOrigem;NomeOrigem;CodigoEspecie;NomeEspecie;CodigoRubrica;NomeRubrica;CodigoAlinea;"
           "NomeAlinea;CodigoSubAlinea;NomeSubAlinea;CodigoDetalhamentoNivel1;NomeDetalhamentoNivel1;"
           "CodigoDetalhamentoNivel2;NomeDetalhamentoNivel2;CodigoDetalhamentoNivel3;NomeDetalhamentoNivel3;"
           "CodigoTipoDetalhamento;NomeTipoDetalhamento;CodigoGrupo;NomeGrupo;CodigoFonteReduzida;NomeFonteReduzida;"
           "CodigoDetalhamento;NomeDetalhamento;PrevisaoInicial;PrevisaoAtualizada;Arrecadada;PrevisaoInicialFUNDEB;"
           "PrevisaoAtualizadaFUNDEB;ArrecadadaFUNDEB")


def linha_rec(ano, mes, esfera, fonte, prev, arrec):
    campos = [str(ano), str(mes), "017E06", "Secretaria de Finanças", esfera, "11180111"] + ["x"] * 22 + \
             [fonte, "RECURSOS NÃO VINCULADOS", "0000", "X", prev, "0,00", arrec, "0,00", "0,00", "0,00"]
    return ";".join(campos)


def zip_de(texto: str, cod="latin-1") -> bytes:
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("municipios-receitas.csv", texto.encode(cod))
    return b.getvalue()


def test_tcees_le_zip_latin1_e_filtra_cariacica():
    texto = "\n".join([CAB_REC, linha_rec(2026, 1, "Cariacica", "500", "1.000,00", "80,50"),
                       linha_rec(2026, 1, "Vitória", "500", "9,00", "9,00")])
    df = tcees.preparar(tcees.ler_zip(zip_de(texto)), "receitas")
    assert len(df) == 1 and df.iloc[0]["Arrecadada"] == "80.50" and df.iloc[0]["PrevisaoInicial"] == "1000.00"


def test_tcees_coluna_faltando_falha_alto():
    with pytest.raises(ValueError):
        tcees.preparar(pd.DataFrame({"EsferaAdministrativa": ["Cariacica"], "Ano": ["2026"]}), "receitas")


def _grava_receitas(pasta, ano, meses, valor, previsao, fonte="500", classificacao="11125011", extra=()):
    linhas = [{"Ano": str(ano), "Mes": str(m), "ClassificacaoReceita": classificacao, "CodigoFonteReduzida": fonte,
               "PrevisaoInicial": f"{previsao if m == 1 else 0:.2f}", "PrevisaoAtualizada": "0.00",
               "Arrecadada": f"{valor:.2f}"} for m in meses]
    pd.DataFrame(linhas + list(extra)).to_csv(pasta / "tcees" / f"receitas_{ano}.csv", index=False)


def test_indicador_de_arrecadacao(tmp_path, monkeypatch):
    monkeypatch.setattr(indicadores, "DADOS", tmp_path)
    (tmp_path / "tcees").mkdir()
    intra = {"Ano": "2026", "Mes": "9", "ClassificacaoReceita": "72150011", "CodigoFonteReduzida": "800",
             "PrevisaoInicial": "0.00", "PrevisaoAtualizada": "0.00", "Arrecadada": "999999.00"}   # contribuição ao IPC
    _grava_receitas(tmp_path, 2025, range(1, 13), 100.0, 1200.0)   # 1.200 no ano
    _grava_receitas(tmp_path, 2026, range(1, 10), 120.0, 1000.0, extra=[intra])   # 9 meses a 120 (+20%)
    r = indicadores.arrecadacao(2026)
    assert r["ate_mes"] == 9 and r["arrecadado"] == 1080 and r["arrecadado_ano_anterior_mesmo_periodo"] == 900
    assert r["variacao"] == pytest.approx(0.2)
    assert r["projecao_no_ritmo_do_ano_anterior"] == pytest.approx(1440)
    assert r["excesso_projetado"] == pytest.approx(440)
    assert indicadores.arrecadacao(2026, fonte=None)["arrecadado"] == 1080      # intraorçamentária fora
    texto = indicadores.secao_markdown(2026)
    assert "Arrecadação de 2026" in texto and "não conferiu com o RREO" in texto   # sem RREO: dotação omitida


def test_indicador_nunca_quebra_e_usa_o_ano_anterior_em_janeiro(tmp_path, monkeypatch):
    monkeypatch.setattr(indicadores, "DADOS", tmp_path)
    (tmp_path / "tcees").mkdir()
    assert indicadores.secao_markdown(2026) == ""                                # nada baixado
    _grava_receitas(tmp_path, 2026, range(1, 3), 50.0, 100.0, fonte="600")      # sem nenhuma linha da fonte 500
    assert indicadores.arrecadacao(2026) is None and indicadores.secao_markdown(2026) == ""
    _grava_receitas(tmp_path, 2024, range(1, 13), 100.0, 1200.0)
    _grava_receitas(tmp_path, 2025, range(1, 13), 110.0, 1300.0)
    assert "Arrecadação de 2025" in indicadores.secao_markdown(2026)           # 2026 sem fonte livre: usa 2025


def test_indicador_mesmo_mes_nas_duas_colunas(tmp_path, monkeypatch):
    monkeypatch.setattr(indicadores, "DADOS", tmp_path)
    (tmp_path / "tcees").mkdir()
    outubro = {"Ano": "2026", "Mes": "10", "ClassificacaoReceita": "17115011", "CodigoFonteReduzida": "540",
               "PrevisaoInicial": "0.00", "PrevisaoAtualizada": "0.00", "Arrecadada": "70.00"}  # outra fonte já em outubro
    _grava_receitas(tmp_path, 2025, range(1, 13), 100.0, 1200.0)
    _grava_receitas(tmp_path, 2026, range(1, 10), 120.0, 1000.0, extra=[outubro])
    assert indicadores.mes_comum(2026) == 9
    assert indicadores.arrecadacao(2026, fonte=None, mes=9)["arrecadado"] == 1080   # outubro não entra


def _grava_dotacao(pasta, leitura):
    """Despesa com LOA de 1.000 (800 na fonte 500) e +100 de crédito em março; RREO com a mesma conta."""
    linhas = []
    for m in range(1, 5):
        for fonte, ini, cred in (("500", 800.0, 100.0), ("540", 200.0, 0.0)):
            if leitura == "ultimo_mes":
                atual = ini + (cred if m >= 3 else 0)
            else:
                atual = (ini if m == 1 else 0) + (cred if m == 3 else 0)
            linhas.append({"Ano": "2026", "Mes": str(m), "CodigoFonteReduzida": fonte,
                           "PrevisaoInicial": f"{ini if m == 1 else 0:.2f}", "PrevisaoAtualizada": f"{atual:.2f}",
                           "Empenhada": "1.00", "Liquidada": "1.00", "Paga": "1.00"})
    pd.DataFrame(linhas).to_csv(pasta / "tcees" / "despesas_2026.csv", index=False)
    (pasta / "siconfi").mkdir(exist_ok=True)
    rreo = [{"exercicio": "2026", "periodo": str(b), "cod_ibge": "3201308", "anexo": "RREO-Anexo 01",
             "cod_conta": "SubtotalDasDespesas", "coluna": col, "valor": str(v)}
            for b, atu in ((1, 1000.0), (2, 1100.0)) for col, v in (("DOTAÇÃO INICIAL (d)", 1000.0),
                                                                     ("DOTAÇÃO ATUALIZADA (e)", atu))]
    pd.DataFrame(rreo).to_csv(pasta / "siconfi" / "rreo_balanco_orcamentario.csv", index=False)


@pytest.mark.parametrize("leitura", ["ultimo_mes", "soma"])
def test_aumento_da_dotacao_so_quando_confere_com_o_rreo(tmp_path, monkeypatch, leitura):
    monkeypatch.setattr(indicadores, "DADOS", tmp_path)
    (tmp_path / "tcees").mkdir()
    _grava_dotacao(tmp_path, leitura)
    assert indicadores.leitura_validada(2026) == (leitura, 4)
    assert indicadores.aumento_dotacao(2026) == pytest.approx(100)              # fonte 500
    assert indicadores.aumento_dotacao(2026, fonte=None) == pytest.approx(100)
    r = pd.read_csv(tmp_path / "siconfi" / "rreo_balanco_orcamentario.csv", dtype=str)
    r.loc[r["coluna"].str.startswith("DOTAÇÃO ATUALIZADA"), "valor"] = "5000"  # RREO diz outra coisa
    r.to_csv(tmp_path / "siconfi" / "rreo_balanco_orcamentario.csv", index=False)
    assert indicadores.aumento_dotacao(2026) is None


def catalogo(recursos):
    return {"success": True, "result": {"resources": recursos}}


def test_tcees_catalogo_so_zip_com_um_ano_e_ano_repetido_e_erro():
    rec = [{"name": "Receitas 2025", "url": "https://x/r2025.zip", "format": "ZIP", "last_modified": "2026-10-01T00:00"},
           {"name": "Dicionário de dados 2025", "url": "https://x/dic.pdf", "format": "PDF"},
           {"name": "Atualização 2026 - receitas 2025", "url": "https://x/a.zip", "format": "ZIP"},
           {"name": "Receitas 2026", "url": "https://x/r2026.zip", "format": ""}]
    s = SessaoFalsa(lambda caminho, params, cab: (200, catalogo(rec), {}))
    r = tcees.recursos_por_ano(s, "receitas-municipios")
    assert sorted(r) == [2025, 2026] and r[2025]["modificado"] == "2026-10-01T00:00" and r[2026]["modificado"] == ""
    rec.append({"name": "Receitas 2026 (cópia)", "url": "https://x/c.zip", "format": "ZIP"})
    with pytest.raises(ValueError, match="dois ZIPs"):
        tcees.recursos_por_ano(s, "receitas-municipios")


def test_tcees_so_baixa_o_que_falta_ou_mudou(tmp_path, monkeypatch):
    monkeypatch.setattr(tcees, "PASTA", tmp_path)
    for ano in (2020, 2021, 2025):
        (tmp_path / f"receitas_{ano}.csv").write_text("x")
    rec = {2020: {"modificado": "a"}, 2021: {"modificado": "b"}, 2022: {"modificado": "c"},
           2025: {"modificado": ""}, 2026: {"modificado": ""}}
    estado = {("receitas", 2020): "a", ("receitas", 2021): "velho"}
    from datetime import date
    assert tcees.anos_para_baixar("receitas", rec, date(2026, 11, 7), estado) == [2021, 2022, 2025, 2026]   # sem data: anos recentes


def test_tcees_zip_com_dois_csv_falha():
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("a.csv", "x")
        z.writestr("b.csv", "y")
    with pytest.raises(ValueError, match="2 CSVs"):
        tcees.ler_zip(b.getvalue())


def test_tcees_coleta_completa_com_falhas_isoladas(tmp_path, monkeypatch):
    """Ano certo grava; ano errado no arquivo não grava; ano corrente vazio em fevereiro é só aviso; ZIP
    quebrado não derruba os outros anos, mas a coleta termina com erro. O ZIP nacional não é guardado."""
    from datetime import date
    monkeypatch.setattr(tcees, "PASTA", tmp_path)
    monkeypatch.setattr(tcees, "RECURSOS", tmp_path / "recursos.csv")
    monkeypatch.setattr(qualidade, "REGISTRO", qualidade.Registro())
    monkeypatch.setattr(qualidade, "BRUTOS", tmp_path / "brutos")
    def zip_rec(ano, esfera="Cariacica"):
        return zip_de("\n".join([CAB_REC, linha_rec(ano, 1, esfera, "500", "10,00", "5,00")]))
    arquivos = {"/r2025.zip": zip_rec(2025), "/r2026.zip": zip_rec(2026, "Vitória"),
                "/r2024.zip": zip_rec(2023), "/r2023.zip": b"isto nao e zip"}
    rec = [{"name": f"Receitas {a}", "url": f"https://x/r{a}.zip", "format": "ZIP", "last_modified": f"m{a}"}
           for a in (2023, 2024, 2025, 2026)]
    def rotas(caminho, params, cab):
        if caminho.endswith("package_show"):
            return 200, catalogo(rec if params["id"] == "receitas-municipios" else []), {}
        return 200, arquivos[caminho], {}
    with pytest.raises(RuntimeError, match="receitas 2023"):
        tcees.coletar(hoje=date(2026, 2, 10), s=SessaoFalsa(rotas))
    assert sorted(p.name for p in tmp_path.glob("receitas_*.csv")) == ["receitas_2025.csv"]
    assert not (tmp_path / "brutos").exists()                                   # ZIP nacional não fica guardado
    regras = {(c.arquivo, c.regra, c.bloqueante) for c in qualidade.REGISTRO.checagens if not c.ok}
    assert ("receitas_2024.csv", "ano_confere", True) in regras
    assert ("receitas_2026.csv", "ano_sem_dados_ainda", False) in regras
    assert ("receitas_2023.csv", "erro_na_fonte", False) in regras
    assert {m["arquivo_bruto"] for m in qualidade.REGISTRO.manifesto} >= {"tcees_receitas_2025.zip"}
    est = pd.read_csv(tmp_path / "recursos.csv", dtype=str)
    assert list(est["ano"]) == ["2025"] and list(est["modificado"]) == ["m2025"]   # só o que gravou


def test_receita_conferida_com_o_rreo(tmp_path, monkeypatch):
    monkeypatch.setattr(indicadores, "DADOS", tmp_path)
    (tmp_path / "tcees").mkdir()
    (tmp_path / "siconfi").mkdir()
    _grava_receitas(tmp_path, 2026, range(1, 6), 100.0, 1000.0)                 # jan–mai, 100 por mês
    def rreo(valor_b2):
        pd.DataFrame([{"exercicio": "2026", "periodo": "2", "cod_ibge": "3201308", "anexo": "RREO-Anexo 01",
                       "cod_conta": "ReceitasExcetoIntraOrcamentarias", "coluna": "Até o Bimestre (c)",
                       "valor": str(valor_b2)}]).to_csv(tmp_path / "siconfi" / "rreo_balanco_orcamentario.csv", index=False)
    rreo(400.0)                                                                  # jan–abr = 400
    c = indicadores.conferencia_receita(2026)
    assert (c["bimestre"], c["tcees"], c["ok"]) == (2, 400.0, True)
    rreo(500.0)
    assert indicadores.conferencia_receita(2026)["ok"] is False
