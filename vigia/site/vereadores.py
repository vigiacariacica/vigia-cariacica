"""Os 19 vereadores: o que cada um apresentou, separado pelo impacto na vida de quem mora aqui, e a conta.

Dados em data/camara/:
- projetos.json: um projeto de lei por linha e por autor (projeto com dois autores aparece duas vezes), com a
  classificação de impacto feita pelo Vigia lendo a ementa.
- producao_vereadores.json: o total de cada vereador por tipo de papel (pedidos à prefeitura, moções, títulos).
- fonte.json: data da coleta, salário do cargo, gasto da Câmara e de onde veio cada número.

Regras: mesma régua para os 19, ordem alfabética, sem partido e sem ranking. A conta em reais é feita pela
Câmara inteira (gasto ÷ leis aprovadas). Para cada vereador, o salário do cargo fica ao lado do que ele
apresentou, sem dividir um pelo outro (ver docs/DECISOES.md, decisão de 12/11/2026).
"""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import date

from . import dados as D

PASTA = D.DADOS / "camara"
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
         "novembro", "dezembro"]

# chave, nome no arquivo, nome no site, o que quer dizer
NIVEIS = [
    ("concreto", "Efeito concreto", "Muda algo na prática",
     "Cria uma regra, um serviço ou uma obrigação que vale na cidade."),
    ("fraco", "Efeito fraco", "Muda pouco",
     "Cria um programa ou um incentivo, mas sem obrigação, prazo ou dinheiro."),
    ("simbolico", "Simbólico", "Simbólico",
     "Data no calendário, nome de rua, título, campanha ou selo de utilidade pública."),
    ("barrado", "Provavelmente inconstitucional", "Pode ser barrado",
     "O assunto é do governo federal ou só o prefeito pode propor. A Justiça já derrubou leis assim."),
    ("sem", "Ementa não permite avaliar", "Sem como saber",
     "O resumo só diz que muda outra lei, sem dizer o quê."),
]
POR_NOME = {n[1]: n[0] for n in NIVEIS}
ROTULOS = {"concreto": ("muda algo na prática", "mudam algo na prática"), "fraco": ("muda pouco", "mudam pouco"),
           "simbolico": ("é simbólico", "são simbólicos"), "barrado": ("pode ser barrado", "podem ser barrados"),
           "sem": ("sem como saber", "sem como saber")}


def rot_palavras(chave: str, n: int) -> str:
    um, varios = ROTULOS[chave]
    return um if n == 1 else varios


def rot(chave: str, n: int) -> str:
    """'13 mudam algo na prática', '1 muda pouco'."""
    return f"{n} {rot_palavras(chave, n)}"
EXEMPLOS = {   # exemplos reais, com o número do projeto para quem quiser conferir
    "concreto": ("Banheiro químico nas feiras livres", "PL 186/2025"),
    "fraco": ("Programa de incentivo ao ensino de Libras nas escolas", "PL 168/2026"),
    "simbolico": ("Dia municipal de conscientização de uma doença", "PL 347/2025"),
    "barrado": ("Trocar multa de trânsito por doação de sangue", "PL 363/2025"),
}
SITUACAO = {"Virou lei": "Virou lei", "Virou resolução": "Virou resolução", "Vetado pelo prefeito": "Vetado",
            "Em análise": "Em análise", "Arquivado/encerrado": "Arquivado", "Pronto para plenário": "Pronto para votar"}
# cor do selo de cada situação (estilo.css): verde cheio, verde claro, amarelo, cinza; o resto, azul
COR_SITUACAO = {"Virou lei": "cheio", "Virou resolução": "cheio", "Aprovado pela Câmara": "ok",
                "Vetado pelo prefeito": "parcial", "Arquivado/encerrado": "apagado"}
