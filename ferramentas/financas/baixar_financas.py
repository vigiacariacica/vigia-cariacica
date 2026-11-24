"""Coletor de finanças municipais da Grande Vitória.

Baixa, filtra e organiza três fontes públicas, sem mexer no banco do Vigia:

  1. TCE-ES (dados.es.gov.br): empenhos com credor, despesas, receitas, contratações e aditivos,
     folha de pagamento, saúde, educação, pessoal, dívida, índice de vulnerabilidade fiscal.
  2. SICONFI (Tesouro Nacional): balanços anuais (DCA), RREO e RGF padronizados.
  3. TSE: prestações de contas de campanha 2020 e 2024 (quem doou e quem foi pago) e candidatos.

Tudo fica em financas/dados/. Se parar no meio, rode de novo: o que já terminou é pulado.

Uso:
    python baixar_financas.py                # tudo
    python baixar_financas.py --so tce       # só uma fonte (tce, siconfi, tse)
    python baixar_financas.py --manter-brutos   # não apaga os .zip grandes depois de filtrar
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import re
import shutil
import subprocess
import sys
import time
import unicodedata
import zipfile
from pathlib import Path

try:
    import requests
except ImportError:  # pragma: no cover
    print("Falta o pacote 'requests'. Rode: python -m pip install requests")
    sys.exit(1)

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))

RAIZ = Path(__file__).resolve().parent
DADOS = RAIZ / "dados"
BRUTOS, FILTRADO = DADOS / "brutos", DADOS / "filtrado"
ESTADO_ARQ, LOG_ARQ, ESQUEMA_ARQ = DADOS / "estado.json", DADOS / "LOG.txt", DADOS / "ESQUEMA.txt"
UA = "VigiaCariacica/1.0 (controle social; dados publicos)"

CIDADES = {  # IBGE -> nome
    "3201308": "Cariacica", "3205309": "Vitória", "3205200": "Vila Velha", "3205002": "Serra",
    "3205101": "Viana", "3202405": "Guarapari", "3202207": "Fundão",
}

CKAN = "https://dados.es.gov.br/api/3/action/package_show?id="
# (slug, como tratar, filtro de recursos)
#   "filtrar": guarda só as linhas das 7 cidades; "inteiro": guarda o arquivo todo (pequeno, serve
#   para comparar com os 78 municípios do ES).
TCE = [
    ("tcees-empenho", "filtrar", {"desde": 2021}),
    ("despesas-municipios", "filtrar", {"desde": 2019}),
    ("receitas-municipios", "filtrar", {"desde": 2019}),
    ("tcees-contratacoes", "filtrar", {}),
    ("area-tematica-pessoal", "filtrar", {"desde": 2023}),
    ("tcees-despesas-com-saude-educacao-e-pessoal-receita-corrente-liquida-e-endividamento", "inteiro", {}),
    ("indice-vulnerabilidade-fiscal", "inteiro", {}),
    ("julgamento-de-contas", "inteiro", {}),
    ("previdencia", "filtrar", {"desde": 2021}),
    ("obrigacoes", "filtrar", {}),
    ("lista-de-responsaveis-consultas-tcees", "filtrar", {}),
    ("atos-de-pessoal", "filtrar", {"desde": 2021}),
]

SICONFI = "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/"
ANO_ATUAL = dt.date.today().year
ANOS_FECHADOS = list(range(2019, ANO_ATUAL))
DCA_ANEXOS = ["DCA-Anexo I-AB", "DCA-Anexo I-C", "DCA-Anexo I-D", "DCA-Anexo I-E", "DCA-Anexo I-F",
              "DCA-Anexo I-G", "DCA-Anexo I-HI"]
RREO_ANEXOS = ["RREO-Anexo 01", "RREO-Anexo 02", "RREO-Anexo 03", "RREO-Anexo 06", "RREO-Anexo 07",
               "RREO-Anexo 08", "RREO-Anexo 12", "RREO-Anexo 14"]
RGF_ANEXOS = ["RGF-Anexo 01", "RGF-Anexo 02", "RGF-Anexo 05", "RGF-Anexo 06"]

TSE = [
    ("https://cdn.tse.jus.br/estatistica/sead/odsele/prestacao_contas/prestacao_de_contas_eleitorais_candidatos_2024.zip", "contas_2024"),
    ("https://cdn.tse.jus.br/estatistica/sead/odsele/prestacao_contas/prestacao_de_contas_eleitorais_candidatos_2020.zip", "contas_2020"),
    ("https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand/consulta_cand_2024.zip", "candidatos_2024"),
    ("https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand/consulta_cand_2020.zip", "candidatos_2020"),
]

PAUSA_API = 0.35
sessao = requests.Session()
sessao.headers.update({"User-Agent": UA})


# --------------------------------------------------------------------------- utilidades
def agora():
    return dt.datetime.now().strftime("%H:%M:%S")


def log(msg, arquivo=True):
    linha = f"[{agora()}] {msg}"
    print(linha, flush=True)
    if arquivo:
        LOG_ARQ.parent.mkdir(parents=True, exist_ok=True)
        with LOG_ARQ.open("a", encoding="utf-8") as f:
            f.write(linha + "\n")


def norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


NOMES = {norm(n): n for n in CIDADES.values()}


def cidade_de(valor) -> str | None:
    """Diz a qual das 7 cidades um valor se refere (nome, 'Prefeitura Municipal da Serra', código IBGE)."""
    v = norm(valor)
    if not v:
        return None
    if v in NOMES:
        return NOMES[v]
    bruto = str(valor).strip()
    if bruto.isdigit() and len(bruto) in (6, 7):  # código IBGE com 7 ou 6 dígitos
        for cod, nome in CIDADES.items():
            if bruto == cod or bruto == cod[:6]:
                return nome
    for n, nome in NOMES.items():
        if re.search(rf"\b(de|da|do)\s+{n}$", v) or v.endswith(f" {n} es") or v == f"{n} es":
            return nome
    return None


class Estado:
    def __init__(self):
        self.d = json.loads(ESTADO_ARQ.read_text("utf-8")) if ESTADO_ARQ.exists() else {}

    def feito(self, chave, marca=None):
        e = self.d.get(chave)
        return bool(e) and (marca is None or e.get("marca") == marca)

    def marcar(self, chave, marca=None, **extra):
        self.d[chave] = {"quando": dt.datetime.now().isoformat(timespec="seconds"), "marca": marca, **extra}
        ESTADO_ARQ.parent.mkdir(parents=True, exist_ok=True)
        tmp = ESTADO_ARQ.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.d, ensure_ascii=False, indent=1), "utf-8")
        tmp.replace(ESTADO_ARQ)


def esquema(texto):
    with ESQUEMA_ARQ.open("a", encoding="utf-8") as f:
        f.write(texto.rstrip() + "\n\n")


def baixar_arquivo(url, destino: Path, tentativas=4) -> bool:
    """Baixa em partes direto para o disco (serve para arquivos de vários GB)."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_name(destino.name + ".parcial")
    for t in range(tentativas):
        try:
            with sessao.get(url, stream=True, timeout=(30, 300), allow_redirects=True) as r:
                if r.status_code in (400, 403, 404, 410):
                    log(f"    HTTP {r.status_code} em {url}")
                    return False
                r.raise_for_status()
                total = int(r.headers.get("content-length") or 0)
                feito, ultimo = 0, time.time()
                with tmp.open("wb") as f:
                    for bloco in r.iter_content(1 << 20):
                        f.write(bloco)
                        feito += len(bloco)
                        if time.time() - ultimo > 15:
                            pct = f" ({100 * feito / total:.0f}%)" if total else ""
                            print(f"      ... {feito / 1e6:,.0f} MB{pct}", flush=True)
                            ultimo = time.time()
            if tmp.stat().st_size == 0:
                raise IOError("arquivo vazio")
            tmp.replace(destino)
            return True
        except Exception as e:  # noqa: BLE001
            log(f"    falha {t + 1}/{tentativas}: {e}")
            time.sleep(5 * (t + 1))
    # plano B: curl / PowerShell do Windows (certificados e proxies chatos)
    for cmd in _comandos_windows(url, tmp):
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=7200)
            if r.returncode == 0 and tmp.exists() and tmp.stat().st_size > 0:
                tmp.replace(destino)
                log("    baixado pelo plano B do Windows")
                return True
        except Exception:  # noqa: BLE001
            pass
    if tmp.exists():
        tmp.unlink()
    return False


