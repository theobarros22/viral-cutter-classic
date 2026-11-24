# VIRAL CUTTER — Documento Completo do Projeto

## Autor: Theo Barros
## Data: 01/06/2026
## Versão atual: v2

---

## O QUE É

App Python/Gradio que transforma vídeos longos de podcast em clipes curtos 9:16 com enquadramento automático inteligente. Roda localmente no Windows 11 com GPU NVIDIA.

O programa detecta quem está falando e faz cortes secos entre as pessoas, como um editor profissional faria manualmente. Quando os dois lados conversam, divide a tela mostrando as duas pessoas simultaneamente.

---

## PERFIL DO DESENVOLVEDOR

- **Nome**: Theo Barros
- **Localização**: Niterói, Rio de Janeiro, Brasil
- **Background**: Fotógrafo/cineasta com 15 anos de experiência
- **Nível de código**: Iniciante em programação (aprendendo Python)
- **Preferências**: código comentado em português, explicações antes de conceitos novos, comandos exatos para Windows CMD
- **Fluxo de trabalho**: Viral Cutter faz os cortes → Filmora finaliza (legendas, música, efeitos)

---

## AMBIENTE DE DESENVOLVIMENTO

```
OS:        Windows 11
Python:    3.11.9 (via venv311 — Python 3.14 instalado mas incompatível com PyTorch)
GPU:       NVIDIA GeForce RTX 3050 6GB Laptop GPU
CUDA:      13.0 (usa pacote cu124 do PyTorch)
Pasta:     C:\Users\Theo Barros\projetos\viral-cutter
Export:    C:\Users\Theo Barros\Desktop\viral-clipes
API Key:   setx ANTHROPIC_API_KEY "chave"
Iniciar:   clique duplo em iniciar.bat
```

### Stack instalada no venv311:
```
torch 2.6.0+cu124
torchvision, torchaudio
gradio 6+
openai-whisper
anthropic SDK
mediapipe 0.10+
opencv-python (cv2)
pydub
ffmpeg (sistema)
numpy
```

### Para instalar PyTorch com GPU:
```
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
```

---

## VERSÕES DO PROJETO

### v1 (Backup em viral-cutter-v1-backup)
Versão completa com muitas funcionalidades: editor de cortes com tabela, smart cut, split screen, blur background, modo dinâmico, legendas automáticas, histórico de projetos. Mais complexa, mais lenta.

### v2 (Versão atual — em desenvolvimento)
Versão enxuta e focada: detecta pessoas, usuário escolhe quem priorizar, cortes secos automáticos seguindo quem fala, split screen quando os dois lados conversam. Sem legendas (usuário faz no Filmora). Mais rápida e objetiva.

---

## ARQUITETURA v2

```
viral-cutter/
├── iniciar.bat          → clique duplo para iniciar (ativa venv311)
├── interface.py         → UI Gradio (dark theme preto + verde-limão)
├── pipeline.py          → Orquestrador das 3 etapas
├── analise.py           → Transcrição Whisper (GPU) + análise IA ou offline
├── cortes.py            → Corte com FFmpeg
├── rostos.py            → Detecta pessoas, extrai preview, detecta quem fala
├── enquadramento.py     → Aplica enquadramento 9:16 com cortes secos
└── face_detector.tflite → Modelo MediaPipe (baixado automaticamente)
```

---

## FLUXO DO PROGRAMA v2

```
1. Upload do vídeo longo
      ↓
2. DETECTAR PESSOAS (rostos.py)
   - MediaPipe analisa 10 frames distribuídos pelo vídeo
   - Agrupa rostos por posição X (esquerda vs direita)
   - Extrai preview (foto 200x200) de cada pessoa
   - Exibe na interface para o usuário escolher
      ↓
3. Usuário marca quem priorizar (checkbox)
      ↓
4. TRANSCREVER & ANALISAR (analise.py)
   - Whisper transcreve na GPU (modelo small por padrão)
   - Modo online: Claude API identifica segmentos por assunto (score viral, títulos)
   - Modo offline: algoritmo local detecta pausas e transições (sem custo, sem internet)
   - Modo offline ativa automaticamente se créditos da API acabarem
      ↓
5. PROCESSAR VÍDEO (pipeline.py + enquadramento.py)
   - Detecta quem fala em cada frame (rostos.py)
   - Para cada segmento:
     a. Corta o clipe com FFmpeg
     b. Aplica enquadramento com cortes secos
   - Export organizado em subpasta com nome do podcast
      ↓
6. Clipes prontos para o Filmora
```

---

## ENQUADRAMENTO — LÓGICA DOS CORTES (enquadramento.py)

### 3 Modos com Corte Seco:

**SOLO_A** — Lado A falando sozinho
- Crop 9:16 centralizado nas pessoas do lado esquerdo da mesa
- Frame estático, sem movimento de câmera
- Close-up centralizado