JA_VALE = {"Virou lei", "Virou resolução"}
# aprovado pela Câmara (votação final registrada): já vale, foi vetado pelo prefeito ou ainda não tem lei publicada
APROVADO = JA_VALE | {"Aprovado pela Câmara", "Vetado pelo prefeito"}
RESOLUCAO = "Projeto de Resolução"   # resolução não vai à sanção do prefeito e não vira lei: é promulgada pela Câmara
A_CLASSIFICAR = "A classificar"     # projeto novo que o Vigia ainda não leu (ferramentas/camara_producao.py)

# "Leis que mudam a sua vida": o tema sai de palavras do resumo oficial, testadas nesta ordem (a primeira que bate
# vale). Sem nenhuma, "Outros". Mostrados na ordem de ORDEM_TEMAS, sempre a mesma: não é ranking.
TEMAS = [
    ("camara", "Regras da própria Câmara", r"SERVIDORES DA C[ÂA]MARA|DECORO PARLAMENTAR|REGIMENTO INTERNO"),
    ("animais", "Animais", r"\bANIMA(IS|L)\b"),
    ("deficiencia", "Pessoa com deficiência, autismo e idoso",
     r"DEFICI[ÊE]NCIA|AUTIS|\bTEA\b|CADEIRAS? DE RODAS|MOBILIDADE REDUZIDA|ACESSIBILIDADE|\bLIBRAS\b|IDOS[OA]S?\b"),
    ("crianca", "Criança e escola", r"CRIAN[ÇC]A|INFANT|ADOLESCENTE|ESCOLA|ENSINO|ALUNO|CRECHE|ESTUDANTE"),
    ("saude", "Saúde", r"SA[ÚU]DE|M[ÉE]DIC|C[ÂA]NCER|HEMODI[ÁA]LISE|PARTURIENTE|\bSUS\b|BRONZEAMENTO|MEDICAMENTO|"
                       r"HOSPITA|VACINA|DOEN[ÇC]A|PACIENTE"),
    ("cidade", "Cidade e trânsito", r"TR[ÂA]NSITO|BICICLETA|TRANSPORTE|PASSAGEIRO|T[ÁA]XI|[ÔO]NIBUS|FEIRAS?\b|"
                                    r"RES[ÍI]DUOS|\bLIXO\b|COLETA|CAL[ÇC]ADA|\bRUAS?\b|VIAS? P[ÚU]BLICAS?|"
                                    r"EQUIPAMENTOS P[ÚU]BLICOS|ESTACIONAMENTO|\bOBRAS?\b|ILUMINA[ÇC][ÃA]O|"
                                    r"\bPRA[ÇC]AS?\b|ESGOTO|ALAGAMENTO|SINALIZA[ÇC]"),
]
NOME_TEMA = {k: nome for k, nome, _ in TEMAS} | {"outros": "Outros"}
NOTA_TEMA = {"camara": "Valem só dentro da Câmara."}
ORDEM_TEMAS = ["crianca", "saude", "deficiencia", "animais", "cidade", "outros", "camara"]
TIPOS = [("Projeto de Lei", "de lei"), ("Projeto de Lei Complementar", "de lei complementar"),
         (RESOLUCAO, "de resolução")]


def tema(ementa: str) -> str:
    e = ementa.upper()
    return next((k for k, _, rx in TEMAS if re.search(rx, e)), "outros")


def _n(n: int, um: str, varios: str) -> str:
    return um if n == 1 else varios


def _junta(partes: list[str]) -> str:
    return partes[0] if len(partes) == 1 else ", ".join(partes[:-1]) + " e " + partes[-1]


def tipos_txt(projetos: list[dict]) -> str:
    """'de lei, de lei complementar e de resolução': só os tipos que aparecem, na ordem de TIPOS."""
    tem = {p["tipo"] for p in projetos}
    return _junta([t for k, t in TIPOS if k in tem]) if tem else ""


