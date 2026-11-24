"""Sonda de fontes: testa, de dentro do GitHub Actions, as fontes de dados que ainda não usamos.

Por que existe: o ambiente do Claude na nuvem não alcança as APIs públicas brasileiras, mas o
GitHub Actions alcança. Em vez de abrir à mão cada site e copiar amostras, esta sonda
baixa uma amostra de cada fonte candidata (os primeiros 200 KB) e grava em data/sonda/, com um
resumo em data/sonda/RESULTADO.md. Com as amostras no repositório, qualquer chat escreve o coletor
de verdade com o formato real em mãos.

Como usar: no GitHub, Actions > "Sonda de fontes" > Run workflow (ou mude este arquivo e faça push).

Dados pessoais: fontes que podem trazer nome de pessoa (folha, escalas) são guardadas só como
estrutura (`so_chaves`: nomes dos campos e tipos, nenhum valor) ou só o cabeçalho do CSV
(`so_cabecalho`); todo texto passa por mascarar_cpfs. Arquivos binários (xlsx, pdf, zip) são
dicionários de dados oficiais e ficam como vieram. Para arquivos grandes (`so_http`) só os
cabeçalhos HTTP são guardados (tamanho, tipo), nunca o corpo.

A chave da CGU (segredo CHAVE_TRANSPARENCIA) é usada só se existir; sem ela, as fontes da CGU
respondem "sem chave" e isso fica registrado (é a prova de que a chave faz falta).

Rodada 2 (08/11/2026) confirmou ~45 fontes (ver docs/MAPA_DO_DINHEIRO.md); a rodada 3 (mesmo dia) testa o que
ficou em aberto: detalhes de licitação e AFO no portal, dispensas e parcerias em outros anos, PPA,
o host novo do Transferegov (api-publica), georreferenciamento do Estado, transferências
constitucionais do Tesouro, CNES, paginação do Obrasgov e FNDE por POST. A rodada 4 (10/11/2026, revisão
do projeto) testa os assuntos que o Vigia ainda não cobre: empréstimos (SADIPEM, RGF 2, 4 e 5, CADIP),
previdência dos servidores (ISP, CADPREV), royalties e CFEM, merenda e SIOPE (FNDE), openDataSUS, Querido
Diário, PNTP, IEGM e pareceres do TCE-ES, e se o Cloudflare do portal ainda bloqueia a sonda. A lista de
cada rodada fica no histórico do git deste arquivo.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
from vigia.texto import mascarar_cpfs  # noqa: E402  (LGPD: nenhum CPF inteiro vai para o git)

_EMAIL = re.compile(r"[\w.%+-]{1,64}@[\w-]{1,63}(?:\.[\w-]{1,63}){1,4}")


def mascarar_emails(texto: str) -> str:
    """Amostra é para ver a estrutura da fonte: e-mail não é necessário e pode ser pessoal (24/11/2026)."""
    return _EMAIL.sub("[e-mail omitido]", texto)


_COL_DOC = ("CpfCnpjNis", "CpfCnpj", "CPFCNPJ", "CpfCnpjFornecedor", "CpfCnpjFavorecido", "CPF_CNPJ")
_CNPJ = re.compile(r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}")


def sem_nome_de_pessoa_fisica(texto: str) -> str:
    """Amostra em CSV: linha de pessoa física (TipoFavorecido=1, ou documento que não é CNPJ) fica sem nome e sem
    histórico, como nos pagamentos da prefeitura (24/11/2026). A estrutura da fonte, que é o que a sonda quer ver, fica."""
    import csv
    import io
    linhas = texto.splitlines(keepends=True)
    if not linhas:
        return texto
    sep = ";" if linhas[0].count(";") > linhas[0].count(",") else ","
    try:
        rows = list(csv.reader(io.StringIO(texto), delimiter=sep))
    except csv.Error:
        return texto
    cab = rows[0]
    doc = next((cab.index(c) for c in _COL_DOC if c in cab), None)
    tipo = cab.index("TipoFavorecido") if "TipoFavorecido" in cab else None
    nomes = [i for i, c in enumerate(cab) if (("Favorecido" in c or c.lower().startswith("nome")) and
                                               not c.startswith(("Tipo", "Id", "Cpf", "Codigo")) and "Tipo" not in c)]
    historico = [i for i, c in enumerate(cab) if c.lower().startswith(("historico", "descricao", "descrição", "objeto", "observacao", "observação"))]
    descricao = [i for i, c in enumerate(cab) if c.lower().startswith(("descricao", "descrição", "historico", "histórico",
                                                                       "objeto", "observacao", "observação", "objetivo",
                                                                       "justificativa"))]
    if not descricao and (not nomes or (doc is None and tipo is None)):
        return texto
    for r in rows[1:]:
        if len(r) != len(cab):         # linha quebrada ou com separador a mais no texto livre: as colunas se
            r[:] = [x if re.fullmatch(r"[\d\s.,/:\-]*", x) else "(omitido na amostra)" for x in r]   # deslocam;
            r.extend([""] * (len(cab) - len(r)))                                    # só números ficam
            continue
        for i in descricao:            # texto livre pode citar pessoa em qualquer linha; a amostra só precisa da estrutura
            if r[i].strip():
                r[i] = "(omitida na amostra)"
        for i in nomes:                # empresa individual com o CPF do dono no nome
            if re.search(r"\*{2,}\.?\d{3}\.?\d{3}-?\*{2,}", r[i]):
                r[i] = "EMPRESA INDIVIDUAL (nome do titular omitido)"
        pf = (tipo is not None and r[tipo].strip() == "1") or (
            doc is not None and r[doc].strip() != "" and not _CNPJ.fullmatch(r[doc].strip()))
        if pf:
            for i in nomes:
                r[i] = "PESSOA FÍSICA"
            for i in historico:
                r[i] = "(omitido: pessoa física)"
    out = io.StringIO(newline="")
    csv.writer(out, delimiter=sep, lineterminator="\n").writerows(rows)
    return out.getvalue()


PASTA = RAIZ / "data" / "sonda"
LIMITE = 200_000  # bytes guardados por fonte
TIMEOUT = 60
PARALELO = 6
IBGE = "3201308"
UA = "VigiaCariacica/1.0 (controle social; github.com/vigiacariacica/vigia-cariacica)"

P = "https://wstransparencia.cariacica.es.gov.br/api"            # portal da prefeitura
ES = "https://dados.es.gov.br"                                    # dados abertos do Estado (CKAN)
SICONFI = "https://apidatalake.tesouro.gov.br/ords/siconfi/tt"
TG = "https://api.transferegov.gestao.gov.br"
CGU = "https://api.portaldatransparencia.gov.br/api-de-dados"
SAUDE = "https://apidadosabertos.saude.gov.br"
OBRAS = "https://api.obrasgov.gestao.gov.br/obrasgov/api"
TT = "https://www.tesourotransparente.gov.br/ckan"


def ckan_show(nome: str) -> str:
    return f"{ES}/api/3/action/package_show?id={nome}"


def es_recurso(dataset: str, recurso: str, arquivo: str) -> str:
    return f"{ES}/dataset/{dataset}/resource/{recurso}/download/{arquivo}"


# nome, url, para que serve, opções:
#   chave=True        manda a chave da CGU (segredo CHAVE_TRANSPARENCIA)
#   so_cabecalho=True guarda só a primeira linha (CSV que pode ter nome de pessoa)
#   so_chaves=True    guarda só a estrutura do JSON (campos e tipos), nenhum valor
#   binario=True      grava os bytes como vieram (xlsx, pdf, zip de dicionário), sem mascarar
#   so_http=True      não guarda o corpo: só os cabeçalhos HTTP (tamanho, tipo), para arquivos grandes
#   ua_navegador=True manda User-Agent de navegador (sites que bloqueiam robôs declarados)
#   post={...}        envia POST com esses campos de formulário em vez de GET
FONTES = [
    # ------------------------------------------------------------ rodada 5 (10/11/2026): amostras para escrever os coletores da revisão
    ("tesouro_show_pvl_oc_cp", f"{TT}/api/3/action/package_show?id=pvl-oc-cp", "Cronogramas de pagamento das operações de crédito contratadas (URLs dos arquivos)", {}),
    ("tesouro_show_pvl_oc_cl", f"{TT}/api/3/action/package_show?id=pvl-oc-cl", "Cronogramas de liberação (desembolso) das operações contratadas", {}),
    ("tesouro_show_pvl_resumo_oc", f"{TT}/api/3/action/package_show?id=pvl-resumo-oc", "Resumo dos cronogramas de pagamento (contratadas e a contratar)", {}),
    ("tesouro_show_cauc", f"{TT}/api/3/action/package_show?id=cauc", "CAUC: arquivos (URLs e datas)", {}),
    ("tesouro_cauc_municipios", f"{TT}/dataset/72b5f371-0c35-4613-8076-c99c821a6410/resource/07af297a-5e59-494a-a88a-55ddfd2f4b01/download/relatorio-situacao-de-varios-entes---municipios---uf-todas---abrangencia-1.csv", "CAUC de todos os municípios (começo do arquivo e tamanho)", {}),
    ("isp_2025_planilha", "https://www.gov.br/previdencia/pt-br/assuntos/rpps/indice-de-situacao-previdenciaria/arquivos/resultado-final-isp-2025-_-publicado-em-04_12_2025-1.xlsx", "ISP 2025: planilha com o resultado de cada regime (arquivo inteiro)", {"binario": True, "limite": 8_000_000, "ua_navegador": True}),
    ("portal_pessoal_mensal_2025", f"{P}/pessoal/mensal?exercicio=2025", "Folha: total por mês de 2025", {}),
    ("portal_pessoal_cargo_2025_12", f"{P}/pessoal/cargo?exercicio=2025&mes=12", "Folha por cargo, dez/2025 (agregado, sem nome)", {}),
]


def _estrutura(valor, nivel: int = 0):
    """Estrutura de um JSON sem nenhum valor: dict -> {campo: tipo}, lista -> [estrutura do 1º item, n]."""
    if isinstance(valor, dict):
        return {k: _estrutura(v, nivel + 1) for k, v in list(valor.items())[:60]}
    if isinstance(valor, list):
        return [_estrutura(valor[0], nivel + 1) if valor else None, f"{len(valor)} itens"]
    return type(valor).__name__


UA_NAVEGADOR = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"


def baixar(url: str, opcoes: dict) -> tuple[int | str, str, bytes, float, dict]:
    h = {"User-Agent": UA_NAVEGADOR if opcoes.get("ua_navegador") else UA,
         "Accept": "application/json, text/csv, text/html;q=0.8, */*;q=0.5"}
    if opcoes.get("chave"):
        chave = os.environ.get("CHAVE_TRANSPARENCIA", "")
        if not chave:
            return "sem chave (segredo CHAVE_TRANSPARENCIA ausente)", "", b"", 0.0, {}
        h["chave-api-dados"] = chave
    t0 = dt.datetime.now()
    try:
        if opcoes.get("post") is not None:
            r = requests.post(url, data=opcoes["post"], headers=h, timeout=TIMEOUT, stream=True)
        else:
            r = requests.get(url, headers=h, timeout=TIMEOUT, stream=True)
        cab = {k: v for k, v in r.headers.items() if k.lower() in ("content-type", "content-length", "last-modified", "content-disposition")}
        corpo = b""
        if not opcoes.get("so_http"):
            for pedaco in r.iter_content(65536):
                corpo += pedaco
                if len(corpo) >= opcoes.get("limite", LIMITE):
                    break
        r.close()
        return r.status_code, r.headers.get("Content-Type", ""), corpo[:opcoes.get("limite", LIMITE)], (dt.datetime.now() - t0).total_seconds(), cab
    except Exception as e:  # noqa: BLE001
        return f"erro: {type(e).__name__}: {str(e)[:120]}", "", b"", (dt.datetime.now() - t0).total_seconds(), {}


def extensao(tipo: str, corpo: bytes, url: str) -> str:
    t = tipo.lower()
    if "json" in t or corpo[:1] in (b"{", b"["):
        return "json"
    if "spreadsheet" in t or "excel" in t or corpo[:2] == b"PK" and "xlsx" in url.lower():
        return "xlsx"
    if "pdf" in t or corpo[:4] == b"%PDF":
        return "pdf"
    if "zip" in t or corpo[:2] == b"PK":
        return "zip"
    if "csv" in t or url.lower().endswith(".csv") or "/csv" in url.lower():
        return "csv"
    if "html" in t:
        return "html"
    return "txt"


def resumo_conteudo(corpo: bytes, ext: str) -> str:
    if ext in ("xlsx", "pdf", "zip"):
        return f"binário {ext}, {len(corpo)} bytes guardados"
    texto = corpo.decode("utf-8", errors="replace")
    if ext == "json":
        try:
            j = json.loads(texto)
            if isinstance(j, dict):
                return "chaves: " + ", ".join(list(j.keys())[:25])
            if isinstance(j, list) and j and isinstance(j[0], dict):
                return f"lista de {len(j)}+ itens; campos: " + ", ".join(list(j[0].keys())[:30])
            return f"json ({type(j).__name__})"
        except json.JSONDecodeError:
            return "json cortado em 200 KB: " + re.sub(r"\s+", " ", texto[:200])
    if ext == "html":
        titulo = re.search(r"<title>(.*?)</title>", texto, re.I | re.S)
        return "html: " + (titulo.group(1).strip()[:120] if titulo else "sem título")
    if ext == "csv":
        linhas = texto.splitlines()
        return f"{len(linhas)} linhas na amostra; cabeçalho: " + linhas[0][:300] if linhas else "vazio"
    return re.sub(r"\s+", " ", texto[:300])


def sondar(fonte) -> tuple[str, str]:
    nome, url, para_que, op = fonte
    status, tipo, corpo, segundos, cab = baixar(url, op)
    ext = extensao(tipo, corpo, url)
    veio = ""
    if op.get("so_http"):
        veio = "cabeçalhos: " + json.dumps(cab, ensure_ascii=False)
        (PASTA / f"{nome}.json").write_text(json.dumps(cab, ensure_ascii=False, indent=1), encoding="utf-8")
    elif corpo:
        if op.get("so_chaves") and ext == "json":
            try:
                corpo = json.dumps(_estrutura(json.loads(corpo.decode("utf-8", errors="replace"))),
                                   ensure_ascii=False, indent=1).encode("utf-8")
                veio = "só a estrutura (campos e tipos): " + re.sub(r"\s+", " ", corpo.decode("utf-8"))[:400]
            except json.JSONDecodeError:
                corpo = corpo.split(b"\n", 1)[0][:2000]
                veio = "json cortado; guardado só o começo"
        elif op.get("so_cabecalho") or op.get("so_chaves"):
            corpo = corpo.split(b"\n", 1)[0][:2000]
            veio = "só o cabeçalho: " + corpo.decode("utf-8", errors="replace")[:400]
        if ext in ("xlsx", "pdf", "zip") or op.get("binario"):
            if ext not in ("xlsx", "pdf", "zip"):
                ext = "bin"
        else:
            texto = mascarar_emails(mascarar_cpfs(corpo.decode("utf-8", errors="replace")))
            if ext == "csv":
                texto = sem_nome_de_pessoa_fisica(texto)
            corpo = texto.encode("utf-8")
            veio = veio or resumo_conteudo(corpo, ext)
        (PASTA / f"{nome}.{ext}").write_bytes(corpo)
        veio = veio or resumo_conteudo(corpo, ext)
    veio = veio.replace("|", "/").replace("\n", " ")
    linha = f"| [{nome}]({url}) | {para_que} | {status} | {tipo.split(';')[0]} | {len(corpo)} | {segundos:.1f} | {veio[:500]} |"
    print(f"{nome}: {status} {tipo.split(';')[0]} {len(corpo)} bytes {segundos:.1f}s")
    return nome, linha


def main() -> int:
    PASTA.mkdir(parents=True, exist_ok=True)   # amostras de rodadas anteriores ficam (servem para escrever coletores)
    linhas = ["# Sonda de fontes", "", f"Rodada em {dt.datetime.utcnow():%Y-%m-%d %H:%M} (UTC) no GitHub Actions. "
              "Amostras (até 200 KB) ao lado; esta tabela diz o que cada fonte respondeu. "
              "Fontes com nome de pessoa guardam só a estrutura ou o cabeçalho.", "",
              "| Fonte | Para que serve | HTTP | Tipo | Bytes | s | O que veio |", "|---|---|---|---|---|---|---|"]
    with ThreadPoolExecutor(max_workers=PARALELO) as ex:
        resultados = dict(ex.map(sondar, FONTES))
    for nome, *_ in FONTES:
        linhas.append(resultados[nome])
    (PASTA / "RESULTADO.md").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