def _comandos_windows(url, tmp):
    exe = shutil.which("curl.exe") or shutil.which("curl")
    if exe:
        yield [exe, "-L", "-s", "-f", "--retry", "3", "--ssl-revoke-best-effort", "-A", UA, "-o", str(tmp), url]
    if shutil.which("powershell"):
        yield ["powershell", "-NoProfile", "-Command",
               f"$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -UseBasicParsing -Uri '{url}' -OutFile '{tmp}'"]


def get_json(url, params=None, tentativas=5):
    for t in range(tentativas):
        try:
            r = sessao.get(url, params=params, timeout=(20, 120))
            if r.status_code == 429:
                time.sleep(10 * (t + 1))
                continue
            if r.status_code in (400, 404):
                return None
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001
            if t == tentativas - 1:
                log(f"    erro em {url} {params or ''}: {e}")
            time.sleep(3 * (t + 1))
    return None


# --------------------------------------------------------------------------- leitura de CSV
def _abrir_texto(abrir):
    """abrir() devolve um stream binário novo. Detecta codificação e separador."""
    with abrir() as b:
        amostra = b.read(256 * 1024)
    try:
        amostra.decode("utf-8")
        cod = "utf-8-sig"
    except UnicodeDecodeError as e:
        # se o erro for só no fim da amostra (caractere cortado), ainda é UTF-8
        cod = "utf-8-sig" if e.start > len(amostra) - 4 else "latin-1"
    primeira = amostra.decode(cod, "replace").splitlines()[0] if amostra else ""
    sep = max([";", ",", "|", "\t"], key=primeira.count)
    return io.TextIOWrapper(abrir(), encoding=cod, errors="replace", newline=""), sep, cod


