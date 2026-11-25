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
    """Os meses saem da data da coleta (a coleta roda toda segunda): em 24/11/2026 eram 22 meses, R$ 297.000."""
    import json
    v = V.vereadores()
    k, c = v["conta"], v["cidade"]
    meta = json.loads((D.DADOS / "camara" / "fonte.json").read_text(encoding="utf-8"))
    coleta = date.fromisoformat(meta["coletado_em"])
    meses = (coleta.year - 2025) * 12 + coleta.month - 1
    assert k["meses"] == meses and k["salario_periodo_exato"] == D.reais(13_500 * meses)
    assert V.tempo(date(2025, 1, 1), date(2026, 11, 24)) == "quase 2 anos"
    assert V.tempo(date(2025, 1, 1), date(2027, 1, 10)) == "2 anos"
    assert V.tempo(date(2025, 1, 1), date(2027, 4, 10)) == "mais de 2 anos"
    assert c["n"] == sum(c["cont"].values()) and c["aprovados"] == sum(c["cont_aprov"].values())
    assert sum(x["n"] for x in v["lista"]) >= c["n"]          # coautoria conta para cada autor
    assert len(c["cem"]) == 100
    assert V.reais_falado(76_413_310) == "R$ 76,4 milhões" and V.reais_falado(1_960_000) == "R$ 2 milhões"
    assert V.reais_falado(1_389_333) == "R$ 1,4 milhão" and V.reais_falado(297_000) == "R$ 297 mil"
    assert V.ementa_simples("INSTITUI O DIA DO SUS NO MUNICÍPIO DE CARIACICA E DÁ OUTRAS PROVIDÊNCIAS") == \
        "Institui o dia do SUS no município de Cariacica"
    assert V.ementa_simples("PROÍBE A COLAGEM EM BENS PÚBLICOS E DÁ OUTR…") == "Proíbe a colagem em bens públicos…"
    assert V.ementa_simples("DISPÕE SOBRE O TRANSPORTE DE ANIMAIS E DÁ OUTRAS PROVIDÊNCIAS”.") == \
        "Dispõe sobre o transporte de animais"
    assert V.ementa_simples("INCLUI NO CALENDÁRIO A “FEIRA EXPO FESTAR”.") == "Inclui no calendário a “Feira expo festar”"
    assert V.ementa_simples('NOS TERMOS DA RENAME E DÁ OUTRAS PROVIDÊNCIAS.".') == "Nos termos da RENAME"


def test_projeto_que_virou_lei_conta_como_aprovado():
    """Depois que a lei sai, o sistema da Câmara põe o projeto em "Arquivamento". Projeto com lei é aprovado."""
    import json
    projetos = json.loads((D.DADOS / "camara" / "projetos.json").read_text(encoding="utf-8"))
    com_lei = [p for p in projetos if p.get("lei")]
    assert com_lei and all(p["status"] in V.JA_VALE and p["lei_link"] for p in com_lei)
    # resolução não vira lei nem vai à sanção (24/11/2026)
    for p in projetos:
        if p["tipo"] == "Projeto de Resolução":
            assert p["status"] != "Virou lei" and "sancionad" not in p["lei"] and not p["veto"], p["numero"]
        assert "não está ligado" not in p["lei"], p["numero"]
    assert all(not p.get("lei") for p in projetos if p["status"] == "Arquivado/encerrado")
    v = V.vereadores()
    c = v["cidade"]
    assert c["aprovados"] == c["ja_vale"] + c["sem_lei"] + c["vetados"]
    assert c["ja_vale"] == len({p["link"] for p in com_lei})
    assert sum(x["ja_vale"] for x in v["lista"]) >= c["ja_vale"]


def test_veto_conta_como_aprovado_e_moção_de_título_é_homenagem():
    """O veto é sobre o texto já aprovado: projeto com veto é aprovado (salvo a exceção a conferir). Total ou parcial
    é a palavra depois do verbo. Moção que concede título de cidadão é homenagem; de repúdio, não."""
    import importlib.util
    import json
    from pathlib import Path
    caminho = Path(__file__).resolve().parents[1] / "ferramentas" / "camara_producao.py"
    spec = importlib.util.spec_from_file_location("camara_producao", caminho)
    C = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(C)
    assert C.tipo_veto("VETA TOTALMENTE O AUTÓGRAFO N°046/2025, QUE ALTERA PARCIALMENTE A LEI N°6.635") == "total"
    assert C.tipo_veto("VETAR PACIALMENTE O AUTÓGRAFO N° 130/2025") == "parcial"
    assert C.tipo_veto("VETA PARCIALMENTE O AUTÓGRAFO N. 73/2026") == "parcial"
    pl = {"tipo": "Projeto de Lei Legislativo", "fase": "Elaborar Parecer nas Comissões", "situacao": "TRAMITANDO"}
    assert C._situacao(pl, False, {"votado": False}, "total") == "Vetado pelo prefeito"
    assert C._situacao(pl, False, {"votado": False}, None) == "Em análise"
    assert C._situacao(pl, True, {"votado": True}, "total") == "Virou lei"
    mocao = {"tipo": "Moção", "ementa": "CONCEDE “TÍTULO DE CIDADÃO CARIACIQUENSE” À SRA. FULANA"}
    assert C._homenagem(mocao)
    assert not C._homenagem({"tipo": "Moção", "ementa": "MOÇÃO DE REPÚDIO EM DEFESA DOS CIDADÃOS"})
    projetos = json.loads((D.DADOS / "camara" / "projetos.json").read_text(encoding="utf-8"))
    for p in projetos:
        n = p["numero"].split()[1].split("/")
        chave = (p["numero"].split()[0], n[0], n[1])
        if p["veto"] and chave not in C.VETO_A_CONFERIR:
            assert p["status"] in ("Vetado pelo prefeito", "Virou lei"), p["numero"]


