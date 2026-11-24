"""Garantia LGPD sobre o que está NO REPOSITÓRIO: nenhum CPF inteiro e válido em data/ ou docs/.

Roda sobre os arquivos reais versionados (não sobre dados fictícios). Se falhar, algum coletor ou
exportação deixou passar um CPF: corrija o código antes de publicar.
"""
import os
import re
from pathlib import Path

import pytest

from vigia.texto import cpf_valido

RAIZ = Path(__file__).resolve().parent.parent
FORMATADO = re.compile(r"(?<!\d)(\d{3})\.(\d{3})\.(\d{3})-(\d{2})(?!\d)")
ONZE = re.compile(r"(?<![\d./-])(\d{11})(?![\d/-])")


def _cpfs(texto: str):
    for m in FORMATADO.finditer(texto):
        if cpf_valido("".join(m.groups())):
            yield m.group(0)
    for m in ONZE.finditer(texto):
        if cpf_valido(m.group(1)):
            yield m.group(1)


# No GitHub, a mesma varredura roda DEPOIS da coleta (vigia/qualidade.py, varrer_cpfs): se rodasse
# antes, um arquivo antigo bloquearia justamente a coleta que o corrige.
@pytest.mark.skipif(os.environ.get("GITHUB_ACTIONS") == "true", reason="no CI roda depois da coleta")
def test_nenhum_cpf_inteiro_no_repositorio():
    achados = []
    arquivos = [*(RAIZ / "data").rglob("*.csv"), *(RAIZ / "docs").rglob("*.md")]
    for arq in arquivos:
        for n, linha in enumerate(arq.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            # colunas de valor (números com ponto decimal) não são CPF
            for cpf in _cpfs(re.sub(r"(?<![\d])\d{1,13}\.\d{1,2}(?![\d])", "", linha)):
                achados.append(f"{arq.relative_to(RAIZ)}:{n}: ...{cpf[-4:]}")
    assert not achados, f"{len(achados)} CPF(s) inteiro(s), ex.: {achados[:5]}"
