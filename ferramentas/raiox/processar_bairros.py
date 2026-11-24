"""Calcula indicadores por bairro (Censo 2022) e Ideb 2025 por escola, a partir dos CSVs oficiais."""
import csv, glob, os, sys, json, statistics

BASE = sys.argv[1]  # .../raiox/dados_prontos
OUT = sys.argv[2]
B = os.path.join(BASE, "bairros")
CID = {"3201308": "Cariacica", "3205309": "Vitória", "3205200": "Vila Velha", "3205002": "Serra", "3205101": "Viana"}


def num(x):
    if x is None:
        return None
    x = x.strip().replace(",", ".")
    if x in ("", ".", "X", "-", "..", "..."):
        return None
    try:
        return float(x)
    except ValueError:
        return None


def ler(padrao):
    f = glob.glob(os.path.join(B, f"*{padrao}*.csv"))[0]
    with open(f, encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh, delimiter=";"))
    return {r["CD_BAIRRO"]: {k.upper(): v for k, v in r.items()} for r in rows}


bas = ler("basico")
ren = ler("renda_responsavel")
d2 = ler("domicilio2")
alf = ler("alfabetizacao")


def soma(r, cods):
    vals = [num(r.get(c)) for c in cods]
    if any(v is None for v in vals):
        return None
    return sum(vals)


def pct(a, b):
    if a is None or b in (None, 0):
        return None
    return round(100 * a / b, 1)


linhas = []
for cd, r in bas.items():
    mun = r["CD_MUN"]
    if mun not in CID:
        continue
    pop = num(r.get("V0001"))
    dom = num(r.get("V0007"))
    x2 = d2.get(cd, {})
    xr = ren.get(cd, {})
    xa = alf.get(cd, {})
    dppo = soma(x2, ["V00309", "V00310", "V00311", "V00312", "V00313", "V00314", "V00315", "V00316"])
    rede = soma(x2, ["V00309", "V00310"])
    precario = soma(x2, ["V00312", "V00313", "V00314", "V00315", "V00316"])
    lixo_tot = soma(x2, ["V00397", "V00398", "V00399", "V00400", "V00401", "V00402"])
    lixo_col = soma(x2, ["V00397", "V00398"])
    agua_tot = soma(x2, ["V00111", "V00112", "V00113", "V00114", "V00115", "V00116", "V00117", "V00118"])
    pop15 = soma(xa, [f"V00{n}" for n in range(644, 657)])
    alfab = soma(xa, [f"V00{n}" for n in range(748, 761)])
    linhas.append({
        "cd_bairro": cd,
        "bairro": r["NM_BAIRRO"],
        "cidade": CID[mun],
        "distrito": r.get("NM_DIST", ""),
        "area_km2": round(num(r.get("AREA_KM2")) or 0, 3),
        "populacao": int(pop) if pop is not None else None,
        "domicilios": int(dom) if dom is not None else None,
        "renda_media": num(xr.get("V06004")),
        "renda_mediana": num(xr.get("V06006")),
        "pct_esgoto_rede": pct(rede, dppo),
        "pct_esgoto_precario": pct(precario, dppo),
        "pct_sem_banheiro": pct(num(x2.get("V00495")), soma(x2, ["V00494", "V00495"])),
        "pct_agua_rede": pct(num(x2.get("V00111")), agua_tot),
        "pct_lixo_coletado": pct(lixo_col, lixo_tot),
        "pct_lixo_jogado": pct(num(x2.get("V00401")), lixo_tot),
        "pct_alfabetizados_15mais": pct(alfab, pop15),
        "pessoas_15mais_nao_alfabetizadas": int(pop15 - alfab) if pop15 is not None and alfab is not None else None,
    })

os.makedirs(OUT, exist_ok=True)
campos = list(linhas[0].keys())
with open(os.path.join(OUT, "bairros-indicadores.csv"), "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=campos)
    w.writeheader()
    for l in sorted(linhas, key=lambda z: (z["cidade"], z["bairro"])):
        w.writerow(l)

# ---- Ideb por escola (Cariacica) e por município
I = os.path.join(BASE, "ideb")


def ler_inep(f):
    with open(f, encoding="utf-8-sig") as fh:
        rows = list(csv.reader(fh, delimiter=";"))
    cab = rows[9]
    out = []
    for r in rows[10:]:
        if len(r) < len(cab) or not r[0].strip():
            continue
        out.append(dict(zip(cab, r)))
    return out


etapas = {"anos_iniciais": "Anos iniciais (1º–5º)", "anos_finais": "Anos finais (6º–9º)", "ensino_medio": "Ensino médio"}
esc = []
mun = []
for e, rot in etapas.items():
    for r in ler_inep(os.path.join(I, f"ideb_2025_{e}_escolas.csv")):
        if r["CO_MUNICIPIO"] != "3201308":
            continue
        esc.append({
            "id_escola": r["ID_ESCOLA"], "escola": r["NO_ESCOLA"].strip(), "rede": r["REDE"], "etapa": rot,
            "ideb_2023": num(r.get("VL_OBSERVADO_2023")), "ideb_2025": num(r.get("VL_OBSERVADO_2025")),
            "aprovacao_2025": num(r.get("VL_APROVACAO_2025_SI_4")),
            "nota_mat_2025": num(r.get("VL_NOTA_MATEMATICA_2025")), "nota_port_2025": num(r.get("VL_NOTA_PORTUGUES_2025")),
        })
    for r in ler_inep(os.path.join(I, f"ideb_2025_{e}_municipios.csv")):
        if r["CO_MUNICIPIO"] not in CID:
            continue
        mun.append({"cidade": CID[r["CO_MUNICIPIO"]], "rede": r["REDE"], "etapa": rot,
                    "ideb_2023": num(r.get("VL_OBSERVADO_2023")), "ideb_2025": num(r.get("VL_OBSERVADO_2025"))})

for nome, dados in (("ideb-escolas-cariacica.csv", esc), ("ideb-municipios.csv", mun)):
    with open(os.path.join(OUT, nome), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(dados[0].keys()))
        w.writeheader()
        w.writerows(dados)

# ---- resumo no terminal
car = [l for l in linhas if l["cidade"] == "Cariacica"]
print("bairros Cariacica:", len(car), "pop total:", sum(l["populacao"] or 0 for l in car))
for k in ["renda_mediana", "pct_esgoto_rede", "pct_esgoto_precario", "pct_sem_banheiro", "pct_agua_rede", "pct_lixo_coletado", "pct_alfabetizados_15mais"]:
    v = [l[k] for l in car if l[k] is not None and (l["populacao"] or 0) >= 300]
    print(k, "n", len(v), "min", min(v), "med", statistics.median(v), "max", max(v))
print("faltando renda:", sum(1 for l in car if l["renda_mediana"] is None))
print("escolas linhas:", len(esc), "com ideb 2025:", sum(1 for x in esc if x["ideb_2025"] is not None))
print(json.dumps([m for m in mun if m["rede"] in ("Pública", "Municipal")], ensure_ascii=False)[:2500])