DICAS_COLUNA = ["municipio", "nomemunicipio", "nome municipio", "nm municipio", "nm ue", "ente", "nome ente",
                "cod ibge", "codigo ibge", "ibge", "cidade", "unidade gestora", "orgao", "entidade"]


EVITAR_COLUNA = ["credor", "fornecedor", "doador", "nascimento", "endereco", "domicilio", "beneficiario",
                 "contratado", "favorecido", "pessoa", "naturalidade", "residencia", "cep", "logradouro", "bairro"]


def escolher_coluna(cab, linhas):
    """Escolhe a coluna que diz de qual município é a linha (o ente que gastou, não o endereço do credor)."""
    pontos = []
    for i, nome in enumerate(cab):
        n = norm(nome)
        if any(e in n for e in EVITAR_COLUNA):
            continue
        acertos = sum(1 for l in linhas if i < len(l) and cidade_de(l[i]))
        if acertos:
            pontos.append((acertos, any(d in n for d in DICAS_COLUNA), i))
    if not pontos:
        return None
    maximo = max(p[0] for p in pontos)
    fortes = [p for p in pontos if p[0] >= 0.5 * maximo]
    com_dica = [p for p in fortes if p[1]]
    return max(com_dica or fortes)[2]


def filtrar_csv(abrir, destino: Path, rotulo: str, inteiro=False) -> dict:
    """Lê um CSV em fluxo e grava só as linhas das 7 cidades (ou tudo, se inteiro=True)."""
    txt, sep, cod = _abrir_texto(abrir)
    leitor = csv.reader(txt, delimiter=sep)
    try:
        cab = next(leitor)
    except StopIteration:
        return {"linhas": 0}
    cab = [c.strip().lstrip("﻿") for c in cab]
    buffer = []
    for l in leitor:
        buffer.append(l)
        if len(buffer) >= 20000:
            break
    col = None if inteiro else escolher_coluna(cab, buffer)
    modo = "inteiro" if inteiro else (f"coluna '{cab[col]}'" if col is not None else "linha inteira")
    destino.parent.mkdir(parents=True, exist_ok=True)
    por_cidade, valores, lidas, guardadas, amostra = {}, {}, 0, 0, []

    def decide(l):
        if inteiro:
            return "todas"
        if col is not None:
            v = l[col] if col < len(l) else ""
            c = cidade_de(v)
            if c:
                valores[v] = c
            return c
        for v in l:  # sem coluna clara: procura em qualquer campo (mais lento)
            c = cidade_de(v)
            if c:
                return c
        return None

    with destino.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(cab)
        for fonte in (buffer, leitor):
            for l in fonte:
                lidas += 1
                c = decide(l)
                if c:
                    w.writerow(l)
                    guardadas += 1
                    por_cidade[c] = por_cidade.get(c, 0) + 1
                    if len(amostra) < 3:
                        amostra.append(l)
                if lidas % 500000 == 0:
                    print(f"      ... {lidas:,} linhas lidas, {guardadas:,} guardadas", flush=True)
    txt.close()
    if guardadas == 0 and not inteiro:
        destino.unlink(missing_ok=True)
    rel = [f"### {rotulo}", f"arquivo: {destino.relative_to(DADOS) if guardadas else '(nenhuma linha das 7 cidades)'}",
           f"codificação: {cod}  separador: {sep!r}  filtro: {modo}",
           f"linhas lidas: {lidas:,}  guardadas: {guardadas:,}  por cidade: {por_cidade}",
           "colunas: " + " | ".join(cab)]
    if valores:
        rel.append("valores da coluna de município reconhecidos: " +
                   "; ".join(f"{k} -> {v}" for k, v in list(valores.items())[:20]))
    for a in amostra:
        rel.append("exemplo: " + " | ".join(x[:60] for x in a))
    esquema("\n".join(rel))
    return {"linhas": guardadas, "lidas": lidas, "cidades": por_cidade}


