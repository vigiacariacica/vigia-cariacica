# Decisões do Vigia Cariacica

Por que o robô faz cada coisa do jeito que faz. Mudou uma regra, um limite ou o que é publicado? Registre aqui,
com a data e o motivo, no mesmo commit da mudança. O histórico do git guarda o resto.

## Princípios (não mudam)

- Todo alerta é uma **pergunta** com link para a fonte oficial, nunca uma acusação. Indício não é prova.
- Todo número tem fonte oficial. Sem fonte, não sai.
- Sem partido e sem religião. A mesma régua vale para qualquer gestão e para os 19 vereadores.
- Dado pessoal protegido (LGPD): CPF mascarado, nenhum nome de pessoa física nos alertas, nada de dado de
  paciente ou de servidor.
- Nada de trabalho manual que se repete: vira código e roda no GitHub Actions.

## Dados e publicação

- **07/11/2026: CSV simples versionado.** Abre no Excel, e o git mostra o que mudou em cada coleta.
- **07/11/2026: fontes.** O portal da prefeitura é a fonte principal de pagamentos; o PNCP complementa com
  licitações e itens; o Siconfi dá a visão geral e a comparação com a Grande Vitória, sempre por morador.
- **07/11/2026: banco na release, criptografado.** O SQLite (PNCP completo e respostas cruas das APIs, prova
  de origem) fica na release `banco`, criptografado com AES-256 (segredo `VIGIA_CHAVE_BANCO`). Com o repositório
  público, o workflow se recusa a subir o banco aberto. Tudo o que é publicado em `data/` pode ser conferido nas
  fontes oficiais sem o banco.
- **07/11/2026: dados pessoais.** Lista pública e CSVs com CPF mascarado, sem telefone ou e-mail de empresas,
  sem lista de sócios (sócios ficam só no banco, usados pelas regras). Pagamento a pessoa física sai sem nome e
  sem descrição. Um teste varre o repositório inteiro atrás de CPF (`tests/test_lgpd.py`).
- **07/11/2026: diárias sem nome nem CPF.** Quem recebeu vira um pseudônimo (HMAC-SHA256 com o segredo
  `VIGIA_SAL_PSEUDONIMO`), que mostra concentração sem expor ninguém. Sem o segredo, a coluna fica vazia.
- **07/11/2026: emendas espelham o portal**, inclusive autor e partido, porque é o registro oficial de quem
  mandou o dinheiro. Emendas Pix saem sem banco, agência e conta. Nenhum alerta ou relatório cita parlamentar.
- **07/11/2026: R25 (fornecedor de campanha) sem nome de político.** A entrada vem do TSE (despesas de todas as
  candidaturas de Cariacica em 2020 e 2024), só empresas, sem candidato nem partido. Saem as doações entre
  campanhas e o nome do titular de MEI. Exclusões por princípio, não por lista de casos: banco (conta
  obrigatória por lei), concessionária de energia, água ou gás e Correios (monopólio).
- **07/11/2026: indicador do orçamento só mostra o que confere** com o RREO do Tesouro no mesmo bimestre (2%).
- **07/11/2026: camada refinada** (`data/refinado/`): de onde vem cada real, em que vira, quem recebe, por
  morador e a preços constantes (IPCA). Nada estimado: tudo é soma dos registros do portal.
- **07/11/2026: sonda de fontes.** Antes de escrever um coletor novo, o workflow "Sonda de fontes" baixa
  amostras reais de dentro do Actions para `data/sonda/` (CPF mascarado; dado de pessoal só o cabeçalho).
- **12/11/2026: dado pessoal de terceiros publicado por órgão público não entra no Vigia.** A planilha da fila
  de espera da Saúde é lida só na memória; o repositório guarda apenas contagens.
- **12/11/2026: número só vai a público depois de duas contas** independentes, com a fonte aberta.

## Resultado, não publicação

- **12/11/2026: placar de resultados** (`data/resultados.csv`). O Vigia mede sucesso pelo que mudou de verdade
  em Cariacica. Caminho de cada pergunta: primeiro à prefeitura, com prazo (Lei de Acesso); sem resposta, a quem
  tem poder para cobrar (Ministério Público de Contas, TCE-ES, Câmara, conselhos). Os pedidos enviados e os
  prazos estão em `data/pedidos/pedidos.csv`.

## Site

- **12/11/2026: a conta dos vereadores.** Cada projeto em níveis (Muda algo na prática, Muda pouco, Simbólico,
  Pode ser barrado, Sem como saber), com link para o projeto e convite a corrigir. A divisão em reais é da Câmara
  inteira (gasto ÷ leis aprovadas). Por vereador, o salário do cargo fica ao lado do que saiu do gabinete, sem
  dividir um pelo outro, porque a divisão premia quem apresenta mais projetos simbólicos e pune quem é minoria.
  Ordem alfabética, sem partido, sem foto, sem ranking.
