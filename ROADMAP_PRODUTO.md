# Roadmap do Viral Cutter

## Visao do produto

Transformar videos longos em pecas verticais prontas para publicacao. O corte
automatico prepara a materia-prima; o diferencial principal do produto e o
editor de legendas virais, tipografia animada e motion graphics.

O editor de legendas e motions trabalha exclusivamente em formato vertical
9:16, com presets para TikTok, Instagram Reels, YouTube Shorts e Facebook
Reels. Formatos quadrados e horizontais ficam fora deste editor.

## Estado real - versao 2.2.1

### Ativo no fluxo principal

- Executavel Windows `onedir`, sem terminal e com inicializacao validada.
- Upload de video e deteccao de participantes.
- MediaPipe com fallback OpenCV.
- Detecção inicial limitada aos primeiros 5 minutos, usando 30 amostras.
- Transcricao Whisper com GPU e cache persistente.
- Analise semantica online e modo offline.
- Exportacao 720p, 1080p e 4K.
- Enquadramento por cenas com NVENC e fallback CPU.
- Checkpoint recuperavel por video, qualidade e pessoas priorizadas.
- Log geral em `%LOCALAPPDATA%\ViralCutter\logs`.
- Log individual dentro da pasta de cada trabalho.
- Percentual e estimativa restante apos cada clipe concluido.
- Testes automatizados e teste real de inicializacao do executavel.

### Existe no repositorio, mas nao esta integrado ao fluxo principal

- `main.py`: pipeline antigo.
- `reframe.py`, `tracking.py` e `smart_cut.py`: modos antigos de enquadramento.
- `historico.py`: historico antigo sem tela ativa.
- Sistema Remotion de legendas descrito em documento separado, mas sem os
  arquivos necessarios neste repositorio.

Esses itens nao devem ser anunciados como funcionalidades atuais ate serem
integrados e testados no pipeline `interface.py -> pipeline.py -> enquadramento.py`.

## Prioridade 1 - confiabilidade operacional

1. Adicionar cancelamento cooperativo entre clipes.
2. Exibir painel de trabalhos interrompidos e botao "Continuar".
3. Validar video final com FFprobe: imagem, audio e duracao.
4. Manter e revisar `requirements-lock.txt` a cada release.
5. Criar testes de integracao com videos curtos de referencia.
6. Remover definitivamente o pipeline legado apos comparacao funcional.

Meta: nenhuma falha exige recomecar o processamento completo.

## Prioridade 2 - qualidade de enquadramento

1. Trocar agrupamento por posicao por identidade visual persistente.
2. Detectar rosto, tronco e zona de seguranca para cabeca e maos.
3. Manter identidade entre cortes de camera.
4. Adicionar limite de velocidade e antecipacao de troca de falante.
5. Gerar preview de baixa resolucao antes da exportacao final.
6. Criar testes visuais para uma, duas e tres pessoas, plano aberto e B-roll.

Meta: nenhum participante importante fica fora do quadro no conjunto de testes.

## Prioridade 3 - velocidade

1. Perfis Rapido, Equilibrado e Maxima Qualidade implementados.
2. Medicao separada de corte, falante e enquadramento implementada.
3. Whisper Base disponivel como padrao rapido.
4. Criar cache de deteccao facial e posicoes por clipe.
5. Renderizar crops fixos por cena diretamente com filtros FFmpeg.
6. Processar clipes independentes em paralelo, respeitando VRAM e NVENC.

Meta: exportacao 1080p proxima ou superior ao tempo real na RTX 3050.

## Prioridade 4 - legendas virais e motions

1. Reconstruir o modulo Remotion dentro deste repositorio.
2. Transcrever com timestamps por palavra.
3. Criar preview em tempo real no editor.
4. Entregar templates Hook Viral, TikTok Pop, Narrativo, Impacto, Typewriter,
   Dado/Numero, Politico e Minimalista.
5. Permitir varios templates no mesmo video.
6. Criar faixas separadas para palavras, motion, overlays e beats.
7. Aplicar templates a varios cortes em lote.
8. Salvar presets do usuario e do cliente.
9. Aplicar zonas seguras específicas para os controles de cada rede social.
10. Exportar sempre em 1080x1920, com opção de qualidade de codificação.

Meta: o usuario cria legendas e motions profissionais sem precisar finalizar em
outro editor.

## Prioridade 5 - experiencia de edicao

1. Tela de revisao dos cortes antes de processar.
2. Player com marcadores de entrada e saida.
3. Edicao de titulo, inicio, fim e selecao de clipes.
4. Preview do crop vertical e da troca de cameras.
5. Exportacao de projeto para Filmora/Premiere por XML/EDL quando viavel.

Meta: o usuario controla o resultado sem voltar ao video original.

## Prioridade 6 - produto distribuivel

1. Migrar a interface para janela nativa com `pywebview`.
2. Criar instalador Inno Setup.
3. Assinar executavel e instalador.
4. Criar atualizacao automatica assinada.
5. Adicionar diagnostico exportavel sem incluir conteudo dos videos.
6. Testar em maquina Windows limpa.

Meta: instalar, abrir, atualizar e desinstalar sem BAT, servidor manual ou Python.

## Proxima entrega recomendada - versao 2.3

- Painel de trabalhos interrompidos.
- Cancelamento seguro entre clipes.
- Botao para abrir log e pasta de saida.
- Validacao FFprobe completa de cada export.
- Medicao por etapa.
- Primeiro conjunto de videos de regressao.

Essa entrega melhora confiabilidade e suporte antes de adicionar novos efeitos.

## Matriz de funcionalidades

Consulte `FUNCIONALIDADES_ADOTAVEIS.md` para a comparação entre funcionalidades
da referência e o que pode ser adotado de forma responsável no Viral Cutter.
