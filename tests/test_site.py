"""O site público só sai se passar na régua: linguagem simples, nenhum dado pessoal, fonte em toda página."""
import re
from datetime import date

import pytest

from vigia.coletores import equipamentos
from vigia.site import __main__ as site
from vigia.site import dados as D
from vigia.site import legibilidade as L
from vigia.site import vereadores as V


@pytest.fixture(scope="module")
def gerado(tmp_path_factory):
    saida = tmp_path_factory.mktemp("site")
    rel = site.gerar(saida, hoje=date(2026, 11, 12))
    return saida, rel


def test_paginas_principais_existem(gerado):
    saida, rel = gerado
    for c in ("/", "/bairros/", "/fila/", "/perguntas/", "/dinheiro/", "/quem-somos/", "/problemas/", "/vereadores/",
              "/fontes/", "/mapa/", "/novidades/", "/denuncie/"):
        assert c in rel
    assert len([c for c in rel if c.startswith("/bairros/") and c != "/bairros/"]) >= 90
    assert (saida / "fila" / "santa-fe" / "index.html").exists()
    assert "quem-somos" in (saida / "como-trabalhamos" / "index.html").read_text()
    assert (saida / ".nojekyll").exists() and (saida / "sitemap.xml").exists()
    assert len([c for c in rel if c.startswith("/vereadores/") and c != "/vereadores/"]) == 19
    assert len([c for c in rel if c.startswith("/problemas/") and c != "/problemas/"]) >= 8
    assert (saida / "fontes" / "atkinson-400.woff2").exists()


def test_sem_pedido_a_terceiros_e_menu_curto_no_celular(gerado):
    """Fontes no próprio site (nenhum pedido ao Google com o endereço de quem visita) e o menu do celular
    fechado por padrão, para o título aparecer na primeira tela."""
    saida, _ = gerado
    for f in saida.rglob("*.html"):
        t = f.read_text(encoding="utf-8")
        assert "googleapis" not in t and "gstatic" not in t, f
        if "<header" in t:
            assert '<details class="menu-cel">' in t, f


def test_linguagem_simples_em_todas_as_paginas(gerado):
    _, rel = gerado
    for caminho, r in rel.items():
        assert r["flesch"] >= 55, f"{caminho}: leitura difícil (Flesch {r['flesch']})"
        assert not r["frases_longas"], f"{caminho}: frase com mais de 20 palavras: {r['frases_longas'][:1]}"
        assert not r["jargao"], f"{caminho}: palavra de dentro do projeto no texto: {r['jargao']}"
        assert not r["julgamento"], f"{caminho}: palavra de julgamento: {r['julgamento']}"


def test_nenhum_dado_pessoal_nem_assunto_interno(gerado):
    saida, _ = gerado
    cpf = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")
    internos = ["Himalaia", "Forte Ambiental", "Serdel", "Lumen", "R27", "R28", "VC·"]
    for f in saida.rglob("*.html"):
        t = f.read_text(encoding="utf-8")
        assert not cpf.search(t), f"CPF em {f}"
        for x in internos:
            assert x not in t, f"{x} em {f}"


def test_toda_pagina_com_numero_tem_fonte(gerado):
    saida, _ = gerado
    for f in saida.rglob("index.html"):
        t = f.read_text(encoding="utf-8")
        if f.parent == saida:
            continue   # o início resume as outras páginas, que têm a fonte completa
        if re.search(r"\d", L.texto_da_pagina(t)):
            assert 'class="fonte"' in t or 'class="meta"' in t, f"sem fonte: {f}"


def test_toda_pergunta_tem_texto_publico():
    p = D.perguntas(date(2026, 11, 12))
    for itens in p["grupos"].values():
        for it in itens:
            assert "texto em revisão" not in it["pergunta"], it["numeros"]


def test_numeros_como_se_fala():
    assert D.de_cada(71.7) == "7 de cada 10"
    assert D.de_cada(96.0) == "quase todas"
    assert D.de_cada(100) == "todas"
    assert D.meses(236) == "quase 8 meses"
    assert D.meses(400) == "mais de 1 ano"
    assert D.falado(40829) == "quase 41 mil"
    assert D.falado(2569) == "quase 2.600"
    assert D.br(1234567.8, 1) == "1.234.567,8"


def test_flesch_distingue_texto_simples_de_juridiques():
    simples = "A gente olha as contas. Perguntamos o que não está claro. Mostramos a resposta."
    dificil = ("Consoante o disposto na legislação pertinente, procedeu-se à instauração de procedimento "
               "administrativo destinado à apuração de eventuais irregularidades contratuais supervenientes.")
    assert L.flesch(simples) > 75 > L.flesch(dificil)


