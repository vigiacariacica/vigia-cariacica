"""Mundo FICTÍCIO para testar o sistema. Nenhum nome, CNPJ ou valor aqui é real.

Cada caso foi montado para disparar uma regra específica (ou para NÃO disparar).
"""
IBGE = "9900001"          # Município Exemplo (alvo)
IBGE_A, IBGE_B = "9900002", "9900004"   # vizinhos
IBGE_CONS = "9900003"     # consórcio (fora do "ES" fictício)

PREF = "99000000000101"
FUNDO = "99000000000202"
CONS = "99000000000303"
VIZ_A = "99000000000404"
VIZ_B = "99000000000505"

ALFA = "10000000000101"   # fornecedor normal
BETA = "20000000000202"   # sobrepreço, empresa nova, capital baixo, sócio = servidor
GAMA = "30000000000303"   # dispensas fracionadas, MEI
DELTA = "40000000000404"  # aditivos acima do limite, sancionada, concentração
EPSI = "50000000000505"   # sócio e telefone em comum com BETA

ORG = {
    PREF: ("MUNICIPIO EXEMPLO", IBGE, "Município Exemplo", "M"),
    FUNDO: ("FUNDO MUNICIPAL DE SAUDE DE EXEMPLO", IBGE, "Município Exemplo", "M"),
    CONS: ("CONSORCIO PUBLICO INTERMUNICIPAL FICTICIO", IBGE_CONS, "Cidade do Consórcio", "M"),
    VIZ_A: ("MUNICIPIO VIZINHO A", IBGE_A, "Vizinho A", "M"),
    VIZ_B: ("MUNICIPIO VIZINHO B", IBGE_B, "Vizinho B", "M"),
}

FORN_NOMES = {ALFA: "ALFA ALIMENTOS FICTICIA LTDA", BETA: "BETA COMERCIO FICTICIO LTDA",
              GAMA: "GAMA SERVICOS FICTICIOS", DELTA: "DELTA CONSTRUCOES FICTICIAS SA",
              EPSI: "EPSILON DISTRIBUIDORA FICTICIA LTDA"}


def _orgao(cnpj):
    nome, ibge, mun, esfera = ORG[cnpj]
    return ({"cnpj": cnpj, "razaoSocial": nome, "poderId": "E", "esferaId": esfera},
            {"codigoUnidade": "1", "nomeUnidade": "UNIDADE " + nome[:20], "codigoIbge": ibge,
             "municipioNome": mun, "ufSigla": "XX"})


def compra(cnpj, ano, seq, modalidade, objeto, data, estimado, homologado, amparo=None, srp=False):
    org, un = _orgao(cnpj)
    return {
        "numeroControlePNCP": f"{cnpj}-1-{seq:06d}/{ano}", "anoCompra": ano, "sequencialCompra": seq,
        "numeroCompra": str(seq), "processo": f"PROC-{seq}/{ano}", "modalidadeId": modalidade,
        "modalidadeNome": {4: "Concorrência - Eletrônica", 6: "Pregão - Eletrônico", 8: "Dispensa"}[modalidade],
        "situacaoCompraNome": "Divulgada no PNCP", "objetoCompra": objeto, "srp": srp,
        "amparoLegal": {"nome": amparo or "Lei 14.133/2021, Art. 28, I", "descricao": ""},
        "valorTotalEstimado": estimado, "valorTotalHomologado": homologado,
        "dataPublicacaoPncp": data + "T10:00:00", "dataAberturaProposta": data + "T09:00:00",
        "orgaoEntidade": org, "unidadeOrgao": un, "linkSistemaOrigem": "https://exemplo.invalid/compra",
    }


def item(n, desc, qtd, unid, vu, tem=True, ms="M"):
    return {"numeroItem": n, "descricao": desc, "materialOuServico": ms, "quantidade": qtd, "unidadeMedida": unid,
            "valorUnitarioEstimado": vu, "valorTotal": vu * qtd, "situacaoCompraItemNome": "Homologado",
            "criterioJulgamentoNome": "Menor preço", "temResultado": tem, "catalogoCodigoItem": None}


