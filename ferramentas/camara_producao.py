"""O que os 19 vereadores apresentaram e o que virou lei, direto do sistema oficial da Câmara (Câmara Sem Papel).

    python ferramentas/camara_producao.py baixar <pasta>   # CSVs oficiais (exportação "CSV" da própria consulta)
    python ferramentas/camara_producao.py montar <pasta>   # gera data/camara/projetos.json e producao_vereadores.json
    python ferramentas/camara_producao.py resumo [arquivo] # o que mudou e quantos estão "A classificar" (Actions)

O que cada etapa faz:
- baixar: para cada vereador da legislatura (página "Vereadores"), a consulta "Proposições apresentadas" de cada ano
  desde 2025 e a consulta "Leis de sua autoria"; para cada lei desde 2025, a página da norma, que diz o projeto de
  origem. Nada de navegador: são as mesmas consultas públicas do site, com o botão "CSV".
- montar: um projeto de lei por linha e por autor (coautoria aparece para cada autor), com a situação lida assim:
  "Virou lei" quando o projeto é a origem de uma lei no cadastro oficial; "Virou resolução" no projeto de resolução
  (não vai à sanção do prefeito: a Câmara promulga); "Aprovado pela Câmara" quando a votação final está registrada e
  o sistema ainda não mostra a norma; "Vetado pelo prefeito"; "Arquivado/encerrado"; "Pronto para plenário";
  "Em análise".
  A classificação por impacto (coluna "utilidade") é do Vigia, feita lendo a ementa: é mantida de uma coleta para
  a outra e, para projeto novo, vem de data/camara/classificacao_extra.json (ou fica "A classificar").

Por que "Virou lei" vem do cadastro de leis e não da fase: depois que a lei sai, o sistema muda a fase do projeto
para "Arquivamento". Até 24/11/2026 o site lia essa fase como arquivado (ver docs/DECISOES.md).
"""
from __future__ import annotations

import csv
import html
import http.cookiejar
import io
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CAMARA = RAIZ / "data" / "camara"
SPL = "https://cariacica.camarasempapel.com.br/spl/"
LEG = "https://cariacica.camarasempapel.com.br/legislacao/"
UA = {"User-Agent": "Mozilla/5.0 (vigia-cariacica; leitura de dados publicos)"}
ANOS = (2025, 2026)
EXECUTIVO = "125"     # autor "Executivo Municipal" no sistema (vetos do prefeito)
TIPOS_PL = {"Projeto de Lei Legislativo": ("PL", "Projeto de Lei"),
            "Projeto de Lei Complementar Legislativo": ("PLC", "Projeto de Lei Complementar"),
            "Projeto de Lei Complementar": ("PLC", "Projeto de Lei Complementar"),
            "Projeto de Resolução": ("PR", "Projeto de Resolução")}
FASE_APROVADO = {"Aguardando Sanção do Executivo", "Para Encaminhar Autógrafo", "Elaborar Autógrafo",
                 "Aguardando Resultado do Veto", "Elaborar Resolução"}
FASE_ARQUIVO = {"Arquivamento", "Arquivar Proposição", "Para Ciência ao Autor"}
FASE_PLENARIO = {"Incluir Proposição na Ordem do Dia", "Incluir Proposição no Expediente", "Leitura-PLL"}
# Veto do prefeito que não conta como aprovação até a Câmara confirmar (vazio hoje). O PL 169/2025 esteve aqui:
# conferido em 25/11/2026 nas atas 67 e 68 (aprovado em 2ª discussão em 19/11/2025) e na mensagem 111/2025, que veta
# o autógrafo 121/2025 desse projeto; o pedido de arquivamento do autor veio depois das votações.
VETO_A_CONFERIR: set = set()


# ---------------------------------------------------------------- baixar
def _abrir(op, url, dados=None):
    req = urllib.request.Request(url, data=dados, headers=UA)
    for tent in range(4):
        try:
            with op.open(req, timeout=90) as r:
                return r.read()
        except Exception:  # noqa: BLE001 - rede instável: tenta de novo
            if tent == 3:
                raise
            time.sleep(3 * (tent + 1))


