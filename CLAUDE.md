# Instruções para o Claude (e para quem contribui)

**Este repositório é público.** Tudo o que entra aqui fica visível para sempre no histórico do git.

Antes de qualquer commit:
- Nada de nome, e-mail, telefone ou qualquer dado de quem faz o Vigia.
- Nada de rascunho, estudo interno, dossiê ou achado ainda não publicado, nem pedido de LAI ainda não enviado.
  Esse material fica fora deste repositório.
- Nada de dado pessoal de terceiros: CPF inteiro, nome de pessoa física em alerta, dado de paciente ou de servidor.
- Nada de senha, token ou chave. Segredo só em Settings > Secrets and variables > Actions.
- Autor do commit: `vigia-bot <vigia-bot@users.noreply.github.com>` ou `Claude <noreply@anthropic.com>`.

Os testes `tests/test_lgpd.py` e `tests/test_publico.py` travam o básico; o resto é responsabilidade de quem
faz o commit.

Toda mudança de regra, limite ou do que é publicado vai para `docs/DECISOES.md`, no mesmo commit.

Regras que não mudam:
- Todo alerta é uma pergunta com link para a fonte oficial, nunca uma acusação.
- Nada de trabalho manual: se uma tarefa se repete, ela vira código e roda no GitHub Actions.
- Sem misturar política partidária ou religião com os dados.