def sem_lei(p: dict) -> str:
    """Aprovado pela Câmara, mas o sistema ainda não mostra a norma. Não dizemos "espera a sanção": pode ter havido
    sanção tácita, promulgação ou veto derrubado sem registro, e resolução nem vai à sanção."""
    return "Aprovado, sem resolução publicada" if p["tipo"] == RESOLUCAO else "Aprovado, sem lei publicada"


def selo_lei(p: dict) -> tuple[str, str]:
    """(texto, cor) da situação de um projeto aprovado, para o bloco "Leis que mudam a sua vida"."""
    if p["status"] in JA_VALE:
        return "Já vale", "cheio"
    if p["status"] == "Vetado pelo prefeito":
        return ("Vetado em parte" if p.get("veto") == "parcial" else "Vetado pelo prefeito"), "parcial"
    return sem_lei(p), "ok"


def lei_curta(lei: str) -> str:
    """'Lei Ordinária 6.765/2025' -> 'Lei 6.765/2025'. Norma sem número no sistema -> ''."""
    if not re.search(r"\d", lei or ""):
        return ""
    return re.sub(r"\bLei Ordinária\b", "Lei", lei)


def frases_leis(total: int, vale: int, vetado: int, sem: int, ate: str) -> tuple[str, str]:
    """A abertura do bloco, com a concordância certa para qualquer número."""
    partes = []
    if vale:
        partes.append(f"{vale} já {_n(vale, 'vale', 'valem')}")
    if vetado:
        partes.append(f"{vetado} {_n(vetado, 'foi vetado', 'foram vetados')} pelo prefeito")
    lead = (f"{_n(total, 'Do', 'Dos')} {total} {_n(total, 'projeto aprovado', 'projetos aprovados')} que "
            f"{_n(total, 'muda', 'mudam')} algo na prática, " + (_junta(partes) if partes else "nenhum vale ainda") + ".")
    if not sem or not partes:
        return lead, ""
    return lead, (f"{_n(sem, 'Mais', 'Outros')} {sem} {_n(sem, 'está', 'estão')} sem lei ou resolução publicada no "
                  f"sistema até {ate}.")


def tempo(inicio: date, fim: date) -> str:
    """Quanto tempo passou, como se fala: 'quase 2 anos', '2 anos', 'mais de 2 anos'."""
    anos = (fim - inicio).days / 365.25
    f, resto = int(anos), anos - int(anos)
    if resto > 11 / 12:                  # menos de 1 mês para fechar o ano
        f, resto = f + 1, 0
    if resto < 1 / 12 and f:
        return f"{f} {_n(f, 'ano', 'anos')}"
    if resto >= 0.75:
        return f"quase {f + 1} {_n(f + 1, 'ano', 'anos')}"
    return f"mais de {f} {_n(f, 'ano', 'anos')}" if f else "menos de 1 ano"


SIGLAS = ["SUS", "CRAS", "CREAS", "CAPS", "UBS", "APP", "TEA", "PcD", "ECA", "LGBTQIAPN+", "IPTU", "ISS", "EJA",
          "RENAME"]
NOMES = ["Cariacica", "Espírito Santo", "Vitória", "Vila Velha", "Serra", "Viana", "Brasil", "Maria da Penha",
         "Câmara Municipal", "Libras", "Moxuara", "Guarda Municipal", "Heimlich"]


def _ler(nome: str):
    return json.loads((PASTA / nome).read_text(encoding="utf-8"))


def reais_falado(v: float) -> str:
    """76.413.310 -> 'R$ 76,4 milhões'; 1.389.333 -> 'R$ 1,4 milhão'; 297.000 -> 'R$ 297 mil'."""
    if v >= 1e6:
        m = v / 1e6
        txt = D.br(m, 1) if m < 100 else D.br(round(m))
        txt = txt.removesuffix(",0")
        return f"R$ {txt} {'milhão' if txt.split(',')[0] == '1' else 'milhões'}"
    if v >= 1e3:
        return f"R$ {D.br(round(v / 1e3))} mil"
    return D.reais(v)


