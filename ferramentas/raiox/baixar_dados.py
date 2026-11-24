"""
RAIO-X DE CARIACICA - coletor de dados oficiais (versão 2)

Roda separado do Vigia: grava só dentro da pasta "raiox". Pode rodar ao mesmo tempo.
Pode ser rodado de novo: o que já foi baixado não é baixado outra vez.

O que faz:
  1. IBGE: distritos de Cariacica.
  2. IBGE Censo 2022 POR BAIRRO: dados básicos, alfabetização, domicílios (esgoto, água, lixo,
     banheiro), demografia, cor ou raça, óbitos, renda do responsável e entorno das casas
     (calçada, iluminação, pavimentação, esgoto a céu aberto, lixo na rua).
     Guarda só os bairros de Cariacica, Vitória, Vila Velha, Serra e Viana.
  3. IBGE Censo 2022 por município: tabelas de população, renda, saneamento e moradia.
  4. INEP: Ideb por município e por escola.
No final escreve LOG.txt dizendo o que deu certo e o que falhou.
"""
from __future__ import annotations

import csv
import datetime as dt
import gzip
import io
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import unquote, urljoin

BASE = Path(__file__).resolve().parent
BRUTO = BASE / "dados_brutos"
PRONTO = BASE / "dados_prontos"
TESTE = "--teste" in sys.argv
TENTATIVAS = 1 if TESTE else 3
TIMEOUT = 10 if TESTE else 300
PAUSA = 0 if TESTE else 0.5

MUNICIPIOS = {"3201308": "Cariacica", "3205309": "Vitória", "3205200": "Vila Velha",
              "3205002": "Serra", "3205101": "Viana"}
CARIACICA = "3201308"
UA = "VigiaCariacica-RaioX/2.0 (controle social; dados publicos)"
FTP = "https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/"
REGISTRO: list[dict] = []


def agora():
    return dt.datetime.now().strftime("%H:%M:%S")


def info(msg):
    print(f"[{agora()}] {msg}", flush=True)


def registrar(etapa, url, destino, status, tamanho=0):
    rel = ""
    if destino:
        try:
            rel = str(destino.relative_to(BASE))
        except ValueError:
            rel = str(destino)
    REGISTRO.append({"etapa": etapa, "url": url, "arquivo": rel, "status": status, "bytes": tamanho, "hora": agora()})


def descompactar_se_gzip(dados: bytes) -> bytes:
    if dados[:2] == b"\x1f\x8b":
        try:
            return gzip.decompress(dados)
        except OSError:
            return dados
    return dados


