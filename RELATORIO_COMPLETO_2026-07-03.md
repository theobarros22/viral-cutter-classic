# CHECKPOINT — Ecossistema Viral Cutter
## Sessão de 03/07/2026 · Conquistas, Erros e Estado Atual

> **Como retomar:** leia as seções 6 (pendências) e 7 (fila estratégica).
> O primeiro passo de qualquer retomada é confirmar o resultado da rodada
> de revalidação (6/6 clipes válidos?) e commitar. Nada novo entra antes.

> Preparado para: Theo Barros
> Escopo: Viralume (CORTE VIRAL), Viral Cutter v2 (legendas) e viral-cutter (Classic)

---

## 1. Resumo Executivo

Em uma sessão, o ecossistema saiu de "três projetos com identidades confusas e bugs invisíveis" para: estratégia de produto definida, **9 bugs encontrados e corrigidos** (dois deles quebravam a inicialização e a validação de TODOS os clipes), **4 funcionalidades novas implementadas**, 24 testes passando, e um roadmap sequenciado até a interface estilo Palmier. O custo dos problemas encontrados confirma a tese da sessão: quase todos existiam porque código foi escrito e nunca executado ponta-a-ponta.

---

## 2. Decisões Estratégicas

| Decisão | Conteúdo |
|---|---|
| **Dois produtos, não um** | Viralume = máquina de corte preciso e rápido. v2 = referência em transcrição e legendas virais (Remotion, 15 templates). Missões separadas, sem fusão de código. |
| **Classic aposentado** | viral-cutter (original) é o ancestral congelado desde 26/05 — arquivos core idênticos byte a byte ao Viralume. Nenhum investimento; vira backup quando o v2 ganhar venv próprio. |
| **Fusão futura = launcher** | A "tela inicial para escolher produto" será um launcher leve (~80 linhas), nunca uma reescrita do zero. Fusão real, se vier, será por extração gradual de módulos compartilhados. |
| **Estilo Palmier = arquitetura, não clone** | O que se copia do Palmier Pro: galeria como palco, revelação progressiva, objeto com história, e agente via MCP. O que não se copia: timeline NLE nativa (custo de anos, plataforma errada). |
| **Uso pessoal, sem comercialização** | Alvo: executável para instalar no PC do irmão. Viralume empacota fácil (onedir já validado); v2 exige Node/Remotion — fica como ferramenta da máquina de produção. |
| **3 apostas de diferenciação** | WhisperX (v2), loop de dados Instagram (Viralume), hook automático (Viralume — já entregue). |

---

## 3. Conquistas — o que foi implementado hoje

### Viralume (CORTE VIRAL)

**Precisão de corte**
- Limites de corte refinados com word timestamps do Whisper (`refinar_limites_com_palavras`): o corte nunca mais decapita palavra — abre 0.2s antes da primeira palavra e fecha 0.3s depois da última. *Validado em produção: "✂️ Limites refinados" no log real.*
- Snap ao silêncio corrigido: escolhia o PRIMEIRO silêncio da lista, agora escolhe o mais próximo.
- Threshold de silêncio adaptativo: em vez de −40dB fixo, calcula pelo volume médio do áudio (dBFS−16, travado entre −60 e −25). Funciona em festa barulhenta e em estúdio silencioso.

**Velocidade**
- Cache do modelo Whisper em 4 pontos. O pior caso: o loop de legendas virais recarregava até 3GB do disco A CADA clipe.

**Hook automático (cold open)** ⭐
- O Claude identifica a frase de maior impacto de cada segmento (`hook_inicio`/`hook_fim` no prompt de análise).
- `validar_hook` (regras: dentro do clipe, 1–5s, não aplicar se o clipe já abre forte) + `cortar_clipe_com_hook` (FFmpeg concat).
- Checkbox "🪝 Hook automático" na interface. *Validado em produção: 6/6 clipes com hook bem escolhido no teste real.*

**Efeitos virais granulares**
- O checkbox único virou três independentes: 💬 Legendas ASS · 🔍 Zoom dinâmico · 🔊 SFX — qualquer combinação. Clipe sem efeito aplicável nem re-encoda.