def processar_arquivo(caminho: Path, pasta_saida: Path, rotulo: str, inteiro: bool, membros_ok=None,
                      nome_csv: str | None = None) -> int:
    """Filtra um .csv ou todos os .csv/.txt de um .zip (inclusive zip dentro de zip)."""
    total = 0
    if zipfile.is_zipfile(caminho):
        with zipfile.ZipFile(caminho) as z:
            total += _processar_zip(z, pasta_saida, rotulo, inteiro, membros_ok)
    else:
        nome = re.sub(r"[^\w.-]+", "_", nome_csv or caminho.name)
        if not nome.lower().endswith(".csv"):
            nome += ".csv"
        total += filtrar_csv(lambda: caminho.open("rb"), pasta_saida / nome, rotulo, inteiro)["linhas"]
    return total


def _processar_zip(z, pasta_saida, rotulo, inteiro, membros_ok):
    total = 0
    for m in z.infolist():
        if m.is_dir():
            continue
        nome = m.filename.lower()
        if membros_ok and not membros_ok(m.filename):
            continue
        if nome.endswith(".zip"):
            with z.open(m) as zz, zipfile.ZipFile(io.BytesIO(zz.read())) as interno:
                total += _processar_zip(interno, pasta_saida, f"{rotulo} > {m.filename}", inteiro, membros_ok)
        elif nome.endswith((".csv", ".txt")):
            saida = pasta_saida / re.sub(r"[^\w.-]+", "_", Path(m.filename).name)
            if not saida.name.lower().endswith(".csv"):
                saida = saida.with_suffix(".csv")
            total += filtrar_csv(lambda m=m: z.open(m), saida, f"{rotulo} > {m.filename}", inteiro)["linhas"]
        elif nome.endswith((".pdf", ".xlsx", ".xls", ".json", ".md")):
            pasta_saida.mkdir(parents=True, exist_ok=True)
            (pasta_saida / Path(m.filename).name).write_bytes(z.read(m))
    return total


