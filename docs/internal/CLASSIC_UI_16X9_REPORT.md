# Classic UI 16:9 — relatório de implementação

## Escopo

A interface da edição Classic 2.3.2 foi reorganizada para uso desktop horizontal sem alterar o motor, as funções de backend, os callbacks ou suas listas de inputs e outputs.

## Alterações

- Hero removido e substituído por topbar compacta de 50 px com nome, versão e status local.
- Viewport preso a 100dvh, sem rolagem global.
- Aba Corte Viral organizada em três áreas:
  - workflow compacto à esquerda;
  - upload, detecção, análise, logs e resultados no workspace central;
  - configurações no inspector à direita.
- Workspace e inspector usam rolagem interna.
- Ações PROCESSAR VÍDEO e CANCELAR ficam fora da região rolável do inspector.
- Breakpoint abaixo de 1200 px reduz a coluna de workflow e preserva as três colunas.
- Aba Legendas Animadas, componentes existentes e bindings foram preservados.

## TDD e validação

O teste tests/test_classic_ui_layout.py foi criado antes da implementação.

RED inicial:

- 4 testes executados;
- 3 falhas esperadas: topbar ausente, três áreas ausentes e viewport fixo ausente;
- 1 teste de preservação de tabs/callbacks já passava.

GREEN:

- 4/4 testes estruturais aprovados.
- Suíte completa: 81 testes aprovados em 4,352 s (execução final em cache aquecido).
- Smoke funcional de corte/enquadramento com FFmpeg aprovado.
- python -m py_compile interface.py aprovado.
- Construção da árvore Gradio alcançou os componentes (somente aviso preexistente de depreciação de col_count).
- git diff --check sem erros.

## Observações

- A aba Legendas Animadas mantém rolagem interna própria porque não foi redesenhada neste escopo.
- O aviso do Gradio sobre Dataframe(col_count=...) é preexistente e não afeta esta entrega.
- A validação visual final deve ser feita no executável empacotado em 1366x768, pois pequenos detalhes do shell WebView/navegador podem variar conforme escala do Windows.
## Correção de acessibilidade das ferramentas após teste real

O teste real em 1920x1080 revelou que o shell começava abaixo do topo previsto pelo cálculo original e terminava além do viewport, tornando ferramentas inferiores inacessíveis.

TDD RED:

- novo teste de regressão executado isoladamente;
- 1 falha esperada, detectando a regra incorreta height: calc(100dvh - 116px).

GREEN:

- shell limitado por height e max-height em calc(100dvh - 196px);
- área mínima útil de 360 px preservada para telas menores;
- workspace e inspector com rolagem vertical explícita, gutter estável e overscroll contido;
- barras estilizadas e visíveis em navegadores Chromium;
- CTA permanece fora da região rolável do inspector;
- 5/5 testes estruturais aprovados;
- suíte completa: 84/84 testes aprovados em 16,935 s;
- py_compile e git diff --check aprovados.