def _exportar_csv(url: str) -> bytes:
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    t = _abrir(op, url).decode("utf-8", "replace")
    campos = {}
    for tag in re.findall(r'<input[^>]+type="hidden"[^>]*>', t):
        n, v = re.search(r'name="([^"]+)"', tag), re.search(r'value="([^"]*)"', tag)
        if n:
            campos[n.group(1)] = html.unescape(v.group(1)) if v else ""
    campos["ctl00$ContentPlaceHolder1$btn_export_csv"] = "CSV"
    return _abrir(op, url, urllib.parse.urlencode(campos).encode())


def baixar(pasta: Path) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    t = _abrir(urllib.request.build_opener(), SPL + "parlamentares.aspx").decode("utf-8", "replace")
    autores = {}
    for m in re.finditer(r"consulta-producao\.aspx\?autor=(\d+)", t):
        resto = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t[m.end(): m.end() + 4000])))
        n = re.search(r"Fale com [ao] Vereador[a]? ([^()]+?) \(", resto)
        if n and m.group(1) not in autores:
            autores[m.group(1)] = n.group(1).strip()
    (pasta / "autores.json").write_text(json.dumps(autores, ensure_ascii=False, indent=1), encoding="utf-8")
    for aid in autores:
        for ano in ANOS:
            (pasta / f"prod_{aid}_{ano}.csv").write_bytes(
                _exportar_csv(SPL + f"consulta-producao.aspx?autor={aid}&ano_proposicao={ano}"))
            time.sleep(1)
        (pasta / f"leis_{aid}.csv").write_bytes(_exportar_csv(LEG + f"consulta-legislacao.aspx?autor={aid}"))
        time.sleep(1)
    for ano in ANOS:          # mensagens de veto do prefeito
        (pasta / f"prod_{EXECUTIVO}_{ano}.csv").write_bytes(
            _exportar_csv(SPL + f"consulta-producao.aspx?autor={EXECUTIVO}&ano_proposicao={ano}"))
    origem = {}
    for lei in _leis(pasta, autores).values():
        try:
            pag = _abrir(urllib.request.build_opener(), LEG + f"norma.aspx?id={lei['cod']}").decode("utf-8", "replace")
        except Exception:  # noqa: BLE001 - código de norma quebrado no CSV: fica sem origem
            origem[lei["cod"]] = None
            continue
        m = re.search(r"processo\.aspx\?id=(\d+)'[^>]*>(?:\s*<[^>]+>)*\s*([^<]+)</a>", pag)
        origem[lei["cod"]] = m.group(1) if m else None
        time.sleep(0.5)
    (pasta / "leis_origem.json").write_text(json.dumps(origem, indent=0), encoding="utf-8")
    # a página de cada projeto: "Norma resultante" e o histórico (votação, sanção, veto)
    processos = {}
    for x in _producao(pasta, autores):
        if x["tipo"] in TIPOS_PL and x["id"] not in processos:
            pag = _abrir(urllib.request.build_opener(), SPL + f"processo.aspx?id={x['id']}").decode("utf-8", "replace")
            processos[x["id"]] = _so_texto(pag)
            time.sleep(0.4)
    (pasta / "processos.json").write_text(json.dumps(processos, ensure_ascii=False), encoding="utf-8")
    (pasta / "coleta.json").write_text(json.dumps({"coletado_em": date.today().isoformat()}), encoding="utf-8")
    print(f"{len(autores)} vereadores baixados em {pasta}")


def _so_texto(t: str) -> str:
    """Página do processo em texto, campos separados por " | " (do jeito que _estado_processo lê)."""
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", t, flags=re.S)
    x = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " | ", t)))
    x = re.sub(r"(\s*\|\s*)+", " | ", x)
    a = x.find("Data de apresenta")
    return x[a:] if a >= 0 else x[-20000:]


def _estado_processo(p: str) -> dict:
    """O que a página do projeto diz: norma resultante, votação final aprovada, sanção ou promulgação."""
    acoes = []
    for trecho in p.split("| Recebimento: |")[1:]:
        f = re.search(r"Fase: \| ([^|]+) \|", trecho)
        a = re.search(r"Ação: \| ([^|]+) \|", trecho)
        acoes.append(((f.group(1).strip() if f else ""), (a.group(1).strip() if a else "")))
    norma = re.search(r"Norma resultante \| ([^|]+) \|", p)
    feitas = {a for _, a in acoes}
    return {"norma": norma.group(1).strip() if norma else "",
            "votado": any(a == "Proposição Aprovada" and ("2ª Discuss" in f or f.startswith("Para Discussão e Votação-PR"))
                          for f, a in acoes),
            "sancionado": bool(feitas & {"Sancionado", "Promulgado", "Sanção Tácita"})}


