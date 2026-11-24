"""Confere se o formulário de denúncia no ar (Google Formulários) ainda bate com o site (data/site/denuncia.json).

Por quê: o site manda a denúncia sem sair da página e não tem como ler a resposta do Google. Se alguém mudar uma
pergunta, uma opção ou ligar o login no Google, a denúncia pode não chegar e a pessoa ver "Recebido" mesmo assim.
Este teste avisa antes. Sai com código 1 se algo não bate.

    python ferramentas/conferir_formulario.py
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def ler_formulario(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "VigiaCariacica/1.0 (conferencia do formulario)"})
    html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
    if "ServiceLogin" in html or "accounts.google.com/v3/signin" in html:
        raise SystemExit("O formulário passou a pedir login no Google. A denúncia anônima parou de funcionar.")
    m = re.search(r"FB_PUBLIC_LOAD_DATA_ = (.*?);</script>", html, re.S)
    if not m:
        raise SystemExit("Não achei as perguntas na página do formulário (fechado ou mudou o formato?).")
    dados = json.loads(m.group(1))
    campos = {}
    for q in dados[1][1]:
        for e in q[4] or []:
            campos[f"entry.{e[0]}"] = {"obrigatorio": bool(e[2]), "opcoes": [o[0] for o in (e[1] or [])]}
    return campos


def conferir() -> list[str]:
    den = json.loads((RAIZ / "data" / "site" / "denuncia.json").read_text(encoding="utf-8"))
    no_ar = ler_formulario(den["link"])
    erros = []
    for nome, entry in den["campos"].items():
        if entry not in no_ar:
            erros.append(f"o campo '{nome}' ({entry}) não existe mais no formulário")
    obrig_site = {den["campos"][k] for k in ("assunto", "relato", "ok")}
    for entry, info in no_ar.items():
        if info["obrigatorio"] and entry not in obrig_site:
            erros.append(f"{entry} virou obrigatório no Google, e o site não obriga")
    if no_ar.get(den["campos"]["assunto"], {}).get("opcoes") != den["assuntos"]:
        erros.append("as opções de assunto no Google não são iguais às do site")
    if no_ar.get(den["campos"]["ok"], {}).get("opcoes") != [den["ok"]]:
        erros.append("o texto da caixa de concordar no Google não é igual ao do site")
    return erros


if __name__ == "__main__":
    erros = conferir()
    for e in erros:
        print("::warning::Formulário de denúncia:", e)
    print("Formulário de denúncia confere com o site." if not erros else f"{len(erros)} diferença(s).")
    sys.exit(1 if erros else 0)