def resultado(n, forn, qtd, vu, data):
    return {"numeroItem": n, "sequencialResultado": 1, "niFornecedor": forn, "tipoPessoa": "PJ",
            "nomeRazaoSocialFornecedor": FORN_NOMES.get(forn, "OUTRA EMPRESA FICTICIA"),
            "quantidadeHomologada": qtd, "valorUnitarioHomologado": vu, "valorTotalHomologado": qtd * vu,
            "percentualDesconto": 0, "dataResultado": data, "porteFornecedorNome": "ME/EPP"}


def contrato(cnpj, ano, seq, compra_id, forn, objeto, vi, assin, vig_fim, pub=None):
    org, un = _orgao(cnpj)
    return {"numeroControlePNCP": f"{cnpj}-2-{seq:06d}/{ano}", "numeroControlePNCPCompra": compra_id,
            "anoContrato": ano, "sequencialContrato": seq, "numeroContratoEmpenho": f"CT-{seq}/{ano}",
            "tipoContrato": {"id": 1, "nome": "Contrato"}, "categoriaProcesso": {"id": 2, "nome": "Compras"},
            "objetoContrato": objeto, "orgaoEntidade": org, "unidadeOrgao": un, "tipoPessoa": "PJ",
            "niFornecedor": forn, "nomeRazaoSocialFornecedor": FORN_NOMES.get(forn, "X"),
            "valorInicial": vi, "valorGlobal": vi, "valorAcumulado": vi, "dataAssinatura": assin,
            "dataVigenciaInicio": assin, "dataVigenciaFim": vig_fim, "dataPublicacaoPncp": (pub or assin) + "T12:00:00"}


COMPRAS, ITENS, RESULTADOS, CONTRATOS, TERMOS = [], {}, {}, [], {}


def _id(c):
    return c["numeroControlePNCP"]


# ---- 1. Arroz superfaturado (R01) e feijão normal (sem alerta) ---------------------------------
c = compra(PREF, 2026, 10, 6, "Aquisição de gêneros alimentícios para a merenda escolar", "2026-03-10", 310000, 295500)
COMPRAS.append(c)
ITENS[_id(c)] = [item(1, "ARROZ BRANCO TIPO 1 PACOTE 5KG", 6000, "PACOTE", 46.0),
                 item(2, "FEIJAO CARIOCA TIPO 1 PACOTE 1KG", 3000, "PACOTE", 9.0)]
RESULTADOS[(_id(c), 1)] = [resultado(1, BETA, 6000, 45.0, "2026-03-20")]
RESULTADOS[(_id(c), 2)] = [resultado(2, ALFA, 3000, 8.5, "2026-03-20")]
CONTRATOS.append(contrato(PREF, 2026, 50, _id(c), BETA, "Fornecimento de arroz para a merenda", 270000,
                          "2026-03-25", "2027-03-24"))
CONTRATOS.append(contrato(PREF, 2026, 51, _id(c), ALFA, "Fornecimento de feijão para a merenda", 25500,
                          "2026-03-25", "2027-03-24"))

for k, (org, data, arroz, feijao) in enumerate([(VIZ_A, "2026-02-05", 21.0, 8.2), (VIZ_A, "2026-05-15", 22.5, 8.0),
                                                 (VIZ_B, "2026-01-20", 20.0, 7.9), (VIZ_B, "2026-06-01", 23.0, 8.4)]):
    v = compra(org, 2026, 200 + k, 6, "Aquisição de alimentos", data, 60000, 55000)
    COMPRAS.append(v)
    ITENS[_id(v)] = [item(1, "Arroz branco tipo 1, pacote de 5 kg", 1500, "PCT", arroz + 1),
                     item(2, "Feijão carioca tipo 1 - pacote 1 kg", 2000, "PCT", feijao + 0.5)]
    RESULTADOS[(_id(v), 1)] = [resultado(1, "70000000000707", 1500, arroz, data)]
    RESULTADOS[(_id(v), 2)] = [resultado(2, "70000000000707", 2000, feijao, data)]

