"""Gera o site público do Vigia (vigiacariacica.github.io) a partir dos dados do robô.

    python -m vigia.site                 gera em _site/
    python -m vigia.site --saida PASTA   gera em outra pasta

Uma página por bairro (Censo 2022) e por posto de saúde (fila), mais início, perguntas, dinheiro e método.
Antes de gravar, cada página passa pela régua de linguagem simples (vigia/site/legibilidade.py).
"""
from __future__ import annotations

import json

import argparse
import hashlib
import logging
import shutil
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import dados as D
from . import categorias as C
from . import fontes as F
from . import mapa as M
from . import legibilidade
from . import previa as PV
from . import problemas as P
from . import vereadores as V

log = logging.getLogger("vigia.site")
AQUI = Path(__file__).parent
# Endereço do site. Quando o domínio próprio estiver comprado e apontado , escreva o domínio em
# data/site/dominio.txt (ex.: vigiacariacica.com.br): os links passam a usar ele e o arquivo CNAME é gerado.
_DOMINIO_TXT = D.DADOS / "site" / "dominio.txt"
DOMINIO = _DOMINIO_TXT.read_text(encoding="utf-8").strip() if _DOMINIO_TXT.exists() else ""
BASE = f"https://{DOMINIO}" if DOMINIO else "https://vigiacariacica.github.io"
# Buscadores (docs/BUSCA.md). Os códigos de verificação do Google Search Console e do Bing Webmaster Tools são
# públicos (vão numa tag da página inicial); quando alguém da equipe colar um, ele entra em data/site/buscadores.json.
_BUSCA = json.loads((D.DADOS / "site" / "buscadores.json").read_text(encoding="utf-8"))
VERIFICACAO = _BUSCA.get("verificacao", {})
REDES = _BUSCA.get("redes", [])
INDEXNOW = _BUSCA.get("indexnow", "")
MENU = [("/", "Início", "inicio"), ("/bairros/", "Meu bairro", "bairros"), ("/mapa/", "Mapa", "mapa"),
        ("/problemas/", "Maiores problemas", "problemas"),
        ("/fila/", "Fila da saúde", "fila"),
        ("/vereadores/", "Vereadores", "vereadores"), ("/perguntas/", "Perguntas", "perguntas"),
        ("/dinheiro/", "Dinheiro", "dinheiro"), ("/fontes/", "Nossas fontes", "fontes"), ("/quem-somos/", "Quem somos", "quem")]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
         "novembro", "dezembro"]


def _ddmm(x) -> str:
    s = x.isoformat() if hasattr(x, "isoformat") else str(x)
    return f"{s[8:10]}/{s[5:7]}"


def _data_texto(d: date) -> str:
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}"


def _cem(v: float) -> str:
    return str(round(v)) if v >= 10 else D.br(v, 2)