def baixar_pelo_windows(url, destino: Path) -> bool:
    """Plano B para sites com certificado incompleto (ex.: INEP): usa o curl ou o PowerShell do Windows."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(destino.suffix + ".parcial")
    comandos = []
    if shutil.which("curl.exe") or shutil.which("curl"):
        exe = shutil.which("curl.exe") or shutil.which("curl")
        comandos.append([exe, "-L", "-s", "-f", "--retry", "2", "--ssl-revoke-best-effort", "-A", UA, "-o", str(tmp), url])
        comandos.append([exe, "-L", "-s", "-f", "--retry", "2", "-A", UA, "-o", str(tmp), url])
    if shutil.which("powershell"):
        comandos.append(["powershell", "-NoProfile", "-Command",
                         f"$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -UseBasicParsing -Uri '{url}' -OutFile '{tmp}'"])
    for cmd in comandos:
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=TIMEOUT * 2)
            if r.returncode == 0 and tmp.exists() and tmp.stat().st_size > 0:
                tmp.replace(destino)
                return True
        except Exception:  # noqa: BLE001
            pass
    if tmp.exists():
        tmp.unlink()
    return False


def baixar(etapa, url, destino: Path | None = None, texto=False, reaproveitar=False):
    """Baixa uma URL (guarda em 'destino' se informado). Devolve bytes, str ou None."""
    if reaproveitar and destino and destino.exists() and destino.stat().st_size > 0:
        dados = destino.read_bytes()
        registrar(etapa, url, destino, "ok (já baixado)", len(dados))
        return dados.decode("utf-8", "replace") if texto else dados
    erro = "?"
    for t in range(TENTATIVAS):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                dados = descompactar_se_gzip(r.read())
            if destino:
                destino.parent.mkdir(parents=True, exist_ok=True)
                destino.write_bytes(dados)
            registrar(etapa, url, destino, "ok", len(dados))
            time.sleep(PAUSA)
            return dados.decode("utf-8", "replace") if texto else dados
        except urllib.error.HTTPError as e:
            erro = f"HTTP {e.code}"
            if e.code in (400, 404, 410):
                break
        except Exception as e:  # noqa: BLE001
            erro = f"{type(e).__name__}: {str(e)[:150]}"
            if "CERTIFICATE" in erro.upper() and destino and not TESTE:
                if baixar_pelo_windows(url, destino):
                    dados = destino.read_bytes()
                    registrar(etapa, url, destino, "ok (via Windows)", len(dados))
                    return dados.decode("utf-8", "replace") if texto else dados
                erro += " | plano B do Windows também falhou"
                break
        if t < TENTATIVAS - 1:
            time.sleep(5 * (t + 1))
    registrar(etapa, url, destino, "falhou: " + erro)
    return None


def salvar_json(obj, caminho: Path):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def listar(url):
    txt = baixar("lista-ibge", url, None, texto=True)
    if not txt:
        return []
    out = []
    for l in re.findall(r'href="([^"?#][^"]*)"', txt):
        if l.startswith(("http", "/", "..")) or l == "./":
            continue
        out.append(l)
    return out


# ------------------------------------------------------------------ CSV: filtrar só as 5 cidades
def abrir_texto(bruto: bytes) -> str:
    for cod in ("utf-8-sig", "latin-1"):
        try:
            return bruto.decode(cod)
        except UnicodeDecodeError:
            continue
    return bruto.decode("latin-1", "replace")


def filtrar_csv_das_cidades(conteudo: bytes, destino: Path, so_cariacica=False) -> int:
    """Guarda só as linhas cujo código (CD_MUN, CD_BAIRRO, CD_SETOR...) começa por um dos 5 municípios."""
    texto = abrir_texto(conteudo)
    amostra = texto[:5000]
    sep = ";" if amostra.count(";") >= amostra.count(",") else ","
    leitor = csv.reader(io.StringIO(texto), delimiter=sep)
    try:
        cab = next(leitor)
    except StopIteration:
        return 0
    cab_up = [c.strip().upper() for c in cab]
    idx = None
    for nome in ("CD_MUN", "COD_MUN", "CD_MUNICIPIO", "CD_BAIRRO", "CD_SETOR", "CD_DIST", "CD_SUBDIST"):
        if nome in cab_up:
            idx = cab_up.index(nome)
            break
    alvos = {CARIACICA} if so_cariacica else set(MUNICIPIOS)
    linhas = []
    for linha in leitor:
        if idx is not None and idx < len(linha):
            if re.sub(r"\D", "", linha[idx])[:7] in alvos:
                linhas.append(linha)
        elif any(re.sub(r"\D", "", v)[:7] in alvos for v in linha[:6]):
            linhas.append(linha)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with open(destino, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(cab)
        w.writerows(linhas)
    return len(linhas)


def processar_zip_de_csv(zip_bytes: bytes, prefixo: str) -> int:
    try:
        z = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile:
        info(f"   Arquivo {prefixo} não é um ZIP válido")
        return 0
    total = 0
    for nome in z.namelist():
        if not nome.lower().endswith(".csv"):
            continue
        n = filtrar_csv_das_cidades(z.read(nome), PRONTO / "bairros" / f"{prefixo}__{Path(nome).stem}.csv")
        total += n
    return total


# ------------------------------------------------------------------ 1. localidades
def etapa_localidades():
    info("1/4 IBGE: distritos de Cariacica")
    base = "https://servicodados.ibge.gov.br/api/v1/localidades"
    baixar("localidades", f"{base}/municipios/{CARIACICA}/distritos", BRUTO / "ibge" / "distritos_cariacica.json")


# ------------------------------------------------------------------ 2. Censo por bairro
PASTAS_BAIRRO = [
    "Agregados_por_Setores_Censitarios/Agregados_por_Bairro_csv/",
    "Agregados_por_Setores_Censitarios_Caracteristicas_urbanisticas_do_entorno_dos_domicilios/Agregados_por_Bairro_csv/",
    "Agregados_por_Setores_Censitarios_Rendimento_do_Responsavel/",
]
INTERESSE_BAIRRO = re.compile(r"(basico|alfabetiza|domicilio|demografia|cor_ou_raca|obitos|entorno|bairros_renda)", re.I)
DICIONARIOS = re.compile(r"dicion", re.I)


def etapa_bairros():
    info("3/4 IBGE: Censo 2022 por BAIRRO (arquivos grandes; pode levar de 10 a 40 minutos)")
    for pasta in PASTAS_BAIRRO:
        url_pasta = urljoin(FTP, pasta)
        for arq in listar(url_pasta):
            nome = unquote(arq)
            low = nome.lower()
            if DICIONARIOS.search(low) and low.endswith((".xlsx", ".zip", ".ods")):
                baixar("dicionario", urljoin(url_pasta, arq), BRUTO / "ibge" / "dicionarios" / nome, reaproveitar=True)
                continue
            if not low.endswith(".zip") or "xlsx" in low:
                continue
            if "renda" in low and "bairro" not in low:
                continue
            if not INTERESSE_BAIRRO.search(low):
                continue
            info(f"   baixando {nome}")
            dados = baixar("censo-bairro", urljoin(url_pasta, arq), BRUTO / "ibge" / "bairros_zip" / nome, reaproveitar=True)
            if dados:
                n = processar_zip_de_csv(dados, Path(nome).stem)
                info(f"   -> {n} bairros das 5 cidades guardados")
    # dicionário principal fica na pasta-mãe
    url_mae = urljoin(FTP, "Agregados_por_Setores_Censitarios/")
    for arq in listar(url_mae):
        if DICIONARIOS.search(arq) and arq.lower().endswith(".xlsx"):
            baixar("dicionario", urljoin(url_mae, arq), BRUTO / "ibge" / "dicionarios" / unquote(arq), reaproveitar=True)


# ------------------------------------------------------------------ 3. Censo por município (SIDRA)
PALAVRAS_CENSO = ["popula", "idade", "rendimento", "esgot", "abastecimento", "água", "agua", "lixo",
                  "banheiro", "sanit", "alfabet", "favela", "comunidades urbanas", "domicílio", "domicilio",
                  "cor ou raça", "moradores"]


def etapa_censo_municipios():
    info("4/4 IBGE: tabelas do Censo 2022 por município (5 cidades)")
    api = "https://servicodados.ibge.gov.br/api/v3/agregados"
    bruto = baixar("censo", api, BRUTO / "ibge" / "catalogo_agregados.json", texto=True)
    if not bruto:
        return
    try:
        pesquisas = json.loads(bruto)
    except json.JSONDecodeError:
        info("   Catálogo do IBGE em formato inesperado. Pulando.")
        return
    candidatos = [{"id": a.get("id"), "nome": a.get("nome")}
                  for p in pesquisas if str(p.get("id")) == "CD" or "censo demogr" in str(p.get("nome", "")).lower()
                  for a in p.get("agregados", [])
                  if any(k in str(a.get("nome", "")).lower() for k in PALAVRAS_CENSO)]
    info(f"   {len(candidatos)} tabelas candidatas; conferindo quais são de 2022")
    catalogo = []
    for i, c in enumerate(candidatos, 1):
        meta = baixar("censo-metadados", f"{api}/{c['id']}/metadados", None, texto=True)
        try:
            m = json.loads(meta) if meta else None
        except json.JSONDecodeError:
            m = None
        if not m:
            continue
        per = m.get("periodicidade") or {}
        try:
            tem_2022 = int(per.get("inicio") or 0) <= 2022 <= int(per.get("fim") or 0)
        except (TypeError, ValueError):
            tem_2022 = False
        if tem_2022:
            catalogo.append({"id": c["id"], "nome": c["nome"],
                             "variaveis": [{"id": v.get("id"), "nome": v.get("nome"), "unidade": v.get("unidade")}
                                           for v in m.get("variaveis", [])]})
        if i % 50 == 0:
            info(f"   {i}/{len(candidatos)} conferidas, {len(catalogo)} de 2022")
    salvar_json(catalogo, BRUTO / "ibge" / "catalogo_censo_2022.json")
    locs = ",".join(MUNICIPIOS)
    linhas = []
    for t in catalogo[:80]:
        txt = baixar("censo-dados", f"{api}/{t['id']}/periodos/2022/variaveis?localidades=N6[{locs}]",
                     BRUTO / "ibge" / "tabelas" / f"tabela_{t['id']}.json", texto=True, reaproveitar=True)
        try:
            dados = json.loads(txt) if txt else []
        except json.JSONDecodeError:
            continue
        for var in dados if isinstance(dados, list) else []:
            for res in var.get("resultados", []):
                cats = "; ".join(f"{c.get('classificacao', {}).get('nome')}: {', '.join(c.get('categoria', {}).values())}"
                                 for c in res.get("classificacoes", []))
                for s in res.get("series", []):
                    loc = s.get("localidade", {})
                    for periodo, valor in (s.get("serie") or {}).items():
                        linhas.append({"tabela": t["id"], "tabela_nome": t["nome"], "variavel": var.get("variavel"),
                                       "unidade": var.get("unidade"), "categorias": cats,
                                       "municipio_ibge": loc.get("id"), "municipio": loc.get("nome"),
                                       "periodo": periodo, "valor": valor})
    if linhas:
        with open(PRONTO / "censo2022_5_cidades.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(linhas[0].keys()), delimiter=";")
            w.writeheader()
            w.writerows(linhas)
        info(f"   {len(linhas)} valores salvos em dados_prontos\\censo2022_5_cidades.csv")


# ------------------------------------------------------------------ 4. INEP Ideb
def extrair_planilha_inep(conteudo_zip: bytes, alvos: set, destino_csv: Path):
    try:
        import openpyxl
    except ImportError:
        info("   (openpyxl não instalado: guardei o ZIP sem extrair)")
        return 0
    try:
        z = zipfile.ZipFile(io.BytesIO(conteudo_zip))
    except zipfile.BadZipFile:
        return 0
    n = 0
    for nome in z.namelist():
        if not nome.lower().endswith(".xlsx"):
            continue
        wb = openpyxl.load_workbook(io.BytesIO(z.read(nome)), read_only=True, data_only=True)
        ws = wb.active
        saida = []
        for linha in ws.iter_rows(values_only=True):
            valores = ["" if v is None else str(v).strip() for v in linha]
            acerto = any(v in alvos for v in valores[:6])
            if acerto:
                saida.append(valores)
                n += 1
            elif len(saida) < 12 and not n:
                saida.append(valores)
        destino_csv.parent.mkdir(parents=True, exist_ok=True)
        with open(destino_csv, "w", newline="", encoding="utf-8-sig") as f:
            csv.writer(f, delimiter=";").writerows(saida)
    return n


def etapa_ideb():
    info("2/4 INEP: Ideb por município e por escola")
    base = "https://download.inep.gov.br/ideb/resultados"
    for edicao in (2025, 2023):
        achou = False
        for etapa in ("anos_iniciais", "anos_finais", "ensino_medio"):
            for nivel in ("municipios", "escolas"):
                arq = f"divulgacao_{etapa}_{nivel}_{edicao}.zip"
                dados = baixar("ideb", f"{base}/{arq}", BRUTO / "inep" / arq, reaproveitar=True)
                if not dados:
                    continue
                achou = True
                alvos = set(MUNICIPIOS) if nivel == "municipios" else {CARIACICA}
                n = extrair_planilha_inep(dados, alvos, PRONTO / "ideb" / f"ideb_{edicao}_{etapa}_{nivel}.csv")
                info(f"   Ideb {edicao} {etapa} ({nivel}): {n} linhas de interesse")
        if achou:
            break


# ------------------------------------------------------------------ main
def main():
    for p in (BRUTO, PRONTO):
        p.mkdir(parents=True, exist_ok=True)
    inicio = time.time()
    info("RAIO-X DE CARIACICA v2 - baixando dados oficiais")
    info("Separado do Vigia: pode rodar ao mesmo tempo. Se parar, rode de novo e ele continua.")
    for etapa in (etapa_localidades, etapa_ideb, etapa_bairros, etapa_censo_municipios):
        try:
            etapa()
        except Exception as e:  # noqa: BLE001
            info(f"   Erro inesperado em {etapa.__name__}: {e}. Seguindo.")
            registrar(etapa.__name__, "", None, f"erro: {e}")
    ok = [r for r in REGISTRO if r["status"].startswith("ok")]
    falhas = [r for r in REGISTRO if not r["status"].startswith("ok")]
    salvar_json({"versao": 2, "gerado_em": dt.datetime.now().isoformat(timespec="seconds"),
                 "minutos": round((time.time() - inicio) / 60, 1), "registro": REGISTRO}, BASE / "resumo.json")
    with open(BASE / "LOG.txt", "w", encoding="utf-8") as f:
        f.write(f"Raio-X v2 - {dt.datetime.now():%d/%m/%Y %H:%M}\n")
        f.write(f"Downloads ok: {len(ok)} | falhas: {len(falhas)}\n\n")
        for r in falhas + ok:
            f.write(f"[{r['status']}] {r['etapa']} {r['url']}\n")
    info(f"Pronto em {(time.time() - inicio) / 60:.1f} min. Ok: {len(ok)} | falhas: {len(falhas)}")
    info("Avise o Claude no chat para ele ler os resultados.")


if __name__ == "__main__":
    main()
