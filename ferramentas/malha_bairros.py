"""Mapa dos bairros de Cariacica (IBGE, Censo 2022) para o site.

Roda no GitHub Actions (workflow "Mapa dos bairros"), porque o IBGE não abre do computador de quem desenvolve.
1. Procura no FTP de geociências do IBGE a malha de bairros do Censo 2022 (arquivo do ES ou do Brasil).
   Se não achar, usa a malha de setores censitários do ES e junta os setores por código de bairro.
2. Recorta Cariacica (3201308), simplifica (~15 m) e grava data/raiox/bairros-cariacica.geojson com
   cd_bairro e nome, coordenadas com 5 casas (~1 m).
Pode rodar de novo: sobrescreve o arquivo. Escreve no log tudo o que encontrou.
"""
from __future__ import annotations

import io
import json
import re
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import urljoin

RAIZ = ("https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/"
        "malhas_de_setores_censitarios__divisoes_intramunicipais/censo_2022/")
CARIACICA = "3201308"
SAIDA = Path(__file__).resolve().parents[1] / "data" / "raiox" / "bairros-cariacica.geojson"
UA = {"User-Agent": "VigiaCariacica/1.0 (controle social; dados publicos)"}


def abrir(url: str, timeout: int = 600) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def links(url: str) -> list[str]:
    html = abrir(url, 60).decode("utf-8", "replace")
    return [urljoin(url, h) for h in re.findall(r'href="([^"?#]+)"', html) if not h.startswith(("/", ".."))]


def procurar(url: str, profundidade: int = 4) -> list[str]:
    """Todos os arquivos .zip/.gpkg abaixo de url (lista de diretórios do servidor do IBGE)."""
    achados = []
    try:
        filhos = links(url)
    except Exception as e:  # noqa: BLE001
        print("  não abriu", url, e)
        return achados
    for f in filhos:
        if f.endswith("/") and profundidade > 0:
            achados += procurar(f, profundidade - 1)
        elif re.search(r"\.(zip|gpkg)$", f, re.I):
            achados.append(f)
    return achados


def ler(url: str):
    import geopandas as gpd
    print("baixando", url)
    dados = abrir(url)
    print("  tamanho", len(dados) // 1024, "KB")
    with tempfile.TemporaryDirectory() as tmp:
        if url.lower().endswith(".zip"):
            zipfile.ZipFile(io.BytesIO(dados)).extractall(tmp)
            alvos = list(Path(tmp).rglob("*.shp")) + list(Path(tmp).rglob("*.gpkg"))
        else:
            alvo = Path(tmp) / "malha.gpkg"
            alvo.write_bytes(dados)
            alvos = [alvo]
        print("  arquivos", [a.name for a in alvos])
        return gpd.read_file(alvos[0])


def main() -> int:
    import geopandas as gpd  # noqa: F401
    arquivos = procurar(RAIZ)
    print(len(arquivos), "arquivos no FTP do IBGE (Censo 2022)")
    for a in arquivos:
        if re.search(r"bairro|ES_|_ES\b|/ES", a, re.I):
            print("  ", a)
    bairro = [a for a in arquivos if re.search(r"bairro", a, re.I)]
    bairro_es = [a for a in bairro if re.search(r"(^|[/_])ES[_.]", a)] or bairro
    setores_es = [a for a in arquivos if re.search(r"setor", a, re.I) and re.search(r"(^|[/_])ES[_.]", a)]
    gdf = None
    for url in sorted(bairro_es, key=len):
        try:
            g = ler(url)
            print("  colunas", list(g.columns))
            col_mun = next(c for c in g.columns if c.upper() in ("CD_MUN", "CD_MUNICIP", "CD_GEOCODM"))
            g = g[g[col_mun].astype(str) == CARIACICA]
            if len(g):
                gdf = g
                break
        except Exception as e:  # noqa: BLE001
            print("  falhou", e)
    if gdf is None:
        for url in setores_es:
            try:
                g = ler(url)
                print("  colunas", list(g.columns))
                g = g[g["CD_MUN"].astype(str) == CARIACICA]
                gdf = g.dissolve(by=["CD_BAIRRO", "NM_BAIRRO"], as_index=False)
                break
            except Exception as e:  # noqa: BLE001
                print("  falhou", e)
    if gdf is None or not len(gdf):
        print("ERRO: não achei a malha de bairros de Cariacica")
        return 1
    col_cd = next(c for c in gdf.columns if c.upper() in ("CD_BAIRRO", "CD_BAIRRO_", "CD_BAI"))
    col_nm = next(c for c in gdf.columns if c.upper() in ("NM_BAIRRO", "NM_BAI", "NOME"))
    gdf = gdf.to_crs(4674) if gdf.crs and gdf.crs.to_epsg() != 4674 else gdf
    gdf["geometry"] = gdf.geometry.simplify(0.00015, preserve_topology=True)
    feats = []
    for _, r in gdf.sort_values(col_cd).iterrows():
        geo = json.loads(gpd.GeoSeries([r.geometry]).to_json())["features"][0]["geometry"]

        def arred(x):
            return [arred(y) for y in x] if isinstance(x, list) and x and isinstance(x[0], (list, tuple)) \
                else [round(x[0], 5), round(x[1], 5)]
        geo["coordinates"] = arred(geo["coordinates"])
        feats.append({"type": "Feature", "properties": {"cd_bairro": str(r[col_cd]), "nome": str(r[col_nm])},
                      "geometry": geo})
    SAIDA.write_text(json.dumps({"type": "FeatureCollection", "fonte": "IBGE, malha do Censo 2022", "features": feats},
                                ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("gravado", SAIDA, len(feats), "bairros,", SAIDA.stat().st_size // 1024, "KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
