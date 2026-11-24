"""Teste do coletor com um servidor falso (CKAN do dados.es.gov.br, SICONFI e TSE)."""
import io, json, shutil, sys, tempfile, threading, zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
import baixar_financas as B  # noqa: E402

def zip_de(arquivos):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        for nome, conteudo in arquivos.items():
            z.writestr(nome, conteudo)
    return b.getvalue()

# empenhos em latin-1 com ; e coluna do credor com cidade (não pode ser usada como filtro)
EMP = ("NomeEnte;Credor;MunicipioCredor;Valor;Data\n"
       "Prefeitura Municipal de Cariacica;EMPRESA A LTDA;Vitória;1000,00;2024-01-02\n"
       "Prefeitura Municipal de Colatina;EMPRESA B LTDA;Cariacica;500,00;2024-01-03\n"
       "Câmara Municipal de Vila Velha;EMPRESA C;Linhares;20,00;2024-02-01\n"
       "Prefeitura Municipal da Serra;JOSÉ;Serra;30,00;2024-02-01\n"
       "Prefeitura Municipal de Linhares;X;Serra;30,00;2024-02-01\n").encode("latin-1")
DESP = "ano,cod_ibge,municipio,funcao,valor\n2023,3201308,CARIACICA,Saúde,10\n2023,3203205,LINHARES,Saúde,5\n2023,3205101,VIANA,Educação,7\n"
PESSOAL = "Municipio;RCL;Pessoal\nCariacica;100;50\nLinhares;80;30\n"
CAND = ("SG_UF;NM_UE;NM_CANDIDATO;NM_MUNICIPIO_NASCIMENTO\nES;CARIACICA;FULANO;VITORIA\nES;LINHARES;BELTRANO;CARIACICA\n"
        "ES;VITÓRIA;CICLANO;SAO PAULO\n").encode("latin-1")
RECEITAS = ("SG_UF;NM_UE;NR_CPF_CNPJ_DOADOR;NM_DOADOR;VR_RECEITA\nES;CARIACICA;12345678000199;EMPRESA DOADORA;1000,00\n"
            "ES;COLATINA;1;X;5\n").encode("latin-1")

ARQS = {
    "/f/emp2024.zip": zip_de({"empenhos_2024.csv": EMP}),
    "/f/emp2019.zip": zip_de({"empenhos_2019.csv": EMP}),
    "/f/desp2023.csv": DESP.encode(),
    "/f/pessoal.csv": PESSOAL.encode(),
    "/f/dicionario.csv": "campo;descricao\nNomeEnte;Nome do ente\n".encode(),
    "/tse/candidatos.zip": zip_de({"consulta_cand_2024_ES.csv": CAND, "consulta_cand_2024_SP.csv": CAND, "leiame.pdf": b"%PDF"}),
    "/tse/contas.zip": zip_de({"receitas_candidatos_2024_ES.csv": RECEITAS, "receitas_candidatos_2024_BRASIL.csv": RECEITAS}),
}
BASE = {}
PACOTES = {
    "tcees-empenho": [("municipios-despesas-empenhos-1-2024", "/f/emp2024.zip", "ZIP"),
                      ("municipios-despesas-empenhos-1-2019", "/f/emp2019.zip", "ZIP"),
                      ("Dicionário de dados", "/f/dicionario.csv", "CSV")],
    "despesas-municipios": [("municipios-despesas-2023.csv", "/f/desp2023.csv", "CSV")],
    "tcees-despesas-com-saude-educacao-e-pessoal-receita-corrente-liquida-e-endividamento": [("Pessoal", "/f/pessoal.csv", "CSV")],
}
CHAMADAS = {"siconfi": 0}

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, corpo, tipo="application/octet-stream", cod=200):
        self.send_response(cod); self.send_header("Content-Type", tipo); self.send_header("Content-Length", str(len(corpo)))
        self.end_headers(); self.wfile.write(corpo)
    def do_GET(self):
        u = urlparse(self.path); q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path == "/ckan":
            slug = q["id"]
            if slug not in PACOTES:
                return self._send(json.dumps({"success": False}).encode(), "application/json", 404)
            res = [{"id": f"{slug}-{i}", "name": n, "url": BASE["u"] + path, "format": fmt, "last_modified": "2026-11-01"}
                   for i, (n, path, fmt) in enumerate(PACOTES[slug])]
            return self._send(json.dumps({"success": True, "result": {"title": slug.upper(), "notes": "x", "resources": res}}).encode(), "application/json")
        if u.path.startswith("/siconfi/"):
            CHAMADAS["siconfi"] += 1
            ep = u.path.rsplit("/", 1)[-1]
            if q.get("id_ente") != "3201308" or ep != "dca" or q.get("no_anexo") != "DCA-Anexo I-E" or q.get("an_exercicio") != "2023":
                return self._send(json.dumps({"items": [], "hasMore": False}).encode(), "application/json")
            off = int(q.get("offset", 0))
            itens = [{"exercicio": 2023, "cod_ibge": 3201308, "conta": f"conta {i}", "valor": i} for i in range(off, min(off + 3, 7))]
            return self._send(json.dumps({"items": itens, "hasMore": off + 3 < 7, "offset": off, "limit": 3}).encode(), "application/json")
        if u.path in ARQS:
            return self._send(ARQS[u.path])
        self._send(b"nao", cod=404)

