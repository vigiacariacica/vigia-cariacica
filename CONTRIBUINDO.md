# Como contribuir

Obrigado por querer ajudar. O Vigia só tem valor se for correto, então o caminho é sempre o mesmo:
**mostrar a fonte**.

## Encontrou um número errado?

Abra uma *issue* com: o `id` do alerta (ou o arquivo e a linha), o que está errado e o link oficial
que mostra o valor certo. Se o erro for nosso, corrigimos, explicamos no
[registro de decisões](docs/DECISOES.md) e o histórico do git guarda tudo.

## Tem uma explicação para um alerta?

Ótimo, é para isso que eles existem. Abra uma *issue* com o documento (processo, termo aditivo,
publicação no Diário Oficial). Se a explicação se confirmar, o alerta é marcado como `descartado` em
`data/casos.csv`, com a nota e o link do documento.

## Quer propor uma regra nova?

Toda regra precisa de:
1. a **pergunta** que ela faz à prefeitura;
2. a **base legal** (lei e artigo);
3. **como verificar** no processo;
4. o que **pode ser legítimo**;
5. um **teste** com dados fictícios em `tests/`.

O catálogo fica em `vigia/regras.py`; o código, em `vigia/alertas/`.

## Mudando o código

```bash
pip install -r requirements.txt
python -m pytest -q
```

Todos os testes precisam passar. Limites de regra mudam em `config.toml` (R01–R20) ou no topo da
função em `vigia/alertas/portal.py` (R21–R26), sempre com o motivo registrado em `docs/DECISOES.md`.

## O que não aceitamos

- Acusação sem documento, adjetivos ou ataques pessoais.
- Política partidária ou religião misturadas aos dados.
- Exposição de dados pessoais (CPF, telefone, endereço de pessoa física).
- Dados obtidos burlando login, senha, captcha ou qualquer bloqueio.
