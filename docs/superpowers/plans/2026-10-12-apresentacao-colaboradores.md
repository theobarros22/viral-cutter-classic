# Apresentação de colaboradores Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Criar um pacote público de apresentação do Viral Cutter Classic com README, galeria de imagens, roteiro, storyboard, vídeo vertical e texto de divulgação.

**Architecture:** A apresentação documental ficará em `docs/presentation/`; capturas públicas ficarão em `docs/images/`; os artefatos finais do vídeo ficarão em `docs/media/`. O código do motor não será alterado. O vídeo será planejado pelo Brag usando a interface real e mídia demonstrativa autorizada.

**Tech Stack:** Markdown, GitHub README, FFmpeg, Brag/Brag Slim, Hyperframes quando disponível.

## Global Constraints

- Formato do vídeo: vertical 1080x1920.
- Duração alvo: 20–25 segundos.
- Tom: polished/cinematic.
- Usar apenas mídia própria ou autorizada.
- Não publicar chaves, caminhos pessoais, vídeos privados ou dados de clientes.
- Não inventar métricas ou resultados não verificados.

---

### Task 1: Preparar estrutura editorial

**Files:**
- Create: `docs/presentation/roteiro-video.md`
- Create: `docs/presentation/storyboard.md`
- Create: `docs/presentation/texto-divulgacao.md`

- [ ] Escrever o roteiro de 20–25 segundos com a sequência problema → upload → detecção → enquadramento → resultado → colaboração.
- [ ] Escrever o storyboard com cenas, duração, texto, transições e material real a mostrar.
- [ ] Escrever versões de divulgação para GitHub, LinkedIn, Discord e vídeo.
- [ ] Revisar o texto para remover promessas não verificadas e dados privados.
- [ ] Commitar com `docs: add collaborator presentation scripts`.

### Task 2: Preparar galeria pública

**Files:**
- Create: `docs/images/README.md`
- Create: `docs/images/` screenshots aprovadas pelo usuário
- Modify: `README.md`

- [ ] Capturar a tela principal, upload/download, detecção, enquadramento, divisão de tela, progresso e resultado.
- [ ] Anonimizar nomes de arquivo, caminhos, pessoas e dados de clientes.
- [ ] Confirmar que cada imagem mostra uma funcionalidade real.
- [ ] Atualizar o README com a galeria e legendas curtas.
- [ ] Commitar com `docs: add public product gallery`.

### Task 3: Gerar apresentação em vídeo

**Files:**
- Create: `brag-output-*/brag-plan.md`
- Create: `brag-output-*/composition-brief.md`
- Create: `brag-output-*/brag.mp4`
- Create: `brag-output-*/brag.jpg`
- Create: `brag-output-*/share-copy.txt`

- [ ] Executar Brag em formato vertical com tom polished/cinematic.
- [ ] Usar a interface real do Viral Cutter e somente material autorizado.
- [ ] Executar a verificação do Hyperframes antes da renderização.
- [ ] Renderizar o vídeo e selecionar um poster legível.
- [ ] Validar duração, resolução 1080x1920 e existência do áudio quando habilitado.
- [ ] Commitar apenas o roteiro, poster e artefatos leves; manter vídeos grandes via release/LFS conforme tamanho.

### Task 4: Integrar a apresentação ao GitHub

**Files:**
- Modify: `README.md`
- Modify: `docs/presentation/README.md`

- [ ] Adicionar link para o vídeo, poster, galeria e guia de contribuição.
- [ ] Adicionar chamada clara para Issues e Pull Requests.
- [ ] Conferir que todos os links relativos funcionam a partir da página principal.
- [ ] Executar `git diff --check` e revisar o conteúdo público.
- [ ] Commitar com `docs: publish collaborator presentation package`.
