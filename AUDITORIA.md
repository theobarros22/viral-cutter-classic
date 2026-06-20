# Auditoria do Viral Cutter

> Auditoria histórica. O fluxo atual inclui checkpoint, log por trabalho,
> percentual, estimativa e executável 2.2.1. Consulte `ROADMAP_PRODUTO.md`.

## Resultado

O fluxo ativo foi revisado: upload, detecção de pessoas, transcrição, seleção de
segmentos, corte, detecção de falante, enquadramento por cena e exportação.

## Correções aplicadas

- A detecção inicial agora acessa diretamente as amostras escolhidas, sem
  decodificar inutilmente todos os frames intermediários.
- O vídeo só é remuxado quando o OpenCV realmente não consegue abri-lo.
- A detecção de falante analisa somente os intervalos que virarão clipes.
- A detecção de falante agora roda diretamente em cada clipe selecionado, sem
  percorrer o podcast inteiro.
- Frames não analisados usam `grab()`, evitando cópias e decodificações caras.
- A energia do áudio é calculada em fluxo, sem carregar o áudio inteiro na RAM.
- O modelo Whisper fica em cache durante a execução.
- Transcrições repetidas são recuperadas de cache persistente.
- Apenas um modelo Whisper fica na memória por vez, evitando estouro da GPU.
- Falhas da análise online passam automaticamente para o modo offline.
- Segmentos inválidos são descartados antes do processamento pesado.
- Intervalos sobrepostos são unidos para evitar análise duplicada.
- Arquivos temporários críticos agora têm nomes únicos.
- O redimensionamento de exportação usa interpolação mais rápida.
- Os frames são enviados diretamente ao FFmpeg/NVENC, eliminando uma passagem
  completa de codificação e o vídeo intermediário do enquadramento.
- NVENC é testado de verdade antes de uso; se falhar, o programa usa CPU.
- O modelo facial passa a ser incluído no executável.
- O servidor local escuta apenas em `127.0.0.1`.
- A interface escolhe uma porta livre automaticamente.
- O teste do build confirma resposta HTTP real da interface.
- O executável bloqueia segunda instância e registra falhas em arquivo.
- O build não usa UPX, não abre console e inclui metadados de versão.
- O projeto procura FFmpeg dentro de `tools/` e o inclui no executável.
- Foram adicionados diagnóstico do ambiente, testes básicos e build verificável.

## Bloqueios da validação nesta sessão

- O Python 3.11 existe no computador, mas a sessão isolada não recebeu permissão
  para executá-lo.
- `ffmpeg.exe` e `ffprobe.exe` não estão disponíveis no `PATH` nem em `tools/`.
- Por esses dois motivos, não foi possível executar os testes Python nem gerar
  um novo executável validado nesta auditoria.

## Risco restante

A identificação de pessoas ainda agrupa por posição na tela, não por identidade
facial. Em produções multicâmera, a mesma pessoa pode aparecer em posições
diferentes. O enquadramento por cena reduz bastante o efeito, mas reconhecimento
facial por identidade seria a evolução correta para eliminar esse limite.

## Funcionalidades legadas

Os arquivos `main.py`, `reframe.py`, `smart_cut.py`, `tracking.py` e
`historico.py` existem, mas não são chamados pela interface v2 atual. Portanto,
modos antigos descritos na documentação não aparecem no fluxo ativo. A versão
atual usa `interface.py -> pipeline.py -> enquadramento.py`.