# --------------------------------------------------------------------------- 1. TCE-ES
def ano_do_recurso(r) -> int | None:
    anos = [int(a) for a in re.findall(r"(20\d\d)", f"{r.get('name', '')} {r.get('url', '')}")
            if 2000 <= int(a) <= ANO_ATUAL + 1]
    return max(anos) if anos else None


def etapa_tce(estado: Estado, manter_brutos: bool):
    log("=== 2/3 TCE-ES: dados que os municípios enviam ao Tribunal de Contas ===")
    for slug, modo, filtro in TCE:
        pacote = get_json(CKAN + slug)
        if not pacote or not pacote.get("success"):
            log(f"  [{slug}] não encontrado na API, pulando")
            continue
        recursos = pacote["result"].get("resources", [])
        titulo = pacote["result"].get("title", slug)
        log(f"  [{slug}] {titulo}: {len(recursos)} arquivos")
        esquema(f"## {titulo} ({slug})\n{(pacote['result'].get('notes') or '').strip()[:600]}")
        for r in recursos:
            nome = r.get("name") or r.get("id")
            ano = ano_do_recurso(r)
            dicionario = "dicion" in norm(nome)
            if filtro.get("desde") and ano and ano < filtro["desde"] and not dicionario:
                continue
            chave = f"tce|{slug}|{r['id']}"
            marca = r.get("last_modified") or r.get("metadata_modified") or r.get("size")
            if estado.feito(chave, marca):
                log(f"    ok (já feito): {nome}")
                continue
            url = r.get("url")
            if not url:
                continue
            ext = Path(url.split("?")[0]).suffix.lower()
            fmt = (r.get("format") or "").lower()
            if not ext or len(ext) > 5:
                ext = "." + (fmt if fmt in ("zip", "csv", "xlsx", "json", "pdf") else "bin")
            bruto = BRUTOS / slug / f"{r['id']}{ext}"
            ja_tem = bruto.exists() and bruto.stat().st_size > 0 and (ext != ".zip" or zipfile.is_zipfile(bruto))
            log(f"    {'reaproveitando' if ja_tem else 'baixando'}: {nome} ({ano or 's/ ano'})")
            if not ja_tem and not baixar_arquivo(url, bruto):
                log(f"    FALHOU: {nome}")
                continue
            saida = FILTRADO / slug / re.sub(r"[^\w.-]+", "_", f"{nome}")
            saida = saida.with_suffix("") if saida.suffix.lower() in (".zip", ".csv") else saida
            try:
                if dicionario or ext in (".xlsx", ".pdf", ".json"):
                    destino = FILTRADO / slug / (re.sub(r"[^\w.-]+", "_", nome) + (ext if not nome.lower().endswith(ext) else ""))
                    destino.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(bruto, destino)
                    if ext == ".csv" or zipfile.is_zipfile(bruto):
                        processar_arquivo(bruto, saida, f"{slug} / {nome} (dicionário)", True)
                    n = -1
                else:
                    n = processar_arquivo(bruto, saida, f"{slug} / {nome}", modo == "inteiro", nome_csv=nome)
            except Exception as e:  # noqa: BLE001
                log(f"    ERRO ao ler {nome}: {e}")
                continue
            log(f"    -> {'copiado' if n < 0 else f'{n:,} linhas guardadas'}")
            estado.marcar(chave, marca, linhas=n, arquivo=str(saida.relative_to(DADOS)))
            if not manter_brutos and not dicionario:
                bruto.unlink(missing_ok=True)


# --------------------------------------------------------------------------- 2. SICONFI
def siconfi_paginado(endpoint, params):
    itens, offset = [], 0
    while True:
        p = dict(params, offset=offset) if offset else params
        js = get_json(SICONFI + endpoint, p)
        time.sleep(PAUSA_API)
        if js is None:
            return itens if itens else None
        lote = js.get("items", [])
        itens.extend(lote)
        if not js.get("hasMore") or not lote:
            return itens
        offset += len(lote)