**Enquadramento (as 4 correções dos frames do Papo Reto)**
- Split screen agora dá ZOOM na pessoa (~1.6x, painel de 62% da altura centrado no rosto) — antes espremia o plano aberto inteiro e as pessoas ficavam minúsculas.
- Rastreio vertical (Y): o detector sempre soube a altura do rosto; o código jogava fora. Agora posiciona o crop na regra dos terços.
- Filtro de falsos positivos: rostos <2,5% da largura ignorados (mata manequim da estante, rostos na TV do cenário).
- Fallback inteligente: quando o detector frontal falha (rostos de perfil), usa a posição de QUEM FALA antes de herdar a cena anterior — o crop não cai mais na mesa/planta.

### Viral Cutter v2 (legendas)
- **F0/F1 entregues:** `.gitignore`, `requirements.txt`, `iniciar.bat` com venv próprio (fim da dependência do venv de outro projeto). Comandos de git init + venv + npm entregues para execução no Windows.
- Diagnóstico completo em `DIAGNOSTICO_2026-07-03.md` com plano F0→F5.

### Documentos produzidos
- `DIAGNOSTICO_2026-07-03.md` (v2) — auditoria + plano de 6 fases
- `LOOP_DADOS_INSTAGRAM.md` — spec do score calibrado com dados reais
- `ROADMAP_PRODUTO.md` — nova Prioridade 7: modo agente (MCP server, 6 ferramentas)
- Este relatório

---

## 4. Erros Encontrados e Corrigidos (a lista da verdade)

| # | Bug | Gravidade | Causa raiz | Status |
|---|---|---|---|---|
| 1 | `legendas.py` não existia no Viralume — app **não abria** desde 22/06 | CRÍTICA | Aba de legendas criada importando módulo do v2 que nunca foi copiado; ninguém abriu o app depois | ✅ Módulo criado/adaptado |
| 2 | `CoreEngine.py` ausente — efeitos virais 100% mortos | CRÍTICA | Arquivo existia só em D:\CORTE VIRAL\files; sync entre cópias falhou | ✅ Copiado (hash verificado) |
| 3 | Encoding cp1252 em subprocess — vídeo com acento no nome quebrava o ffprobe | CRÍTICA | `text=True` sem `encoding` no Windows; só aparece com nomes brasileiros | ✅ UTF-8 forçado em 8 arquivos |
| 4 | Validação rejeitava TODOS os clipes com hook (6/6 no teste real) | CRÍTICA | Eu adicionei o hook e esqueci de somar sua duração na validação — erro meu | ✅ Duração esperada = base + hook − pausas |
| 5 | Mesmo bug latente com "remover pausas" (subtração não contabilizada) | ALTA | Nunca detectado porque validação + remover pausas nunca rodaram juntos | ✅ Corrigido junto |
| 6 | Gradio 6: `Row` recebendo `choices` — crash pós-processamento | ALTA | Update destinado ao Dropdown caía no Row do painel | ✅ Outputs realinhados |
| 7 | Teste de checkpoint falhava (2≠1) desde a v2.3 | MÉDIA | Teste com arquivo falso nunca foi atualizado para simular a validação FFprobe | ✅ Mock da validação |
| 8 | Split screen sem zoom + sem Y + falsos positivos + fallback na mesa | ALTA | Detalhado na seção 3 | ✅ 4 correções |
| 9 | Validação da etapa 4 comparava com duração teórica | MÉDIA | Mesma cegueira do bug 4 na outra ponta | ✅ Mede o arquivo real |

**Padrão dos 9 erros:** sete existiam antes desta sessão e nunca apareceram porque o caminho de código nunca foi executado. Dois foram meus (hook × validação), pegos pelo SEU teste real — a prova de que rodar vídeo de verdade vale mais que qualquer suíte.

---

## 5. Testes e Validação

- Suíte do Viralume: **19/19 → 24 testes** (9 novos: refinamento, silêncio, threshold, hook).
- Lógica pura validada no sandbox antes de cada entrega (7/7, 9/9, 4/4 nas três frentes).
- Teste real (podcast PMERJ, 18.9 min): transcrição GPU ok (259 fps), 6 segmentos IA com scores por nicho, refinamento ativo, hook 6/6 — bloqueado na validação (bug 4, já corrigido) → **rodada de revalidação em andamento**.