def test_coletor_equipamentos_le_cnes_e_mapa_do_estado():
    pagina = [{"codigo_cnes": 2445107, "nome_fantasia": "US ALTO LAGE", "codigo_tipo_unidade": 2,
               "bairro_estabelecimento": "ALTO LAGE", "endereco_estabelecimento": "RUA EDMILSON VAREJAO",
               "numero_estabelecimento": "104", "codigo_cep_estabelecimento": "29151050",
               "latitude_estabelecimento_decimo_grau": -20.32, "longitude_estabelecimento_decimo_grau": -40.36}]
    df = equipamentos.ler_cnes([pagina])
    assert df.iloc[0]["bairro"] == "ALTO LAGE" and df.iloc[0]["tipo"] == "Unidade de saúde"
    csv = ("﻿LOGRADOURO;MUNICIPIO;BAIRRO;NOME;CODESCOLA;ADMINISTRA;CLASSECNAE;NUMERO;COORDX;COORDY\n"
           "Rua A;Cariacica;Itaquari;EMEF X;32033656;Municipal;Fundamental;10;-40,3;-20,3\n"
           "Rua B;Vitória;Centro;EMEF Y;1;Municipal;Fundamental;1;-40,3;-20,3\n")
    e = equipamentos.ler_escolas_es(csv)
    assert list(e["inep"]) == ["32033656"] and e.iloc[0]["lat"] == "-20.3"


def test_bairro_do_posto_casa_com_o_censo():
    chaves = {D.normalizar(b["bairro"]) for b in D.bairros()}
    assert D.chave_bairro("NOVA ROSA DA PENHA I", chaves) == "NOVA ROSA DA PENHA"
    assert D.chave_bairro("Porto de Santana", chaves) == "PORTO SANTANA"
    assert D.chave_bairro("Bairro que não existe", chaves) is None


def test_vereadores_sem_partido_e_em_ordem_alfabetica(gerado):
    saida, _ = gerado
    for f in sorted(D.DADOS.joinpath("camara").glob("*.json")):
        assert '"partido"' not in f.read_text(encoding="utf-8"), f
    partidos = ["Republicanos", "Podemos", "PSB", "PSDB", "MDB", "PDT", "Avante", "Solidariedade", "Cidadania",
                "União Brasil", "Progressistas", "PSOL", "PCdoB", "PRD", "Mobiliza"]
    for f in (saida / "vereadores").rglob("index.html"):
        t = f.read_text(encoding="utf-8")
        for p in partidos:
            assert p not in t, f"{p} em {f}"
    v = V.vereadores()
    nomes = [x["nome"] for x in v["lista"]]
    assert len(nomes) == 19 and nomes == sorted(nomes, key=D.normalizar)


def test_conta_dos_vereadores():
    v = V.vereadores()
    k, c = v["conta"], v["cidade"]
    assert k["meses"] == 22 and k["salario_periodo_exato"] == "R$ 297.000"
    assert c["n"] == sum(c["cont"].values()) and c["aprovados"] == sum(c["cont_aprov"].values())
    assert sum(x["n"] for x in v["lista"]) >= c["n"]          # coautoria conta para cada autor
    assert len(c["cem"]) == 100
    assert V.reais_falado(76_413_310) == "R$ 76,4 milhões" and V.reais_falado(1_960_000) == "R$ 2 milhões"
    assert V.reais_falado(1_389_333) == "R$ 1,4 milhão" and V.reais_falado(297_000) == "R$ 297 mil"
    assert V.ementa_simples("INSTITUI O DIA DO SUS NO MUNICÍPIO DE CARIACICA E DÁ OUTRAS PROVIDÊNCIAS") == \
        "Institui o dia do SUS no município de Cariacica"
    assert V.ementa_simples("PROÍBE A COLAGEM EM BENS PÚBLICOS E DÁ OUTR…") == "Proíbe a colagem em bens públicos…"


def test_obras_no_bairro(gerado):
    saida, _ = gerado
    o = D.obras(D.bairros(), date(2026, 11, 12))
    assert o["total"] == sum(o["anos"].values())
    assert all(not x["slugs"] for x in o["sem_bairro"])
    # serviço da cidade toda não vai para um bairro só, mesmo quando o sistema põe um bairro
    assert all(not x["servico"] for xs in o["por_bairro"].values() for x in xs)
    if o["por_bairro"]:
        slug, xs = next(iter(o["por_bairro"].items()))
        t = (saida / "bairros" / slug / "index.html").read_text(encoding="utf-8")
        assert "Obras da prefeitura no bairro" in t and xs[0]["id"] in t


