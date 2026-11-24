"""Guarda do repositório público (24/11/2026): nada de senha, chave ou e-mail pessoal nos arquivos versionados,
e os links diretos das planilhas da fila (que trazem dados de pacientes) nunca entram no git.

Complementa tests/test_lgpd.py (CPF). Varre só texto; binários (fontes, imagens, planilhas de dicionário) ficam
de fora."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

SEGREDOS = {
    "token do GitHub": re.compile(rb"gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}"),
    "chave de API": re.compile(rb"\bsk[-_](?:ant-|proj-|live_)?[A-Za-z0-9_-]{24,}|AIza[0-9A-Za-z_-]{35}|AKIA[0-9A-Z]{16}"),
    "chave privada": re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "senha na URL": re.compile(rb"https?://[^/\s:@\"']{1,64}:[^/\s@\"'$]{1,64}@"),
}
EMAIL = re.compile(rb"[\w.%+-]{1,64}@([\w-]{1,63}(?:\.[\w-]{1,63}){1,4})")
# E-mail que pode aparecer: o público do Vigia, endereços "noreply" e órgãos públicos.
EMAIL_OK = re.compile(rb"(^|\.)(gov\.br|jus\.br|leg\.br|mp\.br|tc\.br|def\.br|noreply\.github\.com|anthropic\.com)$")
EMAIL_VIGIA = b"vigiacariacica@gmail.com"
NUNCA_NO_GIT = ["data/fila/links.csv", "data/fila/arquivos.csv"]


def _versionados() -> list[Path]:
    try:
        saida = subprocess.run(["git", "-C", str(RAIZ), "ls-files", "-z"], capture_output=True, check=True).stdout
        return [RAIZ / p for p in saida.decode().split("\0") if p]
    except (OSError, subprocess.CalledProcessError):     # fora de um clone git: varre a pasta
        return [p for p in RAIZ.rglob("*") if p.is_file() and ".git" not in p.parts]


def _texto(p: Path) -> bytes | None:
    try:
        b = p.read_bytes()
    except OSError:
        return None
    return None if b"\x00" in b[:8000] else b


def test_sem_senha_nem_chave():
    achados = []
    for p in _versionados():
        if p.name == "test_publico.py" or (b := _texto(p)) is None:
            continue
        for nome, rx in SEGREDOS.items():
            if rx.search(b):
                achados.append(f"{p.relative_to(RAIZ)}: {nome}")
    assert not achados, achados


def test_sem_email_pessoal():
    """Código, documentos e amostras da sonda (que mascara e-mail). Os CSVs gerados pelos coletores ficam de fora
    aqui: um e-mail novo vindo do portal não pode parar a coleta inteira; o saneamento deles é dos coletores."""
    achados = []
    for p in _versionados():
        rel = p.relative_to(RAIZ).as_posix()
        if rel.startswith("data/") and not rel.startswith("data/sonda/"):
            continue
        if p.name == "test_publico.py" or (b := _texto(p)) is None:
            continue
        for m in EMAIL.finditer(b):
            if m.group(0).lower() == EMAIL_VIGIA or EMAIL_OK.search(m.group(1).lower()):
                continue
            achados.append(f"{p.relative_to(RAIZ)}: e-mail de domínio {m.group(1).decode(errors='replace')}")
            break
    assert not achados, achados[:20]


def test_sem_link_direto_de_planilha_com_dado_de_paciente():
    rx = re.compile(rb"docs\.google\.com/spreadsheets|drive\.google\.com/(?:uc|file)|uploads/files/[^\s,\"']*fila")
    achados = [p.relative_to(RAIZ).as_posix() for p in _versionados()
               if p.relative_to(RAIZ).as_posix().startswith("data/") and (b := _texto(p)) is not None and rx.search(b)]
    assert not achados, achados


def test_fiscal_de_contrato_sem_nome():
    import csv
    sobra = []
    for p in sorted((RAIZ / "data" / "transparencia").glob("*.csv")):
        if not p.name.startswith(("contratos_", "emergenciais_")):
            continue
        with open(p, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                if r.get("Fiscal", "").strip() not in ("", "(servidor designado; nome omitido)"):
                    sobra.append(p.name)
                    break
    assert not sobra, sobra


def test_nome_de_pessoa_sai_da_descricao_do_empenho():
    from vigia.coletores.transparencia import sem_servidor_na_descricao as f
    casos = {
        "ressarcimento da servidora cedida Fulana Beltrana Souza, durante o exercício": "Fulana",
        "CESSAO DA SERVIDORA FULANA DE TAL, CONFORME DOCUMENTAÇÃO ANEXA.": "FULANA",
        "pagamento de pensão em favor de Ciclana Pereira Lima relativo decisão judicial": "Ciclana",
        "Órgão cedente: Município de Vitória Servidora: Beltrana Ramos – cargo: auxiliar": "Beltrana",
        "cessão do (a) servidor (a), FULANO DOS SANTOS, titular do cargo, matricula nº356425-2": "356425",
    }
    for texto, some in casos.items():
        assert some not in f(texto), texto
    for fica in ("SERVIDORES DESTA MUNICIPALIDADE, RELATIVO AO MÊS", "em favor da empresa ALFA SERVIÇOS LTDA",
                 "SERVIDOR CEDIDO PELA PREFEITURA DE VILA VELHA", "UNIDADE DE PRONTO ATENDIMENTO MONSENHOR FULANO"):
        assert f(fica) == fica


def test_descricao_que_cita_pessoa_sai_inteira():
    from vigia.coletores.transparencia import DESCRICAO_OMITIDA, descricao_publica as f
    for texto in ("PAGAMENTO DE HOSPEDAGEM PARA PACIENTE FULANA BELTRANA SOUZA EM TRATAMENTO",
                  "TRANSPORTE DO MENOR CICLANO PEREIRA DOS SANTOS PARA REINTEGRAÇÃO",
                  "REMOÇÃO DE CORPO DE BELTRANO RAMOS LIMA",
                  "INDENIZAÇÃO A SRA FULANA DE TAL QUEIROZ",
                  "SERVIDOR - CONVÊNIO 015/2021 - CICLANO EDUARDO MENDES",
                  "contratação por meio do representante exclusivo Fulano Beltrano Ciclano, inscrito no CPF nº ***.123.456-**"):
        assert f(texto) == DESCRICAO_OMITIDA, texto
    assert "98765" not in f("servidora cedida, MATRÍCULA: 98765")
    for fica in ("AQUISIÇÃO DE MATERIAL DE LIMPEZA PARA AS UNIDADES DE SAÚDE",
                 "REF. CONTRATO 123/2024 COM A EMPRESA ALFA LTDA"):
        assert f(fica) == fica


def test_links_da_fila_fora_do_git():
    assert not [f for f in NUNCA_NO_GIT if (RAIZ / f).exists() and (RAIZ / f) in set(_versionados())]
    ignorados = (RAIZ / ".gitignore").read_text(encoding="utf-8")
    assert all(f in ignorados for f in NUNCA_NO_GIT)
