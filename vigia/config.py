"""Configuração central do Vigia Cariacica.

Duas partes, ambas auditáveis:
1. Constantes deste arquivo: o que identifica a prefeitura e as cidades de comparação.
2. `config.toml` (na raiz): parâmetros ajustáveis da coleta do PNCP e de cada regra de alerta.
   Mudou um limite? Mude lá, com comentário, e registre em docs/DECISOES.md.
"""
from __future__ import annotations

import datetime as dt
import os
import tomllib
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
# Pastas (as variáveis de ambiente servem para os testes rodarem numa pasta temporária)
DADOS = Path(os.environ.get("VIGIA_DADOS") or RAIZ / "data")    # CSVs versionados no git (abrem no Excel)
DOCS = Path(os.environ.get("VIGIA_DOCS") or RAIZ / "docs")      # relatório e qualidade, gerados
BANCO = Path(os.environ.get("VIGIA_BANCO") or RAIZ / "banco")   # SQLite (release "banco" no GitHub)

# Município monitorado
CARIACICA_IBGE = 3201308
# CNPJ da Prefeitura (Município de Cariacica). Outros órgãos municipais
# (Câmara, fundos, autarquias) são descobertos automaticamente no PNCP.
CARIACICA_CNPJS = ["27150549000119"]

# Cidades da Grande Vitória usadas na comparação (código IBGE -> nome esperado).
# O coletor confere os nomes no cadastro do Siconfi e avisa se algo não bater.
GRANDE_VITORIA = {
    3201308: "Cariacica",
    3205309: "Vitória",
    3205200: "Vila Velha",
    3205002: "Serra",
    3205101: "Viana",
    3202405: "Guarapari",
    3202207: "Fundão",
}

# Janela histórica
ANO_INICIAL_SICONFI = 2017          # pega o último ano da gestão anterior p/ comparação

# Parâmetros das regras do portal municipal (R21–R27). Os das regras R01–R20 ficam em config.toml.
ALERTAS = {
    # Aumento do valor do contrato acima do inicial (art. 125 da Lei 14.133: 25%)
    "aditivo_pct": 0.25,
}


# ---------------------------------------------------------------- config.toml
PADRAO = {
    "projeto": {
        "municipio_nome": "Cariacica",
        "municipio_ibge": str(CARIACICA_IBGE),
        "uf": "ES",
        "esferas": ["M"],
        "cnpjs_extras": [],
        "data_inicial": "2023-01-01",
        "data_final": "",
    },
    "vizinhos": {"ativo": False, "meses": 12, "modalidades": [6, 8], "municipios": {}},
    "coleta": {
        "pausa_segundos": 1.5,
        "timeout_segundos": 90,
        "max_tentativas": 6,
        "recoletar_ultimos_dias": 60,
        "coletar_itens": True,
        "coletar_resultados": True,
        "coletar_termos": True,
        "coletar_atas": True,
        "coletar_compras_externas": True,
        "modalidades": list(range(1, 14)),
    },
    "apis": {
        "pncp_consulta": "https://pncp.gov.br/api/consulta",
        "pncp": "https://pncp.gov.br/api/pncp",
        "cnpj": ["https://brasilapi.com.br/api/cnpj/v1/{cnpj}"],
        "transparencia": "https://api.portaldatransparencia.gov.br/api-de-dados",
        "chave_transparencia": "",
    },
    "alertas": {},
    "ia": {"modelo": "claude-sonnet-5-5"},
}


def _mesclar(base: dict, extra: dict) -> dict:
    saida = dict(base)
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(saida.get(k), dict):
            saida[k] = _mesclar(saida[k], v)
        else:
            saida[k] = v
    return saida


def carregar(caminho: str | Path | None = None) -> dict:
    """Lê config.toml (valores ausentes usam PADRAO). A chave da CGU pode vir da variável
    de ambiente CHAVE_TRANSPARENCIA (segredo do GitHub), para nunca ficar no repositório."""
    caminho = Path(caminho) if caminho else RAIZ / "config.toml"
    cfg = PADRAO
    if caminho.exists():
        with open(caminho, "rb") as f:
            cfg = _mesclar(PADRAO, tomllib.load(f))
    if os.environ.get("CHAVE_TRANSPARENCIA"):
        cfg["apis"]["chave_transparencia"] = os.environ["CHAVE_TRANSPARENCIA"]
    cfg["_caminho"] = str(caminho)
    cfg["_pasta_dados"] = str(Path(cfg.get("_pasta_dados") or BANCO))
    return cfg


def periodo(cfg: dict) -> tuple[dt.date, dt.date]:
    p = cfg["projeto"]
    ini = dt.date.fromisoformat(p["data_inicial"])
    fim = dt.date.fromisoformat(p["data_final"]) if p.get("data_final") else dt.date.today()
    return ini, fim


def alerta(cfg: dict, chave: str, padrao):
    return cfg.get("alertas", {}).get(chave, padrao)