# ---- 2. Dispensas fracionadas para GAMA (R04, R05) e MEI acima do limite (R11) ----------------
for k, (data, valor) in enumerate([("2026-02-10", 30000), ("2026-05-12", 31000), ("2026-08-20", 29500)]):
    d = compra(PREF, 2026, 30 + k, 8, f"Manutenção preventiva e corretiva de aparelhos de ar condicionado - etapa {k + 1}",
               data, valor, valor, amparo="Lei 14.133/2021, Art. 75, II")
    COMPRAS.append(d)
    ITENS[_id(d)] = [item(1, "Serviço de manutenção de ar condicionado", 1, "SERVIÇO", valor, ms="S")]
    RESULTADOS[(_id(d), 1)] = [resultado(1, GAMA, 1, valor, data)]

# ---- 3. Obra com aditivos de 40% (R03), DELTA sancionada (R13) e concentração (R17) -----------
o = compra(PREF, 2025, 5, 4, "Construção de escola municipal", "2025-06-01", 1050000, 1000000)
COMPRAS.append(o)
CONTRATOS.append(contrato(PREF, 2025, 20, _id(o), DELTA, "Construção de escola municipal", 1000000,
                          "2025-07-01", "2026-12-31"))
TERMOS[f"{PREF}-2-000020/2025"] = [
    {"sequencialTermoContrato": 1, "numeroTermoContrato": "1º TA", "tipoTermoContrato": {"nome": "Termo Aditivo"},
     "objetoTermoContrato": "Acréscimo de serviços", "valorAcrescido": 200000, "valorGlobal": 1200000,
     "qualificacaoAcrescimoSupressao": True, "dataAssinatura": "2025-11-10", "excluido": False},
    {"sequencialTermoContrato": 2, "numeroTermoContrato": "2º TA", "tipoTermoContrato": {"nome": "Termo Aditivo"},
     "objetoTermoContrato": "Novo acréscimo", "valorAcrescido": 200000, "valorGlobal": 1400000,
     "qualificacaoAcrescimoSupressao": True, "dataAssinatura": "2026-04-02", "excluido": False}]

# ---- 4. Carona em ata de consórcio sem quantitativos e com desconto mínimo (R07 alta) ---------
cc = compra(CONS, 2025, 90, 6, "Registro de preços para serviços ambientais diversos", "2025-04-01", 79000000,
            77500000, srp=True)
COMPRAS.append(cc)
ITENS[_id(cc)] = [item(1, "Serviços ambientais conforme demanda", 1, "SERVIÇO", 79000000, ms="S", tem=False)]
CONTRATOS.append(contrato(PREF, 2025, 40, _id(cc), ALFA, "Serviços ambientais na rede escolar", 2400000,
                          "2025-07-10", "2026-07-09"))

# ---- 5. Pregão com desconto de 0,4% (R08) -----------------------------------------------------
p = compra(FUNDO, 2026, 12, 6, "Aquisição de medicamentos da atenção básica", "2026-04-01", 500000, 498000)
COMPRAS.append(p)
ITENS[_id(p)] = [item(1, "DIPIRONA 500MG COMPRIMIDO", 100000, "COMPRIMIDO", 5.0)]
RESULTADOS[(_id(p), 1)] = [resultado(1, EPSI, 100000, 4.98, "2026-04-15")]
CONTRATOS.append(contrato(FUNDO, 2026, 8, _id(p), EPSI, "Fornecimento de medicamentos", 498000,
                          "2026-04-20", "2027-04-19"))

