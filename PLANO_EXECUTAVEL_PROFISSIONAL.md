# Plano para transformar o Corte Viral em produto executável

> Documento histórico. O planejamento vigente está em `ROADMAP_PRODUTO.md`.
> O executável, os testes e a retomada de processamento já foram implementados.

## Objetivo

Entregar um programa Windows confiável, com inicialização rápida, atualização
controlada, instalação simples e diagnóstico compreensível para usuários que não
programam.

## Estado atual após a auditoria

- A interface abre antes de carregar Torch, Whisper, MediaPipe e OpenCV.
- O processamento analisa somente os clipes selecionados.
- Transcrições repetidas usam cache persistente.
- Codificação NVIDIA é usada automaticamente quando disponível.
- Há fallback para CPU e para análise offline.
- Erros não tratados são registrados em `%LOCALAPPDATA%\ViralCutter\logs`.
- Uma segunda instância é bloqueada para evitar conflito de GPU e arquivos.
- O build é `onedir`, sem UPX e sem console, priorizando abertura rápida.
- O build só é aprovado após diagnóstico, testes e teste de inicialização.

## Fase 1 — Base reproduzível

Meta: qualquer máquina de desenvolvimento deve gerar o mesmo produto.

1. Tornar `D:\CORTE VIRAL\files` a única fonte oficial.
2. Recriar um ambiente Python 3.11 limpo dentro do projeto.
3. Fixar versões exatas em `requirements-lock.txt`.
4. Incluir `ffmpeg.exe`, `ffprobe.exe` e modelo facial em `tools/`.
5. Remover ou arquivar módulos antigos que não fazem parte da interface v2.
6. Colocar o projeto sob Git, com tags de versão.

Critério de conclusão: uma instalação limpa consegue executar testes e gerar o
mesmo build sem ajustes manuais.

## Fase 2 — Executável rápido e estável

Meta: duplo clique até interface visível em menos de 8 segundos em SSD.

1. Manter formato `onedir`; não usar `onefile`.
2. Trocar Gradio + navegador por uma janela nativa com `pywebview`, mantendo o
   backend Python local.
3. Exibir tela inicial imediatamente enquanto componentes pesados carregam sob
   demanda.
4. Carregar Whisper somente ao iniciar transcrição.
5. Medir tempo de inicialização e registrar regressões automaticamente.
6. Assinar digitalmente o executável.

Critério de conclusão: interface abre rápido, sem console e sem navegador
externo; antivírus não apresenta alertas indevidos.

## Fase 3 — Pipeline de vídeo profissional

Meta: processar vídeos longos com uso previsível de GPU, CPU, RAM e disco.

1. Substituir passagem frame a frame em Python por filtros FFmpeg sempre que o
   enquadramento puder ser representado como crop fixo por cena.
2. Exportar cada cena com FFmpeg/NVENC e concatenar no final.
3. Manter OpenCV apenas para análise, não para renderização completa.
4. Adicionar cancelamento seguro e retomada de processamento.
5. Criar cache de análise facial e cenas por vídeo.
6. Medir tempo por etapa e mostrar estimativa ao usuário.

Critério de conclusão: exportação 1080p próxima ou superior à velocidade real
na RTX 3050, sem crescimento excessivo de memória.

## Fase 4 — Qualidade de enquadramento

Meta: não deixar participantes fora do quadro em material multicâmera.

1. Trocar agrupamento por posição por rastreamento de identidade facial.
2. Manter identidade entre cortes de câmera.
3. Detectar corpo/rosto quando o rosto estiver parcialmente oculto.
4. Criar zona de segurança para cabeça, mãos e legendas.
5. Adicionar preview rápido do enquadramento antes da exportação final.
6. Criar conjunto de vídeos de teste com close, plano aberto, três pessoas,
   movimento e ausência temporária de rosto.

Critério de conclusão: conjunto de testes visuais aprovado sem pessoas cortadas.

## Fase 5 — Instalação e manutenção

Meta: distribuição para usuários sem suporte técnico manual.

1. Criar instalador com Inno Setup ou WiX.
2. Instalar em `%LOCALAPPDATA%\Programs\ViralCutter`.
3. Criar atalhos, desinstalador e associação opcional de arquivos.
4. Verificar requisitos de GPU e espaço em disco no primeiro uso.
5. Adicionar atualização automática assinada.
6. Criar coleta opcional de relatórios de falha sem conteúdo dos vídeos.

Critério de conclusão: usuário instala, abre, processa e atualiza sem terminal,
BAT ou configuração manual.

## Prioridade recomendada

1. Restaurar Python 3.11 e incluir FFmpeg no projeto.
2. Sincronizar o código auditado para `D:\CORTE VIRAL\files`.
3. Executar testes e gerar uma build de release validada.
4. Migrar a interface para janela nativa.
5. Migrar a renderização frame a frame para FFmpeg por cenas.
6. Implementar identidade facial multicâmera.
