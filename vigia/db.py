"""Banco SQLite (banco/vigia.db): PNCP completo, dados das empresas, alertas e respostas cruas.

Não vai para o git (é grande). Fica na release "banco" do GitHub: o workflow baixa no início e
sobe no fim de cada execução. O que é publicado em CSV sai daqui por vigia/exportar.py.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

ESQUEMA = """
-- Cópia exata de cada resposta baixada: é a prova de onde veio cada número.
CREATE TABLE IF NOT EXISTS bruto (
    url TEXT PRIMARY KEY,
    status INTEGER,
    corpo TEXT,
    baixado_em TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS orgaos (
    cnpj TEXT PRIMARY KEY,
    razao_social TEXT,
    esfera TEXT,
    poder TEXT,
    municipio_ibge TEXT,
    municipio_nome TEXT,
    alvo INTEGER DEFAULT 0          -- 1 = órgão do município analisado; 0 = vizinho/externo
);

CREATE TABLE IF NOT EXISTS contratacoes (
    id_pncp TEXT PRIMARY KEY,       -- ex.: 27150549000119-1-000214/2026
    cnpj_orgao TEXT,
    ano INTEGER,
    sequencial INTEGER,
    numero_compra TEXT,
    processo TEXT,
    modalidade_id INTEGER,
    modalidade_nome TEXT,
    modo_disputa TEXT,
    situacao TEXT,
    objeto TEXT,
    info_complementar TEXT,
    srp INTEGER,
    amparo_legal TEXT,
    valor_estimado REAL,
    valor_homologado REAL,
    data_publicacao TEXT,
    data_abertura TEXT,
    data_encerramento TEXT,
    unidade_nome TEXT,
    municipio_ibge TEXT,
    municipio_nome TEXT,
    link_origem TEXT,
    alvo INTEGER DEFAULT 0,
    itens_coletados INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS itens (
    id_pncp TEXT,
    numero_item INTEGER,
    descricao TEXT,
    material_servico TEXT,
    quantidade REAL,
    unidade TEXT,
    valor_unit_estimado REAL,
    valor_total_estimado REAL,
    situacao TEXT,
    criterio TEXT,
    tem_resultado INTEGER,
    catalogo_codigo TEXT,
    ncm TEXT,
    orcamento_sigiloso INTEGER,
    resultados_coletados INTEGER DEFAULT 0,
    PRIMARY KEY (id_pncp, numero_item)
);

CREATE TABLE IF NOT EXISTS resultados (
    id_pncp TEXT,
    numero_item INTEGER,
    sequencial INTEGER,
    ni_fornecedor TEXT,
    nome_fornecedor TEXT,
    tipo_pessoa TEXT,
    porte TEXT,
    quantidade REAL,
    valor_unit REAL,
    valor_total REAL,
    percentual_desconto REAL,
    data_resultado TEXT,
    situacao TEXT,
    PRIMARY KEY (id_pncp, numero_item, sequencial)
);

CREATE TABLE IF NOT EXISTS contratos (
    id_pncp TEXT PRIMARY KEY,       -- ex.: 27150549000119-2-000123/2025
    id_pncp_compra TEXT,
    cnpj_orgao TEXT,
    cnpj_orgao_compra TEXT,         -- se diferente do órgão: adesão/"carona" em compra de outro órgão
    ano INTEGER,
    sequencial INTEGER,
    numero TEXT,
    processo TEXT,
    tipo_contrato TEXT,
    categoria TEXT,
    objeto TEXT,
    info_complementar TEXT,
    tipo_pessoa TEXT,
    ni_fornecedor TEXT,
    nome_fornecedor TEXT,
    valor_inicial REAL,
    valor_global REAL,
    valor_acumulado REAL,
    data_assinatura TEXT,
    vigencia_inicio TEXT,
    vigencia_fim TEXT,
    data_publicacao TEXT,
    unidade_nome TEXT,
    municipio_ibge TEXT,
    termos_coletados INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS termos (
    id_contrato TEXT,
    sequencial INTEGER,
    numero TEXT,
    tipo TEXT,
    objeto TEXT,
    fundamento TEXT,
    valor_acrescido REAL,
    valor_global REAL,
    prazo_aditado_dias INTEGER,
    qualifica_acrescimo INTEGER,
    qualifica_vigencia INTEGER,
    qualifica_fornecedor INTEGER,
    data_assinatura TEXT,
    PRIMARY KEY (id_contrato, sequencial)
);

CREATE TABLE IF NOT EXISTS arquivos_compra (   -- documentos de cada contratação no PNCP (edital, suspensão...)
    id_pncp TEXT,
    sequencial INTEGER,
    data_publicacao TEXT,
    titulo TEXT,
    tipo TEXT,
    ativo INTEGER,
    PRIMARY KEY (id_pncp, sequencial)
);

CREATE TABLE IF NOT EXISTS atas (
    id_ata TEXT PRIMARY KEY,
    id_pncp_compra TEXT,
    cnpj_orgao TEXT,
    nome_orgao TEXT,
    numero TEXT,
    objeto TEXT,
    data_assinatura TEXT,
    vigencia_inicio TEXT,
    vigencia_fim TEXT,
    cancelada INTEGER
);

CREATE TABLE IF NOT EXISTS fornecedores (
    cnpj TEXT PRIMARY KEY,
    razao_social TEXT,
    nome_fantasia TEXT,
    data_abertura TEXT,
    situacao TEXT,
    data_situacao TEXT,
    capital_social REAL,
    porte TEXT,
    natureza_juridica TEXT,
    cnae TEXT,
    cnae_descricao TEXT,
    opcao_mei INTEGER,
    opcao_simples INTEGER,
    logradouro TEXT,
    numero TEXT,
    complemento TEXT,
    bairro TEXT,
    cep TEXT,
    municipio TEXT,
    uf TEXT,
    telefone TEXT,
    email TEXT,
    fonte TEXT,
    consultado_em TEXT
);

CREATE TABLE IF NOT EXISTS socios (
    cnpj TEXT,
    nome TEXT,
    qualificacao TEXT,
    documento TEXT,
    data_entrada TEXT,
    faixa_etaria TEXT
);
CREATE INDEX IF NOT EXISTS ix_socios_cnpj ON socios(cnpj);

CREATE TABLE IF NOT EXISTS sancoes (
    cnpj TEXT,
    cadastro TEXT,                  -- CEIS / CNEP
    tipo TEXT,
    orgao_sancionador TEXT,
    data_inicio TEXT,
    data_fim TEXT,
    fundamentacao TEXT,
    PRIMARY KEY (cnpj, cadastro, tipo, data_inicio)
);

CREATE TABLE IF NOT EXISTS servidores (
    nome TEXT,
    nome_normalizado TEXT,
    cargo TEXT,
    lotacao TEXT,
    fonte TEXT
);
CREATE INDEX IF NOT EXISTS ix_servidores_nome ON servidores(nome_normalizado);

CREATE TABLE IF NOT EXISTS alertas (
    id TEXT PRIMARY KEY,
    regra TEXT,
    gravidade TEXT,                 -- alta / media / baixa
    pontos INTEGER,
    titulo TEXT,
    resumo TEXT,
    pergunta TEXT,                  -- a pergunta à prefeitura (catálogo em vigia/regras.py)
    cnpj_orgao TEXT,
    nome_orgao TEXT,
    ni_fornecedor TEXT,
    nome_fornecedor TEXT,
    valor_envolvido REAL,
    valor_excesso REAL,
    data_referencia TEXT,
    id_contratacao TEXT,
    id_contrato TEXT,
    evidencias TEXT,                -- JSON
    links TEXT,                     -- JSON
    status TEXT DEFAULT 'novo',     -- novo / em_analise / descartado / confirmado / denunciado
    nota TEXT DEFAULT '',
    criado_em TEXT DEFAULT (datetime('now','localtime')),
    atualizado_em TEXT,
    ativo INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS execucoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    etapa TEXT,
    inicio TEXT,
    fim TEXT,
    detalhes TEXT
);

CREATE INDEX IF NOT EXISTS ix_contr_orgao ON contratacoes(cnpj_orgao);
CREATE INDEX IF NOT EXISTS ix_contr_mun ON contratacoes(municipio_ibge);
CREATE INDEX IF NOT EXISTS ix_contratos_forn ON contratos(ni_fornecedor);
CREATE INDEX IF NOT EXISTS ix_contratos_compra ON contratos(id_pncp_compra);
CREATE INDEX IF NOT EXISTS ix_result_forn ON resultados(ni_fornecedor);
"""


def conectar(pasta_dados: str | Path) -> sqlite3.Connection:
    pasta = Path(pasta_dados)
    pasta.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(pasta / "vigia.db")
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=OFF")
    con.executescript(ESQUEMA)
    # Migrações de bancos criados por versões anteriores
    colunas = {r[1] for r in con.execute("PRAGMA table_info(alertas)")}
    if "pergunta" not in colunas:
        con.execute("ALTER TABLE alertas ADD COLUMN pergunta TEXT")
    return con


def upsert(con: sqlite3.Connection, tabela: str, linha: dict, chaves: list[str],
           preservar: tuple[str, ...] = ()) -> None:
    """Insere ou atualiza. Colunas em `preservar` não são sobrescritas em atualizações."""
    cols = list(linha.keys())
    marcadores = ",".join("?" for _ in cols)
    atualizar = [c for c in cols if c not in chaves and c not in preservar]
    sql = f"INSERT INTO {tabela} ({','.join(cols)}) VALUES ({marcadores})"
    if atualizar:
        sql += f" ON CONFLICT({','.join(chaves)}) DO UPDATE SET " + ",".join(
            f"{c}=excluded.{c}" for c in atualizar)
    else:
        sql += f" ON CONFLICT({','.join(chaves)}) DO NOTHING"
    con.execute(sql, [linha[c] for c in cols])


def registrar_execucao(con, etapa, inicio, fim, detalhes) -> None:
    con.execute("INSERT INTO execucoes(etapa,inicio,fim,detalhes) VALUES (?,?,?,?)",
                (etapa, inicio, fim, json.dumps(detalhes, ensure_ascii=False)))
    con.commit()