# ---- 6. Contrato assinado antes da publicação da compra (R18) ---------------------------------
q = compra(PREF, 2026, 60, 6, "Aquisição de material de limpeza", "2026-06-20", 80000, 78000)
COMPRAS.append(q)
ITENS[_id(q)] = [item(1, "Detergente líquido 500ml", 5000, "UN", 3.0, tem=False)]
CONTRATOS.append(contrato(PREF, 2026, 61, _id(q), ALFA, "Fornecimento de material de limpeza", 78000,
                          "2026-06-05", "2027-06-04", pub="2026-06-25"))

# ---- 7. Mesmo item comprado pelo próprio município por preços muito diferentes (R02) -----------
ZETA = "60000000000606"   # empresa baixada na Receita antes do contrato (R12)
FORN_NOMES[ZETA] = "ZETA PAPELARIA FICTICIA LTDA"
for k, (data, preco, qtd, forn) in enumerate([("2026-02-01", 25.0, 1000, ALFA), ("2026-04-01", 24.0, 1000, ALFA),
                                               ("2026-07-01", 60.0, 500, ZETA)]):
    x = compra(PREF, 2026, 70 + k, 6, "Aquisição de papel A4", data, qtd * preco, qtd * preco)
    COMPRAS.append(x)
    ITENS[_id(x)] = [item(1, "PAPEL SULFITE A4 75G RESMA 500 FOLHAS", qtd, "RESMA", preco)]
    RESULTADOS[(_id(x), 1)] = [resultado(1, forn, qtd, preco, data)]
CONTRATOS.append(contrato(PREF, 2026, 75, f"{PREF}-1-000072/2026", ZETA, "Fornecimento de papel A4", 30000,
                          "2026-07-10", "2027-07-09"))

# ---- 8. Emergências repetidas com o mesmo fornecedor (R06) --------------------------------------
for k, data in enumerate(["2025-03-01", "2025-11-01"]):
    e = compra(PREF, 2025, 80 + k, 8, "Contratação emergencial de coleta de resíduos", data, 400000, 400000,
               amparo="Lei 14.133/2021, Art. 75, VIII")
    COMPRAS.append(e)
    ITENS[_id(e)] = [item(1, "Serviço de coleta de resíduos", 1, "SERVIÇO", 400000, ms="S")]
    RESULTADOS[(_id(e), 1)] = [resultado(1, DELTA, 1, 400000, data)]

# ---- 9. Contrato emergencial prorrogado (R19) e emergência repetida para o mesmo serviço (R20) ----
CONTRATOS.append(contrato(PREF, 2025, 85, f"{PREF}-1-000080/2025", DELTA, "Coleta de resíduos emergencial", 400000,
                          "2025-03-05", "2025-12-04"))    # 274 dias + 180 prorrogados: passa de 1 ano → alta
CONTRATOS.append(contrato(PREF, 2025, 86, f"{PREF}-1-000080/2025", DELTA, "Coleta de resíduos emergencial (2)", 300000,
                          "2025-03-05", "2025-09-04"))    # 183 + 180 = 363 dias: dentro de 1 ano → média
TERMOS[f"{PREF}-2-000085/2025"] = [
    {"sequencialTermoContrato": 1, "numeroTermoContrato": "1º TA", "tipoTermoContrato": {"nome": "Termo Aditivo"},
     "objetoTermoContrato": "Prorrogação do prazo de vigência por 180 dias", "valorAcrescido": 400000,
     "valorGlobal": 800000, "prazoAditadoDias": 180, "qualificacaoVigencia": True, "dataAssinatura": "2025-09-01",
     "excluido": False}]

TERMOS[f"{PREF}-2-000086/2025"] = [
    {"sequencialTermoContrato": 1, "numeroTermoContrato": "1º TA", "tipoTermoContrato": {"nome": "Termo Aditivo"},
     "objetoTermoContrato": "Prorrogação do prazo de vigência por 180 dias", "valorAcrescido": 300000,
     "valorGlobal": 600000, "prazoAditadoDias": 180, "qualificacaoVigencia": True, "dataAssinatura": "2025-09-01",
     "excluido": False}]

