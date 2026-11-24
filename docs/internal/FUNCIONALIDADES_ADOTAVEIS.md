# Funcionalidades adotáveis no Viral Cutter

Referência analisada: Real Oficial. A intenção é adotar conceitos úteis, sem
copiar marca, textos, identidade visual ou implementação.

## Já temos o núcleo

| Funcionalidade | Estado no Viral Cutter |
|---|---|
| Upload de MP4/MOV | Ativo |
| IA encontra momentos relevantes | Ativo com Whisper + análise semântica |
| Score e títulos dos cortes | Ativo no resultado da análise |
| Detecção de pessoas | Ativo com MediaPipe e OpenCV |
| Enquadramento automático | Ativo |
| Exportação 720p, 1080p e 4K | Ativo |
| GPU/NVENC | Ativo com fallback CPU |
| Processamento local e privado | Ativo |
| Retomada após falha | Ativo |
| Exportação em lote | O pipeline já processa todos os segmentos selecionados |

Grande parte da diferença atual está na experiência de uso, não no motor.

## Foco principal do produto

O diferencial central sera o editor de legendas virais e motion graphics:

- Legenda palavra por palavra.
- Templates animados.
- Tipografia hierarquica.
- Contadores e dados.
- Typewriter.
- Shake e spring.
- Pills, badges, logos e overlays.
- Sincronizacao com beats.
- Varios estilos no mesmo corte.
- Aplicacao em massa.
- Presets por cliente.

O corte automatico e o enquadramento continuam essenciais, mas passam a
alimentar esse editor.

### Escopo de formato

- Somente vertical 9:16.
- TikTok: preset de zona segura para botões laterais e descrição inferior.
- Instagram Reels: proteção para interface inferior e bordas.
- YouTube Shorts: proteção para título, canal e botões laterais.
- Facebook Reels: proteção para descrição e ações.
- Resolução padrão: 1080x1920.
- O conteúdo fica centralizado dentro da menor zona segura comum.

## Adotar primeiro

### 1. Galeria de cortes antes da exportação

- Cards com thumbnail, título, duração e score.
- Selecionar ou rejeitar cortes.
- Editar título, início e fim.
- Preview rápido em baixa resolução.

Impacto: alto. Complexidade: média.

### 2. Edição em massa

- Aplicar layout, qualidade, pessoa prioritária e formato a todos.
- Selecionar grupos de cortes.
- Fila visível com percentual, estimativa e status.
- Reprocessar apenas os cortes alterados.

Impacto: alto. Complexidade: baixa a média, pois o pipeline já trabalha em lote.

### 3. Painel de trabalhos

- Projetos recentes.
- Trabalhos interrompidos.
- Botões Continuar, Abrir pasta, Abrir log e Excluir checkpoint.
- Histórico de exportações.

Impacto: alto. Complexidade: baixa.

### 4. Perfis de exportação

- Reels/TikTok/Shorts 9:16.
- Feed 1:1.
- YouTube 16:9.
- Perfis Rápido, Equilibrado e Máxima qualidade.

Impacto: alto. Complexidade: baixa.

## Segunda etapa

### 5. Brand Kit local

- Logo ou marca d'água.
- Paleta de cores.
- Fonte.
- Posição e tamanho.
- Kits diferentes por cliente.

Implementação: JSON local + FFmpeg overlay. Não exige nuvem.

Impacto: alto para agências. Complexidade: média.

### 6. Legendas automáticas

- Legenda simples com ASS/FFmpeg inicialmente.
- Destaque da palavra atual.
- Presets reutilizáveis.
- Censura opcional de palavras.
- Aplicar legenda a todos os cortes.

O documento de Remotion existente descreve uma solução maior, mas os arquivos
necessários não estão presentes neste repositório. Começar com ASS/FFmpeg é mais
seguro para o executável.

Impacto: alto. Complexidade: média.

### 7. Entrada por link

- YouTube via `yt-dlp`.
- Google Drive por link público.
- Download com progresso, pausa e retomada.
- Validação de direitos autorais e uso permitido.

Impacto: médio. Complexidade: média.

### 8. Score viral mais explicável

Em vez de alegar muitos parâmetros genéricos, mostrar notas separadas:

- Força do gancho.
- Clareza sem contexto.
- Emoção ou tensão.
- Ritmo de fala.
- Novidade da informação.
- Potencial de comentário ou compartilhamento.
- Qualidade técnica de áudio e imagem.

Impacto: alto. Complexidade: média.

## Terceira etapa

### 9. Editor profissional

- Player e timeline.
- Entrada e saída arrastáveis.
- Preview do crop.
- Troca manual de pessoa.
- Split screen.
- Legendas e logo.
- Undo/redo.

Impacto: muito alto. Complexidade: alta. Exige frontend próprio.

### 10. Publicação direta

- YouTube Shorts.
- Instagram Reels.
- TikTok.
- Agendamento e descrição.

Exige OAuth, APIs sujeitas a mudanças, armazenamento seguro de credenciais e
possível revisão dos aplicativos pelas plataformas.

Impacto: médio. Complexidade: alta.

### 11. Monitoramento de lives

- Twitch, Kick ou YouTube Live.
- Gravação por blocos.
- Análise quase em tempo real.
- Geração automática de cortes.

Isso transforma o produto local em serviço contínuo e exige infraestrutura,
monitoramento e tratamento de falhas de rede.

Impacto: específico. Complexidade: muito alta.

## O que não recomendo agora

- Sistema de créditos e assinaturas.
- Renderização em nuvem.
- Marketplace de templates.
- Publicação para todas as redes simultaneamente.
- Monitoramento de muitos canais ao vivo.
- Prometer análise de emoções sem validação e métricas claras.

Esses recursos aumentam custos e suporte antes de o editor local estar maduro.

## Sequência recomendada

1. Galeria de cortes e revisão.
2. Painel de trabalhos e retomada visual.
3. Edição em massa.
4. Perfis de exportação.
5. Brand Kit.
6. Legendas automáticas.
7. Editor com timeline.
8. Entrada por link.
9. Publicação direta.
10. Lives somente se houver demanda real.