def ementa_simples(t: str) -> str:
    """Ementa oficial em letra normal (o sistema da Câmara grava tudo em maiúsculas), sem o 'e dá outras
    providências'. O texto continua o oficial; só muda a caixa das letras."""
    t = re.sub(r"^\s*(EMENTA|PROJETO DE LEI LEGISLATIVO)\s*:\s*", "", t.strip(), flags=re.I)
    # aspas do fim sem par ('… E DÁ OUTRAS PROVIDÊNCIAS”.'): a de abertura já saiu na coleta; as que fecham um nome
    # ('A “FEIRA EXPO”.') ficam
    fim = re.search(r'\s*([”"])\s*\.?\s*$', t)
    if fim and (t.count("“") < t.count("”") if fim.group(1) == "”" else t.count('"') % 2 == 1):
        t = t[:fim.start()]
    t = re.sub(r",?\s*E\s+D[ÁA](\s+OUTRAS(\s+PROVID\w*)?)?\.?\s*$", "", t, flags=re.I)
    # ementa cortada pelo sistema no meio do "e dá outras providências": "…Cariacica e dá outr…"
    t = re.sub(r"[,\s]+E(\s+D[ÁA]?(\s+O\w*(\s+P\w*)?)?)?\s*…$", "…", t, flags=re.I).strip().rstrip(".,;")
    if not t:
        return ""
    s = t.lower()
    s = s[0].upper() + s[1:]
    s = re.sub(r'([“"«])(\w)', lambda m: m.group(1) + m.group(2).upper(), s)
    for n in NOMES:
        s = re.sub(rf"(?<!\w){re.escape(n.lower())}(?!\w)", n, s)
    for g in SIGLAS:
        s = re.sub(rf"(?<!\w){re.escape(g.lower())}(?!\w)", g, s)
    s = re.sub(r"/es\b", "/ES", s)
    return s


def _contagem(projetos: list[dict]) -> dict:
    c = Counter(POR_NOME.get(p["utilidade"], "sem") for p in projetos)
    return {k: c.get(k, 0) for k, *_ in NIVEIS}


def _pilha(cont: dict, total: int) -> list[dict]:
    """Pedaços da barra de impacto, em %, que somam 100."""
    if not total:
        return []
    return [{"chave": k, "nome": nome, "n": cont[k], "pct": round(100 * cont[k] / total, 2)}
            for k, _, nome, _ in NIVEIS if cont[k]]


def _cem(cont: dict, total: int) -> list[str]:
    """100 quadradinhos coloridos por nível (maiores restos), para 'se fossem 100 projetos'."""
    if not total:
        return []
    bruto = {k: 100 * cont[k] / total for k in cont}
    base = {k: int(v) for k, v in bruto.items()}
    falta = 100 - sum(base.values())
    for k in sorted(bruto, key=lambda k: bruto[k] - base[k], reverse=True)[:falta]:
        base[k] += 1
    return [k for k, *_ in NIVEIS for _ in range(base[k])]


def _parte(n: int, total: int) -> str:
    """'3 de cada 10' quando há projetos bastantes; '1 de 3' quando são poucos."""
    if total < 10:
        return f"{n} de {total}"
    return D.de_cada(100 * n / total)