# ---- Dados da Receita (formato BrasilAPI) -------------------------------------------------------
def receita(cnpj, abertura, capital, mei=False, socios=(), tel="2733330000", email=None, logradouro="RUA UM", num="1"):
    return {"cnpj": cnpj, "razao_social": FORN_NOMES[cnpj], "nome_fantasia": "", "data_inicio_atividade": abertura,
            "descricao_situacao_cadastral": "ATIVA", "data_situacao_cadastral": abertura, "capital_social": capital,
            "porte": "MICRO EMPRESA", "natureza_juridica": "Sociedade Empresária Limitada", "cnae_fiscal": 4639701,
            "cnae_fiscal_descricao": "Comércio atacadista de produtos alimentícios", "opcao_pelo_mei": mei,
            "opcao_pelo_simples": True, "descricao_tipo_de_logradouro": "", "logradouro": logradouro, "numero": num,
            "complemento": "", "bairro": "CENTRO", "cep": "29100000", "municipio": "EXEMPLO", "uf": "XX",
            "ddd_telefone_1": tel, "email": email,
            "qsa": [{"nome_socio": n, "qualificacao_socio": "Sócio-Administrador", "cnpj_cpf_do_socio": "***123456**",
                     "data_entrada_sociedade": abertura, "faixa_etaria": "31 a 40 anos"} for n in socios]}


RECEITA = {
    ALFA: receita(ALFA, "2005-03-01", 2000000, socios=["ANTONIO FICTICIO DOS SANTOS"], tel="2730000001",
                  logradouro="AVENIDA CENTRAL", num="100"),
    BETA: receita(BETA, "2026-01-15", 10000, socios=["JOSE CARLOS DA SILVA PEREIRA", "MARIA APARECIDA SOUZA LIMA"],
                  tel="2799998888", logradouro="RUA DAS FLORES", num="55"),
    GAMA: receita(GAMA, "2019-07-01", 5000, mei=True, socios=["PEDRO FICTICIO GOMES"], tel="2730000003",
                  logradouro="RUA TRES", num="3"),
    DELTA: receita(DELTA, "1998-01-10", 5000000, socios=["CARLOS FICTICIO MOURA"], tel="2730000004",
                   logradouro="RODOVIA QUATRO", num="4"),
    EPSI: receita(EPSI, "2015-09-09", 300000, socios=["MARIA APARECIDA SOUZA LIMA"], tel="2799998888",
                  logradouro="RUA CINCO", num="5"),
    ZETA: receita(ZETA, "2010-01-01", 1000000, socios=["JOAO FICTICIO RAMOS"], tel="2730000006",
                  logradouro="RUA SEIS", num="6"),
}
RECEITA[ZETA]["descricao_situacao_cadastral"] = "BAIXADA"
RECEITA[ZETA]["data_situacao_cadastral"] = "2026-01-10"

CSV_CEIS = ("CADASTRO;CPF OU CNPJ DO SANCIONADO;NOME DO SANCIONADO;CATEGORIA DA SANÇÃO;DATA INÍCIO SANÇÃO;"
            "DATA FINAL SANÇÃO;ÓRGÃO SANCIONADOR\n"
            f"CEIS;{DELTA[:2]}.{DELTA[2:5]}.{DELTA[5:8]}/{DELTA[8:12]}-{DELTA[12:]};DELTA CONSTRUCOES FICTICIAS SA;"
            "Suspensão - Lei de Licitações;01/01/2025;31/12/2025;PREFEITURA FICTICIA DE OUTRO LUGAR\n")

CSV_SERVIDORES = "Nome;Cargo;Lotação\nJOSÉ CARLOS DA SILVA PEREIRA;Assessor;Secretaria de Educação\nFULANO DE TAL;Motorista;Obras\n"