def etapa_siconfi(estado: Estado):
    log("=== 1/3 SICONFI (Tesouro Nacional): balanços, RREO e RGF das 7 cidades ===")
    pasta = DADOS / "siconfi"
    pasta.mkdir(parents=True, exist_ok=True)
    pedidos = []
    for ibge in CIDADES:
        for ano in ANOS_FECHADOS:
            for anx in DCA_ANEXOS:
                pedidos.append(("dca", {"an_exercicio": ano, "no_anexo": anx, "id_ente": ibge}))
            for anx in RREO_ANEXOS:
                pedidos.append(("rreo", {"an_exercicio": ano, "nr_periodo": 6, "co_tipo_demonstrativo": "RREO",
                                         "no_anexo": anx, "co_esfera": "M", "id_ente": ibge}))
            for anx in RGF_ANEXOS:
                for poder in (["E", "L"] if anx == "RGF-Anexo 01" else ["E"]):
                    pedidos.append(("rgf", {"an_exercicio": ano, "in_periodicidade": "Q", "nr_periodo": 3,
                                            "co_tipo_demonstrativo": "RGF", "no_anexo": anx, "co_esfera": "M",
                                            "co_poder": poder, "id_ente": ibge}))
        for per in range(1, 7):  # ano corrente: todos os bimestres que já saíram
            for anx in RREO_ANEXOS:
                pedidos.append(("rreo", {"an_exercicio": ANO_ATUAL, "nr_periodo": per, "co_tipo_demonstrativo": "RREO",
                                         "no_anexo": anx, "co_esfera": "M", "id_ente": ibge}))
        for per in (1, 2, 3):
            pedidos.append(("rgf", {"an_exercicio": ANO_ATUAL, "in_periodicidade": "Q", "nr_periodo": per,
                                    "co_tipo_demonstrativo": "RGF", "no_anexo": "RGF-Anexo 01", "co_esfera": "M",
                                    "co_poder": "E", "id_ente": ibge}))
    log(f"  {len(pedidos)} consultas (cerca de {len(pedidos) * 1.2 / 60:.0f} minutos)")
    vazios = 0
    for i, (ep, p) in enumerate(pedidos, 1):
        chave = "siconfi|" + ep + "|" + "|".join(f"{k}={v}" for k, v in sorted(p.items()))
        hoje = dt.date.today().isoformat()
        if estado.feito(chave) and estado.d[chave].get("marca") in (None, hoje):
            continue  # já baixado (ou, no ano corrente, já tentado hoje sem resultado)
        itens = siconfi_paginado(ep, p)
        if itens is None:
            continue  # erro de rede: tenta de novo na próxima rodada
        # municípios pequenos (Fundão) entregam RGF semestral/simplificado
        if not itens and ep == "rgf" and p["an_exercicio"] < ANO_ATUAL:
            for tipo in ("RGF", "RGF Simplificado"):
                alt = dict(p, in_periodicidade="S", nr_periodo=2, co_tipo_demonstrativo=tipo)
                itens = siconfi_paginado(ep, alt) or []
                if itens:
                    break
        if not itens and ep == "rreo" and p["an_exercicio"] < ANO_ATUAL:
            alt = dict(p, co_tipo_demonstrativo="RREO Simplificado")
            itens = siconfi_paginado(ep, alt) or []
        nome = f"{ep}_{p['id_ente']}_{p['an_exercicio']}_{p.get('nr_periodo', 'a')}_{re.sub(r'[^A-Za-z0-9]+', '', p['no_anexo'])}_{p.get('co_poder', '')}.json"
        if itens:
            (pasta / nome).write_text(json.dumps(itens, ensure_ascii=False), "utf-8")
        else:
            vazios += 1
            if p["an_exercicio"] >= ANO_ATUAL:
                # relatório do ano corrente ainda não entregue: tenta de novo em outro dia
                estado.marcar(chave, hoje, linhas=0)
                continue
        estado.marcar(chave, None, linhas=len(itens))
        if i % 50 == 0:
            log(f"  ... {i}/{len(pedidos)} consultas ({vazios} sem dados, normal para relatórios ainda não entregues)")
    log(f"  SICONFI concluído ({vazios} consultas sem dados)")