def vereadores(hoje: date | None = None) -> dict:
    meta = _ler("fonte.json")
    resumo = {r["vereador"]: r for r in _ler("producao_vereadores.json")}
    linhas = _ler("projetos.json")
    unicos_cidade = _ler("cidade.json")
    coleta = date.fromisoformat(meta["coletado_em"])
    inicio = date.fromisoformat(meta["periodo_inicio"])
    meses = (coleta.year - inicio.year) * 12 + coleta.month - inicio.month   # meses fechados até a coleta
    salario_periodo = meta["salario_mensal"] * meses

    por_ver: dict[str, list[dict]] = {nome: [] for nome in resumo}
    unicos: dict[str, dict] = {}
    autores: Counter = Counter()
    for p in linhas:
        p = dict(p)
        p["nivel"] = POR_NOME.get(p["utilidade"], "sem")      # "A classificar" fica em "Sem como saber"
        p["novo"] = p["utilidade"] == A_CLASSIFICAR
        p["situacao"] = SITUACAO.get(p["status"], p["status"])
        if p["status"] == "Vetado pelo prefeito" and p.get("veto") == "parcial":
            p["situacao"] = "Vetado em parte"
        elif p["status"] == "Aprovado pela Câmara":
            p["situacao"] = sem_lei(p)
        p["lei_curta"] = lei_curta(p.get("lei", ""))
        p["cor"] = COR_SITUACAO.get(p["status"], "neutro")
        p["ementa_txt"] = ementa_simples(p["ementa"])
        p["data_txt"] = f"{p['data'][8:10]}/{p['data'][5:7]}/{p['data'][:4]}"
        por_ver.setdefault(p["vereador"], []).append(p)
        unicos.setdefault(p["numero"], p)
        autores[p["numero"]] += 1

    lista = []
    for nome in sorted(por_ver, key=D.normalizar):
        ps = sorted(por_ver[nome], key=lambda p: p["data"], reverse=True)
        for p in ps:
            p["coautoria"] = autores[p["numero"]] > 1
        r = resumo.get(nome, {})
        cont = _contagem(ps)
        aprov = [p for p in ps if p["status"] in APROVADO]
        avaliados = len(ps) - cont["sem"]
        lista.append({
            "nome": nome, "slug": D.slug(nome), "n": len(ps), "cont": cont, "pilha": _pilha(cont, len(ps)),
            "aprovados": len(aprov), "concreto_aprovado": sum(1 for p in aprov if p["nivel"] == "concreto"),
            "ja_vale": sum(1 for p in aprov if p["status"] in JA_VALE),
            "vetados": sum(1 for p in aprov if p["status"] == "Vetado pelo prefeito"),
            "tipos": tipos_txt(ps), "um_tipo": len({p["tipo"] for p in ps}) <= 1,
            "pronto": sum(1 for p in ps if p["status"] == "Pronto para plenário"),
            "parte_concreto": _parte(cont["concreto"], avaliados) if avaliados else "",
            "pedidos": r.get("indicacoes", 0), "homenagens": r.get("titulos_mocoes", 0),
            "projetos": ps,
            "grupos": [{"chave": k, "nome": nm, "itens": [p for p in ps if p["nivel"] == k],
                        "o_que": oq + (" Ou o projeto é novo e ainda vamos ler o resumo." if k == "sem" and any(
                            p["novo"] for p in ps if p["nivel"] == k) else "")}
                       for k, _, nm, oq in NIVEIS],
        })

    todos = list(unicos.values())
    cont = _contagem(todos)
    aprov = [p for p in todos if p["status"] in APROVADO]
    cont_aprov = _contagem(aprov)
    datas = [p for p in aprov if re.search(r"\bDIA\b|\bSEMANA\b|\bM[ÊE]S\b|CALEND[ÁA]RIO", p["ementa"].upper())]
    gasto = sum(meta["gasto_camara"].values())
    gasto_ate = date.fromisoformat(meta["gasto_camara_ate"])
    cidade = {
        "n": len(todos), "cont": cont, "cem": _cem(cont, len(todos)), "pilha": _pilha(cont, len(todos)),
        "aprovados": len(aprov), "cont_aprov": cont_aprov, "pilha_aprov": _pilha(cont_aprov, len(aprov)),
        "ja_vale": sum(1 for p in aprov if p["status"] in JA_VALE),
        "sem_lei": sum(1 for p in aprov if p["status"] == "Aprovado pela Câmara"),
        "vetados": sum(1 for p in aprov if p["status"] == "Vetado pelo prefeito"),
        "tipos": tipos_txt(todos),
        "datas_aprov": len(datas), "parte_datas_aprov": D.de_cada(100 * len(datas) / len(aprov)),
        "parte_aprovados": D.de_cada(100 * len(aprov) / len(todos)),
        "parte_simb_aprov": D.de_cada(100 * cont_aprov["simbolico"] / len(aprov)),
        "parte_conc_aprov": D.de_cada(100 * cont_aprov["concreto"] / len(aprov)),
        # papel com vários autores conta uma vez na conta da cidade (cidade.json, de ferramentas/camara_producao.py)
        "pedidos": unicos_cidade["indicacoes"], "homenagens": unicos_cidade["homenagens"],
        "titulos_cidadao": unicos_cidade["titulos_cidadao"],
        "coautoria": sum(1 for v in autores.values() if v > 1),
        "novos": sum(1 for p in todos if p["novo"]),
    }
    cidade["sem_resumo"] = cont["sem"] - cidade["novos"]

    # Leis que mudam a sua vida: aprovados que mudam algo na prática, cada projeto uma vez, por tema
    conc = [p for p in aprov if p["nivel"] == "concreto"]
    for p in conc:
        p["tema"], p["selo_lei"] = tema(p["ementa"]), selo_lei(p)
    leis = {"total": len(conc), "vale": sum(1 for p in conc if p["status"] in JA_VALE),
            "vetado": sum(1 for p in conc if p["status"] == "Vetado pelo prefeito"),
            "sem_lei": sum(1 for p in conc if p["status"] == "Aprovado pela Câmara"),
            "grupos": [{"chave": k, "nome": NOME_TEMA[k], "nota": NOTA_TEMA.get(k, ""),
                        "itens": sorted((p for p in conc if p["tema"] == k), key=lambda p: p["data"], reverse=True)}
                       for k in ORDEM_TEMAS if any(p["tema"] == k for p in conc)]}
    leis["lead"], leis["resto"] = frases_leis(leis["total"], leis["vale"], leis["vetado"], leis["sem_lei"],
                                              coleta.strftime("%d/%m/%Y"))
    conta = {
        "salario_mes": D.reais(meta["salario_mensal"]), "meses": meses,
        # valores com todos os zeros (o tamanho tem que pesar) e, ao lado, como se lê
        "salario_periodo": D.reais_cheio(salario_periodo), "salario_periodo_exato": D.reais(salario_periodo),
        "salario_19": D.reais_cheio(salario_periodo * len(lista)),
        "salario_19_ext": D.extenso(salario_periodo * len(lista)),
        "gabinete": D.reais_cheio(meta["gabinete_teto_mensal"]), "gabinete_lei": meta["gabinete_teto_lei"],
        "gasto": D.reais_cheio(gasto), "gasto_ext": D.extenso(gasto), "gasto_exato": D.reais(round(gasto)),
        "gasto_ate": gasto_ate.strftime("%d/%m/%Y"),
        "por_lei": D.reais_cheio(gasto / len(aprov)), "por_lei_ext": D.extenso(gasto / len(aprov)),
        "por_lei_concreta": D.reais_cheio(gasto / cont_aprov["concreto"]) if cont_aprov["concreto"] else "",
        "por_lei_concreta_ext": D.extenso(gasto / cont_aprov["concreto"]) if cont_aprov["concreto"] else "",
        "por_morador": D.br(meta["gasto_por_morador_2025"], 2),
        "gasto_anos": {a: D.reais(round(v)) for a, v in meta["gasto_camara"].items()},
    }
    return {"lista": lista, "cidade": cidade, "conta": conta, "meta": meta, "niveis": NIVEIS, "leis": leis,
            "exemplos": EXEMPLOS, "coleta": coleta.strftime("%d/%m/%Y"), "tempo": tempo(inicio, coleta),
            "periodo": f"de janeiro de {inicio.year} a {coleta.day} de {MESES[coleta.month - 1]} de {coleta.year}"}
