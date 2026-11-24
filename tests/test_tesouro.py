"""Transferências da União aos municípios (Tesouro Transparente): VAAR e VAAT do Fundeb."""
import pandas as pd
import pytest

from tests.sessao_falsa import SessaoFalsa
from vigia import qualidade
from vigia.coletores import tesouro as T

CAB = "Município;UF;ANO;Mês;1º Decêndio;2º Decêndio;3º Decêndio;Item transferência;Transferência;\n"


def csv_mes(ano, mes, vaar=True, extra=""):
    linhas = [f"Cariacica;ES;{ano};{mes:02d};0;0;7988960.97;COUN VAAT;FUNDEB;",
              f"Cariacica;ES;{ano};{mes:02d};100.50;200;300;FPM;FPM;",
              f"Vitória;ES;{ano};{mes:02d};0;0;1000;COUN VAAT;FUNDEB;",
              f"Cariacica;MG;{ano};{mes:02d};0;0;5;COUN VAAR;FUNDEB;",          # outra UF, mesmo nome: fora
              f"Acrelândia;AC;{ano};{mes:02d};759016.49;165675.66;506191.3;FPM;FPM;"]
    if vaar:
        linhas.append(f"Cariacica;ES;{ano};{mes:02d};0;0;912873.65;COUN VAAR;FUNDEB;")
    return (CAB + "\n".join(linhas) + "\n" + extra).encode("latin-1")


@pytest.fixture
def pasta(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "PASTA", tmp_path)
    monkeypatch.setattr(T, "SAIDA", tmp_path / "transferencias.csv")
    monkeypatch.setattr(T, "RECURSOS", tmp_path / "recursos.csv")
    monkeypatch.setattr(qualidade, "REGISTRO", qualidade.Registro())
    return tmp_path


def catalogo(recursos):
    return {"success": True, "result": {"resources": recursos}}


def rec(nome, arquivo, modificado="2026-10-05T10:00:00"):
    return {"id": arquivo, "name": nome, "url": f"https://www.tesourotransparente.gov.br/ckan/x/download/{arquivo}",
            "last_modified": modificado}


def test_le_so_as_cidades_da_grande_vitoria_e_soma_os_decendios():
    df = T.ler_csv(csv_mes(2026, 3))
    assert set(df["municipio"]) == {"Cariacica", "Vitória"}
    fpm = df[(df["municipio"] == "Cariacica") & (df["item"] == "FPM")]
    assert fpm["valor"].tolist() == ["600.50"] and fpm["mes"].tolist() == ["03"]
    assert not ((df["municipio"] == "Cariacica") & (df["valor"] == "5.00")).any()   # Cariacica de MG ficou fora


def test_coleta_baixa_novos_e_modificados_e_o_mes_vem_do_conteudo(pasta):
    arquivos = {"transferenciamensalmunicipios202501.csv.csv": csv_mes(2025, 1),
                "transferenciamensalmunicipios202602.csv.csv": csv_mes(2026, 2, vaar=False)}
    recursos = [rec("Transferencia_Mensal_Municipios_202502.csv", "transferenciamensalmunicipios202501.csv.csv"),
                rec("Transferencia_Mensal_Municipios_202602.csv", "transferenciamensalmunicipios202602.csv.csv"),
                rec("Transferencia_Mensal_Municipios_201902.csv", "transferenciamensalmunicipios201902.csv.csv")]

    def rotas(caminho, params, cab):
        if caminho.endswith("package_show"):
            return 200, catalogo(recursos), {}
        return 200, arquivos[caminho.split("/")[-1]], {}

    s = SessaoFalsa(rotas)
    assert T.coletar(s=s) == 2                                         # 2019 fica de fora (antes de ANO_INICIAL)
    df = pd.read_csv(T.SAIDA, dtype=str)
    assert set(zip(df["ano"], df["mes"])) == {("2025", "01"), ("2026", "02")}   # o nome dizia 202502; o arquivo é jan
    assert len(qualidade.REGISTRO.manifesto) == 2
    s.chamadas.clear()
    assert T.coletar(s=s) == 0 and len(s.chamadas) == 1               # nada novo: só o catálogo
    recursos[1]["last_modified"] = "2026-11-01T10:00:00"               # arquivo republicado
    assert T.coletar(s=s) == 1


def test_arquivo_quebrado_nao_derruba_os_outros(pasta):
    recursos = [rec("a_202601.csv", "a202601.csv"), rec("b_202602.csv", "b202602.csv")]

    def rotas(caminho, params, cab):
        if caminho.endswith("package_show"):
            return 200, catalogo(recursos), {}
        if caminho.endswith("a202601.csv"):
            return 200, b"coluna;errada\n1;2\n", {}
        return 200, csv_mes(2026, 2), {}

    with pytest.raises(RuntimeError, match="1 arquivo"):
        T.coletar(s=SessaoFalsa(rotas))
    assert pd.read_csv(T.SAIDA, dtype=str)["mes"].unique().tolist() == ["02"]
    assert any(c.regra == "erro_na_fonte" for c in qualidade.REGISTRO.checagens)


def test_secao_do_relatorio_pergunta_quando_o_vaar_some(pasta):
    partes = [T.ler_csv(csv_mes(2024, m)) for m in (3, 4)] + [T.ler_csv(csv_mes(2026, m, vaar=False)) for m in (1, 2)]
    pd.concat(partes).to_csv(T.SAIDA, index=False)
    t = T.complementacao_fundeb()
    assert t.set_index("ano").loc["2024", "meses_com_vaar"] == 2
    assert t.set_index("ano").loc["2026", "VAAR"] == 0
    md = T.secao_markdown()
    assert "| 2026 (até 02) |" in md and "não recebeu VAAR em 2026" in md and "art. 14" in md


def test_arquivo_em_centavos_e_convertido():
    """O arquivo de 10/2024 (mês 09) veio sem separador decimal: '134712203' quer dizer R$ 1.347.122,03."""
    txt = (CAB + "Cariacica;ES;2024;09;556088055;98901889;328529722;FPM;FPM;\n"
           "Cariacica;ES;2024;09;0;0;134712203;AJUSTE FUNDEB VAAR;AJUSTE FUNDEB;\n").encode("latin-1")
    df = T.ler_csv(txt).set_index("item")
    assert df.loc["AJUSTE FUNDEB VAAR", "valor"] == "1347122.03"
    assert df.loc["FPM", "valor"] == "9835196.66"


def test_mes_sem_complementacao_no_arquivo_vira_aviso(pasta):
    partes = [T.ler_csv(csv_mes(2024, m)) for m in (7, 9)]
    sem = T.ler_csv(csv_mes(2024, 8, vaar=False))
    sem = sem[~sem["item"].str.contains("VAA")]                       # agosto veio sem as complementações
    pd.concat(partes + [sem]).to_csv(T.SAIDA, index=False)
    t = T.complementacao_fundeb().set_index("ano")
    assert t.loc["2024", "sem_complementacao"] == "08/2024"
    assert "08/2024" in T.secao_markdown() and "abaixo do real" in T.secao_markdown()
