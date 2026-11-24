"""Exporta do banco (banco/vigia.db) para CSVs versionados no git.

O banco guarda tudo, inclusive as compras das cidades vizinhas (referência de preço) e as
respostas cruas das APIs. Aqui sai só o que é de Cariacica, em CSV que abre no Excel:

    data/pncp/orgaos.csv        órgãos municipais encontrados no PNCP
    data/pncp/contratacoes.csv  licitações, dispensas e inexigibilidades
    data/pncp/itens.csv         itens de cada contratação (descrição, quantidade, valor estimado)
    data/pncp/resultados.csv    quem ganhou cada item e por quanto
    data/pncp/contratos.csv     contratos (valor inicial, global, vigência)
    data/pncp/termos.csv        termos aditivos
    data/pncp/atas.csv          atas de registro de preço
    data/receita/empresas.csv   dados cadastrais dos fornecedores (Receita Federal)

Dados pessoais (LGPD): CPF de pessoa física sai mascarado; telefone e e-mail das empresas e a
lista de sócios NÃO são exportados (ficam só no banco, usados pelas regras R14–R16).
"""
from __future__ import annotations

import pandas as pd

from . import armazem, log
from .config import DADOS
from .texto import mascarar_cpf

ALVO = "SELECT cnpj FROM orgaos WHERE alvo=1"
CONSULTAS = {
    "pncp/orgaos.csv": (f"SELECT cnpj, razao_social, esfera, poder, municipio_ibge, municipio_nome "
                        f"FROM orgaos WHERE alvo=1", ["cnpj"]),
    "pncp/contratacoes.csv": ("SELECT * FROM contratacoes WHERE alvo=1", ["data_publicacao", "id_pncp"]),
    "pncp/itens.csv": ("SELECT i.* FROM itens i JOIN contratacoes c ON c.id_pncp=i.id_pncp WHERE c.alvo=1",
                       ["id_pncp", "numero_item"]),
    "pncp/resultados.csv": ("SELECT r.* FROM resultados r JOIN contratacoes c ON c.id_pncp=r.id_pncp "
                            "WHERE c.alvo=1", ["id_pncp", "numero_item", "sequencial"]),
    "pncp/contratos.csv": (f"SELECT * FROM contratos WHERE cnpj_orgao IN ({ALVO})", ["data_publicacao", "id_pncp"]),
    "pncp/termos.csv": (f"SELECT t.* FROM termos t JOIN contratos c ON c.id_pncp=t.id_contrato "
                        f"WHERE c.cnpj_orgao IN ({ALVO})", ["id_contrato", "sequencial"]),
    "pncp/atas.csv": (f"SELECT * FROM atas WHERE cnpj_orgao IN ({ALVO})", ["data_assinatura", "id_ata"]),
    "pncp/arquivos_compras.csv": ("SELECT a.* FROM arquivos_compra a JOIN contratacoes c ON c.id_pncp=a.id_pncp "
                                  "WHERE c.alvo=1", ["id_pncp", "sequencial"]),
    "receita/empresas.csv": ("SELECT cnpj, razao_social, nome_fantasia, data_abertura, situacao, data_situacao, "
                             "capital_social, porte, natureza_juridica, cnae, cnae_descricao, opcao_mei, "
                             "opcao_simples, municipio, uf, fonte, consultado_em FROM fornecedores", ["cnpj"]),
}
# Colunas internas de controle da coleta, sem valor para quem lê
INTERNAS = {"alvo", "itens_coletados", "resultados_coletados", "termos_coletados"}
DOCUMENTOS = {"ni_fornecedor"}


def exportar_tudo(con) -> dict[str, int]:
    contagem = {}
    for arquivo, (sql, ordem) in CONSULTAS.items():
        cur = con.execute(sql)
        colunas = [d[0] for d in cur.description]
        # dtype=object mantém inteiros como inteiros e vazio como vazio (sem "nan" nem "12.0")
        df = pd.DataFrame(cur.fetchall(), columns=colunas, dtype=object)
        df = df.drop(columns=[c for c in df.columns if c in INTERNAS])
        df = df.where(pd.notna(df), "")
        for c in DOCUMENTOS & set(df.columns):
            df[c] = df[c].map(lambda d: mascarar_cpf(d) if d else "")
        if {"tipo_pessoa", "nome_fornecedor"} <= set(df.columns):    # pessoa física sem nome (24/11/2026)
            from .coletores.transparencia import EI_OMITIDA, dono_no_nome
            df.loc[df["tipo_pessoa"].astype(str).str.upper() == "PF", "nome_fornecedor"] = "PESSOA FÍSICA"
            df.loc[df["nome_fornecedor"].astype(str).map(dono_no_nome), "nome_fornecedor"] = EI_OMITIDA
        if arquivo == "receita/empresas.csv":                          # MEI com CPF/CNPJ do dono no nome
            from .coletores.transparencia import EI_OMITIDA, dono_no_nome
            for c in ("razao_social", "nome_fantasia"):
                if c in df.columns:
                    df.loc[df[c].astype(str).map(dono_no_nome), c] = EI_OMITIDA
        textos = [c for c in ("objeto", "info_complementar", "informacao_complementar") if c in df.columns]
        if textos:                                                    # nome de pessoa citado no objeto (24/11/2026)
            from .coletores.transparencia import objeto_publico, vocabulario
            comuns = vocabulario(pd.concat([df[c] for c in textos]))
            for c in textos:
                df[c] = df[c].astype(str).map(lambda t: objeto_publico(t, comuns))
        for c in df.columns:
            df[c] = df[c].astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
        armazem.gravar(df, DADOS / arquivo, ordenar=ordem)
        contagem[arquivo] = len(df)
    log.info("  exportados: " + ", ".join(f"{k} {v}" for k, v in contagem.items()))
    return contagem