---

## 6. Pendências Imediatas (nesta ordem)

1. ⏳ **Rodada de revalidação** (em andamento na sua máquina): expectativa 6/6 válidos + frames do split novo para comparação.
2. Commit do Viralume: `git add -A && git commit -m "Hook + efeitos granulares + enquadramento v2 + fixes encoding/Gradio/validacao"`
3. v2 no Windows: bloco git init + venv + `npm install` (já entregue).
4. Calibração fina com seu olho: `ZOOM_SPLIT` (0.62) e `MIN_TAMANHO_ROSTO` (0.025) no topo do `enquadramento.py`.

## 7. Fila Estratégica (pós-validação)

| Ordem | Item | Produto | Esforço |
|---|---|---|---|
| 1 | Interface estilo Palmier (mockup → aprovação → implementação) | Viralume | 1-2 sessões |
| 2 | MCP server — 6 ferramentas (Prioridade 7 do roadmap) | Viralume | 1-2 sessões |
| 3 | F2: primeiro render Remotion | v2 | 1 sessão |
| 4 | WhisperX (transcrição de elite, sync <100ms) | v2 | 1-2 sessões |
| 5 | Loop de dados Instagram (spec pronta) | Viralume | 2 sessões |
| 6 | Split-screen multi-câmera ⚠️ prazo: casamentos em agosto | Viralume | 2 sessões |

---

## 8. Indicadores do Ecossistema

| Indicador | Início do dia | Agora |
|---|---|---|
| App Viralume abre | ❌ (quebrado desde 22/06) | ✅ |
| Clipe ponta-a-ponta com hook | inexistente | ⏳ revalidação |
| Testes | 19 (1 falhando) | 24 (todos passando) |
| Bugs críticos conhecidos | desconhecidos | 0 abertos |
| v2 com git/requirements/venv próprio | ❌ | ✅ arquivos prontos |
| Projetos com missão definida | 0 de 3 | 3 de 3 |

---

---

## 9. ATUALIZAÇÃO — Reconstrução do Enquadramento (04/07/2026)

**O que a 2ª rodada de frames revelou:** o zoom do split passou a funcionar
(close-ups corretos), mas as pessoas apareciam nas quinas dos painéis.
Investigação descartou erro de convenção (x,y são o centro do rosto,
verificado em `rostos.py`). Causa raiz encontrada: **a detecção de cena
caseira perdia cortes de câmera** — o log mostrava "cenas" de 66s num
podcast multicâmera. Posições de câmeras diferentes eram misturadas numa
média só, e o crop mirava num ponto falso para as duas câmeras.

**Decisão do Theo:** reconstruir (opção recomendada), não remendar.

**O que foi implementado (bug #10 — o estrutural):**

1. **PySceneDetect** (ContentDetector, threshold 27) substitui o detector
   caseiro, com fallback automático se não instalado.
   Instalação: `venv311\Scripts\pip install scenedetect`
2. **Mediana + clip no Y (0.15–0.55)** nas posições por cena — detecção
   espúria não contamina mais o grupo.
3. **Crop suavizado** (ALPHA 0.18 por frame) com **corte seco** nas trocas
   de cena — solo e painéis do split deslizam suave dentro da cena e
   saltam limpo no corte, como um editor humano.

**Estado ao salvar este checkpoint:**
- ⏳ Aguardando: `pip install scenedetect` + reprocessamento do vídeo
  PMERJ + frames de comparação (3ª rodada).
- Critério de sucesso: log mostra `[PySceneDetect]` com número de cenas
  realista (10–20 no clipe, não 3), pessoas centradas nos painéis.
- Depois do visto-bom: commit único com toda a sessão.

**Lição registrada (para o produto e para o processo):** quando duas
rodadas de correção melhoram sintomas mas os erros migram de lugar, o
problema é de fundação — pare de remendar e reconstrua o alicerce.

---

*"Nenhuma opinião sem evidência. Nenhuma estratégia sem métrica. Nenhuma ação sem objetivo."*
