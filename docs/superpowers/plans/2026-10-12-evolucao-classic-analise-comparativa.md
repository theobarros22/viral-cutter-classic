# Viral Cutter Classic — Plano de evolução e implementação

> Para execução por agentes: usar a skill executing-plans, entregar uma tarefa por vez e registrar evidências. Este documento autoriza planejamento; implementação e publicação devem seguir a autorização do mantenedor.

**Objetivo:** aumentar a confiabilidade da retomada, a qualidade editorial dos cortes e o controle do usuário, preservando a produção do Classic.

**Arquitetura:** evoluir o pipeline Python existente, os checkpoints JSON, os callbacks da interface Gradio e os renderizadores FFmpeg/NVENC e pipe. Reutilizar o que já existe; separar persistência, seleção editorial e renderização por contratos pequenos, sem introduzir um segundo motor ou serviço obrigatório.

**Tecnologias:** Python, Gradio, Whisper/faster-whisper, OpenCV, FFmpeg/FFprobe, JSON, pytest e empacotamento existente.

## 1. Base e limites da análise

- Inspeção estática em 12/10/2026 da pasta `H:\CORTE VIRAL\ViralCutter-Classic-Atualizado`, commit `3d7ea0dde5ebc67ae24b9cb65abd6bb99bd22aa5`, branch `integracao/melhorias-amigo`.
- A branch local está um commit à frente do upstream de integração. Há `brag-output/` não rastreado. Preservar esses arquivos; não incluir mídia ou alterações alheias nas entregas.
- `AGENTS.md` ainda cita D: e uma pasta antiga. O escopo atual informado pelo usuário é H:. Corrigir documentação de instalação após confirmar o launcher ativo, sem migrar dados por inferência.
- Foram lidos os módulos de análise, persistência, trechos do pipeline/interface/renderização, inventário de testes e fontes externas abaixo. Não foi feita auditoria exaustiva de todos os módulos.
- Nenhuma suíte, exportação ou benchmark foi executado nesta análise. Achados de código são distinguíveis de falhas reproduzidas. Números de testes e performance históricos não comprovam o estado atual.
- Referência externa lida via `main`, que é mutável. Antes de reutilizar código, registrar SHA e licença do snapshot escolhido.

## 2. O que já existe e o que precisa evoluir

| Área | Evidência no Classic | Ação |
|---|---|---|
| Transcrição local | `analise.py`: faster-whisper, fallback Whisper, timestamps de palavras, chunks no fallback | Persistir resultados intermediários, progresso e parâmetros de cache |
| Seleção editorial | `segmentar_por_assunto`, `_segmentar_com_ia`, `_segmentar_offline`, `ajustar_score_por_nicho` | Análise longa em blocos, validação, deduplicação e justificativas |
| Retomada | `checkpoint.py`: JSON, log, varredura de pasta, estados de análise | Fortalecer identidade dos artefatos, gravação e validação |
| Pessoas | `rostos.py`: rodadas de amostragem, reconhecimento e filtro de candidatos | Medir cobertura real e testar introduções longas/trocas de câmera |
| Enquadramento | `_calcular_crop_seguro`, `_crop_validado`, grafo FFmpeg, fallback pipe, status revisar | Validar resultado visual e permitir ajustes específicos |
| Progresso | `atualizar_progresso`, `progresso_evento_callback`, Gradio Progress | Percentuais medidos dentro das etapas e estados visíveis |
| Legendas/efeitos | `legendas.py`, `etapa4_efeitos_virais`, `_fatiar_palavras_transcricao` | Cache por dependências, retomada e revisão da sincronização |
| Interoperabilidade | `exportar_premiere.py`, relatórios/resultados do pipeline | Manifesto portátil sem segredos e mapa temporal consistente |
| Distribuição | `viral_cutter.spec`, `gerar_release.ps1`, `validar_build.ps1`, CI | Validar instalação limpa e atualização preservando projetos |

### Achados prioritários da leitura local