def gerar(saida: Path, hoje: date | None = None) -> dict[str, dict]:
    hoje = hoje or D.hoje_brasilia()
    env = Environment(loader=FileSystemLoader(AQUI / "modelos"), autoescape=select_autoescape(["html"]),
                      trim_blocks=True, lstrip_blocks=True)
    css = (AQUI / "estatico" / "estilo.css").read_bytes() + (AQUI / "estatico" / "site.js").read_bytes()
    comum = {"base": BASE, "menu": MENU, "versao": hashlib.sha1(css).hexdigest()[:8],
             "hoje_texto": _data_texto(hoje), "br": D.br, "meses": D.meses, "falado": D.falado,
             "de_cada": D.de_cada, "ddmm": _ddmm, "cem": _cem, "rot": V.rot, "rot_palavras": V.rot_palavras,
             "verificacao": VERIFICACAO, "redes": REDES,
             "rf": D.reais_cheio, "cheio": D.reais_cheio, "extenso": D.extenso, "categorias": C.CATEGORIAS}

    if saida.exists():
        shutil.rmtree(saida)
    saida.mkdir(parents=True)
    for f in ("estilo.css", "site.js", "marca.svg", "bandeira.svg", "compartilhar.png", "manifest.webmanifest",
              "icone-48.png", "icone-192.png", "icone-512.png", "apple-touch-icon.png", "favicon.ico"):
        orig = AQUI / "estatico" / f
        if orig.exists():
            shutil.copy(orig, saida / f)
    shutil.copytree(AQUI / "estatico" / "fontes", saida / "fontes")
    (saida / ".nojekyll").write_text("")
    if INDEXNOW:   # chave do IndexNow (Bing, Yandex, Seznam, Naver): arquivo público na raiz, com a própria chave
        (saida / f"{INDEXNOW}.txt").write_text(INDEXNOW, encoding="utf-8")
    if DOMINIO:
        (saida / "CNAME").write_text(DOMINIO + "\n")

    bs = D.bairros()
    cid = D.cidade(bs)
    pad = D.padroes(bs)
    fl = D.fila()
    postos = D.postos_por_bairro(bs, fl)
    nome_bairro = {b["slug"]: b["nome"] for b in bs}
    for u in fl["unidades"]:
        if u.get("bairro_slug"):
            u["bairro_nome"] = nome_bairro[u["bairro_slug"]]
    escolas = D.escolas_por_bairro(bs)
    ob = D.obras(bs, hoje)
    ideb_cid = D.ideb_cidade()
    perg = D.perguntas(hoje)
    for itens in perg["grupos"].values():
        for it in itens:
            it["n"] = len(it["numeros"])

    def pergunta(numero):
        for itens in perg["grupos"].values():
            for it in itens:
                if numero in it["numeros"]:
                    return it
        return None

    def quando(prazo):
        n = (prazo - hoje).days
        return (f"faltam {n} dias" if n > 1 else "vence amanhã" if n == 1 else "vence hoje" if n == 0
                else f"venceu há {-n} dias")

    g = D.dinheiro()
    por_morador = g["total"] / g["populacao"]
    resultados = D.resultados()
    primeiro_prazo = perg["proximo"].strftime("%d/%m") if perg["proximo"] else ""
    def casas_txt(pct):
        n = D.de_cada(pct)
        return f"{n} casas" if "de cada" in n else f"{n} as casas"
    padrao_baixa, padrao_alta = casas_txt(pad["esgoto_renda_baixa"]), casas_txt(pad["esgoto_renda_alta"])
    apelidos = {"Porto de Santana": "Porto Santana", "Morada de Santa Fé": "Santa Fé",
                "Presidente Médici": "Presidente Médice", "Alto da Boa Vista": "Alto Boa Vista",
                "São Geraldo": "São Geraldo I"}
    for b in bs:
        b["apelidos"] = apelidos.get(b["nome"], "")

    relatorio: dict[str, dict] = {}

    def escrever(caminho: str, modelo: str, titulo: str, descricao: str, pagina: str, **ctx):
        html = env.get_template(modelo).render(**comum, **ctx, titulo=titulo, descricao=descricao, pagina=pagina,
                                               caminho=caminho)
        destino = saida / caminho.strip("/") / "index.html" if caminho.endswith("/") else saida / caminho.strip("/")
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(html, encoding="utf-8")
        relatorio[caminho] = legibilidade.avaliar(html)

    def previa(nome: str, rotulo: str, numero: str, legenda: str, fonte: str, destaque: bool = True) -> dict:
        """Imagem que aparece quando o link é mandado no WhatsApp, com o achado da página."""
        PV.gerar(saida / "previas" / f"{nome}.png", rotulo, numero, legenda, fonte, destaque)
        return {"og_imagem": f"{BASE}/previas/{nome}.png", "og_alt": f"{rotulo}: {numero} {legenda}"}

    zap_padrao = "Vigia Cariacica: veja como a prefeitura usa o nosso dinheiro, com prova oficial."
    escrever("/", "inicio.html", "Vigia Cariacica: as contas da prefeitura de Cariacica, explicadas",
             "O Vigia Cariacica mostra como a prefeitura de Cariacica (ES) usa o seu dinheiro: o seu bairro, a fila "
             "do seu posto, os vereadores e as perguntas que fizemos. Feito por moradores, com fonte oficial.", "inicio",
             bairros=bs, busca_id="inicio", busca_so_com_texto=True, padrao_baixa=padrao_baixa, pad=pad,
             padrao_alta=padrao_alta, pop_total=sum(b["populacao"] for b in bs), fila_falado=D.br(fl["pedidos"]), n_perguntas=perg["total"],
             por_mes=D.reais(round(por_morador / 12)), resultados=resultados, primeiro_prazo=primeiro_prazo, parciais=perg['parciais'], respondidas=perg['respondidas'],
             zap=zap_padrao)

    cesan = pergunta("2026111046")
    escrever("/bairros/", "bairros.html", "Como está o seu bairro?",
             "Esgoto, leitura, renda e posto de saúde de cada bairro de Cariacica, comparados com a cidade.",
             "bairros", bairros=bs, busca_id="bairros", busca_so_com_texto=False, padrao_baixa=padrao_baixa, pad=pad,
             padrao_alta=padrao_alta, piores=pad["piores_esgoto"], cesan=cesan, obras=ob,
             zap="Veja como está o seu bairro em Cariacica: esgoto, posto de saúde e fila.",
             **previa("bairros", "Meu bairro · Cariacica", D.de_cada(pad["esgoto_renda_baixa"]),
                      "das casas têm esgoto na rede nos bairros de menor renda. Nos de maior renda, "
                      f"{D.de_cada(pad['esgoto_renda_alta'])}.", "IBGE, Censo 2022"))

    # números brutos de cada bairro, com a posição entre os bairros (1º = o maior número)
    for b in bs:
        b["densidade"] = b["populacao"] / b["area_km2"] if b.get("area_km2") else 0
    validos = [b for b in bs if b["populacao"] > 0]
    tot = {"pop": sum(b["populacao"] for b in validos), "casas": sum(b["domicilios"] for b in validos),
           "area": sum(b["area_km2"] for b in validos),
           "nao_le": sum(b["pessoas_15mais_nao_alfabetizadas"] for b in validos)}
    LINHAS = [("Moradores", "geral", "populacao", D.br(tot["pop"])),
              ("Casas", "geral", "domicilios", D.br(tot["casas"])),
              ("Moradores por km²", "geral", "densidade", D.br(round(tot["pop"] / tot["area"]))),
              ("Casas sem esgoto ligado na rede", "saneamento", "sem_rede", D.br(cid["sem_rede"])),
              ("Pessoas de 15 anos ou mais que não sabem ler", "educacao", "pessoas_15mais_nao_alfabetizadas",
               D.br(tot["nao_le"])),
              ("Metade das famílias ganha até", "renda", "renda_mediana", "—")]
    todos_val = {campo: [x[campo] for x in validos] for _, _, campo, _ in LINHAS}

    def numeros(b):
        return [{"rot": rot, "cat": cat, "cidade": cidade,
                 "aqui": (f"R$ {D.br(round(b[campo]))}" if campo == "renda_mediana" else D.br(round(b[campo]))),
                 "pos": D.posicao(b[campo], todos_val[campo])} for rot, cat, campo, cidade in LINHAS]

    CAT_CARTAO = {"Esgoto": "saneamento", "Água e lixo": "saneamento", "Água": "saneamento", "Lixo": "saneamento",
                  "Ler e escrever": "educacao", "Renda": "renda"}
    mp = M.mapa(bs) if M.existe() else None
    caminho_de = {c["slug"]: c["d"] for c in mp["caminhos"]} if mp else {}
    if mp:   # o mapa de fundo, igual para todos os bairros: baixa uma vez e fica guardado no celular
        (saida / "mapa").mkdir(parents=True, exist_ok=True)
        (saida / "mapa" / "base.svg").write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {mp["largura"]} {mp["altura"]}">'
            "<style>path{fill:#dfe8e1;stroke:#f3f6f2;stroke-width:1.5}"
            "@media (prefers-color-scheme:dark){path{fill:#1d3b2b;stroke:#07291a}}</style>"
            + "".join(f'<path d="{c["d"]}"/>' for c in mp["caminhos"]) + "</svg>", encoding="utf-8")

    fixas = [pergunta("008838.2026-28"), pergunta("008935.2026-28")]
    for b in bs:
        ps = []
        if b["pct_esgoto_rede"] < 95 and cesan:
            ps.append(cesan)
        if postos.get(b["slug"]):
            ps.append(pergunta("008949.2026-38"))
        ps += fixas
        ps = [p for p in ps if p][:3]
        esg = D.de_cada(b["pct_esgoto_rede"])
        cartoes = D.cartoes_bairro(b, cid)
        for c in cartoes:
            c["cat"] = CAT_CARTAO.get(c["tema"], "saneamento")
        c0 = cartoes[0]
        escrever(f"/bairros/{b['slug']}/", "bairro.html", f"{b['nome']}, Cariacica: esgoto, posto de saúde e obras",
                 f"{b['nome']}, Cariacica: esgoto na rede em {esg} das casas, posto de saúde, fila e mais. "
                 "Comparado com a cidade, com fonte oficial.", "bairros",
                 b=b, cartoes=cartoes, postos=postos.get(b["slug"], []), fila=fl,
                 escolas=escolas.get(b["slug"], []), ideb_cidade=ideb_cid, perguntas=ps,
                 obras_b=ob["por_bairro"].get(b["slug"], []), obras=ob, numeros=numeros(b), n_bairros=len(validos),
                 mapinha=({"largura": mp["largura"], "altura": mp["altura"], "d": caminho_de[b["slug"]]}
                          if mp and b["slug"] in caminho_de else None),
                 zap=f"Veja como está {b['nome']} (Cariacica): esgoto, posto de saúde e fila.",
                 **previa(f"bairro-{b['slug']}", f"Meu bairro · {b['nome']}", c0["numero"],
                          f"{c0['frase']} {c0['cidade']}", "IBGE, Censo 2022"))

    if mp:
        rm = M.resumo(bs)
        rm["dens_cidade"] = round(tot["pop"] / tot["area"])
        escrever("/mapa/", "mapa.html", "Mapa de Cariacica: onde mora a gente",
                 f"{D.br(rm['total'])} pessoas em {rm['bairros']} bairros. Veja no mapa onde mora mais gente, onde é "
                 "mais apertado, onde falta esgoto e onde a renda é menor.", "mapa", m=mp, r=rm,
                 tabela=sorted(validos, key=lambda b: D.normalizar(b["nome"])),
                 zap="Mapa de Cariacica: quantas pessoas moram em cada bairro, esgoto e renda.",
                 **previa("mapa", "Mapa de Cariacica · Censo 2022", D.br(rm["total"]),
                          f"pessoas moram nos {rm['bairros']} bairros. Metade delas em só {rm['metade']} bairros.",
                          "IBGE, Censo 2022"))

    ordem = sorted(fl["unidades"], key=lambda x: D.normalizar(x["nome"]))
    data_ref = date.fromisoformat(fl["data_ref"])
    fl["data_ref_texto"] = _data_texto(data_ref)
    pf = pergunta("008949.2026-38")
    cidade_d = {"pedidos": fl["pedidos"], "mediana": fl["mediana"], "ano": fl["ano"]}
    comum["max_pedidos"] = max(x["pedidos"] for x in fl["unidades"])
    escrever("/fila/", "fila.html", "Quanto tempo se espera no seu posto?",
             f"A fila de consultas e exames com especialista em cada posto de saúde de Cariacica, {fl['mes_texto']}.",
             "fila", fila=fl, u=None, d=cidade_d, unidades_ordem=ordem, pergunta_fila=pf,
             zap="Quanto tempo se espera por consulta e exame em cada posto de Cariacica?",
             **previa("fila", "Fila da saúde · Cariacica", D.br(fl["pedidos"]),
                      "consultas e exames com especialista esperam vaga. Veja o seu posto.",
                      f"Secretaria de Saúde, {fl['mes_texto']}"))
    for u in fl["unidades"]:
        escrever(f"/fila/{u['slug']}/", "fila.html", f"Fila da saúde: {u['nome']}, Cariacica",
                 f"{u['nome']}: {D.br(u['pedidos'])} consultas e exames esperam vaga. Metade espera há "
                 f"{D.meses(u['mediana'])}.", "fila", fila=fl, u=u, d=u, unidades_ordem=ordem, pergunta_fila=pf,
                 zap=f"Fila do {u['nome']}: veja quanto tempo se espera.",
                 **previa(f"fila-{u['slug']}", f"Fila da saúde · {u['nome']}", D.br(u["pedidos"]),
                          f"consultas e exames esperam vaga. Metade espera há {D.meses(u['mediana'])}.",
                          f"Secretaria de Saúde, {fl['mes_texto']}"))

    lista_p = P.problemas(fl, cid, pad)
    for x in lista_p:
        x["cat"] = P.CAT_PROBLEMA.get(x["slug"], "seguranca")
        x["perg"] = [q for q in (pergunta(n) for n in x["perguntas"]) if q]
        vistos = set()
        x["perg"] = [q for q in x["perg"] if not (id(q) in vistos or vistos.add(id(q)))]
    escrever("/problemas/", "problemas.html", "Os maiores problemas de Cariacica",
             "Fila da saúde, bebês e grávidas, esgoto, morros, escola e creche, violência, contratos sem concorrência "
             "e pouco dinheiro próprio: o número de cada um, o que melhorou e o que o Vigia já perguntou.",
             "problemas", problemas=lista_p,
             zap="Os maiores problemas de Cariacica, com número oficial e o que já foi perguntado à prefeitura.",
             **previa("problemas", "Maiores problemas · Cariacica", f"{len(lista_p)} problemas",
                      "fila, bebês, esgoto, morros, escola, violência, contratos e dinheiro. O número de cada um.",
                      "dados oficiais"))
    for i, x in enumerate(lista_p):
        escrever(f"/problemas/{x['slug']}/", "problema.html", f"{x['titulo']} em Cariacica",
                 f"Cariacica: {x['numero']} {x['legenda']} O que melhorou, o outro lado e o que o Vigia já perguntou.",
                 "problemas", x=x, i=i + 1, total=len(lista_p), ant=lista_p[i - 1] if i else None,
                 prox=lista_p[i + 1] if i + 1 < len(lista_p) else None,
                 zap=f"Cariacica: {x['numero']} {x['legenda']}",
                 **previa(f"problema-{x['slug']}", f"Maiores problemas · {x['titulo']}", x["numero"], x["legenda"],
                          x["fontes"][0][0] if x["fontes"] else "dados oficiais"))

    ver = V.vereadores(hoje)
    perg_camara = [q for q in (pergunta("2026111226344"), pergunta("2026111273015")) if q]
    escrever("/vereadores/", "vereadores.html", "O que fizeram os 19 vereadores",
             f"Os {ver['cidade']['n']} projetos de lei dos 19 vereadores de Cariacica, separados pelo que muda na vida "
             "de quem mora aqui. E a conta: salário, gasto da Câmara e leis aprovadas.", "vereadores",
             v=ver, perguntas=perg_camara,
             zap="O que fez cada vereador de Cariacica? Veja os projetos, separados pelo que muda na vida da gente.",
             **previa("vereadores", "Os 19 vereadores de Cariacica", f"{ver['cidade']['n']} projetos de lei",
                      f"{D.de_cada(100 * ver['cidade']['cont']['concreto'] / ver['cidade']['n'])} mudam algo na "
                      f"prática. {ver['cidade']['aprovados']} foram aprovados. {ver['periodo'].capitalize()}.",
                      f"Câmara de Cariacica, {ver['coleta']}"))
    for x in ver["lista"]:
        escrever(f"/vereadores/{x['slug']}/", "vereador.html", f"{x['nome']}: projetos de lei na Câmara de Cariacica",
                 f"{x['nome']}, vereador de Cariacica: {x['n']} projetos de lei {ver['periodo']}, separados pelo que "
                 "muda na vida de quem mora aqui.", "vereadores", v=ver, x=x,
                 zap=f"Veja o que {x['nome']} apresentou na Câmara de Cariacica.",
                 # na prévia, o nome é o destaque e os números vêm na legenda, iguais para os 19: um "0" gigante
                 # com marca-texto viraria figurinha de ataque, e o Vigia não humilha ninguém
                 **previa(f"vereador-{x['slug']}", "Vereadores de Cariacica · o que cada um fez", x["nome"],
                          f"{x['n']} {'projeto' if x['n'] == 1 else 'projetos'} de lei"
                          + (f": {V.rot('concreto', x['cont']['concreto'])}, "
                             f"{V.rot('simbolico', x['cont']['simbolico'])}. {x['aprovados']} aprovados"
                             if x["n"] else "") + f". {D.br(x['pedidos'])} pedidos à prefeitura. "
                          f"{ver['periodo'].capitalize()}.", f"Câmara de Cariacica, {ver['coleta']}", destaque=False))

    partes = [dict(p) for p in F.PARTES]
    for p in partes:
        if p["id"] == "vereadores":
            p["atualiza"] = ("A Câmara bloqueia o robô. Por enquanto, copiamos os dados pelo navegador. "
                             f"A última cópia é de {ver['coleta']}.")
    escrever("/fontes/", "fontes.html", "De onde vêm os nossos números",
             "Todas as fontes do Vigia Cariacica: de onde vem cada número do site, como fazemos a conta, quando "
             "atualiza e o que o dado não mostra.", "fontes", principios=F.PRINCIPIOS, partes=partes,
             palavras=F.PALAVRAS, zap="De onde vêm os números do Vigia Cariacica: todas as fontes oficiais.")

    escrever("/perguntas/", "perguntas.html", "O que perguntamos à prefeitura",
             f"{perg['total']} perguntas oficiais à prefeitura e à Câmara de Cariacica, com prazo e resposta.",
             "perguntas", p=perg, quando=quando,
             zap="Veja o que o Vigia perguntou à prefeitura de Cariacica e quem já respondeu.",
             **previa("perguntas", "Perguntas oficiais do Vigia", f"{perg['total']} perguntas",
                      "à prefeitura, à Câmara e ao Governo do ES, com prazo para responder. Veja quem respondeu.",
                      "Lei de Acesso à Informação"))

    max_bloco = max(b["de_cada_100"] for b in g["blocos"])
    max_saude = max(s["por_morador"] for s in g["saude"])
    saude_car = next(s["por_morador"] for s in g["saude"] if s["cidade"] == "Cariacica")
    saude_top = max(g["saude"], key=lambda s: s["por_morador"])
    saude_diferenca = (saude_top["por_morador"] - saude_car) * g["populacao"] if saude_top["cidade"] != "Cariacica" else 0
    escrever("/dinheiro/", "dinheiro.html", "Para onde vai o dinheiro da prefeitura?",
             f"Em {g['ano']}, a prefeitura de Cariacica gastou o equivalente a {D.reais(round(por_morador / 12))} "
             "por mês com cada morador. Veja em quê.", "dinheiro",
             g=g, por_mes_num=D.br(round(por_morador / 12)), total_texto="R$ 1,66 bilhão",
             por_dia_texto=f"R$ {D.br(g['total'] / 365 / 1e6, 1)} milhões", max_bloco=max_bloco,
             max_saude=max_saude, saude_dia=D.br(saude_car / 365, 2), pergunta_saude=pergunta(g["pergunta_saude"]),
             saude_diferenca=saude_diferenca, saude_ref=saude_top["cidade"],
             zap="Para onde vai o dinheiro da prefeitura de Cariacica? Veja em números simples.",
             **previa("dinheiro", "Dinheiro da prefeitura", D.reais(round(por_morador / 12)),
                      f"por mês com cada morador: é o que a prefeitura gastou em {g['ano']}. Veja em quê.",
                      "Tribunal de Contas do ES e IBGE"))

    escrever("/quem-somos/", "quem.html", "Quem somos",
             "Somos moradores de Cariacica. Olhamos as contas da prefeitura e mostramos para todo mundo. Sem partido: "
             "nosso lado é o povo de Cariacica.", "quem", pergunta_saude=pergunta(g["pergunta_saude"]),
             zap="Conheça o Vigia Cariacica: moradores que olham as contas da prefeitura, sem partido.")
    red = saida / "como-trabalhamos" / "index.html"
    red.parent.mkdir(parents=True, exist_ok=True)
    red.write_text(env.get_template("redireciona.html").render(base=BASE, destino="/quem-somos/"), encoding="utf-8")
    escrever("/404.html", "404.html", "Página não encontrada", "Este endereço não existe no site do Vigia.", "404")

    # mapa do site para buscadores
    urls = "\n".join(f"<url><loc>{BASE}{c}</loc></url>" for c in relatorio if c.endswith("/"))
    (saida / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
                                       '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                                       f"{urls}\n</urlset>\n", encoding="utf-8")
    (saida / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\n")
    return relatorio


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--saida", default="_site")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rel = gerar(Path(args.saida))
    pior = min(rel.items(), key=lambda kv: kv[1]["flesch"])
    log.info("%d páginas em %s. Leitura mais difícil: %s (Flesch %.0f).", len(rel), args.saida, pior[0],
             pior[1]["flesch"])
    problemas = {c: r for c, r in rel.items() if r["jargao"] or r["julgamento"] or r["frases_longas"]}
    for c, r in list(problemas.items())[:10]:
        log.warning("%s: jargão %s, julgamento %s, frases longas %d", c, r["jargao"], r["julgamento"],
                    len(r["frases_longas"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
