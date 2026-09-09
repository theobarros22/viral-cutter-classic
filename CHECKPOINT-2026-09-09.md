# Checkpoint — 09/09/2026

## Objetivo atual

Detectar participantes distintos em vídeos de podcast sem duplicar a mesma
pessoa quando ela aparece em dois ângulos.

## Alterações realizadas

- A galeria de pessoas permanece montada na interface; o Gradio não a remonta
  após a detecção.
- O YuNet passou a preservar os cinco pontos faciais durante a limpeza das
  detecções.
- O SFace passou a alinhar o rosto pelos pontos do YuNet antes de gerar o
  embedding facial.
- A fusão de identidades aceita duas visualizações simultâneas da mesma pessoa
  somente com similaridade facial alta (>= 0,48).
- A amostragem foi alterada para reservar parte dos 30 pontos nos primeiros
  cinco minutos e distribuir o restante pela duração total do vídeo.
- O limiar normal de identidade foi calibrado para 0,42.

## Evidências e acertos

- No quadro 1000 do vídeo `F:\Meu_Vídeo\RFNSL_BENY.mov`, o detector encontrou
  duas faces com confiança 0,893 e 0,884; a similaridade SFace entre elas foi
  0,363, confirmando que são pessoas distintas.
- O alinhamento real do YuNet foi validado: ambos os rostos chegam ao SFace
  como imagens 112x112.
- Testes adicionados/aprovados cobrem:
  - preservação de pontos YuNet;
  - alinhamento YuNet/SFace;
  - fusão de imagens simultâneas da mesma pessoa;
  - não aceitação de rosto passageiro;
  - cobertura de vídeo longo com orçamento de 30 amostras.

## Erros encontrados e tratados

- O Gradio tentou usar `D:\ViralCutter\gradio_temp` quando a unidade não
  estava pronta; esse é um bug de inicialização ainda pendente de consolidação
  no `runtime.py` e no `iniciar.bat`.
- O limpador de detecções removia os pontos faciais do YuNet, impedindo o
  alinhamento; corrigido.
- A regra antiga considerava automaticamente duas faces no mesmo frame como
  pessoas diferentes; corrigida com limiar de similaridade mais rigoroso.
- A regra que preservava uma única detecção YuNet de alta confiança foi
  revertida: visualmente ela ainda selecionava o mesmo homem, em outro ângulo.

## Estado da validação visual

Os dois previews da última execução ainda mostravam o mesmo homem. A próxima
validação obrigatória é rodar a nova estratégia de amostragem inicial, conferir
os previews e só então reiniciar a janela do aplicativo.

## Arquivos principais alterados

- `rostos.py`
- `interface.py`
- `app_desktop.py`
- `ViralCutter.vbs`
- `tests/test_core.py`
- `tests/test_interface_detection.py`
- `tests/test_startup.py`