def test_leis_que_mudam_a_sua_vida(gerado):
    """O bloco "Leis que mudam a sua vida" (/vereadores/): os aprovados que mudam algo na prática, cada projeto uma
    vez, com os números tirados de projetos.json e link para a Câmara em todo projeto (e para a lei, se já vale)."""
    import json
    projetos = json.loads((D.DADOS / "camara" / "projetos.json").read_text(encoding="utf-8"))
    unicos = {p["link"]: p for p in projetos}
    conc = [p for p in unicos.values() if p["utilidade"] == "Efeito concreto" and p["status"] in V.APROVADO]
    leis = V.vereadores()["leis"]
    itens = [p for g in leis["grupos"] for p in g["itens"]]
    assert conc and leis["total"] == len(itens) == len(conc)
    assert {p["link"] for p in itens} == {p["link"] for p in conc}          # cada projeto uma vez
    assert leis["vale"] == sum(p["status"] in V.JA_VALE for p in conc)
    assert leis["vetado"] == sum(p["status"] == "Vetado pelo prefeito" for p in conc)
    assert leis["sem_lei"] == sum(p["status"] == "Aprovado pela Câmara" for p in conc)
    assert leis["vale"] + leis["vetado"] + leis["sem_lei"] == leis["total"]
    for p in itens:
        assert p["link"].startswith("https://cariacica.camarasempapel.com.br/"), p["numero"]
        if p["status"] in V.JA_VALE:
            assert p["selo_lei"][0] == "Já vale" and p["lei_link"].startswith("https://"), p["numero"]
        if p.get("veto") == "parcial" and p["status"] == "Vetado pelo prefeito":
            assert p["selo_lei"][0] == "Vetado em parte"
    # sem ranking: temas na ordem fixa e, dentro do tema, do mais novo para o mais antigo
    chaves = [g["chave"] for g in leis["grupos"]]
    assert chaves == [k for k in V.ORDEM_TEMAS if k in chaves]
    for g in leis["grupos"]:
        assert [p["data"] for p in g["itens"]] == sorted((p["data"] for p in g["itens"]), reverse=True)
    # regra que vale só dentro da Câmara fica no grupo dela
    assert all(V.tema(p["ementa"]) == "camara" for p in conc if p["numero"] in ("PL 175/2025", "PR 12/2025"))
    assert V.tema("DISPÕE SOBRE O SOCORRO AOS ANIMAIS ATROPELADOS") == "animais"
    assert V.tema("DISPÕE SOBRE A CRIAÇÃO E A COMERCIALIZAÇÃO DE CÃES E GATOS") == "animais"
    assert V.tema("Dispõe sobre o atendimento de idosos e pessoas com deficiência") == "deficiencia"
    assert V.tema("Institui a cor oficial do município") == "outros"
    # concordância
    assert V.frases_leis(2, 1, 1, 0, "24/11/2026") == (
        "Dos 2 projetos aprovados que mudam algo na prática, 1 já vale e 1 foi vetado pelo prefeito.", "")
    assert V.frases_leis(31, 13, 17, 1, "24/11/2026")[1] == \
        "Mais 1 está sem lei ou resolução publicada no sistema até 24/11/2026."
    # na página: logo depois de "Quantos foram aprovados", com a abertura e o link de cada projeto
    saida, _ = gerado
    t = (saida / "vereadores" / "index.html").read_text(encoding="utf-8")
    assert t.index("Quantos foram aprovados") < t.index('id="h-leis"') < t.index('id="h-cada"')
    bloco = t[t.index('id="h-leis"'):t.index('id="h-cada"')]
    assert leis["lead"] in bloco and str(leis["total"]) in leis["lead"] and str(leis["vale"]) in leis["lead"]
    assert (not leis["sem_lei"]) or leis["resto"] in bloco
    for p in itens:
        assert f'href="{p["link"]}"' in bloco, p["numero"]
        if p["status"] in V.JA_VALE and p["lei_curta"]:
            assert f'href="{p["lei_link"]}"' in bloco, p["numero"]


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
        assert "Obras pagas pela prefeitura no bairro" in t and xs[0]["id"] in t


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
    assert "R$ 1.663.887.317" in d


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
