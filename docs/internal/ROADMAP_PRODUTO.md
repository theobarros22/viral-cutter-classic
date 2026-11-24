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

7. Criar painel de andamento visivel durante todo o fluxo, sem interromper a
   producao atual, mostrando:
   - etapa em execucao e etapas ja concluidas;
   - percentual por etapa e percentual geral;
   - quantidade de clipes processados e total previsto;
   - tempo decorrido e estimativa de tempo restante;
   - estados aguardando, processando, concluido, pausado e erro;
   - aviso claro de quando o usuario pode avancar para a proxima etapa.

Registro de teste da Classic 2.3.2 (11/08/2026): o processamento acontece, mas
o usuario ainda nao consegue acompanhar com clareza se cada processo terminou
ou esta proximo de terminar. Implementar somente depois dos testes atuais, sem
alterar o programa enquanto estiver em producao.

Avaliacao de qualidade da Classic 2.3.2 (11/08/2026): os cortes, a disposicao
dos cortes e o enquadramento atendem aproximadamente 90% da necessidade real.
O resultado esta proximo de 10/10, foi considerado muito bom e confirma que o
projeto esta seguindo por um caminho bastante promissor. Preservar essa
qualidade como baseline nas proximas calibracoes e na futura versao Beta.

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
4. ✅ Cache de deteccao facial e posicoes por clipe (04/07 — retry/retomada gratis).
5. Renderizar crops fixos por cena diretamente com filtros FFmpeg. [PROXIMO — ganho 3-5x no render; PySceneDetect tornou as cenas confiaveis]
6. Processar clipes independentes em paralelo, respeitando VRAM e NVENC. [ULTIMO — complexidade alta, so apos baseline]
7. ✅ faster-whisper com fallback (04/07 — ativar: pip install faster-whisper; ganho ~4x na transcricao).
8. ✅ silencedetect FFmpeg no lugar do pydub (04/07 — com fallback).
9. Eliminar encode intermediario do corte (enquadramento le direto do original com offset). [ganho ~20-30s/clipe]
10. MediaPipe em modo VIDEO com tracking entre frames (2-3x na deteccao de falante + menos jitter).

Regra: itens 5, 6, 9 e 10 so entram DEPOIS da revalidacao do enquadramento
reconstruido, um por vez, com os tempos por etapa como baseline.

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

## Prioridade 7 - modo agente (MCP server)

Inspiracao validada: Palmier Pro (palmier.io) expoe o editor via MCP local e
o Claude opera o projeto por chat. Aplicado ao Viralume: o pipeline vira um
conjunto de ferramentas MCP e o agente executa fluxos completos por linguagem
natural ("corta esse podcast em clipes de 60s com hook e legenda tiktok").

Ferramentas propostas (FastMCP em Python, servidor local, reutiliza as
funcoes existentes do pipeline sem duplicar codigo):

1. `estado_projeto()` - video carregado, segmentos, checkpoints pendentes.
2. `transcrever(video, modelo, idioma)` - etapa 1/2 atual.
3. `analisar_segmentos(nicho, duracao_min, duracao_max)` - retorna
   segmentos com titulo, score e hook.
4. `processar_clipes(indices, qualidade, perfil, aplicar_hook,
   remover_pausas)` - etapa 3 atual, com checkpoint.
5. `aplicar_legendas(clipe, template, config)` - etapa 4 atual.
6. `listar_resultados()` - clipes prontos com caminhos e metricas de tempo.

Regras:
- So comeca depois dos dois produtos estaveis e sem bugs (F2 do v2 concluida
  e Viralume validado com video real).
- O agente usa as MESMAS funcoes da interface Gradio - uma unica fonte de
  verdade, nada de logica duplicada no servidor MCP.
- Fase 2 futura: painel de chat dentro da propria UI chamando a Claude API
  com tool use sobre as mesmas ferramentas.

Meta: fluxo completo executado por uma unica instrucao em linguagem natural.

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
