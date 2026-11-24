# Vigia Cariacica

**Para onde vai o dinheiro da Prefeitura de Cariacica (ES)?**

O Vigia Cariacica é um projeto de controle social. Todo dia, sozinho, ele baixa os dados oficiais
de pagamentos, contratos, licitações e orçamento do município, confere esses dados e transforma
padrões estranhos em **perguntas públicas**, sempre com o link da fonte oficial.

Acreditamos em Cariacica e no Brasil. A máquina pública funciona melhor quando qualquer cidadão
consegue ver, conferir e perguntar.

## O que tem aqui

| | |
|---|---|
| ❓ [**Alertas**](data/alertas.csv) | Perguntas que merecem resposta, uma por linha, com a fonte oficial |
| 📊 [Relatório](docs/relatorio.md) | Para onde vai o dinheiro, quem mais recebe, comparação com a Grande Vitória |
| 🗺️ [Mapa do dinheiro](docs/MAPA_DO_DINHEIRO.md) | Quem gasta dinheiro público em Cariacica (município, consórcios, Estado, União), por onde entra, em que vira, e o que o Vigia já vê |
| 📖 [Dicionário de dados](docs/DICIONARIO.md) | O que é cada arquivo e cada coluna de `data/` |
| 📏 [As 26 regras](docs/REGRAS.md) | O que cada alerta procura, base legal e o que pode ser legítimo |
| 🔎 [Metodologia](docs/METODOLOGIA.md) | De onde vem cada número e como conferir à mão |
| ✅ [Qualidade dos dados](docs/qualidade.md) | Checagens de cada coleta e conferência com o Tesouro Nacional |
| 🧭 [Protocolo de verificação](docs/PROTOCOLO_DE_VERIFICACAO.md) | O que fazer antes de falar publicamente de um caso |
| 📨 [Pedidos de LAI](docs/PEDIDOS_LAI.md) | Modelos prontos de pedido de acesso à informação |
| 🗂️ [Dados](data/) | Tudo em CSV, abre no Excel |

## Princípios

1. **Um alerta é uma pergunta, não uma acusação.** Há explicações legítimas para quase todo padrão;
   o alerta só diz "isto merece explicação".
2. **Tudo tem fonte.** Cada número aponta para o portal oficial onde ele está publicado.
3. **Tudo é auditável.** O código, as regras e os dados estão aqui. Qualquer pessoa roda o mesmo
   processo e chega ao mesmo resultado.
4. **Plural e técnico.** Sem partido e sem religião. O mesmo critério vale para qualquer gestão.
5. **Dados pessoais protegidos.** CPF mascarado; nenhum nome de pessoa física exposto nos alertas.

## Fontes (todas públicas e oficiais)

- Portal da Transparência da Prefeitura de Cariacica: pagamentos, contratos, emergenciais, punidos,
  emendas parlamentares, obras, diárias (sem nome de servidor) e receitas
- Tesouro Nacional (Siconfi): contas anuais e bimestrais das 7 cidades da Grande Vitória
- PNCP (Portal Nacional de Contratações Públicas): compras item a item, preços, contratos e aditivos
- Receita Federal (via BrasilAPI) e CGU (CEIS/CNEP): dados e punições das empresas
- Tribunal de Contas do ES (TCE-ES): receita e despesa mês a mês, para acompanhar a arrecadação
- Transferegov (governo federal): emendas Pix para Cariacica, com plano de ação, metas e relatórios
- TSE: empresas contratadas pelas campanhas eleitorais de Cariacica em 2020 e 2024 (sem nome de candidato)
- IBGE (SIDRA): IPCA, para comparar anos a preços constantes

## Como reproduzir

```bash
pip install -r requirements.txt
python -m pytest -q          # testes com dados fictícios
python -m vigia diario       # coleta, checa e gera alertas e relatório
```

Tudo o que o Vigia publica está em `data/` e confere com as fontes oficiais. O banco completo (com sócios das
empresas e respostas cruas das APIs) fica criptografado na release `banco`, porque tem dados pessoais. Detalhes em
[docs/METODOLOGIA.md](docs/METODOLOGIA.md#13-como-reproduzir-tudo-no-seu-computador).

## Achou um erro? Quer ajudar?

Abra uma *issue* aqui no GitHub. Erro nosso é corrigido em público e fica registrado no histórico.
Veja [CONTRIBUINDO.md](CONTRIBUINDO.md).

## Licença

Código sob licença MIT ([LICENSE](LICENSE)). Os dados são públicos (Lei 12.527/2011 e LC 131/2009)
e podem ser reutilizados livremente, citando a fonte original.
