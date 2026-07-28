# Enquadramento humano seguro

## Objetivo

Garantir que todo corte vertical mantenha pessoas reais como alvo, sem centro vazio e sem cortar agressivamente cabeça, rosto, ombros, braços, mãos, tronco ou microfone.

## Modos

### SOLO

Usado quando há uma pessoa ou quando a mesma pessoa domina a fala por pelo menos 3 segundos contínuos. O crop é centralizado pelo conjunto rosto-tronco, preserva microfone e mãos quando visíveis e usa zoom conservador.

### GRUPO

Usado quando duas pessoas próximas cabem com margem segura no mesmo crop vertical. O centro é o ponto médio do conjunto humano, e o zoom abre o suficiente para nenhuma pessoa ser cortada.

### SPLIT

Usado quando duas pessoas conversam alternadamente. A saída é dividida horizontalmente em dois painéis empilhados. Cada painel recebe crop independente e centraliza uma pessoa com margem para cabeça, tronco e microfone.

## Máquina de estados de fala

- Conversa alternada entre duas pessoas mantém SPLIT.
- Após 3 segundos contínuos da mesma pessoa, muda para SOLO nessa pessoa.
- Quando a outra pessoa retoma, volta imediatamente para SPLIT.
- Silêncio ou falha momentânea mantém o último enquadramento humano válido.
- A troca de alvo não pode cair em x=0.5 sem uma pessoa validada nessa posição.

## Margens e zoom

- Centralizar pelo eixo do tronco, usando o rosto como âncora superior.
- Priorizar quadro mais aberto em vez de cortar pessoa ou microfone.
- O crop deve conter a caixa humana estimada com folga lateral e vertical.
- Em SPLIT, calcular o crop de cada painel separadamente.
- Quando duas pessoas estiverem no mesmo lado, usar GRUPO e enquadrar o conjunto.

## Fallbacks

1. Último alvo humano válido da cena atual.
2. Pessoa priorizada mais próxima.
3. Pessoa global detectada mais próxima.
4. Se nenhuma pessoa foi validada, não renderizar silenciosamente com centro vazio; registrar erro claro para revisão.

## Fluxo

`rostos.py` fornece pessoas e posições de fala. `enquadramento.py` transforma essas posições numa máquina de estados SOLO/GRUPO/SPLIT e calcula crops seguros. `pipeline.py` passa as pessoas validadas ao enquadrador e trata falha sem alvo humano.

## Testes de aceitação

- Uma pessoa permanece centralizada e inteira com microfone visível quando possível.
- Duas pessoas próximas cabem juntas sem cortes agressivos.
- Duas pessoas alternando fala aparecem em SPLIT, cada uma centralizada em seu painel.
- Três segundos contínuos de fala mudam SPLIT para SOLO.
- Retomada da outra pessoa volta para SPLIT.
- Silêncio preserva o último alvo humano.
- Nenhum caminho produz centro vazio quando pessoas foram detectadas.
- Falha total de detecção é explícita, nunca um crop central silencioso.