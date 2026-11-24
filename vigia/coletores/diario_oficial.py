"""Diário Oficial de Cariacica: o que cada edição traz de compra sem licitação, emergência, aditivo e crédito extra.

Fonte: a API pública que o próprio site do Diário usa (https://diariooficial.cariacica.es.gov.br):
    GET https://api.cariacica.es.gov.br/api/publicacao/v1/diario/          lista das edições (15 por página)
    GET https://api.cariacica.es.gov.br/api/publicacao/v1/diario/<id>      edição com o texto completo
-> data/diario_oficial/edicoes.csv: uma linha por edição, só CONTAGENS por tipo de ato e a soma dos créditos
   suplementares ou especiais abertos por decreto. Nenhum trecho de texto é gravado.

LGPD: o texto do Diário tem nomes de servidores, nomeações e exonerações. Por isso o arquivo público guarda só
números (quantas menções de cada tipo e valores de crédito), a data, o número da edição e o link. Quem quiser
ler o ato abre o Diário pelo link.

Para não pesar: só baixa o texto das edições que ainda não estão no CSV (no primeiro uso, as dos últimos 30 dias).
"""
from __future__ import annotations

import csv
import logging
import re
from datetime import date, timedelta

from ..config import DADOS
from ..http import sessao

log = logging.getLogger("vigia.diario_oficial")
FONTE = "diario_oficial"
PASTA = DADOS / "diario_oficial"
ARQ = PASTA / "edicoes.csv"
API = "https://api.cariacica.es.gov.br/api/publicacao/v1/diario/"
SITE = "https://diariooficial.cariacica.es.gov.br/"
DIAS_INICIAIS = 30
CAMPOS = ["edicao", "data", "dispensa", "inexigibilidade", "emergencia", "aditivo", "carona_em_ata",
          "contratacao_temporaria", "creditos_qtd", "creditos_valor", "link"]
TERMOS = {
    "dispensa": r"dispensa de licita",
    "inexigibilidade": r"inexigibilidade",
    "emergencia": r"emergencial|situa[cç][aã]o de emerg",
    "aditivo": r"termo aditivo",
    "carona_em_ata": r"ades[aã]o [àa] ata",
    "contratacao_temporaria": r"contrata[cç][aã]o tempor[aá]ria",
}
CREDITO = re.compile(r"CR[ÉE]DITO (?:SUPLEMENTAR|ESPECIAL) NO VALOR DE R\$ ?([\d\.]+,\d{2})", re.I)


def contar(texto: str) -> dict:
    """Contagens por tipo de ato e soma dos créditos abertos. Só números: nada do texto sai daqui."""
    linha = {k: len(re.findall(p, texto, re.I)) for k, p in TERMOS.items()}
    valores = [float(v.replace(".", "").replace(",", ".")) for v in CREDITO.findall(texto)]
    linha["creditos_qtd"] = len(valores)
    linha["creditos_valor"] = f"{sum(valores):.2f}"
    return linha


def _ja_vistas() -> set[str]:
    if not ARQ.exists():
        return set()
    with ARQ.open(encoding="utf-8") as f:
        return {r["edicao"] for r in csv.DictReader(f)}


def coletar() -> None:
    PASTA.mkdir(parents=True, exist_ok=True)
    s = sessao()
    vistas = _ja_vistas()
    corte = (date.today() - timedelta(days=DIAS_INICIAIS)).isoformat()
    novas, url = [], API
    while url:
        pagina = s.get(url, timeout=60).json()
        parar = False
        for ed in pagina.get("results", []):
            if ed.get("publicacao", "") < corte:
                parar = True
                break
            if str(ed["edicao"]) not in vistas:
                novas.append(ed)
        url = None if parar else (pagina.get("next") or "").replace("http://", "https://") or None
    for ed in novas:
        texto = (s.get(API + ed["id"], timeout=180).json().get("texto") or "")
        if not texto:
            log.warning("edição %s sem texto; fica para a próxima", ed["edicao"])
            continue
        linha = {"edicao": ed["edicao"], "data": ed["publicacao"], **contar(texto), "link": SITE}
        novo = not ARQ.exists()
        with ARQ.open("a", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=CAMPOS)
            if novo:
                w.writeheader()
            w.writerow(linha)
    log.info("diario_oficial: %d edições novas", len(novas))
