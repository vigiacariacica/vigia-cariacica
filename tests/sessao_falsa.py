"""Sessão HTTP falsa para testar coletores sem internet.

Devolve objetos requests.Response de verdade (raise_for_status, json, headers), montados por uma função
de rotas: rotas(caminho, params, cabecalhos) -> (status, corpo, cabecalhos_da_resposta). Corpo em bytes
vai como está (os CSVs do portal são windows-1252); qualquer outro corpo vira JSON.
"""
from __future__ import annotations

import json
from urllib.parse import urlencode, urlparse

import requests


def resposta(url: str, status: int, corpo, cabecalhos: dict | None = None) -> requests.Response:
    cab = dict(cabecalhos or {})
    if not isinstance(corpo, (bytes, bytearray)):
        corpo = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
        cab.setdefault("Content-Type", "application/json; charset=utf-8")
    r = requests.Response()
    r.status_code = status
    r._content = bytes(corpo)
    r._content_consumed = True          # iter_content (download em blocos) lê de _content
    r.headers.update(cab)
    r.url = url
    r.encoding = "utf-8"
    return r


class SessaoFalsa:
    def __init__(self, rotas):
        self.rotas = rotas
        self.chamadas: list[tuple[str, dict, dict]] = []
        self.headers: dict = {}

    def get(self, url, params=None, timeout=None, headers=None, stream=False):
        params = dict(params or {})
        self.chamadas.append((urlparse(url).path, params, dict(headers or {})))
        status, corpo, cab = self.rotas(urlparse(url).path, params, dict(headers or {}))
        completa = url + ("?" + urlencode(params) if params else "")
        return resposta(completa, status, corpo, cab)