**SOLO_B** — Lado B falando
- Corte seco instantâneo (sem transição suave)
- Crop 9:16 centralizado nas pessoas do lado direito
- Mesma lógica estática

**SPLIT** — Os dois lados conversando
- Tela dividida ao meio
- Metade de cima: crop centralizado no lado A, ocupa 100% da largura
- Metade de baixo: crop centralizado no lado B, ocupa 100% da largura
- Sem distorção — cada metade mantém proporção
- Sem barras pretas — preenche todo o espaço
- Linha fina de 2px separando as metades
- Ativado quando detecta fala dos dois lados nos últimos 0.5s

### Regras:
- Cortes secos e rápidos — sem transição suave, sem câmera deslizando
- Enquadramento estático dentro de cada shot — câmera parada
- Duração mínima de 1 segundo em cada modo (evita cortes irritantes)
- Cada lado pode ter 1, 2 ou mais pessoas — enquadra todas do mesmo lado
- Detecção de lados: rostos com x < 0.45 = lado A, x > 0.55 = lado B

---

## DETECÇÃO DE PESSOAS (rostos.py)

### Fluxo:
1. Inicializa MediaPipe FaceDetector (novo 0.10+ ou antigo como fallback)
2. Analisa frames distribuídos pelo vídeo (10 amostras para velocidade)
3. Agrupa rostos por posição X:
   - x < 0.4 → "esquerda" (Lado A)
   - x > 0.6 → "direita" (Lado B)
   - 0.4-0.6 → "centro"
4. Ignora grupos com menos de 3 aparições (ruído)
5. Extrai melhor recorte de cada grupo (maior área)
6. Converte para preview 200x200 em base64 para exibir no Gradio

### Detecção de quem fala:
- Compara frames consecutivos na região da boca (movimento labial)
- Combina com energia do áudio por janela de tempo
- Retorna posição X do falante para cada frame

### Correção de MP4:
- Antes de analisar, passa o vídeo pelo FFmpeg com `-movflags +faststart`
- Resolve o erro "moov atom not found" do OpenCV

---

## ANÁLISE — DOIS MODOS (analise.py)

### Modo Online (Claude API):
- Envia transcrição para Claude claude-opus-4-5
- IA identifica blocos temáticos com início/fim precisos
- Gera título chamativo, score viral 1-10, resumo
- Calibrado por nicho: podcast, casamento, crime, esporte, educação
- Custo: ~$0.05-0.15 por vídeo de 1h

### Modo Offline (sem API):
- Detecta pausas longas na fala (> 1.5s = possível mudança de assunto)
- Identifica palavras de transição ("mas", "então", "agora", "outro ponto")
- Agrupa segmentos respeitando duração min/max
- Título: primeiras 12 palavras do segmento
- Score: heurísticas (perguntas, exclamações, palavras de impacto)
- Custo: $0 — funciona 100% offline
- Ativa automaticamente se créditos da API acabarem

---

## INTERFACE (interface.py)

### Seções:
```
01 — Upload do Vídeo (gr.File)
[Botão] 🔍 DETECTAR PESSOAS
02 — Escolha Quem Priorizar (Gallery + CheckboxGroup)
03 — Transcrição & Análise (Idioma, Modelo Whisper, Nicho, Modo offline)
     Duração mínima/máxima dos clipes
[Botão] 🎙️ TRANSCREVER & ANALISAR
04 — Export (Pasta destino, Qualidade 720p/1080p/4K)
[Botão] ⚡ PROCESSAR VÍDEO
05 — Progresso & Resultado (logs + relatório)
06 — Preview dos Clipes (Gallery)
```