1. `criar_id_trabalho` recebe `segmentos`, mas não os inclui no hash. `etapa3_processar` pode restaurar segmentos de um checkpoint anterior. Reproduzir alteração de seleção/tempos sob a mesma configuração e verificar reaproveitamento incorreto.
2. `salvar_checkpoint` termina com escrita direta no arquivo final após repetidos PermissionError. Uma interrupção nesse ponto pode destruir a última cópia válida.
3. `resultado_valido` retorna verdadeiro por existência/tamanho quando não encontra FFprobe no PATH; a aplicação já tem resolução centralizada em `ffmpeg_utils.py`. Um arquivo grande não prova exportação válida.
4. `etapa2_analisar` transcreve sempre e persiste apenas depois da segmentação/refinamento. Uma falha da análise pode desperdiçar a transcrição concluída.
5. O estado salvo contém pessoas/transcrição/segmentos, mas não registra uma chave completa de idioma/modelo/provedor/prompt/nicho. A validade por etapa precisa ficar explícita.
6. `restaurar_estado_analise` preserva valores existentes no cache global. Testar a troca A→B antes de considerar qualquer valor válido: a propriedade do cache deve acompanhar o vídeo.
7. `atualizar_progresso` usa contagem de clipes para percentual global e 0/100 para etapa. Isso não fornece avanço contínuo de transcrição ou renderização.
8. A transcrição usa nomes temporários fixos, como `_whisper_audio_temp.wav`. Há risco de colisão entre trabalhos/processos. O bloqueio existente é em memória e cobre exportação por pasta, não todo o ciclo entre processos.
9. `_transcrever_em_chunks` pode continuar após falha de extração e retornar transcrição parcial como concluída. A cobertura temporal precisa ser registrada.
10. `_segmentar_com_ia` envia a transcrição inteira numa chamada e usa modelo fixo. Vídeos extensos precisam de limite de contexto, resultados parciais persistidos e política de erro explícita.
11. O log da detecção ainda menciona enquadramento central sem pessoas. Verificar se esse caminho resulta em `revisar`, conforme a regra de segurança, em vez de anunciar sucesso visual.

## 3. Aproveitamento da referência externa

Fontes examinadas:

- [Seleção editorial](https://github.com/Anil-matcha/AI-Youtube-Shorts-Generator/blob/main/shorts_generator/highlights.py)
- [Renderização local](https://github.com/Anil-matcha/AI-Youtube-Shorts-Generator/blob/main/shorts_generator/local/clipper.py)
- [Pipeline](https://github.com/Anil-matcha/AI-Youtube-Shorts-Generator/blob/main/shorts_generator/pipeline.py)
- [Transcrição/cache](https://github.com/Anil-matcha/AI-Youtube-Shorts-Generator/blob/main/shorts_generator/local/transcriber.py)
- [Licença](https://github.com/Anil-matcha/AI-Youtube-Shorts-Generator/blob/main/LICENSE)

Seleção: aproveitar critérios editoriais, justificativa por candidato e supressão de sobreposição. Há risco estático no chunking externo: os segmentos mantêm tempos absolutos, enquanto a chamada usa duração local e depois adiciona offset. Não portar essa lógica sem corrigir o contrato temporal. A deduplicação também depende da duração do candidato; definir nossa métrica explicitamente.

Renderização: o caminho local externo escolhe o maior rosto com Haar, suaviza a posição e usa centro quando falta detecção. Não identifica necessariamente o falante, nem contempla nossos layouts seguros de podcast. Manter o motor do Classic e comparar somente com fixtures equivalentes.

Transcrição: o cache externo por nome-base e data em SRT é simples, mas não preserva timestamps de palavras e pode colidir entre vídeos homônimos. Manter JSON completo versionado e exportar SRT como derivado.

Pipeline: o modo local externo ainda chama um provedor LLM remoto. Não equivale a zero custo ou funcionamento inteiramente offline. Preservar o modo offline real do Classic.

Reutilização literal exige preservar avisos MIT e registrar origem dos trechos. A licença atual do Classic é personalizada não comercial; não anunciar o projeto como open source OSI. Adicionar `THIRD_PARTY_NOTICES.md` apenas quando houver incorporação, com os componentes efetivamente usados.

## 4. Contratos e regras globais

- Fonte, transcrição e tempos editoriais usam segundos absolutos no vídeo original. Tempos locais de exportação são derivados por mapa temporal explícito, inclusive hook e remoção de silêncio.
- Preservar campos atuais `inicio`, `fim`, `titulo`, `score_viral` (1–10) e `resumo`. Novos campos são opcionais para manter compatibilidade.
- Score é prioridade editorial, não probabilidade de viralizar. Registrar origem `offline` ou provedor e versão do método.
- Manter arquivos originais. Publicar exportações finais apenas após validação; escrever primeiro em arquivo parcial exclusivo.
- 9:16 ocupa o quadro; sem fundo desfocado. Priorizar pessoa centralizada, cabeça inteira e margem, com o mínimo de aproximação. Usar dois painéis seguros quando necessário; impossibilidade gera `revisar`.
- Não prometer que dois vídeos 16:9 completos preenchem, sem corte, duas metades de um 9:16: cada metade tem proporção 9:8. O layout exige recorte ou outro arranjo, sempre validado quanto à pessoa.
- Nenhuma chamada paga no modo offline. Transcrições só saem da máquina quando o usuário escolhe análise remota.
- Sem alteração automática da versão em uso durante processamento. Implementar e testar em branch isolada; distribuir release candidata antes da estável.
- Toda tarefa: teste reproduz o caso → mudança mínima → testes direcionados → revisão do diff → commit específico. Não agrupar mudanças de motor e seleção editorial na mesma entrega.

## 5. Sequência de implementação

### T0 — Baseline e fixtures (P0)

Arquivos: `docs/validation/classic-baseline.md` (novo), `tests/fixtures/README.md` (novo), `.github/workflows/tests.yml`, `AGENTS.md`.

- [ ] Confirmar runtime, launcher, dependências e revisão realmente executada pelo app. Documentar caminhos atuais e corrigir instruções obsoletas.
- [ ] Rodar a suíte existente no ambiente do projeto: `rtk proxy .\venv311\Scripts\python.exe -m pytest tests -q`. Se esse Python não existir, identificar o ambiente configurado em vez de instalar pacotes globalmente.
- [ ] Montar corpus local autorizado: 2 e 4 participantes; lado a lado; câmeras opostas; introdução longa; rosto no limite; oclusão; WEBM; vídeo VFR; ausência de áudio; arquivo corrompido; podcast acima de uma hora.
- [ ] Registrar para cada caso: hash da fonte, versão, parâmetros, trechos esperados, tempo por etapa, RAM/VRAM quando mensurável, duração/codec/dimensões de saída e avaliação humana.

Aceite: baseline reproduzível com aprovado/falhou/não executado separados. Mídia pessoal permanece fora do Git; fixtures públicas/sintéticas pequenas são permitidas.

### T1 — Identidade e retomada segura (P0, depende T0)

Modificar: `checkpoint.py`, `pipeline.py`, `ffmpeg_utils.py`. Testar: `tests/test_estado_analise.py`, `tests/test_checkpoint_integridade.py` (novo).

Interfaces propostas em `checkpoint.py`: `assinatura_etapa(video_id: str, etapa: str, parametros: dict, dependencias: dict) -> str`; `criar_id_clipe(video_id: str, segmento: dict, render_config: dict) -> str`. Serialização canônica e rejeição de números não finitos.

- [ ] Separar identidade estável do vídeo das assinaturas de transcrição, análise e renderização. Conteúdo relevante inclui tempos, hook, pessoas, layout, qualidade, efeitos e versões de algoritmo; título não deve sozinho invalidar pixels.
- [ ] Dar ID estável por clipe. Reordenar a lista não troca sua identidade. Mudanças de tempos/configuração invalidam apenas os derivados afetados.
- [ ] Substituir fallback de escrita direta por temporário único, flush/fsync, replace com tentativas limitadas e última cópia válida recuperável. Falha deve aparecer na UI como retomada indisponível, sem anunciar salvamento bem-sucedido.
- [ ] Usar o localizador central de FFprobe e validar duração esperada, resolução e áudio conforme a fonte. Sem FFprobe, classificar como não verificado.
- [ ] Migração versionada: importar checkpoint antigo como candidato, validar artefatos e preservar `revisar`. Nome/índice/log isolados não provam correspondência à seleção atual.
- [ ] Testar troca de vídeo A→B, troca de seleção, renomeação, duas instâncias, JSON truncado, PermissionError e MP4 parcial.

Regressão mínima inicial para o defeito atual:

```python
def test_mudar_intervalo_muda_identidade(tmp_path):
    from checkpoint import criar_id_trabalho
    video = tmp_path / 'fonte.mp4'
    video.write_bytes(b'fixture-identidade')
    a = criar_id_trabalho(str(video), [{'inicio': 0, 'fim': 30}], '1080p', [])
    b = criar_id_trabalho(str(video), [{'inicio': 60, 'fim': 90}], '1080p', [])
    assert a != b
```

Aceite: nenhuma mídia de outro intervalo é aceita; exportações válidas inalteradas não são refeitas; reinício não perde a última geração válida do estado. Retomada ocorre na menor unidade concluída e validada, não no byte exato de uma codificação interrompida.

### T2 — Cache por etapa e transcrição recuperável (P0, depende T1)

Modificar: `analise.py`, `pipeline.py`, `checkpoint.py`; ampliar `tests/test_estado_analise.py`; criar `tests/test_transcricao_retomavel.py`.

- [ ] Salvar transcrição imediatamente após concluída, antes da análise editorial. `etapa2_analisar` deve consultar a assinatura válida antes de chamar Whisper.
- [ ] Persistir por bloco os resultados e intervalos cobertos; guardar palavras, idioma, modelo, backend e versão. Falha num bloco deixa etapa incompleta e permite retomá-lo.
- [ ] Dar a cada trabalho diretório temporário exclusivo. Liberar leitores/processos antes de remover temporários.
- [ ] Uniformizar o texto final a partir dos segmentos consolidados; remover duplicações de borda sem perder palavras. Não tratar falha de extração como trecho silencioso.
- [ ] Cache de pessoas vinculado a vídeo/modelo/parâmetros; testar que estado de A não é mesclado em B. Cache visual hoje em memória só será persistido se seu custo justificar e sua serialização for validada.

Aceite: matar o processo após a transcrição e retomar não chama Whisper novamente; mudar apenas nicho reanalisa texto; mudar idioma/modelo invalida transcrição e derivados; falha em bloco fica visível.

### T3 — Progresso contínuo e cancelamento (P0, depende T1–T2)

Modificar: `checkpoint.py:atualizar_progresso`, callbacks de `pipeline.py`, `analise.py`, `enquadramento.py`, `interface.py`; criar `tests/test_progresso.py`.

Contrato de evento: `job_id`, `etapa`, `clipe_id`, `estado`, `unidades_feitas`, `unidades_total`, `percentual_etapa`, `percentual_global`, `decorrido_segundos`, `estimativa_segundos`. Percentual/estimativa podem ser nulos quando desconhecidos.

- [ ] Medir transcrição por cobertura de áudio, detecção por amostras realizadas, exportação por tempo reportado pelo FFmpeg (`-progress`) ou frames no pipe.
- [ ] Agregar progresso com pesos estimados a partir da baseline, mantendo separadas contagem de prontos e fração computacional. Não inventar progresso temporal para API em espera.
- [ ] ETA baseada nas últimas amostras comparáveis; indicar estimativa e recalcular após alteração da fila. 100% só depois de todas as etapas solicitadas e validação.
- [ ] Mostrar pendente/processando/pronto/revisar/erro/cancelado e erro acionável; atualizar sem bloquear UI. Limitar escrita persistente por intervalo, garantindo salvamento nas transições.
- [ ] Cancelar com liberação de processos/arquivos, preservar parciais úteis e impedir duas instâncias de escrever no mesmo trabalho.

Aceite: durante exportação longa há atualização pelo menos a cada 2 s; desconhecido aparece como calculando; clipe em revisão não vira pronto; cancelamento não corrompe exportações anteriores.

### T4 — Seleção editorial para vídeos longos (P1, depende T2)

Modificar: `analise.py:_segmentar_com_ia`, `segmentar_por_assunto`, `pipeline.py:etapa2_analisar`. Criar `selecao_editorial.py`, `tests/test_selecao_editorial.py`.

Interfaces propostas: `dividir_transcricao(transcricao: dict, janela_s: float = 1200, sobreposicao_s: float = 60) -> list[dict]`; `validar_candidatos(candidatos: list, duracao_video: float) -> tuple[list, list]`.

- [ ] Dividir análise por janela e também limitar quantidade de texto/tokens por provedor. Incluir frases que cruzam bordas; tempos permanecem absolutos, sem aplicar offset ao retorno.
- [ ] Distribuir amostras de classificação ao longo da transcrição; nicho escolhido manualmente prevalece.
- [ ] Validar tipo, números finitos, limites do vídeo, duração, hook dentro do clipe e resposta incompleta. Rejeições entram no relatório, não viram cortes silenciosamente alterados.
- [ ] Persistir cada janela por assinatura do texto/modelo/prompt. Repetir somente janelas falhas, com timeout, limite de tentativas e distinção de autenticação, custo e erro transitório.
- [ ] Tornar modelo configurável e preservar o modo offline. Novos provedores são opcionais e entram somente após esses contratos; não adicionar MuAPI ao caminho padrão.

Teste obrigatório: vídeo de 3.600 s com frase em 2.450–2.470 s deve retornar exatamente esse intervalo, inclusive em janelas sobrepostas. Testar NaN, infinito, JSON truncado, resultado vazio e frase na fronteira.

Aceite: nenhum offset duplicado; cobertura de toda a transcrição elegível; resposta inválida não renderiza; falha de uma janela não perde as demais.

### T5 — Deduplicação, ranking e explicação (P1, depende T4)

Modificar: `selecao_editorial.py`, `analise.py`, `interface.py`; ampliar `tests/test_selecao_editorial.py`.

Interfaces propostas: `deduplicar_candidatos(candidatos: list, limiar: float = 0.5) -> tuple[list, list]`; `ranquear_candidatos(candidatos: list, limite: int | None = None) -> list`.

- [ ] Normalizar candidatos sem mudar a escala pública 1–10. Acrescentar `motivo_selecao`, `tipo_gancho`, `origem_analise`, `versao_analise` e componentes do score quando disponíveis.
- [ ] Definir sobreposição como interseção/duração do menor trecho. Acima de 0,5, reter o de maior score, desempate determinístico por início e ID. Guardar descartado e motivo para restauração manual.
- [ ] Executar deduplicação após refinamento de palavras e limitar Top-N depois de validar/deduplicar. Não impor embeddings ou provedor adicional.
- [ ] Listar score, duração, justificativa, seleção e prévia. Permitir ordenar cronologicamente, excluir, restaurar e editar limites antes de renderizar.

Exemplo de teste do contrato proposto:

```python
def test_dedup_prefere_maior_score():
    from selecao_editorial import deduplicar_candidatos
    itens = [{'inicio': 10, 'fim': 70, 'score_viral': 7},
             {'inicio': 15, 'fim': 65, 'score_viral': 9}]
    mantidos, descartados = deduplicar_candidatos(itens)
    assert len(mantidos) == len(descartados) == 1
    assert mantidos[0]['score_viral'] == 9
```

Aceite: lista estável, sem duplicatas involuntárias; justificativas coerentes com o trecho; offline sem chamadas remotas. Avaliar Top-5 em pelo menos 10 fontes autorizadas comparando preferência editorial humana à baseline, sem alegar viralidade comprovada.

### T6 — Segurança visual e detecção (P0 para falhas, após T0; integrar com T1)

Modificar: `rostos.py`, `enquadramento.py`, `pipeline.py`; ampliar `tests/test_participantes_distintos.py`, `tests/test_enquadramento_seguro.py`, `tests/test_fast_export.py`.

- [ ] Medir cobertura das rodadas de detecção: câmeras observadas, identidades recorrentes, confiança e tempo amostrado. Encerrar com orçamento e estabilidade explícitos; nunca presumir número fixo de participantes.
- [ ] Testar todos os modos SOLO, GRUPO, SPLIT e FALLBACK_SPLIT usando a fonte única `_calcular_filtros_shot` em ambos os motores.
- [ ] Invalidar alvo antigo na mudança de câmera. Falta de rosto exige nova busca ou estado revisar, não segurança baseada apenas na detecção anterior.
- [ ] Validar limites do crop, cabeça e margem em cada plano; registrar instantes problemáticos. Amostrar frames renderizados em transições e intervalos de risco, pois FFprobe não valida pessoas.
- [ ] Quando impossível enquadrar com segurança, usar painéis válidos ou revisão explícita. Informar quando houver repetição do mesmo participante no fallback para permitir decisão editorial.

Aceite: zero cabeça cortada nos trechos anotados do corpus de regressão; todo caso não resolvido é marcado revisar. Isso é uma meta de aceite do corpus, não garantia universal. Medir diferenças visuais entre grafo e pipe e ausência de saltos indevidos.

### T7 — Revisão e reexportação seletiva (P1, depende T1 e T6)

Modificar: `interface.py`, `pipeline.py`, `checkpoint.py`; criar `tests/test_revisao_clipe.py`.

- [ ] Selecionar um clipe por ID e intervalo problemático; controlar modo, pessoa, centro e escala dentro dos limites seguros.
- [ ] Persistir `ajustes_manuais` por intervalo absoluto, versão e motivo. Gerar prévia reduzida antes de exportação final.
- [ ] Invalidar só renderização e efeitos dependentes do clipe alterado; preservar transcrição e demais clipes.
- [ ] Salvar nova revisão em arquivo distinto e permitir voltar à anterior. Aprovação manual registra autor/data e não apaga alertas históricos.

Aceite: editar o clipe 8 não altera hashes/tempos de modificação dos outros arquivos; revisão persiste após reinício; ajuste inválido é rejeitado com motivo.

### T8 — Manifesto, efeitos e exportação (P1, depende T1–T5 e T7)

Modificar: `pipeline.py:etapa4_efeitos_virais`, `_fatiar_palavras_transcricao`, `legendas.py`, `exportar_premiere.py`; criar `relatorio_projeto.py`, `tests/test_relatorio_projeto.py`.

Interface proposta: `exportar_manifesto(checkpoint: dict, destino: str, anonimizar: bool = True) -> str`.

- [ ] Manifesto JSON versionado com fonte, configuração, candidatos aceitos/rejeitados, resultados, validações, custos conhecidos, tempos e erros. Remover chaves API e caminhos pessoais da cópia compartilhável.
- [ ] Salvar mapas de tempo de hook/pausas para legendas, revisão e Premiere. Marcar onde o texto não tem timestamp de palavra; não inventar alinhamento.
- [ ] Retomar legendas/efeitos por assinatura separada. Mudança de estilo não provoca nova transcrição.
- [ ] Validar XML em projeto real do Premiere e sincronização de legendas com cortes/hook. JSON/SRT são derivados exportáveis; estado local completo continua sendo a fonte de retomada.

Aceite: reabertura preserva o projeto; relatório não contém credenciais; exportação solicitada só consta pronta após efeitos; legendas mantêm alinhamento nos pontos anotados com tolerância definida na baseline.

### T9 — Release e contribuição (P2, depende entregas anteriores selecionadas)

Modificar: `viral_cutter.spec`, `gerar_release.ps1`, `validar_build.ps1`, `.github/workflows/tests.yml`, `README.md`; criar notas da release em `docs/releases/`.

- [ ] Rodar suíte completa e casos reais em CPU e NVENC quando disponível. Registrar tempos/memória; investigar regressão superior a 10% em tarefa equivalente antes de promover.
- [ ] Testar pacote em Windows sem Python/FFmpeg no PATH, com caminho acentuado/espaços, porta ocupada, disco cheio e sem internet quando modelos já estão disponíveis.
- [ ] Conferir modelos, DLLs, FFprobe, yt-dlp e licenças de dependências; documentar downloads iniciais necessários.
- [ ] Testar atualização e retorno à versão anterior preservando fontes, exports, checkpoints e configurações. Manter instalador anterior e hash SHA256 do novo.
- [ ] Atualizar documentação: fonte disponível não comercial, capacidades testadas, limitações e exemplos anônimos. Converter tarefas em issues somente quando solicitado para publicação.

Aceite: release candidata usada em um trabalho real completo, incluindo interrupção e retomada; nenhuma falha crítica pendente; validação visual humana; rollback verificado.

## 6. Marcos de entrega e decisão

1. **Confiabilidade:** T0–T3 e regressões de T6. Resultado: não perder trabalho, não reutilizar saída errada, progresso compreensível.
2. **Qualidade editorial:** T4–T5. Resultado: vídeos longos analisados com cobertura, candidatos explicados e deduplicados.
3. **Controle e acabamento:** concluir T6–T8. Resultado: corrigir um recorte específico e reaproveitar o restante.
4. **Distribuição:** T9. Resultado: pacote candidato validado e documentação atualizada.

Cada marco pode ser lançado separadamente após aceite. Não bloquear correções P0 esperando todos os recursos. Esforço e datas só serão estimados após T0, pois ambiente e corpus ainda precisam de validação.

## 7. Verificação e handoff

Comandos-base na raiz, usando o runtime confirmado em T0:

```powershell
rtk proxy .\venv311\Scripts\python.exe -m pytest tests/test_estado_analise.py tests/test_enquadramento_seguro.py tests/test_fast_export.py -q
rtk proxy .\venv311\Scripts\python.exe -m pytest tests -q
rtk git diff --check
```

Para cada tarefa, acrescentar seu novo arquivo de teste ao comando direcionado. Testes de transcrição/LLM devem usar doubles em CI; testes reais de mídia exigem FFmpeg e fixtures, com motivo explícito para skip. CI verde não substitui teste de interface, renderização, retomada e instalação.

Registrar por entrega: commit, configuração, casos executados, pass/fail/skip, arquivos de evidência, limitações e instruções de rollback. O próximo implementador começa por T0 e pelo teste de identidade de T1, sem assumir que os achados já foram corrigidos.

Checklist desta análise: código local inspecionado; referência externa inspecionada; funcionalidades existentes separadas das propostas; contratos temporais definidos; dependências entre tarefas definidas; critérios de aceite documentados. Implementação, benchmarks e publicação deste plano: não realizados nesta etapa.
