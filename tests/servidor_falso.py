"""Servidor local que imita as APIs do PNCP e da Receita com os dados fictícios."""
from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import dados_ficticios as F

ESTADO = {"429_enviados": 0, "chamadas": 0}


def _ymd(s):
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, status=200):
        corpo = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _vazio(self, status=204):
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _paginar(self, regs, q, padrao=50):
        pag = int(q.get("pagina", ["1"])[0])
        tam = int(q.get("tamanhoPagina", [str(padrao)])[0])
        if not regs:
            return self._vazio()
        total_pag = (len(regs) + tam - 1) // tam
        fatia = regs[(pag - 1) * tam: pag * tam]
        self._json({"data": fatia, "totalRegistros": len(regs), "totalPaginas": total_pag, "numeroPagina": pag,
                    "paginasRestantes": max(total_pag - pag, 0), "empty": not fatia})

    def do_GET(self):
        ESTADO["chamadas"] += 1
        u = urlparse(self.path)
        q = parse_qs(u.query)
        p = u.path

        if p == "/consulta/v1/contratacoes/publicacao":
            ini, fim = _ymd(q["dataInicial"][0]), _ymd(q["dataFinal"][0])
            mod = int(q["codigoModalidadeContratacao"][0])
            ibge = q.get("codigoMunicipioIbge", [None])[0]
            regs = [c for c in F.COMPRAS if ini <= c["dataPublicacaoPncp"][:10] <= fim and c["modalidadeId"] == mod
                    and (ibge is None or c["unidadeOrgao"]["codigoIbge"] == ibge)
                    and c["orgaoEntidade"]["cnpj"] != F.CONS]
            return self._paginar(regs, q)

        if p == "/consulta/v1/contratos":
            if ESTADO["429_enviados"] == 0:      # simula a API pedindo calma uma vez
                ESTADO["429_enviados"] += 1
                return self._vazio(429)
            ini, fim = _ymd(q["dataInicial"][0]), _ymd(q["dataFinal"][0])
            cnpj = q.get("cnpjOrgao", [None])[0]
            regs = [c for c in F.CONTRATOS if ini <= c["dataPublicacaoPncp"][:10] <= fim
                    and c["orgaoEntidade"]["cnpj"] == cnpj]
            return self._paginar(regs, q, 500)

        if p == "/consulta/v1/atas":
            return self._vazio()

        m = re.fullmatch(r"/pncp/v1/orgaos/(\d+)/compras/(\d+)/(\d+)(/itens(?:/(\d+)/resultados)?)?", p)
        if m:
            cnpj, ano, seq, sub, n = m.groups()
            id_ = f"{cnpj}-1-{int(seq):06d}/{ano}"
            if not sub:
                for c in F.COMPRAS:
                    if c["numeroControlePNCP"] == id_:
                        return self._json(c)
                return self._vazio(404)
            if n:
                return self._json(F.RESULTADOS.get((id_, int(n)), []))
            itens = F.ITENS.get(id_, [])
            pag, tam = int(q.get("pagina", ["1"])[0]), int(q.get("tamanhoPagina", ["10"])[0])
            return self._json(itens[(pag - 1) * tam: pag * tam])

        m = re.fullmatch(r"/pncp/v1/orgaos/(\d+)/contratos/(\d+)/(\d+)/termos", p)
        if m:
            cnpj, ano, seq = m.groups()
            return self._json(F.TERMOS.get(f"{cnpj}-2-{int(seq):06d}/{ano}", []))

        m = re.fullmatch(r"/cnpj/(\d+)", p)
        if m:
            d = F.RECEITA.get(m.group(1))
            return self._json(d) if d else self._vazio(404)

        self._vazio(404)


def iniciar():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"
