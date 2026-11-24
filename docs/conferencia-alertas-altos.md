# Conferência dos alertas de gravidade alta (checklist, item 1)

Feita em 08/11/2026 pelo Claude, a pedido do Vigia, contra a fonte oficial de cada alerta, antes de abrir o
repositório. Registro para quem quiser refazer: o método, o que bateu, o que estava errado e o que mudou.

## Como foi feita

- **Portal da prefeitura (R21, R23):** cada número do alerta foi buscado de novo na API oficial
  (`wstransparencia.cariacica.es.gov.br`), pelo navegador, e comparado com o alerta.
- **PNCP (R06, R19, R20):** a página do contrato no PNCP abriu, mas a lista de termos não carregou (o PNCP
  estava lento). A conferência usou os termos que o robô baixou da mesma API oficial (`data/pncp/termos.csv`,
  com hash no manifesto). Falta uma conferência manual por amostra (abaixo).
- **Portal da prefeitura (R22):** o portal só publica o total dos aditivos de cada contrato. Não há como
  conferir pela fonte o que é prorrogação, reajuste ou acréscimo sem os termos aditivos, então a conferência
  foi do método.

## Resultado (74 alertas altos na lista de 08/11/2026)

| Regra | Altos | Resultado |
|---|---|---|
| R21 salto de pagamentos | 8 | **8 de 8 batem ao centavo** com a API, inclusive o "máximo dos três anos anteriores". |
| R23 emergencial acima de R$ 1 mi | 5 | **5 de 5 batem** (número, fornecedor, valor e vigência). Todos com vigência de até 1 ano. |
| R06 emergência repetida com a mesma empresa | 2 | Batem com os termos do PNCP. Continuam altos. |
| R20 o mesmo serviço por emergência de novo | 4 | Valores e datas batem, mas **um grupo juntava serviços diferentes**. O alerta de "3 emergências" para limpeza incluía uma de portaria (PNCP 2025/277), porque o texto padrão ("empresa especializada para prestação de serviços... de forma contínua") deixava os objetos parecidos. **Mudou:** a comparação ignora esse texto padrão. Agora são 2 emergências de limpeza, e a de portaria fica fora. Os outros três batem: PA do Trevo (3 emergências, R$ 144,9 mi), remoção em ambulância e transporte de pacientes em tratamento. |
| R19 emergencial prorrogado | 4 | Fatos batem, mas **3 dos 4 ficaram dentro de 1 ano** somando prazo original e prorrogação (356 a 363 dias). Há entendimento de que prorrogar dentro do teto de 1 ano é aceitável. **Mudou:** alta só quando passa de 1 ano. Fica alto: Serdel, contrato 044/2024 (364 + 180 = 544 dias). Viram média: Lorenzi 078/2024, Himalaia 074/2025, Conserma 048/2025. |
| R22 aditivos no portal | 51 | **Método superestimava.** O título dizia "+426%" e a conta tratava como sobra o reajuste anual e o acréscimo legal de 25%, que se repete em cada ano prorrogado. Caso de teste: Ideal Engenharia, contrato 192/2023. O alerta dizia que sobravam 126% do original. Os termos aditivos citados no Pedido 15 mostram acréscimos de 25% + 3,73%, que somados passam do limite de 25%. Esse é o ponto real, e é bem menor do que o alerta sugeria. **Mudou:** a R22 virou triagem, nunca alta. Ela considera reajuste de até 6% ao ano e o teto com 25% de acréscimo, e o título não traz mais percentual. Resultado: 0 alto, 43 médios e 122 baixos. |

**Depois das mudanças:** os 74 altos viram 20. São 8 R21, 5 R23, 2 R06, 4 R20 e 1 R19. Todos os 20 batem
com a fonte oficial.

## Para conferir por amostra (3 links, 5 minutos)

1. **R21, Cinco Estrelas Construtora, 2026.** Abrir
   https://wstransparencia.cariacica.es.gov.br/api/despesa/fornecedor?exercicio=2026&nomeCPFCNPJ=30.686.869/0001-00
   e ver se "ValorPago" é 47941297.81.
2. **R23, contrato emergencial 184/2026 (Santa Casa de Salto Grande).** Abrir
   https://wstransparencia.cariacica.es.gov.br/api/contratos-emergenciais/csv?unidadeGestoraId=6&exercicio=2026
   e procurar o contrato 184. Deve dar R$ 54.334.515,72, de 29/10/2026 a 28/10/2027.
3. **R19, Serdel, contrato 044/2024.** Abrir https://pncp.gov.br/app/contratos/27150549000119/2024/13 e, na
   aba Termos, ver se há prorrogação de 180 dias. A vigência original vai de 18/03/2024 a 17/03/2025.

## O que isto não cobre

- Os alertas médios e baixos não foram conferidos um a um.
- A R22 só fica certa com os termos aditivos de cada contrato. Os PDFs dos aditivos do portal são o passo
  3b da lista de próximos passos do projeto. Até lá, nenhum post deve usar número da R22 sem o termo aditivo em mãos.
- Conferir que o número bate não diz se houve irregularidade. Cada alerta continua sendo uma pergunta.