def tipo_veto(e: str) -> str:
    """"VETA PARCIALMENTE" (e o erro de digitação "VETAR PACIALMENTE", mensagem 007/2026) é parcial; o resto diz
    "VETA TOTALMENTE", "VETA O AUTÓGRAFO" ou "DECIDI VETAR TOTALMENTE". Só vale a palavra logo depois do verbo:
    "VETA TOTALMENTE ... QUE ALTERA PARCIALMENTE A LEI" é total (mensagem 057/2025, PL 81/2025)."""
    return "parcial" if re.search(r"\bVETA\w*\s+PAR?CIAL", e.upper()) else "total"


def _vetos(pasta: Path) -> dict[tuple[str, str, str], str]:
    """Mensagens de veto do prefeito -> (sigla, número, ano) do projeto do vereador: "total" ou "parcial".
    A sigla entra na chave porque PL 1/2026 e PLC 1/2026 são projetos diferentes; resolução não tem veto."""
    if not (pasta / f"prod_{EXECUTIVO}_{ANOS[0]}.csv").exists():
        return {}
    out = {}
    for x in _producao(pasta, {EXECUTIVO: "Executivo Municipal"}):
        if x["tipo"] != "Veto":
            continue
        e = re.sub(r"\s+", " ", x["ementa"]).upper()
        if "EXECUTIVO N" in e:          # veto a emenda em projeto do próprio prefeito
            continue
        m = re.search(r"(?:PROJETO|JOJETO|PROTEJOTO|PL)[^0-9]*?N?[°º\.]?\s*(\d+)/(\d{4})", e)
        if m:
            sigla = "PLC" if "COMPLEMENTAR" in m.group(0) else "PL"
            out[(sigla, m.group(1).lstrip("0"), m.group(2))] = tipo_veto(e)
    return out


# ---------------------------------------------------------------- ler
def _texto(b: bytes) -> str:
    try:
        return b.decode("utf-8-sig")
    except UnicodeDecodeError:
        return b.decode("cp1252")


REGISTRO = re.compile(r"^(\d+),(\d+),(\d{4}),([^,]+),(\d+),(\d{4}),(.*),(\d+),(.*?),(\d\d/\d\d/\d{4}),(.*),([^,]*),"
                      r"(Sim|Não),([^,]*)$", re.S)
CAMPOS = ["id", "processo", "ano", "tipo", "num", "ano2", "ementa", "protocolo", "autor", "data", "fase", "setor",
          "arquivado", "situacao"]


def _producao(pasta: Path, autores: dict) -> list[dict]:
    """O CSV oficial não põe aspas na ementa: junta as linhas de cada registro e separa pelos campos das pontas."""
    linhas = []
    for aid, nome in autores.items():
        for ano in ANOS:
            regs, atual = [], None
            for ln in _texto((pasta / f"prod_{aid}_{ano}.csv").read_bytes()).splitlines()[1:]:
                if re.match(r"^\d{5,7},\d+,20\d\d,", ln):
                    if atual is not None:
                        regs.append(atual)
                    atual = ln
                elif atual is not None:
                    atual += " " + ln
            if atual is not None:
                regs.append(atual)
            for reg in regs:
                m = REGISTRO.match(reg.strip())
                if not m:
                    raise ValueError(f"registro não lido em prod_{aid}_{ano}.csv: {reg[:80]}")
                d = dict(zip(CAMPOS, (g.strip() for g in m.groups())))
                d["vereador_id"], d["ano_consulta"] = aid, ano
                linhas.append(d)
    # o CSV oficial às vezes repete o mesmo papel no arquivo de um autor (Indicação 1290/2025, id 125895, em
    # 24/11/2026): cada id conta uma vez por autor
    vistos, unicas = set(), []
    for d in linhas:
        if (d["vereador_id"], d["id"]) not in vistos:
            vistos.add((d["vereador_id"], d["id"]))
            unicas.append(d)
    return unicas