# --------------------------------------------------------------------------- 3. TSE
def etapa_tse(estado: Estado, manter_brutos: bool):
    log("=== 3/3 TSE: contas de campanha e candidatos (2020 e 2024) ===")
    for url, rotulo in TSE:
        chave = f"tse|{rotulo}"
        if estado.feito(chave):
            log(f"  ok (já feito): {rotulo}")
            continue
        bruto = BRUTOS / "tse" / Path(url).name
        log(f"  baixando {Path(url).name} (arquivo grande, pode levar um bom tempo)")
        if not (bruto.exists() and zipfile.is_zipfile(bruto)) and not baixar_arquivo(url, bruto):
            log(f"  FALHOU: {rotulo}")
            continue

        def so_es(nome):
            n = nome.lower()
            return n.endswith(("_es.csv", "_es.txt")) or "leiame" in n or n.endswith(".pdf")

        try:
            n = processar_arquivo(bruto, FILTRADO / "tse" / rotulo, f"TSE {rotulo}", False, membros_ok=so_es)
        except Exception as e:  # noqa: BLE001
            log(f"  ERRO ao ler {rotulo}: {e}")
            continue
        log(f"  -> {n:,} linhas das 7 cidades")
        estado.marcar(chave, None, linhas=n)
        if not manter_brutos:
            bruto.unlink(missing_ok=True)


# --------------------------------------------------------------------------- principal
def resumo():
    linhas = ["", "=" * 60, "RESUMO", "=" * 60]
    for pasta in sorted(FILTRADO.glob("*")) if FILTRADO.exists() else []:
        arqs = list(pasta.rglob("*.csv"))
        tam = sum(a.stat().st_size for a in arqs) / 1e6
        linhas.append(f"  {pasta.name:<70} {len(arqs):>4} arquivos  {tam:>9,.1f} MB")
    sic = list((DADOS / "siconfi").glob("*.json")) if (DADOS / "siconfi").exists() else []
    linhas.append(f"  {'siconfi':<70} {len(sic):>4} arquivos")
    falhas = [l for l in LOG_ARQ.read_text("utf-8").splitlines() if "FALHOU" in l or "ERRO" in l] if LOG_ARQ.exists() else []
    linhas.append(f"\nFalhas nesta pasta de log: {len(falhas)}")
    linhas += ["  " + f for f in falhas[-30:]]
    texto = "\n".join(linhas)
    log(texto)
    (DADOS / "RESUMO.txt").write_text(texto, "utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--so", choices=["tce", "siconfi", "tse"], help="roda só uma fonte")
    ap.add_argument("--manter-brutos", action="store_true", help="não apaga os arquivos brutos do TCE-ES depois de filtrar")
    ap.add_argument("--apagar-brutos", action="store_true", help="apaga os brutos do TCE-ES mesmo com disco sobrando")
    a = ap.parse_args(argv)
    DADOS.mkdir(parents=True, exist_ok=True)
    livre = shutil.disk_usage(DADOS).free / 1e9
    log(f"Início. Pasta: {DADOS}  (espaço livre no disco: {livre:,.0f} GB)")
    if not a.manter_brutos and not a.apagar_brutos:
        # com folga no disco, guarda os brutos do TCE-ES para poder refiltrar sem baixar de novo
        a.manter_brutos = livre > 40
        log("  Os arquivos brutos do TCE-ES " + ("serão guardados" if a.manter_brutos else "serão apagados depois de filtrados (pouco espaço)"))
    if livre < 8:
        log("  ATENÇÃO: menos de 8 GB livres. Libere espaço antes de continuar.")
    estado = Estado()
    if a.so in (None, "siconfi"):  # primeiro o mais rápido (uns 25 minutos)
        etapa_siconfi(estado)
    if a.so in (None, "tce"):
        etapa_tce(estado, a.manter_brutos)
    if a.so in (None, "tse"):
        etapa_tse(estado, False)
    resumo()
    log("Fim. Mande o aviso no chat: vou ler o ESQUEMA.txt e montar as análises.")


if __name__ == "__main__":
    main()
