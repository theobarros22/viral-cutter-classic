# Projeto: Legendas Animadas — Viral Cutter v2

## Visão Geral

Sistema de legendas animadas integrado como aba ("Legendas Animadas") dentro do Viral Cutter v2, um programa desktop em Python/Gradio que corta clipes virais de podcasts e vídeos longos. A aba de legendas funciona de forma independente — aceita qualquer vídeo, não apenas os gerados pelo pipeline de corte.

**Stack tecnológico:**
- Python (Gradio) → interface web local
- Whisper (OpenAI) → transcrição com timestamps por palavra (`word_timestamps=True`)
- Remotion (React/TypeScript) → renderização de legendas animadas
- FFmpeg → processamento de áudio/vídeo
- librosa → detecção de beats para sincronização musical (esqueleto pronto)

**Diretório do projeto:** `C:\Users\Theo Barros\projetos\viral-cutter-v2\`  
**Backup:** `D:\CORTE VIRAL\files\`

---

## Arquitetura

```
viral-cutter-v2/
├── interface.py          # Gradio com 2 abas (Corte Viral + Legendas Animadas)
├── pipeline.py           # Pipeline de corte (etapas 1-3)
├── analise.py            # Whisper + segmentação IA
├── cortes.py             # FFmpeg corte
├── rostos.py             # Detecção facial
├── enquadramento.py      # Reframe 9:16
├── legendas.py           # Ponte Python → Remotion
├── musica.py             # Módulo de música (esqueleto)
└── remotion/             # Módulo Remotion (React/TypeScript)
    ├── package.json      # Remotion 4.0.481, React 19
    ├── tsconfig.json
    ├── remotion.config.ts
    └── src/
        ├── index.ts      # registerRoot
        ├── index.css      # 19 fontes Google Fonts (4 categorias)
        ├── Root.tsx        # Composition "SubtitleVideo" (1080x1920, 30fps)
        ├── types.ts        # Tipos TypeScript
        └── SubtitleComposition.tsx  # 15 templates de legenda
```

---

## Templates Disponíveis (15 total)

### Originais (10)
1. **hook-viral** — Texto gigante bold + pill de destaque verde. Para hooks de abertura.
2. **palavra-vazada** — Metálico transparente com mix-blend-mode screen + webkit-text-stroke. Bebas Neue.
3. **legenda-sutil** — Texto branco limpo com sombra, SEM caixa de fundo. Inter bold.
4. **cta** — Cor de destaque com entrada deslizante (slide da esquerda). Pill colorida.
5. **dado-numero** — Números gigantes com glow, texto contextual menor. Spring pop.
6. **impacto-shake** — Treme (shake com decay) + escala spring. Vermelho, Oswald bold.
7. **minimalista** — Fade suave in/out, Inter, sem efeitos extras.
8. **politico** — Barra sólida institucional com borda dourada lateral. Montserrat bold.
9. **cinema** — Bebas Neue vazado (transparent + webkit-text-stroke). Letter-spacing animado.
10. **tiktok** — 2 cores alternadas por palavra, Bangers, pop spring. Sombra bicolor.

### Novos (5) — baseados em referências virais
11. **narrativo** — Serifado elegante (Playfair Display), sombra sutil, slide up suave. Estilo vlog/documentário. Baseado no vídeo renderverso.ia.
12. **typewriter** — Letra por letra com cursor piscando. Para texto em fundo preto ou sobre vídeo.
13. **contador** — Número animado que sobe de 0 ao valor final com easing. Pop spring no final. Para estatísticas/dados.
14. **hierarquia** — Tamanhos mistos automatizados: números ficam 3x maiores, preposições ficam 0.5x em itálico serif, substantivos em tamanho padrão. Baseado no estilo "mais de 50 mil usuários" do vídeo matheusgobbi.
15. **infografico** — Badge circular para números / pill com borda glow e backdrop blur para texto. Estilo dashboard/dados.

---

## Fontes Disponíveis (19 fontes Google Fonts)

### Bold/Impact (para hooks, títulos)
- Montserrat (400, 700, 900)
- Bebas Neue
- Oswald (400, 700)
- Anton
- Archivo Black
- Bangers
- Russo One
- Righteous

### Clean/Modern (para legendas narrativas)
- Inter (400, 700, 900)
- Poppins (400, 600, 700, 900)
- DM Sans (400, 500, 700)
- Space Grotesk (400, 500, 700)

### Serif/Elegante (para estilo cinema, editorial)
- Playfair Display (400, 700, italic)
- Cormorant Garamond (400, 600, 700)
- Lora (400, 700, italic)

### Display/Handwritten (para TikTok, memes, destaque)
- Caveat (400, 700)
- Permanent Marker
- Pacifico
- Abril Fatface

---

## Fluxo de Uso

1. Usuário abre `http://localhost:7860`
2. Vai na aba "🎨 Legendas Animadas"
3. Upload de vídeo OU aponta para pasta com vídeos
4. Escolhe: template, fonte (19 opções ou padrão), tamanho, cor do texto, cor de destaque, posição (top/center/bottom)
5. Escolhe idioma e modelo Whisper
6. Clica "APLICAR LEGENDAS"
7. O programa: transcreve → extrai palavras com timestamps → agrupa (se necessário) → gera JSON de props → chama `npx remotion render` → exporta vídeo com legendas