def test_previa_de_cada_pagina(gerado):
    """Cada bairro, posto, problema e vereador tem a sua imagem de prévia (WhatsApp), com endereço completo."""
    saida, _ = gerado
    t = (saida / "bairros" / "itaquari" / "index.html").read_text(encoding="utf-8")
    assert 'og:image" content="https://' in t and "/previas/bairro-itaquari.png" in t
    for nome in ("bairro-itaquari", "fila-santa-fe", "problema-esgoto", "vereador-acucena", "vereadores"):
        f = saida / "previas" / f"{nome}.png"
        assert f.exists() and 5_000 < f.stat().st_size < 60_000, nome


def test_mapa_e_numeros_brutos(gerado):
    """O mapa tem os 99 bairros com dado, o bairro tem a tabela de números com posição, e dinheiro vai com os zeros."""
    saida, _ = gerado
    t = (saida / "mapa" / "index.html").read_text(encoding="utf-8")
    assert t.count('data-qpop="') == 99 and (saida / "mapa" / "base.svg").exists()
    b = (saida / "bairros" / "itaquari" / "index.html").read_text(encoding="utf-8")
    assert "Os números do bairro" in b and "º de 99" in b and "/mapa/base.svg" in b
    assert D.reais_cheio(76_413_310.65) == "R$ 76.413.311"
    assert D.extenso(1_663_887_316) == "1 bilhão e 664 milhões de reais"
    assert D.extenso(297_000) == "297 mil reais" and D.posicao(10, [10, 20, 5]) == 2
    d = (saida / "dinheiro" / "index.html").read_text(encoding="utf-8")
    assert "R$ 1.619.123.621" in d


def test_denuncia_cai_no_formulario_e_nada_e_publicado(gerado):
    """A denúncia vai para o formulário do Google do Vigia (nunca para o site), com os mesmos campos e opções do
    formulário; a página não carrega script de fora e tem o aviso de privacidade."""
    import json as _json
    saida, rel = gerado
    assert "/denuncie/" in rel
    t = (saida / "denuncie" / "index.html").read_text(encoding="utf-8")
    den = _json.loads((D.DADOS / "site" / "denuncia.json").read_text(encoding="utf-8"))
    assert den["form"].startswith("https://docs.google.com/forms/d/e/") and den["form"].endswith("/formResponse")
    assert f'action="{den["form"]}"' in t and den["link"].endswith("/viewform")
    for nome in den["campos"].values():
        assert nome.startswith("entry.") and f'name="{nome}"' in t, nome
    for a in den["assuntos"]:
        assert f"<option>{a}</option>" in t, a
    assert f'value="{den["ok"]}"' in t and 'id="privacidade"' in t
    assert not re.search(r'<script[^>]+src="https?://', t)
    for n, _ in den["urgencia"]:
        assert f'href="tel:{n}"' in t


def test_o_que_fizemos(gerado):
    """Toda publicação listada já foi ao ar (data passada e link da rede) e aparece na linha do tempo."""
    from vigia.site import novidades as N
    saida, rel = gerado
    assert "/novidades/" in rel
    t = (saida / "novidades" / "index.html").read_text(encoding="utf-8")
    pubs = N.publicacoes()
    assert pubs
    for p in pubs:
        assert p["link"].startswith("https://") and p["data"] <= D.hoje_brasilia(), p["titulo"]
        assert p["titulo"] and p["resumo"] and p["fonte"], p["link"]
    hoje = date(2026, 11, 12)
    assert all(e["data"] <= hoje for e in N.linha_do_tempo(D.perguntas(hoje), pubs, [], hoje))
    assert "Mandamos" in t and "/perguntas/" in t


def test_sinais_para_buscadores(gerado):
    """Nome do site para o Google (WebSite), página de erro fora do índice, chave do IndexNow e ícones."""
    import json as _json
    saida, _ = gerado
    t = (saida / "index.html").read_text(encoding="utf-8")
    assert '"@type":"WebSite"' in t and '"name":"Vigia Cariacica"' in t and "<title>Vigia Cariacica:" in t
    assert 'content="index,follow' in t
    assert 'name="robots" content="noindex"' in (saida / "404.html").read_text(encoding="utf-8")
    chave = _json.loads((D.DADOS / "site" / "buscadores.json").read_text(encoding="utf-8"))["indexnow"]
    assert (saida / f"{chave}.txt").read_text() == chave
    assert (saida / "favicon.ico").exists() and (saida / "icone-48.png").exists()
    b = (saida / "bairros" / "itaquari" / "index.html").read_text(encoding="utf-8")
    assert "<title>Itaquari, Cariacica:" in b