def _leis(pasta: Path, autores: dict) -> dict:
    leis = {}
    for aid in autores:
        b = (pasta / f"leis_{aid}.csv").read_bytes()
        if b.lstrip()[:1] == b"<":          # vereador sem lei: o sistema devolve a página, não o CSV
            continue
        for r in csv.DictReader(io.StringIO(_texto(b))):
            dd, mm, aa = r["Data"].split("/")
            if int(aa) < ANOS[0]:
                continue
            leis[r["cod"]] = {"cod": r["cod"], "nome": f'{r["Lei"]} {int(r["Numero"]):,}/{r["Ano"]}'.replace(",", "."),
                              "data": f"{aa}-{mm}-{dd}", "ementa": r["Ementa"]}
    return leis


# ---------------------------------------------------------------- montar
def _chave(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z ]", "", s).strip()


def _situacao(x: dict, virou_lei: bool, est: dict | None, veto: str | None) -> str:
    """Com a página do projeto (est), aprovado é o que tem a votação final registrada no histórico. Vetado é o que
    recebeu mensagem de veto do prefeito e ainda não virou lei: o veto é sobre o autógrafo, que só existe depois da
    aprovação, então conta como aprovado mesmo sem a votação na página (PL 113/2025 e PL 153/2026, 24/11/2026).
    Sem a página, vale a fase."""
    if virou_lei:
        return "Virou resolução" if x["tipo"] == "Projeto de Resolução" else "Virou lei"
    if veto:
        return "Vetado pelo prefeito"
    if est is not None:
        if est["votado"]:
            return "Aprovado pela Câmara"
    elif x["fase"] in FASE_APROVADO:
        return "Aprovado pela Câmara"
    if x["situacao"] == "ARQUIVADO" or x["fase"] in FASE_ARQUIVO:
        return "Arquivado/encerrado"
    if x["fase"] in FASE_PLENARIO or "Discussão e Votação" in x["fase"]:
        return "Pronto para plenário"
    return "Em análise"


def _categoria(ementa: str) -> str:
    e = ementa.upper()
    if re.search(r"UTILIDADE P[ÚU]BLICA", e):
        return "Utilidade pública"
    if re.search(r"DENOMIN|PASSAR[ÁA] A (SE )?CHAMAR|D[ÁA] NOME", e):
        return "Nome de rua/local"
    if re.search(r"\bDIA (MUNICIPAL|DO|DA|DE)\b|\bSEMANA\b|\bM[ÊE]S\b|CALEND[ÁA]RIO", e):
        return "Data comemorativa"
    return "Política pública/regra"


def _homenagem(x: dict) -> bool:
    """Decreto legislativo que concede título, comenda, medalha ou honra ao mérito, e moção de aplauso ou
    congratulação. Moção de pesar não entra."""
    e = x["ementa"].upper()
    if x["tipo"] == "Projeto de Decreto Legislativo":
        return bool(re.search(r"CIDAD[ÃA]|COMENDA|MEDALHA|HONRA|M[ÉE]RITO|DIPLOMA|T[ÍI]TULO", e))
    if x["tipo"] == "Moção":
        # moção que concede "Título de Cidadão Cariaciquense" também é homenagem (24/11/2026)
        return "PESAR" not in e and not re.search(r"REP[ÚU]DIO", e) and bool(re.search(
            r"APLAUSO|CONGRATULA|LOUVOR|PARAB|RECONHEC|HOMENAG|AGRADEC|M[ÉE]RITO|T[ÍI]TULO|CIDAD[ÃA]", e))
    return False


def _sem_rodape(e: str) -> str:
    e = re.sub(r"E D[ÁA] OUTRAS PROVID\w*|EMENTA:", "", e.upper())
    return re.sub(r"[^A-Z0-9ÁÉÍÓÚÂÊÔÃÕÇ]+", " ", e).strip()