---

## Detalhes Técnicos por Arquivo

### legendas.py
- `TEMPLATES` — dict com 15 IDs → labels
- `FONTES` — dict com 19 nomes → CSS font-family strings
- `verificar_remotion_instalado()` / `instalar_remotion()` — gerencia npm install
- `extrair_palavras_do_whisper()` — extrai word-level timestamps, ajusta pra tempo relativo do clipe. Fallback: divide texto uniformemente se não tiver word timestamps
- `agrupar_palavras()` — agrupa em blocos de 2-3 palavras para templates que não são palavra-por-palavra
- `aplicar_legendas()` — copia vídeo pro Remotion public/, gera JSON de props, chama subprocess `npx remotion render SubtitleVideo`, limpa temp
- Templates por palavra (sem agrupamento): tiktok, impacto-shake, hook-viral, dado-numero, contador, hierarquia

### SubtitleComposition.tsx (Remotion)
- `getPalavraAtiva()` — encontra qual palavra/grupo está ativo no frame atual
- `getPosicaoCSS()` — top/center/bottom com padding
- `GradientOverlay` — degradê preto→transparente embaixo ou em cima
- 15 funções `render*()` — cada uma com suas animações (spring, interpolate, Easing)
- `SubtitleComposition` — componente principal: `<Video>` + overlay + renderer do template
- **Efeitos usados:** spring scale, interpolate opacity, translateY/X, shake (sin/cos com decay), typewriter (slice progressivo), mix-blend-mode screen, webkit-text-stroke, backdrop-filter blur, letter-spacing animado

### musica.py (esqueleto)
- `detectar_beats()` — librosa: BPM, beat timestamps, downbeats (cada 4 beats), drops (energia > percentil 90)
- `sincronizar_legendas_com_beats()` — modos: "beat" (snap ao beat mais próximo), "drop" (palavras longas nos drops), "livre" (sem sync)
- `mixar_audio()` — FFmpeg amix: volume música/fala, fade in/out. Copia vídeo sem recodificar (copy video stream)

### interface.py
- 2 abas Gradio: "✂️ Corte Viral" + "🎨 Legendas Animadas"
- Tab Legendas: upload OU scanner de pasta → dropdown de template (15) → dropdown de fonte (19 + padrão) → slider de tamanho → cores → posição → idioma/Whisper → botão → log + preview
- `ao_legendar()` — pipeline completo: determina vídeo → transcreve com Whisper → extrai palavras → chama `aplicar_legendas()`
- `ao_escanear_pasta()` — lista vídeos numa pasta (.mp4, .mov, .avi, .mkv, .webm)

---

## Referências Visuais Analisadas

1. **renderverso.ia** — Vlog storytelling. Hook com texto gigante branco + pill verde-limão. Legendas narrativas limpas, serifadas, sem caixa de fundo. CTA "Follow" animado no final.
2. **matheusgobbi** — Estilo motion graphics. Tipografia hierárquica ("50" gigante + "mil" médio + "usuários" em cursiva). Typewriter em fundo preto. Overlays gráficos (cards Instagram, mockups, badges "40% OFF"). Colagens com face swap + logos. Cutout de pessoa com halo.

---

## O que Falta Implementar

1. **npm install** — Remotion ainda não foi instalado (rodar `npm install` na pasta remotion/)
2. **Teste end-to-end** — App não foi testado/lançado ainda
3. **Módulo de música** — UI na aba de legendas (upload música, dropdown de modo sync, sliders de volume)
4. **Overlays estáticos** — Possibilidade de inserir imagens/PNGs como overlay (logos, badges) em posições customizáveis
5. **Multi-template por vídeo** — Permitir diferentes templates para diferentes trechos do mesmo vídeo (ex: hook-viral nos primeiros 5s, narrativo no resto)
6. **Preview em tempo real** — Remotion Studio para pré-visualizar antes de renderizar

---

## Como Rodar

```bash
# Na pasta viral-cutter-v2/
pip install gradio whisper torch ffmpeg-python

# Instalar Remotion (primeira vez)
cd remotion
npm install
cd ..

# Rodar
python interface.py
# Abre em http://localhost:7860
```

**Requisitos:** Python 3.10+, Node.js 18+, FFmpeg, GPU recomendada (Whisper + Remotion)