# ---------------------------------------------------------------- correções do juiz de dados (24/11/2026)

def _texto(saida, caminho):
    return L.texto_da_pagina((saida / caminho.strip("/") / "index.html").read_text(encoding="utf-8"))


def test_coluna_cariacica_e_o_total_oficial_do_ibge():
    """A soma dos 99 bairros deixava de fora 4.387 moradores e a zona rural; a coluna Cariacica é o município."""
    bs = D.bairros()
    c = D.cidade(bs)
    assert (c["populacao"], c["domicilios"], c["sem_rede"], c["nao_le"]) == (353_491, 130_183, 23_545, 12_745)
    assert c["populacao"] - sum(b["populacao"] for b in bs) == 4_387
    assert round(c["densidade"], 1) == 1263.7 and round(c["pct_nao_le"]) == 5
    assert (c["pct_esgoto_rede"], c["pct_agua_rede"], c["pct_lixo_coletado"]) == (81.8, 97.4, 98.5)
    assert c["rotulo"] == "Cariacica"


def test_bairro_com_posto_no_cnes_nunca_diz_nao_achamos(gerado):
    saida, _ = gerado
    bs = D.bairros()
    postos = D.postos_por_bairro(bs, D.fila())
    assert {"itaciba", "campo-grande", "alto-da-boa-vista"} <= set(postos)
    for slug in postos:
        assert "Não achamos um posto" not in _texto(saida, f"/bairros/{slug}/"), slug
    assert "US Itacibá" in _texto(saida, "/bairros/itaciba/")
    assert "US Bom Pastor" in _texto(saida, "/bairros/campo-grande/")
    # a US com o nome do bairro que fica no vizinho
    assert "A US Rio Marinho, que tem o nome do bairro, fica em Castelo Branco." in _texto(saida, "/bairros/rio-marinho/")
    assert "fica em Maracanã" in _texto(saida, "/bairros/itapemirim/")
    assert "fica em Vila Independência" in _texto(saida, "/bairros/mucuri/")
    # presídio e vigilância não são o posto do bairro
    assert all("PENITENCIARIA" not in D.normalizar(p["nome"]) for ps in postos.values() for p in ps)


def test_empate_da_renda_entra_inteiro(gerado):
    saida, _ = gerado
    bs = D.bairros()
    grandes = [b for b in bs if b["domicilios"] >= D.MIN_DOMICILIOS_RANKING]
    n_1212 = sum(1 for b in grandes if b["renda_mediana"] == 1212)
    pad = D.padroes(bs)
    assert n_1212 == 29 == pad["n_renda_baixa"] == sum(1 for b in bs if b["renda_baixa"])
    assert round(pad["esgoto_renda_baixa"], 1) == 68.2
    for slug in ("santa-luzia", "vista-linda", "tiradentes"):
        assert "Está entre os 29 bairros onde metade ganha até 1 salário mínimo (R$ 1.212)." in \
            _texto(saida, f"/bairros/{slug}/"), slug
    assert "Nos 29 bairros de menor renda (R$ 1.212), 7 de cada 10 casas têm esgoto na rede." in _texto(saida, "/bairros/")


def test_renda_diz_que_so_conta_quem_tem_renda(gerado):
    saida, _ = gerado
    t = _texto(saida, "/bairros/itaquari/")
    assert "metade dos responsáveis pela casa que têm renda ganha até esse valor" in t
    assert "Metade dos responsáveis com renda ganha até" in t
    assert "Metade das famílias" not in t and "responsáveis pelas casas ganha" not in t


def test_casas_sem_rede_exatas_e_frase_do_zero():
    b = {x["slug"]: x for x in D.bairros()}
    assert b["nova-rosa-da-penha"]["sem_rede"] == 2_038
    assert D.casas(0, "têm esgoto ligado na rede.") == ("Nenhuma", "casa tem esgoto ligado na rede.")
    assert D.casas(71.7, "têm esgoto ligado na rede.") == ("7 de cada 10", "casas têm esgoto ligado na rede.")
    assert D.casas(99.7, "têm esgoto ligado na rede.")[1] == "as casas têm esgoto ligado na rede."


def test_bairro_pequeno_mostra_pessoas(gerado):
    saida, _ = gerado
    t = _texto(saida, "/bairros/foz-do-rio-bubu/")
    assert "No Censo, só 3 pessoas de 15 anos ou mais foram contadas aqui. As 3 não sabem ler e escrever." in t
    assert "Nenhuma casa tem esgoto" in t.replace("\n", " ") and "Nenhuma as casas" not in t