def main():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    BASE["u"] = f"http://127.0.0.1:{srv.server_port}"
    tmp = Path(tempfile.mkdtemp(prefix="fin_teste_"))
    B.DADOS = tmp; B.BRUTOS = tmp / "brutos"; B.FILTRADO = tmp / "filtrado"
    B.ESTADO_ARQ, B.LOG_ARQ, B.ESQUEMA_ARQ = tmp / "estado.json", tmp / "LOG.txt", tmp / "ESQUEMA.txt"
    B.CKAN = BASE["u"] + "/ckan?id="
    B.SICONFI = BASE["u"] + "/siconfi/"
    B.TSE = [(BASE["u"] + "/tse/contas.zip", "contas_2024"), (BASE["u"] + "/tse/candidatos.zip", "candidatos_2024")]
    B.ANOS_FECHADOS = [2023]; B.ANO_ATUAL = 2024; B.PAUSA_API = 0
    B.CIDADES = {k: v for k, v in B.CIDADES.items()}
    B.sessao.trust_env = False
    B.main([])
    falhas = []
    def ler(rel):
        return (tmp / "filtrado" / rel).read_text("utf-8")
    emp = ler("tcees-empenho/municipios-despesas-empenhos-1-2024/empenhos_2024.csv")
    if "Colatina" in emp or "Linhares;X" in emp: falhas.append("empenho: filtrou pelo município do credor")
    if emp.count("\n") != 4: falhas.append(f"empenho: esperava 3 linhas + cabeçalho, veio {emp.count(chr(10))}")
    if "Câmara Municipal de Vila Velha" not in emp: falhas.append("empenho: perdeu acento (latin-1)")
    if (tmp / "filtrado" / "tcees-empenho" / "municipios-despesas-empenhos-1-2019").exists(): falhas.append("empenho 2019 não deveria ser baixado")
    desp = ler("despesas-municipios/municipios-despesas-2023/municipios-despesas-2023.csv")
    if "LINHARES" in desp or "VIANA" not in desp: falhas.append("despesas: filtro errado")
    pes = ler("tcees-despesas-com-saude-educacao-e-pessoal-receita-corrente-liquida-e-endividamento/Pessoal/Pessoal.csv")
    if "Linhares" not in pes: falhas.append("pessoal deveria vir inteiro")
    cand = ler("tse/candidatos_2024/consulta_cand_2024_ES.csv")
    if "BELTRANO" in cand or "CICLANO" not in cand: falhas.append("TSE candidatos: filtro errado (usar NM_UE)")
    if (tmp / "filtrado" / "tse" / "candidatos_2024" / "consulta_cand_2024_SP.csv").exists(): falhas.append("TSE: não devia ler SP")
    rec = ler("tse/contas_2024/receitas_candidatos_2024_ES.csv")
    if "COLATINA" in rec: falhas.append("TSE receitas: filtro errado")
    sic = list((tmp / "siconfi").glob("dca_3201308_2023_*AnexoIE*.json"))
    if not sic or len(json.loads(sic[0].read_text())) != 7: falhas.append("SICONFI: paginação errada")
    n1 = CHAMADAS["siconfi"]
    B.main([])  # segunda rodada: não deve repetir nada
    if CHAMADAS["siconfi"] - n1 > 30: falhas.append(f"SICONFI repetiu consultas na 2ª rodada: {CHAMADAS['siconfi'] - n1}")
    esq = (tmp / "ESQUEMA.txt").read_text("utf-8")
    if "coluna 'NomeEnte'" not in esq or "coluna 'NM_UE'" not in esq: falhas.append("ESQUEMA não registrou a coluna usada")
    print("\n" + ("FALHAS:\n  " + "\n  ".join(falhas) if falhas else "OK: coletor de finanças passou em todos os testes."))
    print("pasta:", tmp)
    srv.shutdown()
    sys.exit(1 if falhas else 0)

if __name__ == "__main__":
    main()
