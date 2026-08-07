# Detecção adaptativa de participantes

Data: 2026-08-07

## Objetivo

Substituir a amostragem fixa dos primeiros cinco minutos por uma busca progressiva que atravesse o vídeo até confirmar os participantes reais. O caso principal é podcast com introdução longa, mudanças de câmera e duas ou mais pessoas no mesmo lado da composição.

## Comportamento

- Analisar o vídeo em rodadas distribuídas progressivamente pela duração total.
- Cada rodada coleta amostras em uma nova faixa temporal, sem repetir quadros já examinados.
- Agrupar por identidade facial; posição esquerda, centro ou direita é somente metadado de cobertura, nunca identidade.
- Confirmar uma pessoa apenas quando o mesmo rosto aparece em quadros distintos e em mais de uma rodada, salvo vídeo curto sem duração suficiente para duas rodadas.
- Continuar enquanto novas identidades forem descobertas ou enquanto só um lado humano tiver cobertura suficiente.
- Encerrar após três rodadas consecutivas sem identidade nova, desde que todas as identidades confirmadas tenham repetição suficiente e os lados humanos encontrados estejam estáveis.
- Usar a duração inteira como limite final de busca, com amostragem esparsa para evitar decodificar o vídeo completo.
- Nunca promover objetos, corpos sem rosto, televisão ou cenário para a galeria de pessoas.
- Escolher o preview entre recortes faciais nítidos e validados; se não houver preview facial válido, a identidade não aparece na seleção.

## Estratégia de amostragem

1. Dividir a duração do vídeo em faixas progressivas.
2. Começar com uma rodada curta no início, preservando rapidez em vídeos normais.
3. Se a lista ainda não estiver estável, avançar para faixas posteriores, inclusive depois de introduções longas.
4. Coletar um pequeno lote de quadros bem distribuídos em cada faixa.
5. Reagrupar todas as detecções acumuladas após cada rodada e medir identidades novas, repetição e cobertura lateral.
6. Parar pela estabilidade ou ao alcançar o fim do vídeo.

## Casos importantes

- Introdução sem pessoas: a busca continua automaticamente.
- Uma pessoa de cada lado: encerra quando ambas estiverem repetidamente confirmadas e estáveis.
- Quatro pessoas, duas de cada lado: retorna quatro identidades, não dois ou três grupos posicionais.
- Cortes de câmera movem a mesma pessoa: mantém uma única identidade.
- SFace indisponível ou sem embeddings: o fallback por posição não poderá inventar múltiplas pessoas; continuará conservador e exibirá somente candidatos faciais persistentes.
- Vídeo curto: reduz o número de rodadas sem exigir duração inexistente.
- Nenhum rosto real: retorna lista vazia com mensagem clara, sem previews de cenário.

## Progresso e interface

O log mostrará a faixa analisada, o número de amostras acumuladas, quantas identidades estão confirmadas e por que a busca continua ou encerra. A interface existente e o botão `DETECTAR PESSOAS` permanecem iguais.

## Testes

- Introdução longa seguida por rostos: avança além da janela inicial.
- Nova identidade em rodada posterior: continua e inclui a pessoa.
- Três rodadas estáveis: encerra sem varrer desnecessariamente o restante.
- Duas identidades no mesmo lado: mantém ambas separadas quando o reconhecimento facial está disponível.
- Falsos positivos sem rosto válido: não aparecem na galeria.
- Vídeo curto e vídeo ilegível preservam o comportamento esperado.
- Teste real no podcast enviado pelo usuário valida que os participantes aparecem como rostos nos previews.

## Fora de escopo

- Reconhecimento nominal das pessoas.
- Alteração do enquadramento ou da seleção de falante.
- Controle manual da quantidade esperada de participantes.
