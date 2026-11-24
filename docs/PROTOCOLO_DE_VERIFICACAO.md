# Protocolo de verificação

Siga estes passos **antes** de falar publicamente sobre qualquer caso ou de fazer uma denúncia.
O objetivo é simples: só levar adiante o que for verdade e estiver documentado.

Em público, o Vigia **pergunta**: "por que este contrato cresceu 400%?", com o número, o `id` do
alerta e o link oficial. Afirmar irregularidade só depois de documento ou decisão de órgão oficial.

## 1. Conferir o dado na fonte

- Abra o link oficial do alerta (coluna `link` de `data/alertas.csv`: PNCP ou portal da prefeitura)
  e confira valor, data, fornecedor e objeto **no dia da publicação**.
- Procure o mesmo ato no **Diário Oficial do Município**.
- Se o número do PNCP estiver diferente do Diário Oficial, é provável erro de lançamento:
  registre e descarte o alerta (`python -m vigia marcar ID descartado "erro de lançamento"`, ou edite
  `data/casos.csv` no GitHub).

### 1.1 Situação, datas e prazos: só com documento (lição de 13/11/2026)

O campo "Situação" do Portal da Transparência não é atualizado: o Chamamento 1/2023 aparecia "Em Andamento"
dois anos depois de anulado, e o 2/2025, depois de revogado. Uma frase pública errada ("seleção parada há
608 dias", "suspensa desde 07/07") saiu desse campo. Por isso:

- Nenhuma frase pública diz que uma licitação está "parada", "suspensa", "em andamento" ou "há N dias" sem
  o **documento** que prova a situação: o aviso, a decisão ou a ata nos anexos do portal ou no PNCP
  (`data/pncp/arquivos_compras.csv`). Anote o documento em `data/transparencia/situacao_corrigida.csv`.
- "Desde quando" é a data do documento, não a data de publicação do edital.
- Quando duas fontes oficiais dão datas diferentes (ex.: fim do contrato 99/2025: 27/10/2026 no portal,
  28/10/2026 no PNCP), a peça usa a data que não depende da diferença ou pergunta qual é a certa.
- Resposta do e-SIC marcada "Resposta Completa" não prova nada: confira item por item e registre o
  resultado do Vigia, publicado junto com a resposta.
- Relatório de fiscalização publicado (ex.: COMAF) vale como fonte: cite a página e a competência. O que
  a comissão aponta é fato do relatório; se foi resolvido depois, é pergunta.
- Antes de cada post, releia as frases já publicadas sobre o mesmo caso e corrija em público o que mudou.
- Obra: a página da obra (`ObraServico.Detalhes.aspx`) traz medições e fotos; os termos de recebimento, aditivos e
  ordem de serviço ficam na página do contrato (`Contrato.Detalhes.aspx`). Confira as duas antes de afirmar que um
  documento "não está no portal", e abra o arquivo: em 13/11/2026 um "termo de recebimento provisório" publicado era de
  outro contrato.

## 2. Entender o caso

- Leia a seção "Pode ser legítimo se" do alerta e procure, no processo, cada uma dessas explicações.
- Compare com casos parecidos: o município sempre faz assim, ou foi só desta vez?
- Para sobrepreço: confirme que o item é o mesmo (especificação, marca, embalagem, quantidade, frete).

## 3. Pedir os documentos (LAI)

- Gere o dossiê (`python -m vigia dossie ID`): ele traz as evidências, os links oficiais e o pedido
  de LAI pronto. Protocole no e-SIC da prefeitura e guarde o número do protocolo.
  Modelos de pedidos gerais em [PEDIDOS_LAI.md](PEDIDOS_LAI.md).
- Prazo legal: 20 dias, prorrogáveis por mais 10 com justificativa (Lei 12.527/2011, art. 11).
- Sem resposta: recurso à autoridade superior (art. 15) e, depois, à Controladoria.
- Recurso cobra só o que o pedido original pediu, item por item, com o endereço do que já está público. Pedir mais
  (outros documentos, "se vai corrigir", "quando vai fazer") dá motivo para negar o recurso inteiro: isso vira
  pedido novo ou pergunta à imprensa. A Lei de Acesso garante informação que existe, não promessa.
- Você **não precisa** dizer por que quer a informação (art. 10, §3º).

## 4. Decidir

| Situação | O que fazer |
|---|---|
| Há explicação documentada e razoável | Marcar `descartado` com a explicação |
| Faltam documentos | Manter `em_analise` e insistir no pedido |
| Os documentos confirmam o problema | Marcar `confirmado` e preparar a denúncia |

## 5. Denunciar do jeito certo

- Leve aos órgãos de controle **primeiro** (TCE-ES, MPES, Controladoria, Câmara; CGU/MPF se houver
  dinheiro federal). Eles têm poder de investigar; você tem os indícios.
- Escreva fatos, não adjetivos: datas, valores, links, documentos.
- Use "há indícios de", "solicita-se apuração". Nunca escreva que alguém "roubou" ou "é corrupto".
- Não exponha nomes de servidores ou sócios em redes sociais. Acusar sem prova pode gerar
  processo por calúnia ou difamação (Código Penal, arts. 138 e 139) e destrói a credibilidade do projeto.
- Guarde cópia de tudo o que enviou e o protocolo de cada órgão.

## 6. Depois

- Acompanhe o andamento pelo número do processo no TCE-ES ou no MPES.
- Atualize o alerta: `python -m vigia marcar ID denunciado "TCE-ES proc. nº ..."`.
- Quando houver decisão pública (multa, suspensão, condenação), aí sim é seguro divulgar —
  citando a decisão oficial.
