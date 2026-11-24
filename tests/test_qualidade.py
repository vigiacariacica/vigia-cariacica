"""A camada de qualidade precisa barrar download ruim e registrar dado antigo alterado."""
import pandas as pd
import pytest

from vigia import qualidade
from vigia.coletores.transparencia import OBRIGATORIAS_PAGAMENTO


@pytest.fixture(autouse=True)
def registro_limpo(monkeypatch):
    monkeypatch.setattr(qualidade, "REGISTRO", qualidade.Registro())


def pag(n, valor=100.0, id_inicial=1):
    return pd.DataFrame({
        "IdEmpenho": [str(id_inicial + i) for i in range(n)],
        "Data": ["02/01/2025 00:00:00"] * n,
        "ValorEmpenhado": [f"{valor:.2f}"] * n,
        "CpfCnpjFornecedor": ["27.320.787/0001-25"] * (n - 1) + ["****47.207**"],
    })


def validar(novo, antigo, fechado=False):
    return qualidade.validar_tabela(novo, antigo, fonte="t", arquivo="pagamentos_2025.csv",
                                    obrigatorias=OBRIGATORIAS_PAGAMENTO, coluna_total="ValorEmpenhado",
                                    ano=2025, ano_fechado=fechado)


def test_download_normal_passa():
    assert qualidade.aprovado(validar(pag(1000), pag(990)))


def test_download_cortado_e_barrado():
    assert not qualidade.aprovado(validar(pag(500), pag(1000)))


def test_total_que_cai_e_barrado():
    assert not qualidade.aprovado(validar(pag(1000, valor=50), pag(1000, valor=100)))


def test_registro_fantasma_e_barrado():
    ruim = pd.concat([pag(500), pd.DataFrame([{"IdEmpenho": "", "Data": "", "ValorEmpenhado": "",
                                               "CpfCnpjFornecedor": ""}])], ignore_index=True)
    chs = validar(ruim, pd.DataFrame())
    assert not qualidade.aprovado(chs)
    assert any(c.regra == "formato_IdEmpenho" and not c.ok for c in chs)


def test_ano_fechado_alterado_e_registrado_sem_bloquear():
    chs = validar(pag(1001), pag(1000), fechado=True)
    assert qualidade.aprovado(chs)
    assert len(qualidade.REGISTRO.alteracoes) == 1
    assert qualidade.REGISTRO.alteracoes[0]["linhas_depois"] == 1001


def test_conciliacao_portal_siconfi():
    pagamentos = pd.DataFrame({"Ano": ["2024", "2024"], "ValorEmpenhado": ["600", "400"]})
    dca = pd.DataFrame({
        "cod_ibge": ["3201308", "3201308", "3201308"],
        "exercicio": ["2024"] * 3,
        "coluna": ["Despesas Empenhadas", "Despesas Empenhadas", "Despesas Pagas"],
        "conta": ["Despesas Exceto Intraorçamentárias", "Despesas Intraorçamentárias",
                  "Despesas Exceto Intraorçamentárias"],
        "valor": ["990", "20", "900"],
    })
    c = qualidade.conciliar_siconfi(pagamentos, dca, "3201308")
    assert c.loc[0, "siconfi_empenhado"] == 1010 and bool(c.loc[0, "ok"])


def test_guarda_conta_registros_e_nao_quebras_de_linha():
    com_quebra = b'id,nome\n1,"FLORA\r\nSERVICOS"\n2,X\n'
    limpo = b'id,nome\n1,FLORA SERVICOS\n2,X\n'
    assert qualidade.contar_registros(com_quebra) == qualidade.contar_registros(limpo) == 2


def test_origem_da_mudanca_pelo_hash_do_arquivo_cru():
    r = qualidade.REGISTRO
    r.hash_anterior.update({"a.csv": "h1", "b.csv": "h1", "c.csv": None})
    r.hash_atual.update({"a.csv": "h1", "b.csv": "h2", "c.csv": "h3"})
    assert qualidade.origem_da_mudanca(["a.csv"]).startswith("nosso leitor")
    assert qualidade.origem_da_mudanca(["b.csv"]).startswith("prefeitura")
    assert qualidade.origem_da_mudanca(["c.csv"]).startswith("a verificar")


def test_compra_externa_sem_resposta_nao_derruba_o_pncp(monkeypatch):
    """PNCP fora do ar numa compra externa: registra, para depois de 3 seguidas e não levanta exceção."""
    import sqlite3
    from vigia.coletores import pncp
    from vigia.http import LimiteDeTentativas
    monkeypatch.setattr(qualidade, "REGISTRO", qualidade.Registro())
    con = sqlite3.connect(":memory:")
    con.executescript("""CREATE TABLE orgaos (cnpj TEXT, alvo INT); CREATE TABLE contratacoes (id_pncp TEXT);
                         CREATE TABLE contratos (cnpj_orgao TEXT, id_pncp_compra TEXT);
                         INSERT INTO orgaos VALUES ('27150549000119', 1);""")
    for i in range(5):
        con.execute("INSERT INTO contratos VALUES ('27150549000119', ?)", (f"03008926000111-1-{i + 1:06d}/2025",))
    chamadas = []
    class Cli:
        tentativas = 6
        def get(self, url):
            chamadas.append((url, self.tentativas))
            raise LimiteDeTentativas(url)
    cli = Cli()
    n = pncp.coletar_compras_externas(cli, con, {"apis": {"pncp": "https://pncp.gov.br/api/pncp"}})
    assert n == 0 and len(chamadas) == 3                      # parou depois de 3 seguidas
    assert all(t == 3 for _, t in chamadas)                   # cada compra externa tenta só 3 vezes
    assert cli.tentativas == 6                                # e o cliente volta ao normal para o resto
    assert any("compras externas: 3 sem resposta" in f for f in qualidade.REGISTRO.falhas_fonte)