def _ligar_leis(linhas: list[dict], leis: dict, origem: dict) -> dict[str, list[str]]:
    """Liga cada lei ao projeto de origem dito no cadastro, com duas travas, porque o cadastro às vezes aponta o
    projeto errado (24/11/2026: a Lei 6.919, que dá nome à nova sede, aponta para um projeto que dá nome ao
    auditório e ainda nem foi votado):
    1. Se o projeto apontado ainda não passou pela votação e o mesmo autor tem outro projeto com a mesma ementa
       já votado, a lei vai para esse outro (projeto repetido do mesmo autor).
    2. Se o projeto apontado não foi votado e a ementa dele não é praticamente igual à da lei, a ligação é descartada."""
    from difflib import SequenceMatcher
    pl = {}
    for x in linhas:
        if x["tipo"] in TIPOS_PL:
            pl.setdefault(x["id"], x)
    votado = lambda x: x["fase"] in FASE_APROVADO or x["fase"] in FASE_ARQUIVO  # noqa: E731
    lig: dict[str, list[str]] = defaultdict(list)
    for cod, proc in origem.items():
        if not proc or cod not in leis or proc not in pl:
            continue
        x = pl[proc]
        if not votado(x):
            irmaos = [y for k, y in pl.items() if k != proc and y["autor"] == x["autor"] and votado(y)
                      and _sem_rodape(y["ementa"])[:80] == _sem_rodape(x["ementa"])[:80]]
            if irmaos:
                proc = irmaos[0]["id"]
            elif SequenceMatcher(None, _sem_rodape(x["ementa"])[:120],
                                 _sem_rodape(leis[cod].get("ementa", x["ementa"]))[:120]).ratio() < 0.95:
                print(f"ligação descartada: {leis[cod]['nome']} -> {x['tipo']} {x['num']}/{x['ano']}")
                continue
        lig[proc].append(cod)
    return lig


