"""Importa o que o baixar_financas.py guardou para um banco SQLite (financas/dados/financas.db).

- Cada grupo de CSVs com o mesmo cabeçalho vira uma tabela (ex.: os 5 arquivos de empenhos de cada
  ano entram juntos em "tcees_empenho").
- O SICONFI vira a tabela "siconfi" (uma linha por conta/coluna de cada relatório).
- Os nomes das colunas ficam como no original, só sem acentos e espaços.

Uso: python importar.py          (refaz o banco do zero; leva alguns minutos)
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
import sys
import unicodedata
from pathlib import Path

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
RAIZ = Path(__file__).resolve().parent
DADOS = RAIZ / "dados"
FILTRADO = DADOS / "filtrado"
BANCO = DADOS / "financas.db"
CIDADES = {"3201308": "Cariacica", "3205309": "Vitória", "3205200": "Vila Velha", "3205002": "Serra",
           "3205101": "Viana", "3202405": "Guarapari", "3202207": "Fundão"}


def col(nome: str) -> str:
    s = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_") or "coluna"
    return ("c_" + s) if s[0].isdigit() else s


def nome_tabela(dataset: str, cab: list[str], arquivo: Path) -> str:
    base = col(dataset)
    # arquivos diferentes do mesmo conjunto (ex.: "Itens" e "Obras" em contratações) viram tabelas separadas
    tipo = re.sub(r"(_?20\d\d)|(_\d+)$|(-\d+-)", "", col(arquivo.stem))
    tipo = re.sub(r"_+", "_", tipo).strip("_")
    assinatura = hashlib.md5("|".join(cab).encode()).hexdigest()[:4]
    return f"{base}__{tipo}__{assinatura}"[:120]


def importar_csvs(con):
    tabelas, por_assinatura = {}, {}
    for arq in sorted(FILTRADO.rglob("*.csv")):
        dataset = arq.relative_to(FILTRADO).parts[0]
        with arq.open(encoding="utf-8", newline="") as f:
            r = csv.reader(f, delimiter=";")
            try:
                cab = next(r)
            except StopIteration:
                continue
            cols, vistos = [], {}
            for c in cab:
                n = col(c)
                vistos[n] = vistos.get(n, 0) + 1
                cols.append(n if vistos[n] == 1 else f"{n}_{vistos[n]}")
            # mesmo conjunto + mesmo cabeçalho = mesma tabela, qualquer que seja o nome do arquivo
            chave = (dataset, tuple(cols))
            t = por_assinatura.setdefault(chave, nome_tabela(dataset, cols, arq))
            if t not in tabelas:
                con.execute(f'DROP TABLE IF EXISTS "{t}"')
                con.execute(f'CREATE TABLE "{t}" (' + ", ".join(f'"{c}" TEXT' for c in cols) + ', "_arquivo" TEXT)')
                tabelas[t] = {"colunas": cols, "linhas": 0, "arquivos": []}
            sql = f'INSERT INTO "{t}" VALUES (' + ",".join("?" * (len(cols) + 1)) + ")"
            rel = str(arq.relative_to(FILTRADO))
            lote = []
            for l in r:
                l = (l + [""] * len(cols))[:len(cols)]
                lote.append(l + [rel])
                if len(lote) >= 20000:
                    con.executemany(sql, lote)
                    tabelas[t]["linhas"] += len(lote)
                    lote = []
            if lote:
                con.executemany(sql, lote)
                tabelas[t]["linhas"] += len(lote)
            tabelas[t]["arquivos"].append(rel)
        print(f"  {rel} -> {t}")
    return tabelas


def importar_siconfi(con):
    pasta = DADOS / "siconfi"
    con.execute("DROP TABLE IF EXISTS siconfi")
    con.execute("""CREATE TABLE siconfi (relatorio TEXT, ano INTEGER, periodo INTEGER, periodicidade TEXT,
                   poder TEXT, ibge TEXT, cidade TEXT, populacao INTEGER, instituicao TEXT, anexo TEXT, rotulo TEXT,
                   coluna TEXT, cod_conta TEXT, conta TEXT, valor REAL)""")
    n = 0
    for arq in sorted(pasta.glob("*.json")) if pasta.exists() else []:
        rel = arq.name.split("_")[0]
        partes = arq.stem.split("_")
        poder = partes[-1] if rel == "rgf" else ""
        itens = json.loads(arq.read_text("utf-8"))
        lote = []
        for it in itens:
            ibge = str(it.get("cod_ibge") or partes[1])
            lote.append((rel, it.get("exercicio"), it.get("periodo"), it.get("periodicidade"), poder or it.get("poder"),
                         ibge, CIDADES.get(ibge, ibge), it.get("populacao"), it.get("instituicao"), it.get("anexo"),
                         it.get("rotulo"), it.get("coluna"), it.get("cod_conta"), it.get("conta"), it.get("valor")))
        con.executemany("INSERT INTO siconfi VALUES (" + ",".join("?" * 15) + ")", lote)
        n += len(lote)
    con.execute("CREATE INDEX IF NOT EXISTS ix_sic ON siconfi(relatorio, anexo, ano, ibge)")
    print(f"  siconfi: {n:,} linhas")
    return n


def main():
    DADOS.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(BANCO)
    con.execute("PRAGMA journal_mode=WAL")
    print("Importando CSVs filtrados...")
    tabelas = importar_csvs(con)
    print("Importando SICONFI...")
    importar_siconfi(con)
    con.commit()
    linhas = ["TABELAS DO BANCO financas.db", ""]
    for t, info in tabelas.items():
        linhas.append(f"{t}  ({info['linhas']:,} linhas, {len(info['arquivos'])} arquivos)")
        linhas.append("   colunas: " + ", ".join(info["colunas"]))
    (DADOS / "TABELAS.txt").write_text("\n".join(linhas), "utf-8")
    print(f"\nPronto: {BANCO}  (lista em dados/TABELAS.txt)")


if __name__ == "__main__":
    main()