- **12/11/2026: uma página, uma tarefa.** A primeira tela do celular é título e resposta; fontes e palavras
  difíceis moram em `/fontes/`; letras servidas pelo próprio site (nada de Google). O teste do site trava isso.
- **13/11/2026: números inteiros.** Dinheiro com todos os zeros e, ao lado, como se lê ("1 bilhão e 664 milhões
  de reais"). Valor que vem arredondado da fonte continua com "cerca de".

## Abertura do repositório (24/11/2026)

- O repositório público começou com **histórico novo**. Código, regras, testes e dados são os do último dia do
  repositório de trabalho (15/11/2026). O material de trabalho interno (estudos, rascunhos, dossiês ainda não
  publicados e o estúdio de vídeo) ficou fora, num arquivo privado.
- **R25 fora da lista pública até a revisão jurídica.** O texto diz quantas candidaturas a prefeito a empresa
  atendeu; com 1 ou 2 por eleição, isso aponta para uma campanha só. A regra continua rodando e os alertas ficam
  no banco (`EM_REVISAO` em `vigia/alertas/__init__.py`). Para voltar a publicar, registre aqui a revisão.
- **Fila de espera:** os links diretos das planilhas e o registro de arquivos lidos (`data/fila/links.csv` e
  `data/fila/arquivos.csv`) não vão para o repositório público, porque as planilhas publicadas trazem dados
  pessoais de pacientes. As contagens por mês, procedimento e unidade continuam em `data/fila/`.
- **Arquivos crus e painel** não viram artefato do Actions com o repositório público (têm dados pessoais).
- **O site se atualiza sozinho** a partir deste repositório público: o workflow do repositório
  `vigiacariacica.github.io` lê este código e estes dados, gera e publica o site todo dia, sem token extra.
- **Câmara:** a data da sessão vem do título do vídeo, não do resumo automático (em 11/11/2026 o resumo devolveu
  o ano errado). A transcrição e o resumo automáticos das sessões erram e citam pessoas pelo nome: até existir uma
  etapa de conferência, o workflow roda só pelo botão e a saída fica fora do git (`data/camara/sessoes/`).
- **Mesma régua dos pagamentos nos contratos:** contrato com pessoa física (aluguel de imóvel, plantão) sai sem o
  nome; empresa individual cujo nome traz o CPF do dono também; o fiscal do contrato (servidor) sai como
  "(servidor designado; nome omitido)". No PNCP, fornecedor pessoa física sai como "PESSOA FÍSICA".
- **Nome de pessoa na descrição do empenho:** a descrição é texto livre da prefeitura e às vezes cita paciente,
  menor, pessoa falecida, servidor cedido, pensionista, conselheiro ou quem recebe por sentença. Primeiro sai o nome
  que dá para achar; se a descrição ainda cita pessoa (palavra que anuncia pessoa seguida de nome próprio, ou um CPF),
  ela sai inteira: "(descrição omitida: cita pessoa física; o texto completo está no empenho, no portal)". Hoje isso
  vale para cerca de 1% das descrições; valor, data, órgão, natureza e número do empenho ficam. A matrícula sai
  sempre. Código e testes: `descricao_publica` em `vigia/coletores/transparencia.py` e `tests/test_publico.py`.
- **Objeto de contrato** (portal e PNCP): o objeto diz o que foi contratado e não some; sai só o trecho com cara de
  nome de pessoa quando há palavra que anuncia pessoa ("Sr.", "servidor", "paciente"...), e qualquer CPF
  (`objeto_publico`).
- **Razão social de empresário individual nos cadastros:** em `data/receita/empresas.csv`, `data/refinado/` e nos
  pagamentos, a razão social fica como a Receita e a prefeitura publicam (é o nome da empresa, que a lei manda
  publicar). O que muda é a lista de alertas: ali a pergunta não leva o nome do dono.
- **Fila e Actions:** se a página da fila recusar o robô e não houver link guardado, a fila fica no último mês, com
  aviso em `docs/qualidade.md`, sem deixar a coleta vermelha; o log não mostra o link da planilha.
- **Alertas sobre empresário individual e MEI:** a razão social é o nome do dono, então na lista pública ela vira
  "empresa individual (CNPJ …)". O banco e o dossiê local mantêm o nome para a conferência.
- **Entrada da R25 (TSE) fora do git** enquanto a R25 está em revisão: o arquivo diz quantas candidaturas a prefeito
  cada empresa atendeu. A coleta semanal deixa de baixar o TSE até a revisão.
- **Sonda de fontes:** as amostras saem sem e-mail e, nas linhas de pessoa física, sem nome e sem histórico.
- **Arquivos fora:** listas recebidas por LAI (`data/entrada/`) nunca vão para o git público.
