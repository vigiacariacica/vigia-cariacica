# Ferramentas ainda manuais (a automatizar)

Vieram do Vigia do computador do projeto em 07/11/2026, junto com o resto do sistema, para que todo o
código do projeto more num lugar só. Ao contrário do resto do repositório, **ainda não rodam no
GitHub Actions**. A integração está na lista de próximos passos do projeto.

| Pasta | O que faz | Fontes | Por que ainda é manual |
|---|---|---|---|
| `financas/` | Baixa e filtra para as 7 cidades da Grande Vitória os dados abertos do TCE-ES (empenhos com credor, contratações e aditivos, receitas, despesas, pessoal, previdência, julgamento de contas) e do TSE (contas de campanha 2020 e 2024); `importar.py` monta um SQLite para análise | `dados.es.gov.br` (CKAN do TCE-ES), `apidatalake.tesouro.gov.br`, `cdn.tse.jus.br` | ~12 GB de arquivos; inclui folha de pagamento **com nome de servidor**, que exige decidir o que pode ser publicado (LGPD) antes de automatizar |
| `raiox/` | Indicadores do Censo 2022 por bairro (renda, esgoto, água, lixo, alfabetização) e Ideb por escola | IBGE (SIDRA e agregados por setor), INEP | Dado que muda uma vez por ano/censo; os resultados já estão em `data/raiox/` |

Uso (no computador, com Python 3.12):

```bash
python ferramentas/financas/baixar_financas.py          # várias horas na primeira vez
python ferramentas/financas/importar.py                 # monta ferramentas/financas/dados/financas.db
python ferramentas/raiox/baixar_dados.py
python ferramentas/raiox/processar_bairros.py ferramentas/raiox/dados_prontos data/raiox
```

Os dados baixados ficam em `ferramentas/*/dados*` e **não** vão para o git (`.gitignore`).

Já automatizados (saíram daqui): a receita e a despesa mensal do TCE-ES (`vigia/coletores/tcees.py`) e as
empresas contratadas pelas campanhas de Cariacica, entrada da regra R25 (`vigia/coletores/tse.py` →
`data/tse/fornecedores_campanha.csv`, hoje(fora do repositório público enquanto a R25 está em revisão jurídica; ver docs/DECISOES.md)). O antigo `financas/gerar_fornecedores_campanha.py` foi substituído
pelo coletor do TSE, que produz o mesmo arquivo.