def montar(pasta: Path) -> None:
    autores = json.loads((pasta / "autores.json").read_text(encoding="utf-8"))
    coleta = json.loads((pasta / "coleta.json").read_text(encoding="utf-8"))["coletado_em"]
    linhas = _producao(pasta, autores)
    leis = _leis(pasta, autores)
    origem = json.loads((pasta / "leis_origem.json").read_text(encoding="utf-8"))
    lei_do_processo = _ligar_leis(linhas, leis, origem)
    proc_f = pasta / "processos.json"
    processos = json.loads(proc_f.read_text(encoding="utf-8")) if proc_f.exists() else {}
    estados = {k: _estado_processo(v) for k, v in processos.items()}
    vetos = _vetos(pasta)

    antigos = json.loads((CAMARA / "projetos.json").read_text(encoding="utf-8"))
    resumo_antigo = json.loads((CAMARA / "producao_vereadores.json").read_text(encoding="utf-8"))
    nome_site = {_chave(r["vereador"]): r["vereador"] for r in resumo_antigo}     # grafia já usada no site
    extra_f = CAMARA / "classificacao_extra.json"
    extra = json.loads(extra_f.read_text(encoding="utf-8")) if extra_f.exists() else {}
    clas = {}
    for p in antigos:
        m = re.search(r"id=(\d+)", p.get("link", ""))
        if m and p.get("utilidade") and p["utilidade"] != "A classificar":
            clas[m.group(1)] = {k: p.get(k, "") for k in ("utilidade", "motivo", "categoria")}
    for pid, v in extra.items():
        clas.setdefault(pid, {"utilidade": v["utilidade"], "motivo": v.get("motivo", ""), "categoria": ""})

    projetos = []
    for x in sorted(linhas, key=lambda x: (x["vereador_id"], x["data"][6:] + x["data"][3:5] + x["data"][:2])):
        if x["tipo"] not in TIPOS_PL:
            continue
        sigla, tipo = TIPOS_PL[x["tipo"]]
        cods = sorted(lei_do_processo.get(x["id"], []), key=lambda c: leis[c]["data"])
        est = estados.get(x["id"])
        if est and not est["votado"]:
            # a própria página às vezes põe "Norma resultante" em projeto que nunca foi votado (PL 342/2025, PR 4/2026,
            # 24/11/2026): sem votação registrada, só vale a ligação do cadastro de leis que passou pelas travas
            est = {**est, "norma": "", "sancionado": False}
        if est and est["norma"] and cods:   # a página do projeto manda: a ligação do cadastro tem de bater com ela
            n = re.sub(r"\D", "", est["norma"].split("/")[0])
            cods = [k for k in cods if re.sub(r"\D", "", leis[k]["nome"].split("/")[0]).endswith(n)]
        c = clas.get(x["id"], {})
        ementa = re.sub(r"\s+", " ", x["ementa"]).strip(" \"'“”’")
        if cods:
            lei, lei_link = " e ".join(leis[k]["nome"] for k in cods), LEG + f"norma.aspx?id={cods[0]}"
        elif est and est["norma"]:          # "Norma resultante" na página do projeto: "Lei Ordinária 6765/2025"
            m = re.match(r"(.+?)\s+(\d+)/(\d{4})$", est["norma"])
            lei = f"{m.group(1)} {int(m.group(2)):,}/{m.group(3)}".replace(",", ".") if m else est["norma"]
            lei_link = SPL + f'processo.aspx?id={x["id"]}'
        elif est and est["votado"] and est["sancionado"]:
            # resolução não vai à sanção: a Câmara promulga. Lei sancionada sem o número da norma na página.
            lei = ("resolução promulgada" if x["tipo"] == "Projeto de Resolução"
                   else "lei sancionada (o número não aparece no sistema)")
            lei_link = SPL + f'processo.aspx?id={x["id"]}'
        else:
            lei, lei_link = "", ""
        chave_veto = (sigla, x["num"].lstrip("0"), x["ano"])
        veto = vetos.get(chave_veto)
        projetos.append({
            "vereador": nome_site.get(_chave(autores[x["vereador_id"]]), autores[x["vereador_id"]].title()),
            "numero": f'{sigla} {x["num"]}/{x["ano"]}', "tipo": tipo,
            "data": f'{x["data"][6:]}-{x["data"][3:5]}-{x["data"][:2]}',
            "categoria": c.get("categoria") or _categoria(ementa),
            "status": _situacao(x, bool(lei), est, None if chave_veto in VETO_A_CONFERIR else veto),
            "fase": x["fase"], "ementa": ementa,
            "link": SPL + f'processo.aspx?id={x["id"]}',
            "utilidade": c.get("utilidade", "A classificar"), "motivo": c.get("motivo", ""),
            "lei": lei, "lei_link": lei_link, "veto": veto or "",
        })

    por: dict[str, list[dict]] = defaultdict(list)
    for x in linhas:
        por[x["vereador_id"]].append(x)
    sit = Counter()
    for p in projetos:
        sit[(p["vereador"], p["status"])] += 1
    resumo = []
    for aid, nome in autores.items():
        xs = por[aid]
        t = Counter(x["tipo"] for x in xs)
        ns = nome_site.get(_chave(nome), nome.title())
        n_pl = sum(t[k] for k in TIPOS_PL)
        resumo.append({
            "vereador": ns, "total": len(xs),
            **{f"total_{a}": sum(1 for x in xs if x["ano_consulta"] == a) for a in ANOS},
            "indicacoes": t["Indicação"], "requerimentos": t["Requerimento"], "mocoes": t["Moção"],
            "decretos_legislativos": t["Projeto de Decreto Legislativo"], "projetos": n_pl,
            "emendas": sum(v for k, v in t.items() if k.startswith("Emenda")),
            "aprovados": sum(sit[(ns, s)] for s in ("Aprovado pela Câmara", "Virou lei", "Virou resolução",
                                                     "Vetado pelo prefeito")),
            "virou_lei": sit[(ns, "Virou lei")], "virou_resolucao": sit[(ns, "Virou resolução")],
            "vetados": sit[(ns, "Vetado pelo prefeito")],
            "arquivados": sit[(ns, "Arquivado/encerrado")],
            "em_analise": sit[(ns, "Em análise")] + sit[(ns, "Pronto para plenário")],
            "titulos_mocoes": sum(1 for x in xs if _homenagem(x)),
        })
    resumo.sort(key=lambda r: _chave(r["vereador"]))
    for r in resumo:      # confere: soma por tipo = total do sistema
        assert r["total"] == sum(1 for x in por[next(a for a, n in autores.items()
                                                    if nome_site.get(_chave(n), n.title()) == r["vereador"])]), r
    (CAMARA / "projetos.json").write_text(json.dumps(projetos, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (CAMARA / "producao_vereadores.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=1) + "\n",
                                                     encoding="utf-8")
    unicos = {x["id"]: x for x in linhas}          # na conta da cidade, papel com vários autores conta uma vez
    tu = Counter(x["tipo"] for x in unicos.values())
    cidade = {"papeis": len(unicos), "indicacoes": tu["Indicação"], "requerimentos": tu["Requerimento"],
              "homenagens": sum(1 for x in unicos.values() if _homenagem(x)),
              "titulos_cidadao": sum(1 for x in unicos.values() if (
                  x["tipo"] == "Projeto de Decreto Legislativo" and re.search(r"CIDAD[ÃA]", x["ementa"].upper()))
                  or (x["tipo"] == "Moção" and _homenagem(x)
                      and re.search(r"T[ÍI]TULO", x["ementa"].upper()) and re.search(r"CIDAD[ÃA]O", x["ementa"].upper()))),
              "mocoes_aplauso": sum(1 for x in unicos.values() if x["tipo"] == "Moção" and _homenagem(x)),
              "decretos_homenagem": sum(1 for x in unicos.values()
                                        if x["tipo"] == "Projeto de Decreto Legislativo" and _homenagem(x))}
    (CAMARA / "cidade.json").write_text(json.dumps(cidade, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    fonte = json.loads((CAMARA / "fonte.json").read_text(encoding="utf-8"))
    fonte["coletado_em"] = coleta
    fonte["fonte_leis"] = "Cadastro de leis da Câmara (Leis de sua autoria), com o projeto de origem de cada norma"
    fonte["url_leis"] = LEG + "consulta-legislacao.aspx"
    fonte["leis_ultimo_lancamento"] = max(v["data"] for v in leis.values()) if leis else ""
    (CAMARA / "fonte.json").write_text(json.dumps(fonte, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    unicos = {p["link"]: p for p in projetos}
    falta = sum(1 for p in unicos.values() if p["utilidade"] == "A classificar")
    print(f"{len(projetos)} linhas de projeto; {len(unicos)} projetos; "
          f"situações: {dict(Counter(p['status'] for p in unicos.values()))}; a classificar: {falta}")


def resumo(saida: str = "-") -> int:
    """Resumo em markdown para a página da execução no Actions (GITHUB_STEP_SUMMARY): situações, projetos novos
    sem classificação (o Vigia lê a ementa e põe o nível em data/camara/classificacao_extra.json) e aviso se o gasto
    da Câmara em fonte.json ficou velho. Devolve quantos estão "A classificar"."""
    projetos = json.loads((CAMARA / "projetos.json").read_text(encoding="utf-8"))
    fonte = json.loads((CAMARA / "fonte.json").read_text(encoding="utf-8"))
    unicos = {p["link"]: p for p in projetos}
    sit = Counter(p["status"] for p in unicos.values())
    novos = [p for p in unicos.values() if p["utilidade"] == "A classificar"]
    linhas = [f"## Vereadores: dados da Câmara de {fonte['coletado_em']}", "",
              f"{len(unicos)} projetos. " + "; ".join(f"{k}: {v}" for k, v in sorted(sit.items())) + ".", ""]
    if novos:
        linhas += [f"**{len(novos)} projetos novos sem classificação (\"A classificar\").** Leia a ementa e ponha o "
                   "nível em `data/camara/classificacao_extra.json` (chave: o id do link). Até lá, no site, eles "
                   "ficam em \"Sem como saber\".", ""]
        linhas += [f"- [{p['numero']}]({p['link']}): {p['ementa'][:160]}" for p in sorted(novos, key=lambda p: p["data"])]
    else:
        linhas.append("Nenhum projeto sem classificação.")
    dias = (date.fromisoformat(fonte["coletado_em"]) - date.fromisoformat(fonte["gasto_camara_ate"])).days
    if dias > 45:
        linhas += ["", f"**O gasto da Câmara em `data/camara/fonte.json` é de {fonte['gasto_camara_ate']}** "
                   f"({dias} dias antes da coleta). A conta \"por lei aprovada\" mistura períodos: atualize."]
    texto = "\n".join(linhas) + "\n"
    if saida == "-":
        sys.stdout.write(texto)
    else:
        with open(saida, "a", encoding="utf-8") as f:
            f.write(texto)
    if novos:
        print(f"::warning::{len(novos)} projetos novos da Câmara estão \"A classificar\" (ver o resumo da execução).")
    return len(novos)


if __name__ == "__main__":
    if sys.argv[1] == "resumo":
        resumo(sys.argv[2] if len(sys.argv) > 2 else "-")
    else:
        {"baixar": baixar, "montar": montar}[sys.argv[1]](Path(sys.argv[2]))
