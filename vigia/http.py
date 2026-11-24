"""Dois clientes HTTP:

- `sessao()`: para baixar arquivos grandes (CSV do portal, Siconfi), com novas tentativas.
- `Cliente`: para APIs JSON (PNCP, Receita, CGU). Faz pausa entre chamadas, tenta de novo, e
  guarda cada resposta na tabela `bruto` do banco, com URL e data: é a prova de onde veio cada número.
"""
from __future__ import annotations

import json
import logging
import random
import time
from urllib.parse import urlencode

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from . import log as aviso_log

log = logging.getLogger("vigia.http")

USER_AGENT = "VigiaCariacica/1.0 (controle social; +https://github.com/vigiacariacica/vigia-cariacica)"


def sessao() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=6,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        respect_retry_after_header=True,
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers["User-Agent"] = USER_AGENT
    s.headers["Accept"] = "application/json"
    return s


class LimiteDeTentativas(Exception):
    pass


class AcessoNegado(Exception):
    """401/403: a API recusou o acesso (bloqueio do robô, chave inválida). Nunca é tratado como
    "sem dados": derruba a fonte para a execução ficar vermelha."""


class Cliente:
    def __init__(self, cfg: dict, con):
        c = cfg["coleta"]
        self.pausa = float(c.get("pausa_segundos", 1.5))
        self.timeout = float(c.get("timeout_segundos", 90))
        self.tentativas = int(c.get("max_tentativas", 6))
        self.espera_inicial = float(c.get("espera_inicial_segundos", 20))
        self.con = con
        self.sessao = requests.Session()
        self.sessao.headers.update({
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        })
        self._ultima = 0.0
        self.chamadas = 0
        self.do_cache = 0

    @staticmethod
    def montar_url(base: str, params: dict | None = None) -> str:
        if not params:
            return base
        limpos = {k: v for k, v in sorted(params.items()) if v not in (None, "")}
        return f"{base}?{urlencode(limpos)}"

    def _esperar(self):
        falta = self.pausa - (time.monotonic() - self._ultima)
        if falta > 0:
            time.sleep(falta)

    def get(self, base: str, params: dict | None = None, usar_cache: bool = True,
            cabecalhos: dict | None = None):
        """Retorna (status, dados_json_ou_None).

        200 e 204 (sem conteúdo) vêm do cache quando usar_cache=True; 404 é sempre consultado de novo.
        401/403 levantam AcessoNegado. Outros 4xx voltam com o status para quem chamou decidir
        (e não são gravados como prova)."""
        url = self.montar_url(base, params)
        if usar_cache:
            linha = self.con.execute("SELECT status, corpo FROM bruto WHERE url=?", (url,)).fetchone()
            if linha is not None and linha["status"] in (200, 204):
                self.do_cache += 1
                return linha["status"], (json.loads(linha["corpo"]) if linha["corpo"] else None)

        espera = self.espera_inicial
        for tentativa in range(1, self.tentativas + 1):
            self._esperar()
            try:
                r = self.sessao.get(url, timeout=self.timeout, headers=cabecalhos)
                self._ultima = time.monotonic()
                self.chamadas += 1
            except requests.RequestException as e:
                self._ultima = time.monotonic()
                aviso_log.aviso(f"Falha de rede ({e.__class__.__name__}) em {url} - tentativa {tentativa}")
                time.sleep(espera)
                espera = min(espera * 2, 300)
                continue

            tipo = r.headers.get("Content-Type", "")
            if r.status_code == 429 or (r.status_code == 200 and "html" in tipo.lower()):
                aviso_log.aviso(f"API pediu calma (HTTP {r.status_code}). Esperando {espera}s...")
                time.sleep(espera + random.uniform(0, espera * 0.25))
                espera = min(espera * 2, 600)
                continue
            if r.status_code >= 500:
                aviso_log.aviso(f"Erro {r.status_code} no servidor em {url} - tentativa {tentativa}")
                time.sleep(espera)
                espera = min(espera * 2, 300)
                continue

            if r.status_code in (401, 403):
                raise AcessoNegado(f"HTTP {r.status_code} em {url}")
            corpo = None
            if r.status_code == 200 and r.content:
                try:
                    corpo = r.json()
                except ValueError:
                    aviso_log.aviso(f"Resposta não é JSON em {url}")
                    corpo = None
            texto = json.dumps(corpo, ensure_ascii=False) if corpo is not None else None
            if r.status_code in (200, 204, 404):
                self.con.execute(
                    "INSERT OR REPLACE INTO bruto(url,status,corpo,baixado_em) "
                    "VALUES (?,?,?,datetime('now','localtime'))", (url, r.status_code, texto))
            return r.status_code, corpo

        raise LimiteDeTentativas(f"Não consegui baixar {url} após {self.tentativas} tentativas")
