# Relatório final da rodada de engenharia

> Relatório histórico da versão 2.1. Consulte `ROADMAP_PRODUTO.md` para o estado
> atual e as próximas entregas.

## Meta

Deixar o Corte Viral mais rápido, funcional e preparado para evoluir para um
executável Windows sério.

## Correção v2.1.1

- Detector combinado MediaPipe + fallback OpenCV Haar.
- Erros do detector deixam de ser escondidos e passam a ser registrados.
- Varredura sequencial automática quando vídeos grandes falham ao buscar frames.
- Uma aparição válida já pode criar a pessoa no preview.

## Melhorias de velocidade implementadas

- A interface não importa Torch, Whisper, MediaPipe ou OpenCV na inicialização.
- Módulos pesados são carregados somente quando a funcionalidade é acionada.
- A detecção inicial acessa diretamente algumas amostras, sem percorrer todos
  os frames intermediários.
- A detecção de falante roda em cada clipe selecionado, não no podcast inteiro.
- A análise de energia do áudio funciona em fluxo e não carrega tudo na RAM.
- Transcrições repetidas são recuperadas de cache persistente.
- Um único modelo Whisper permanece carregado por vez.
- Detecção de cenas pula frames durante a análise.
- Exportação envia frames diretamente para FFmpeg, eliminando o vídeo
  intermediário e uma segunda codificação completa.
- A RTX é usada automaticamente por NVENC quando um teste real confirma suporte.

## Melhorias de estabilidade implementadas

- Fallback de NVENC para CPU.
- Fallback da análise online para modo offline.
- Arquivos temporários críticos usam nomes únicos.
- Saídas parciais são removidas após falhas.
- Vídeos sem áudio são aceitos.
- Segmentos inválidos são descartados antes do processamento.
- Verificação de arquivo de entrada e espaço livre.
- Segunda instância do programa é bloqueada.
- Logs de falha ficam em `%LOCALAPPDATA%\ViralCutter\logs`.
- Dados temporários e cache ficam na pasta local do usuário.
- Porta ocupada não impede inicialização.

## Executável preparado

- Build `onedir`, priorizando inicialização rápida.
- Janela de console removida.
- UPX removido para melhorar abertura, estabilidade e reputação com antivírus.
- Metadados de versão 2.1.0.
- Modelo facial e ferramentas FFmpeg preparados para inclusão.
- Diagnóstico, testes unitários e teste HTTP de inicialização antes da aprovação.

## Validações concluídas nesta sessão

- Scripts PowerShell passaram pelo parser.
- Arquivos Python passaram por checagens estruturais de delimitadores, tabs,
  caracteres corrompidos e manifesto de sincronização.
- A inicialização ativa contém apenas imports leves, além do Gradio.
- O enquadramento ativo não usa mais `VideoWriter` nem vídeo intermediário.

## Validações pendentes

- Executar testes Python reais.
- Processar vídeos da matriz visual.
- Gerar e testar o novo executável.
- Sincronizar a versão auditada para `D:\CORTE VIRAL\files`.

Essas etapas ficaram bloqueadas nesta sessão isolada por falta de execução do
Python 3.11, ausência do FFmpeg e falta de permissão de escrita no D:.
