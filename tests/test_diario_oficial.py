from vigia.coletores.diario_oficial import CAMPOS, contar

TEXTO = (
    "DECRETO Nº 424 ABRE O CRÉDITO SUPLEMENTAR NO VALOR DE R$ 17.330,00 PARA O FIM QUE ESPECIFICA. "
    "DECRETO Nº 426 ABRE O CRÉDITO SUPLEMENTAR NO VALOR DE R$ 3.876.605,07. "
    "EXTRATO DO 2º TERMO ADITIVO. Dispensa de licitação nº 12. Inexigibilidade nº 3. "
    "Contratação emergencial. Adesão à Ata de Registro de Preços 080/2026. "
    "Fulano de Tal, Secretário Municipal."
)


def test_conta_atos_e_soma_creditos():
    r = contar(TEXTO)
    assert r["creditos_qtd"] == 2
    assert r["creditos_valor"] == "3893935.07"
    assert r["aditivo"] == 1 and r["dispensa"] == 1 and r["inexigibilidade"] == 1
    assert r["emergencia"] == 1 and r["carona_em_ata"] == 1


def test_nenhum_texto_sai_so_numeros():
    r = contar(TEXTO)
    assert all(isinstance(v, int) or v.replace(".", "").isdigit() for v in r.values())
    assert "Fulano" not in str(r)
    assert set(r) | {"edicao", "data", "link"} == set(CAMPOS)