### Design:
- Dark theme: preto (#080808) + verde-limão (#e8ff47) + ciano (#00cec9)
- Fontes: Syne (títulos) + Space Mono (código/labels)
- Gradio 6+ com allowed_paths para pasta de export

---

## ESTRUTURA DE EXPORT

```
📁 viral-clipes/                    ← pasta principal (usuário define)
    📁 Papo_Reto_Ep298/             ← criada com nome do vídeo original
        01_O_Estado_abandonou_a_favela.mp4
        02_10_anos_sem_concurso_PM.mp4
        03_UPP_foi_projeto_politico.mp4
    📁 Fala_Guerreiro_Ep45/
        01_Ex-traficante_me_encontrou.mp4
        02_Moleque_12_anos_fuzil.mp4
```

---

## PROBLEMAS CONHECIDOS E SOLUÇÕES

| Erro | Causa | Solução |
|------|-------|---------|
| `No module named 'torch'` | Rodou sem venv311 | `venv311\Scripts\activate` ou usar iniciar.bat |
| `module 'mediapipe' has no attribute 'solutions'` | MediaPipe 0.10+ mudou API | tracking.py tenta API nova, fallback para antiga |
| `moov atom not found` | MP4 com cabeçalho no final | FFmpeg com `-movflags +faststart` antes de analisar |
| `ValueError: DataFrame is ambiguous` | Gradio 6 retorna pandas DataFrame | `if hasattr(tabela, 'values'): tabela = tabela.values.tolist()` |
| `CheckboxGroup not in choices` | Opções não atualizadas | Usar `gr.update(choices=opcoes, value=opcoes)` |
| `credit balance too low` | Créditos API acabaram | Modo offline ativa automaticamente |
| `OSError: port 7860 in use` | Outra instância rodando | Fechar todos os CMDs |
| Logs do Android no CMD | Celular conectado via USB | Desconectar o celular |

---

## PRÓXIMOS PASSOS (BACKLOG)

### Prioridade alta:
- [ ] Testar enquadramento com cortes secos e split screen
- [ ] Otimizar velocidade geral do processamento
- [ ] Processamento em lote (vários vídeos de uma vez)

### Prioridade média:
- [ ] Detecção de câmera (quando a gravação original já tem cortes de câmera)
- [ ] Score de qualidade do clipe (descartar clipes com problemas)
- [ ] Export com marcadores EDL/XML compatível com DaVinci/Filmora

### Bloco 4 — Produto Final:
- [ ] PyInstaller (.exe) — empacotar como app desktop
- [ ] Janela nativa Windows (sem navegador)
- [ ] Tela de instalação profissional

---

## ARQUIVOS DE CÓDIGO ATUAIS (v2)

### iniciar.bat
```bat
@echo off
cd /d "C:\Users\Theo Barros\projetos\viral-cutter"
call venv311\Scripts\activate
python interface.py
pause
```

### Dependências (requirements.txt):
```
torch
torchvision
torchaudio
gradio
openai-whisper
anthropic
mediapipe
opencv-python
pydub
numpy
```

### Comando para instalar tudo:
```
pip install gradio openai-whisper anthropic mediapipe opencv-python pydub --break-system-packages
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
```

---

## REFERÊNCIA RÁPIDA DE COMO CADA ARQUIVO FUNCIONA

### interface.py
- Gradio Blocks com CSS customizado
- 3 funções principais: `ao_detectar_pessoas()`, `ao_analisar()`, `ao_processar()`
- Estado global `_estado` guarda caminho do vídeo, pessoas detectadas e segmentos entre etapas
- `allowed_paths` configurado para pasta de export

### pipeline.py
- `etapa1_detectar_pessoas()` → chama rostos.py, retorna previews
- `etapa2_analisar()` → chama analise.py, retorna segmentos
- `etapa3_processar()` → para cada segmento: corta → enquadra → salva
- `_cache` guarda dados entre etapas (transcrição, pessoas)
- Cria subpasta automática com nome do vídeo

### analise.py
- `transcrever_video()` → Whisper com GPU automática
- `segmentar_por_assunto()` → roteia entre modo IA e modo offline
- `_segmentar_com_ia()` → Claude API com prompt por nicho
- `_segmentar_offline()` → pausas + transições + heurísticas

### cortes.py
- `detectar_silencio()` → pydub analisa áudio
- `ajustar_cortes_com_silencio()` → ajusta timestamps para silêncios
- `cortar_clipe()` → FFmpeg com `-ss` e `-t`

### rostos.py
- `detectar_pessoas_no_video()` → MediaPipe em 10 amostras
- `salvar_previews()` → salva JPG de cada pessoa
- `detectar_quem_fala_por_frame()` → combina movimento labial + energia áudio
- `_corrigir_mp4()` → FFmpeg faststart antes de analisar

### enquadramento.py
- `aplicar_enquadramento()` → função principal
- `_detectar_lados()` → encontra posição X de cada lado da mesa
- `_gerar_sequencia_modos()` → decide SOLO_A/SOLO_B/SPLIT por frame
- 3 modos com corte seco, split screen ocupa 100% do espaço

---

## DECISÕES DE DESIGN IMPORTANTES

1. **Cortes secos > transições suaves**: como um editor profissional faria
2. **Estático > câmera se movendo**: sem tremido, sem panning
3. **Offline primeiro**: funciona sem internet, API é bônus
4. **Sem legendas no programa**: usuário finaliza no Filmora
5. **Subpastas por podcast**: organização automática do export
6. **10 amostras para detecção**: rápido o suficiente, preciso o bastante
7. **Modo offline ativa sozinho**: se API falhar, não trava o programa
8. **venv311 separado**: Python 3.14 do sistema é incompatível com PyTorch

---

*Documento gerado em 01/06/2026 para continuidade do projeto em qualquer ferramenta de IA.*
