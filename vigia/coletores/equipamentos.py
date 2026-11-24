"""Equipamentos públicos por bairro: postos de saúde e escolas de Cariacica, com o bairro de cada um.

Para que serve: a página "Meu bairro" do site mostra o posto de saúde e as escolas que ficam no bairro, e
liga cada posto à fila de espera (data/fila/) e cada escola ao Ideb (data/raiox/ideb-escolas-cariacica.csv).

Fontes oficiais (sem chave):
- CNES, API de dados abertos do Ministério da Saúde: estabelecimentos de Cariacica (código IBGE 320130) dos tipos
  1 (posto de saúde) e 2 (centro de saúde/unidade básica). Paginada de 20 em 20.
      https://apidadosabertos.saude.gov.br/cnes/estabelecimentos?codigo_municipio=320130&codigo_tipo_unidade=2
- Mapa da educação do Governo do ES (IJSN, dados.es.gov.br): escolas georreferenciadas de todo o Estado; o
  coletor guarda só as de Cariacica. CODESCOLA é o código do INEP, o mesmo do Ideb.

Saída: data/equipamentos/saude.csv e data/equipamentos/escolas.csv. Nenhum dado pessoal (só endereço do
prédio público). Uma fonte que falhar ou vier vazia não apaga o arquivo anterior.
"""
from __future__ import annotations

import csv
import io
import logging

import pandas as pd

from .. import armazem
from ..config import DADOS
from ..http import sessao

log = logging.getLogger("vigia.equipamentos")

PASTA = DADOS / "equipamentos"
CNES = "https://apidadosabertos.saude.gov.br/cnes/estabelecimentos"
TIPOS_SAUDE = {1: "Posto de saúde", 2: "Unidade de saúde"}
ESCOLAS_ES = ("https://dados.es.gov.br/dataset/80d53564-45d2-459d-9601-77685ab8fdf1/resource/"
              "7ea9bafe-86da-4c02-b163-e547e3be8553/download/mapaeducacao.csv")
MUNICIPIO_IBGE6 = "320130"


def ler_cnes(paginas: list[list[dict]]) -> pd.DataFrame:
    linhas = []
    for pagina in paginas:
        for e in pagina:
            linhas.append({
                "cnes": str(e.get("codigo_cnes", "")).strip(),
                "nome": str(e.get("nome_fantasia") or e.get("nome_razao_social") or "").strip(),
                "tipo": TIPOS_SAUDE.get(e.get("codigo_tipo_unidade"), str(e.get("codigo_tipo_unidade", ""))),
                "bairro": str(e.get("bairro_estabelecimento") or "").strip(),
                "endereco": " ".join(str(x) for x in (e.get("endereco_estabelecimento"),
                                                      e.get("numero_estabelecimento")) if x).strip(),
                "cep": str(e.get("codigo_cep_estabelecimento") or "").strip(),
                "lat": e.get("latitude_estabelecimento_decimo_grau") or "",
                "lon": e.get("longitude_estabelecimento_decimo_grau") or "",
            })
    df = pd.DataFrame(linhas)
    if df.empty:
        return df
    return df[df["cnes"] != ""].drop_duplicates("cnes")


def ler_escolas_es(texto: str) -> pd.DataFrame:
    leitor = csv.DictReader(io.StringIO(texto.lstrip("﻿")), delimiter=";")
    linhas = []
    for r in leitor:
        if (r.get("MUNICIPIO") or "").strip().lower() != "cariacica":
            continue
        linhas.append({
            "inep": (r.get("CODESCOLA") or "").strip(),
            "nome": (r.get("NOME") or "").strip(),
            "rede": (r.get("ADMINISTRA") or "").strip(),
            "etapa": (r.get("CLASSECNAE") or "").strip(),
            "bairro": (r.get("BAIRRO") or "").strip(),
            "endereco": " ".join(x for x in ((r.get("LOGRADOURO") or "").strip(), (r.get("NUMERO") or "").strip()) if x),
            "lat": (r.get("COORDY") or "").replace(",", "."),
            "lon": (r.get("COORDX") or "").replace(",", "."),
        })
    return pd.DataFrame(linhas)


def _paginas_cnes(s, tipo: int) -> list[list[dict]]:
    """A API pagina com limit=20. Em 12/11/2026, offset=20 voltou vazio com mais de 20 unidades: o offset pode ser
    o número da página, e não de registros. O coletor testa os dois jeitos e para quando a página se repete."""
    def pagina(offset):
        r = s.get(CNES, params={"codigo_municipio": MUNICIPIO_IBGE6, "codigo_tipo_unidade": tipo,
                                "limit": 20, "offset": offset}, timeout=90)
        r.raise_for_status()
        return r.json().get("estabelecimentos") or []
    primeira = pagina(0)
    paginas = [primeira] if primeira else []
    if len(primeira) < 20:
        return paginas
    vistos = {e.get("codigo_cnes") for e in primeira}
    for passo in (20, 1):                 # registros pulados ou número da página
        n, novos_total = 1, 0
        while n < 200:
            lote = pagina(n * passo)
            novos = [e for e in lote if e.get("codigo_cnes") not in vistos]
            if not novos:
                break
            vistos.update(e.get("codigo_cnes") for e in novos)
            paginas.append(novos)
            novos_total += len(novos)
            if len(lote) < 20:
                break
            n += 1
        if novos_total:
            break
    return paginas


def _saude(s) -> None:
    paginas = []
    for tipo in TIPOS_SAUDE:
        paginas += _paginas_cnes(s, tipo)
    df = ler_cnes(paginas)
    if len(df) < 10:
        raise ValueError(f"CNES: só {len(df)} unidades de saúde em Cariacica; arquivo anterior mantido")
    armazem.gravar(df, PASTA / "saude.csv", chave=["cnes"], ordenar=["bairro", "nome"])
    log.info("CNES: %d unidades de saúde", len(df))


def _escolas(s) -> None:
    r = s.get(ESCOLAS_ES, timeout=180, headers={"Accept": "text/csv,*/*"})
    r.raise_for_status()
    texto = r.content.decode("utf-8", errors="replace")
    df = ler_escolas_es(texto)
    if len(df) < 50:
        raise ValueError(f"Mapa da educação: só {len(df)} escolas em Cariacica; arquivo anterior mantido")
    armazem.gravar(df, PASTA / "escolas.csv", chave=["inep", "nome"], ordenar=["bairro", "nome"])
    log.info("Mapa da educação: %d escolas", len(df))


def coletar(s=None) -> None:
    s = s or sessao()
    erros = []
    for nome, f in (("saúde (CNES)", _saude), ("escolas (IJSN)", _escolas)):
        try:
            f(s)
        except Exception as e:   # uma fonte não derruba a outra
            log.error("Equipamentos, %s: %s", nome, e)
            erros.append(f"{nome}: {e}")
    if len(erros) == 2:
        raise RuntimeError("; ".join(erros))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    coletar()