def test_escola_com_nota_usa_nome_e_rede_do_inep(gerado):
    saida, _ = gerado
    esc = D.escolas_por_bairro(D.bairros())
    ja = {x["nome"]: x for x in esc["jardim-america"]}
    assert "EMEFTI Professor Cerqueira Lima" in ja and ja["EMEFTI Professor Cerqueira Lima"]["ideb"][0]["nota"] == "6.7"
    assert not any("Pautila" in n and x["ideb"] for n, x in ja.items())
    nrp = {x["nome"]: x for x in esc["nova-rosa-da-penha"]}
    assert nrp["EMEF Teotônio Brandão Vilela"]["rede"] == "Municipal"
    # a cidade no mesmo ano da escola
    t = _texto(saida, "/bairros/itaciba/")
    assert "nota 4,1 em 2023 (Cariacica, escolas públicas: 4,7 em 2023)" in t
    assert D.ideb_cidade()["Anos finais (6º–9º)"]["2023"] == "4.7"


def test_obras_citadas_no_nome_e_contrato_que_junta_obras(gerado):
    saida, _ = gerado
    o = D.obras(D.bairros(), date(2026, 11, 12))
    ids = {s: {x["id"] for x in xs} for s, xs in o["por_bairro"].items()}
    assert "1748" in ids["nova-campo-grande"] and "1748" in ids["vista-dourada"]
    assert "1748" not in {x["id"] for x in o["sem_bairro"]}
    juntas = {x["id"]: x["junta"] for xs in o["por_bairro"].values() for x in xs}
    assert juntas["8"] == juntas["9"] == juntas["10"] == 3 and juntas["132"] == juntas["133"] == 2
    t = _texto(saida, "/bairros/novo-brasil/").replace("\xa0", " ")
    assert "pagos no contrato 154/2012, que junta 3 obras" in t
    # a rua Santa Luzia não é o bairro Santa Luzia; Jardim Campo Grande não é Campo Grande
    chaves = {D.normalizar(b["bairro"]): b["slug"] for b in D.bairros()}
    assert D.bairros_no_nome("Drenagem da Avenida Santa Luzia, no Bairro Piranema", chaves) == ["piranema"]
    assert D.bairros_no_nome("Reforma da EMEF X - Bairro Jardim Campo Grande", chaves) == ["jardim-campo-grande"]
    lista = _texto(saida, "/bairros/")
    assert "citam um lugar que o Censo não separa" in lista


def test_fila_em_palavras_e_anos_meses():
    from vigia.site import problemas as P
    assert D.parte_ano(5, 177, " deste posto") == "Só 5 pedidos deste posto esperam há mais de 1 ano."
    assert D.parte_ano(82, 177, " deste posto") == "Quase metade dos pedidos deste posto."
    assert D.parte_ano(16_218, 42_679) == "São 4 de cada 10 pedidos."
    assert P._anos_meses(512) == "1 ano e 4 meses"      # 16,8 meses: "mais de 1 ano e 5 meses" seria falso
    assert P._anos_meses(497) == "1 ano e 4 meses"


def test_dinheiro_sem_contar_duas_vezes():
    g = D.dinheiro()
    assert round(g["total"], 2) == 1_619_123_621.02
    assert round(sum(b["de_cada_100"] for b in g["blocos"]), 1) == 100.0
    car = next(s["por_morador"] for s in g["saude"] if s["cidade"] == "Cariacica")
    vit = next(s["por_morador"] for s in g["saude"] if s["cidade"] == "Vitória")
    assert D.reais_cheio((vit - car) * g["populacao"]) == "R$ 272.844.661"
    assert D.reais_cheio(g["total"] / 365) == "R$ 4.435.955" and round(g["total"] / g["populacao"] / 12) == 359


def test_correcoes_a_vista(gerado):
    from vigia.site import novidades as N
    saida, _ = gerado
    corr = N.correcoes()
    links = {c["link"] for c in corr}
    for p in N.publicacoes():
        if p.get("correcao"):
            assert p["link"] in links, p["titulo"]
    t = _texto(saida, "/quem-somos/")
    assert "Nenhuma até agora" not in t and "Vídeo do PA do Trevo" in t


def test_perguntas_dizem_a_quem_foram(gerado):
    saida, _ = gerado
    assert D.destinos_texto({"prefeitura": 53, "camara": 3, "estado": 4}) == "à prefeitura, à Câmara e ao Governo do ES"
    assert D.destinos_texto({"prefeitura": 2}) == "à prefeitura"
    p = D.perguntas(date(2026, 11, 12))
    assert sum(p["por_destino"].values()) == p["total"]
    assert f"{p['total']} perguntas oficiais {p['destinos']}" in _texto(saida, "/")
