# Aparecer primeiro quando buscarem "Vigia Cariacica"

Estudo e aplicação de 14/11/2026.

## O problema

Hoje, quem busca "vigia cariacica" vê vagas de emprego de vigia (BNE, Trabalha ES) e notícias com a palavra
"vigia". O site do Vigia ainda não aparece: é novo e os buscadores não sabem que ele existe. "Vigia" é palavra
comum (vigilante), então o buscador precisa aprender que "Vigia Cariacica" é um nome próprio.

## O que decide quem aparece primeiro numa busca de nome

1. **O buscador conhecer a página.** Sem estar no índice, não aparece. O Google recomenda o Search Console e
   pedir a indexação das páginas principais. O Bing (que alimenta DuckDuckGo, Yahoo e a busca de assistentes
   como o ChatGPT) aceita aviso automático pelo IndexNow.
2. **O nome estar claro no site.** O Google escolhe o nome do site pelo dado estruturado `WebSite` (o mais
   importante), pelo `og:site_name`, pelo título e pelos títulos da página inicial.
3. **Outros lugares apontarem para o site com o mesmo nome.** Instagram, TikTok, X, GitHub e, o mais forte,
   imprensa. É assim que o buscador entende que "Vigia Cariacica" é uma coisa só, com endereço próprio.
4. **As pessoas clicarem.** Quem busca o nome e clica no site ensina o buscador. Por isso os vídeos e cartazes
   devem dizer "busque Vigia Cariacica" ou mostrar o endereço.
5. **Domínio com o nome** (`vigiacariacica.com.br`) ajuda, mas não é obrigatório. O endereço do GitHub funciona.

## O que já foi aplicado no site

- Página inicial com o título "Vigia Cariacica: as contas da prefeitura de Cariacica, explicadas", descrição com
  o nome e a frase "O Vigia Cariacica olha as contas..." logo abaixo do título.
- Dado estruturado `WebSite` (nome "Vigia Cariacica", outros nomes "Vigia", "VigiaCariacica", "Vigia de
  Cariacica") e `Organization` (logo, cidade, redes) na página inicial.
- Títulos das páginas com o que as pessoas buscam: "Itaquari, Cariacica: esgoto, posto de saúde e obras",
  "Fila da saúde: <posto>, Cariacica", "<vereador>: projetos de lei na Câmara de Cariacica". Cada página nova
  que aparece na busca traz o nome do Vigia junto.
- `robots` liberando tudo (e a página de erro fora do índice), mapa do site (`sitemap.xml`), endereço canônico,
  ícone de 48 px e `favicon.ico` (o Google mostra o ícone ao lado do resultado), prévia própria por página.
- IndexNow: chave em `data/site/buscadores.json` (arquivo público na raiz do site) e o workflow
  "Avisar buscadores" (`ferramentas/avisar_buscadores.py`), que a cada 6 horas avisa as páginas que mudaram.
- Lugar pronto para os códigos de verificação do Google e do Bing (`data/site/buscadores.json`): é só colar.

## Cadastro nos buscadores

Google Search Console e Bing Webmaster Tools, com a conta do Vigia. Os códigos de verificação entram em `data/site/buscadores.json`.

## Quanto tempo leva

O Google diz que pode levar algumas semanas para notar um site novo. Buscando "vigiacariacica" (junto), o site
deve aparecer primeiro logo depois de indexado. Buscando "vigia cariacica" (separado), a disputa é com vagas
de emprego: o site sobe à medida que ganha links (redes, imprensa) e cliques. Não dá para garantir posição;
dá para fazer tudo o que o buscador considera.
