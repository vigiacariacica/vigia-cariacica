"""Avisa os buscadores que usam o IndexNow (Bing, que alimenta o DuckDuckGo e o Yahoo; Yandex; Seznam; Naver)
das páginas do site que mudaram. O Google não usa IndexNow: para ele, o caminho é o Search Console (docs/BUSCA.md).

Roda no GitHub Actions (workflow "Avisar buscadores"). Compara o repositório público vigiacariacica.github.io
com o último commit já avisado (guardado no cache do Actions) e manda só as páginas que mudaram. Na primeira
vez, ou se o cache sumir, manda todas. Antes, confere se o arquivo da chave já está no ar.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PUBLICO = "https://github.com/vigiacariacica/vigiacariacica.github.io.git"
ESTADO = Path(os.environ.get("ESTADO_INDEXNOW", RAIZ / ".indexnow" / "ultimo.txt"))
ENDPOINT = "https://api.indexnow.org/indexnow"


def git(*args: str, cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def url_de(arquivo: str, base: str) -> str | None:
    if not arquivo.endswith(".html") or arquivo == "404.html":
        return None
    if arquivo == "index.html":
        return base + "/"
    if arquivo.endswith("/index.html"):
        return f"{base}/{arquivo[:-len('index.html')]}"
    return f"{base}/{arquivo}"


def main() -> int:
    dominio_txt = RAIZ / "data" / "site" / "dominio.txt"
    host = (dominio_txt.read_text().strip() if dominio_txt.exists() else "") or "vigiacariacica.github.io"
    base = f"https://{host}"
    chave = json.loads((RAIZ / "data" / "site" / "buscadores.json").read_text(encoding="utf-8")).get("indexnow", "")
    if not chave:
        print("sem chave do IndexNow em data/site/buscadores.json")
        return 0
    try:
        no_ar = urllib.request.urlopen(f"{base}/{chave}.txt", timeout=30).read().decode().strip()
    except Exception as e:  # noqa: BLE001
        no_ar = f"erro: {e}"
    if no_ar != chave:
        print("o arquivo da chave ainda não está no ar; tento na próxima vez:", no_ar[:80])
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "publico"
        subprocess.run(["git", "clone", "--quiet", "--depth", "300", PUBLICO, str(repo)], check=True)
        cabeca = git("rev-parse", "HEAD", cwd=repo)
        anterior = ESTADO.read_text().strip() if ESTADO.exists() else ""
        if anterior == cabeca:
            print("nada mudou desde o último aviso", cabeca[:7])
            return 0
        arquivos = []
        if anterior:
            try:
                arquivos = git("diff", "--name-only", anterior, cabeca, cwd=repo).splitlines()
            except subprocess.CalledProcessError:
                anterior = ""
        if not anterior:
            arquivos = git("ls-files", cwd=repo).splitlines()
    urls = sorted({u for a in arquivos if (u := url_de(a, base))})
    print(len(urls), "páginas para avisar", "(todas)" if not anterior else f"(mudaram desde {anterior[:7]})")
    if urls:
        corpo = json.dumps({"host": host, "key": chave, "keyLocation": f"{base}/{chave}.txt",
                            "urlList": urls[:10000]}).encode()
        req = urllib.request.Request(ENDPOINT, data=corpo, method="POST",
                                     headers={"Content-Type": "application/json; charset=utf-8"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                print("IndexNow respondeu", r.status)
        except urllib.error.HTTPError as e:
            print("IndexNow recusou:", e.code, e.read()[:300])
            return 1 if e.code not in (429,) else 0
    ESTADO.parent.mkdir(parents=True, exist_ok=True)
    ESTADO.write_text(cabeca)
    return 0


if __name__ == "__main__":
    sys.exit(main())
