# Fila de espera de consultas e exames especializados

Somas feitas pelo Vigia a partir das planilhas mensais publicadas pela Secretaria Municipal de Saúde
(https://cariacica.es.gov.br/pagina/ler/951/semus-fila-de-espera-para-agendamento-de-consultas-e-exames).

- **Nenhum dado pessoal.** As planilhas oficiais trazem nome e data de nascimento dos pacientes. O Vigia não guarda
  o arquivo, não copia nome nem data de nascimento e só grava contagens. Em 12/11/2026 o Vigia pediu à prefeitura,
  pela Ouvidoria da Saúde, que publique a fila sem esses dados.
- **Espera** = dias entre a "Data da solicitação" e o último dia do mês da planilha (há quanto tempo espera quem
  ainda está na fila). A prefeitura informa no topo da planilha outra medida (tempo médio de espera); as duas não
  são a mesma coisa.
- Maio a julho vêm com datas no formato mês/dia/ano; agosto em dia/mês/ano; setembro como data do Excel. O cálculo
  detecta o formato de cada arquivo.
- **Outubro de 2026: 1.243 datas depois do fim do mês.** Na planilha de outubro, 1.243 dos 42.679 pedidos têm data
  de solicitação em novembro ou dezembro de 2026 (707 e 536), o que não pode ser: tudo indica dia e mês trocados
  (todas viram datas válidas até 31/10 se trocar). O coletor não corrige: essas linhas entram com espera negativa.
  Efeito, conferido em 24/11/2026: a mediana da cidade sai 238 dias (242 se trocar dia e mês); os 16.218 pedidos com
  mais de 1 ano não mudam. As duas contas dão "quase 8 meses".
- **Pedido não é pessoa.** A mesma pessoa pode esperar mais de um procedimento; o resumo traz as duas contas. As
  pessoas são contadas por uma impressão digital de nome + nascimento feita na memória com uma chave aleatória
  de cada execução; nada disso é gravado.
- **Idade pela data de nascimento.** A coluna "Idade do paciente" da planilha não confere com a data de nascimento
  na maior parte das linhas. O Vigia calcula a idade no último dia do mês e guarda só quanto a coluna oficial
  confere (idade_planilha_confere_pct). Até 12/11/2026 a série usava a coluna oficial; o robô refez os cinco meses.
- **Crescimento comparável.** A lista de procedimentos muda (121 em maio, 147 em setembro de 2026). Para dizer
  quanto a fila cresceu, compare só os procedimentos presentes em todos os meses (a seção do relatório faz isso).
- Pedidos com prioridade "MUITO ALTA" e as consultas de neurologia aparecem em colunas próprias no resumo mensal.
- O agendamento das especialidades é feito pela Secretaria de Estado da Saúde (nota da própria planilha).
