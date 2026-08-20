# Retomada, progresso e enquadramento seguro — desenho

## Objetivo

Permitir que o Viral Cutter Classic sobreviva a interrupções (queda de energia,
travamento ou fechamento), evite renderizações duplicadas e mostre ao usuário o
andamento real do trabalho. Ao mesmo tempo, impedir enquadramentos 9:16 que
cortem pessoas ou apresentem uma região vazia como resultado.

## Escopo

Esta melhoria preserva o pipeline local atual e seus formatos de exportação.
Ela não cria um editor manual, não altera a seleção de trechos e não substitui o
motor de corte por um novo sistema.

## Retomada durável

Cada projeto terá um checkpoint persistente na pasta de saída, identificado pela
assinatura do vídeo e pelas opções que afetam o resultado. O checkpoint salvará:

- segmentos planejados e suas configurações;
- estado de cada clipe (`pendente`, `processando`, `concluido`, `falhou` ou
  `revisar`);
- caminho do arquivo exportado, sua duração e a validação de mídia;
- etapa atual, tempos acumulados e histórico de mensagens relevantes.

Ao carregar o mesmo vídeo, a interface procurará esse checkpoint e validará os
arquivos de saída. Um clipe só será considerado concluído se o arquivo existir,
tiver mídia válida e duração compatível com o segmento planejado. Arquivos
válidos encontrados na pasta, mesmo sem estado concluído salvo, serão listados
como concluídos e não serão renderizados outra vez.

Antes de iniciar, a interface exibirá uma decisão explícita:

- **Retomar trabalho:** processa somente clipes pendentes, falhos ou inválidos;
- **Reprocessar tudo:** cria nova execução e mantém a anterior sem sobrescrever
  silenciosamente;
- **Cancelar:** não modifica nenhum arquivo.

Uma interrupção durante um clipe deixa esse clipe pendente para nova execução;
arquivos temporários não contam como resultado concluído.

## Painel de progresso

Durante a execução, um painel persistente mostrará:

- etapa atual e nome do clipe;
- percentual da etapa e percentual global;
- clipes concluídos, total e quantidade restante;
- tempo decorrido e estimativa restante após existir amostra suficiente;
- estados resumidos: concluídos, em andamento, pendentes, revisões e falhas;
- confirmação de checkpoint salvo após cada unidade concluída.

O percentual global é calculado a partir de unidades de trabalho concluídas e da
fase atual, sem fingir precisão antes de haver dados. A estimativa restante fica
como “calculando” até haver ao menos uma unidade representativa finalizada.

## Enquadramento seguro 9:16

O vídeo continua sendo exportado em 9:16. A prioridade passa a ser preservar a
pessoa, não ampliar a imagem.

Para cada cena, o enquadramento deve escolher o crop 9:16 mais amplo possível
que contenha a caixa humana detectada e uma margem de segurança. A caixa usada
combina rosto e parte visível superior do corpo quando disponíveis. A margem
impede que cabeça, rosto, ombros ou braço principal encostem na borda.

O sistema valida cada crop antes de renderizar:

- não pode haver pessoa parcialmente fora do quadro;
- não pode trocar o alvo para uma área sem pessoa;
- não pode aumentar o zoom além do necessário para preencher 9:16;
- mudanças entre cenas precisam respeitar suavização, sem saltos bruscos.

Quando não houver confiança suficiente na pessoa detectada, o fallback obrigatório
é um crop 9:16 central e mais aberto, derivado do quadro original. Ele nunca
escolhe uma região lateral vazia. Se nem esse fallback preservar pessoa válida
depois da validação, o clipe recebe estado `revisar` e não é marcado como
concluído automaticamente.

## Fluxo

1. Usuário carrega vídeo e escolhe opções.
2. Sistema encontra checkpoint e arquivos existentes.
3. Usuário escolhe retomar, reprocessar tudo ou cancelar.
4. Cada clipe atualiza o painel, grava seu estado e produz saída temporária.
5. A saída é validada; apenas então é promovida a concluída.
6. A galeria final separa resultados concluídos de itens que precisam de revisão.

## Tratamento de falhas

Checkpoint corrompido não apaga saídas existentes: a interface informa o problema
e oferece uma nova execução. Falha de mídia, de FFmpeg ou de enquadramento fica
registrada no clipe correspondente, permitindo que os demais continuem. Nenhuma
saída válida é sobrescrita sem a escolha explícita de reprocessar.

## Testes de aceitação

- Interromper após um clipe e retomar: ele é pulado, os demais continuam.
- Encontrar arquivo válido sem checkpoint concluído: ele é reaproveitado.
- Encontrar arquivo incompleto ou inválido: ele é refeito.
- Painel mostra percentuais coerentes, etapa, tempo decorrido e estimativa.
- Pessoa próxima a qualquer borda recebe crop aberto com margem.
- Detecção ausente ou instável nunca gera crop lateral vazio; usa fallback aberto
  ou marca o clipe para revisão.
- Regressão com cenas de uma e duas pessoas mantém o resultado 9:16 e não corta
  pessoas.

## Fora do escopo nesta entrega

- Editor manual quadro a quadro;
- Reenquadrar individualmente um clipe já exportado pela interface;
- Sincronização em nuvem ou fila remota.
