"""Cariacica inteira no Censo 2022 (agregados por município do IBGE), com as mesmas contas dos bairros.

    python ferramentas/raiox/processar_municipio.py PASTA_COM_OS_CSVS

PASTA_COM_OS_CSVS tem os CSVs de "Agregados_por_Municipio_csv" do IBGE (básico, características do domicílio 2 e
alfabetização), baixados de
https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/Agregados_por_Setores_Censitarios/Agregados_por_Municipio_csv/

Grava data/raiox/cariacica-municipio.csv, uma linha só (código 3201308). Por que existe: a soma dos 99 bairros deixa
de fora 4.387 moradores e a zona rural, então a coluna "Cariacica" do site usa o total oficial do município
(docs/DECISOES.md, 24/11/2026). Mesmas variáveis de ferramentas/raiox/processar_bairros.py.
"""
import csv
import glob
import os
import sys

CARIACICA = "3201308"
SAIDA = os.path.join(os.path.dirname(__file__), "..", "..", "data", "raiox", "cariacica-municipio.csv")


def num(x):
    x = (x or "").strip().replace(",", ".")
    try:
        return float(x)
    except ValueError:
        return None


def ler(pasta, padrao):
    f = glob.glob(os.path.join(pasta, f"*municipios*{padrao}*.csv"))[0]
    with open(f, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh, delimiter=";"):
            r = {k.upper(): v for k, v in r.items()}
            if r["CD_MUN"] == CARIACICA:
                return r
    raise SystemExit(f"Cariacica não está em {f}")


def soma(r, cods):
    return sum(num(r[c]) for c in cods)


def main(pasta):
    bas, d2, alf = ler(pasta, "basico"), ler(pasta, "domicilio2"), ler(pasta, "alfabetizacao")
    dppo = soma(d2, [f"V00{n}" for n in range(309, 317)])
    rede = soma(d2, ["V00309", "V00310"])
    agua = soma(d2, [f"V00{n}" for n in range(111, 119)])
    lixo = soma(d2, [f"V00{n}" for n in range(397, 403)])
    pop15 = soma(alf, [f"V00{n}" for n in range(644, 657)])
    alfab = soma(alf, [f"V00{n}" for n in range(748, 761)])
    linha = {
        "cd_mun": CARIACICA, "municipio": bas["NM_MUN"], "area_km2": round(num(bas["AREA_KM2"]), 3),
        "populacao": int(num(bas["V0001"])), "domicilios": int(num(bas["V0007"])),
        "domicilios_permanentes": int(dppo), "domicilios_sem_rede": int(dppo - rede),
        "pct_esgoto_rede": round(100 * rede / dppo, 1), "pct_agua_rede": round(100 * num(d2["V00111"]) / agua, 1),
        "pct_lixo_coletado": round(100 * soma(d2, ["V00397", "V00398"]) / lixo, 1),
        "pessoas_15mais": int(pop15), "pessoas_15mais_nao_alfabetizadas": int(pop15 - alfab),
        "pct_alfabetizados_15mais": round(100 * alfab / pop15, 1),
    }
    with open(SAIDA, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(linha))
        w.writeheader()
        w.writerow(linha)
    print(linha)


if __name__ == "__main__":
    main(sys.argv[1])
