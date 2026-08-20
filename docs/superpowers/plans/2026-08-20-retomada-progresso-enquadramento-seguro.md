# Retomada, progresso e enquadramento seguro Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tornar o processamento recuperável e visível, sem reexportar clipes válidos, e impedir crops 9:16 que cortem pessoas ou apontem para áreas vazias.

**Architecture:** `checkpoint.py` passa a ser a fonte de verdade do estado e da descoberta de resultados já existentes. `pipeline.py` publica eventos estruturados de progresso e só promove um clipe a concluído após validar sua mídia e seu enquadramento. `enquadramento.py` decide o crop mais aberto que preserve a área humana segura; `interface.py` apresenta decisão de retomada e painel de progresso, sem alterar a seleção de cortes.

**Tech Stack:** Python 3.11, Gradio, OpenCV/MediaPipe, FFmpeg/FFprobe, `unittest`.

## Global Constraints

- Preservar exportação local MP4 H.264 em 9:16.
- Não sobrescrever saída válida sem a escolha explícita de reprocessar tudo.
- Sem serviços remotos, banco de dados ou nova dependência.
- Fallback de enquadramento deve ser 9:16 mais aberto; nunca zoom agressivo, pessoa cortada ou região lateral vazia.
- O checkpoint deve continuar sendo gravado atomicamente.
- A versão Classic estável deve continuar executando seus testes existentes.

---

### Task 1: Inventário de retomada e validação de resultados

**Files:**
- Modify: `checkpoint.py:42-117`
- Modify: `pipeline.py:657-1040`
- Test: `tests/test_core.py`

**Interfaces:**
- Consumes: `resultado_valido(resultado: dict) -> bool` e `validar_midia_ffprobe(...) -> dict`.
- Produces: `inspecionar_retomada(checkpoint: dict, pasta_saida: str, segmentos: list) -> dict`, com chaves `concluidos`, `pendentes`, `invalidos`, `total` e `checkpoint_encontrado`.
- Produces: estados de clipe `pendente`, `processando`, `concluido`, `falhou` e `revisar` no checkpoint.

- [ ] **Step 1: Write the failing tests**

```python
def test_retomada_reaproveita_mp4_valido_sem_status_concluido(self):
    checkpoint = novo_checkpoint("abc", self.video, self.segmentos, "1080p", [])
    arquivo = self.criar_mp4_valido("01_teste.mp4")
    checkpoint["clipes"]["1"] = {"status": "processando", "arquivo": arquivo}

    plano = inspecionar_retomada(checkpoint, self.pasta_saida, self.segmentos)

    self.assertEqual(plano["concluidos"], {1: arquivo})
    self.assertEqual(plano["pendentes"], [])

def test_retomada_nao_reaproveita_arquivo_incompleto(self):
    checkpoint = novo_checkpoint("abc", self.video, self.segmentos, "1080p", [])
    arquivo = os.path.join(self.pasta_saida, "01_teste.mp4")
    pathlib.Path(arquivo).write_bytes(b"incompleto")
    checkpoint["clipes"]["1"] = {"status": "concluido", "arquivo": arquivo}

    plano = inspecionar_retomada(checkpoint, self.pasta_saida, self.segmentos)

    self.assertEqual(plano["concluidos"], {})
    self.assertEqual(plano["invalidos"], [1])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv311\Scripts\python.exe -m unittest tests.test_core.TestCore.test_retomada_reaproveita_mp4_valido_sem_status_concluido tests.test_core.TestCore.test_retomada_nao_reaproveita_arquivo_incompleto -v`

Expected: FAIL because `inspecionar_retomada` does not exist.

- [ ] **Step 3: Implement the minimal inventory**

```python
def inspecionar_retomada(checkpoint, pasta_saida, segmentos):
    concluidos, pendentes, invalidos = {}, [], []
    for indice, segmento in enumerate(segmentos, 1):
        item = (checkpoint or {}).get("clipes", {}).get(str(indice), {})
        arquivo = item.get("arquivo") or os.path.join(
            pasta_saida, f"{indice:02d}_{sanitizar_nome(segmento.get('titulo', f'clipe_{indice:02d}'))}.mp4"
        )
        if resultado_valido({"arquivo": arquivo}):
            concluidos[indice] = arquivo
        elif os.path.exists(arquivo):
            invalidos.append(indice)
        else:
            pendentes.append(indice)
    return {"checkpoint_encontrado": checkpoint is not None, "concluidos": concluidos,
            "pendentes": pendentes, "invalidos": invalidos, "total": len(segmentos)}
```

Use o inventário em `etapa3_processar`; promova arquivos válidos encontrados para
`concluido`, marque inválidos como `pendente` e mantenha o arquivo inválido fora
da galeria final. Ao iniciar cada clipe, grave `processando`; em exceção grave
`falhou` com mensagem curta e salve antes de continuar ou propagar o erro.

- [ ] **Step 4: Run focused tests and existing checkpoint tests**

Run: `venv311\Scripts\python.exe -m unittest tests.test_core -v`

Expected: PASS, incluindo retomada de arquivo válido e rejeição de arquivo incompleto.

- [ ] **Step 5: Commit**

```bash
git add checkpoint.py pipeline.py tests/test_core.py
git commit -m "feat: validate outputs before resuming processing"
```

### Task 2: Eventos de progresso duráveis e estimativa honesta

**Files:**
- Modify: `checkpoint.py:42-83`
- Modify: `pipeline.py:657-1040`
- Test: `tests/test_core.py`

**Interfaces:**
- Consumes: o checkpoint produzido pela Task 1.
- Produces: `atualizar_progresso(checkpoint: dict, *, indice: int, etapa: str, concluidos: int, total: int, inicio_sessao: float, amostras: list[float]) -> dict`.
- Produces: eventos `progresso_callback(evento: dict)` com `tipo="progresso"`, `percentual_global`, `percentual_etapa`, `clipe_atual`, `total`, `concluidos`, `etapa`, `decorrido_segundos` e `estimativa_segundos`.

- [ ] **Step 1: Write the failing tests**

```python
def test_progresso_sem_amostra_nao_inventa_estimativa(self):
    evento = atualizar_progresso({}, indice=1, etapa="corte", concluidos=0,
                                 total=3, inicio_sessao=10.0, agora=15.0,
                                 amostras=[])
    self.assertEqual(evento["percentual_global"], 0.0)
    self.assertIsNone(evento["estimativa_segundos"])

def test_progresso_usa_media_dos_clipes_concluidos(self):
    evento = atualizar_progresso({}, indice=2, etapa="enquadramento", concluidos=1,
                                 total=3, inicio_sessao=10.0, agora=30.0,
                                 amostras=[20.0])
    self.assertEqual(evento["percentual_global"], 33.3)
    self.assertEqual(evento["estimativa_segundos"], 40)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv311\Scripts\python.exe -m unittest tests.test_core.TestCore.test_progresso_sem_amostra_nao_inventa_estimativa tests.test_core.TestCore.test_progresso_usa_media_dos_clipes_concluidos -v`

Expected: FAIL because `atualizar_progresso` does not exist.

- [ ] **Step 3: Implement a pure progress helper and publish events**

```python
def atualizar_progresso(checkpoint, *, indice, etapa, concluidos, total,
                        inicio_sessao, agora, amostras):
    decorrido = max(0.0, agora - inicio_sessao)
    restante = None if not amostras else round(sum(amostras) / len(amostras) * (total - concluidos))
    evento = {
        "tipo": "progresso", "clipe_atual": indice, "etapa": etapa,
        "concluidos": concluidos, "total": total,
        "percentual_global": round(100 * concluidos / total, 1) if total else 100.0,
        "percentual_etapa": 0.0 if etapa != "concluido" else 100.0,
        "decorrido_segundos": round(decorrido), "estimativa_segundos": restante,
    }
    checkpoint["progresso"] = evento
    return evento
```

Chame o helper ao começar um clipe, ao mudar de `corte` para
`deteccao_falante`, `enquadramento` e `validacao`, após cada clipe concluído e
em qualquer falha. Salve o checkpoint antes de enviar o evento ao callback.
Mantenha a compatibilidade: quando o callback espera texto, envie a linha de
log existente; para a nova interface, aceite o evento estruturado.

- [ ] **Step 4: Run focused tests and full suite**

Run: `venv311\Scripts\python.exe -m unittest discover -s tests -v`

Expected: PASS; o checkpoint de teste contém progresso e a estimativa fica nula
até o primeiro clipe concluído.

- [ ] **Step 5: Commit**

```bash
git add checkpoint.py pipeline.py tests/test_core.py
git commit -m "feat: persist processing progress and estimates"
```

### Task 3: Contrato de enquadramento 9:16 seguro

**Files:**
- Modify: `enquadramento.py:1-420`
- Modify: `pipeline.py:850-930`
- Test: `tests/test_core.py`

**Interfaces:**
- Consumes: caixas humanas por cena e `posicoes` geradas por `detectar_quem_fala_por_frame`.
- Produces: `calcular_crop_seguro(alvo: tuple[float, float, float, float] | None, largura: int, altura: int, margem: float = 0.08) -> tuple[int, int, int, int]`.
- Produces: `validar_crop_seguro(crop: tuple[int, int, int, int], alvo: tuple[float, float, float, float] | None, largura: int, altura: int) -> bool`.
- Produces: estado `revisar` quando nenhum crop 9:16 seguro puder ser comprovado.

- [ ] **Step 1: Write the failing tests**

```python
def test_crop_seguro_abre_quando_rosto_esta_perto_da_borda(self):
    crop = calcular_crop_seguro((1720, 180, 1900, 740), 1920, 1080)
    self.assertTrue(validar_crop_seguro(crop, (1720, 180, 1900, 740), 1920, 1080))
    self.assertLessEqual(crop[0], 1720)
    self.assertEqual(crop[2] - crop[0], round((crop[3] - crop[1]) * 9 / 16))

def test_crop_sem_alvo_usa_quadro_9_por_16_central_mais_aberto(self):
    crop = calcular_crop_seguro(None, 1920, 1080)
    self.assertEqual(crop, (656, 0, 1264, 1080))

def test_crop_que_exclui_alvo_e_rejeitado(self):
    self.assertFalse(validar_crop_seguro((0, 0, 608, 1080), (1500, 100, 1800, 800), 1920, 1080))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv311\Scripts\python.exe -m unittest tests.test_core.TestCore.test_crop_seguro_abre_quando_rosto_esta_perto_da_borda tests.test_core.TestCore.test_crop_sem_alvo_usa_quadro_9_por_16_central_mais_aberto tests.test_core.TestCore.test_crop_que_exclui_alvo_e_rejeitado -v`

Expected: FAIL because the safe-crop functions do not exist.

- [ ] **Step 3: Implement minimum safe-crop geometry**

```python
def calcular_crop_seguro(alvo, largura, altura, margem=0.08):
    crop_w = round(altura * 9 / 16)
    if alvo is None:
        esquerda = max(0, (largura - crop_w) // 2)
        return esquerda, 0, esquerda + crop_w, altura
    x1, y1, x2, y2 = alvo
    folga = max(1, round((x2 - x1) * margem))
    centro = (x1 + x2) / 2
    esquerda = min(max(round(centro - crop_w / 2), x2 + folga - crop_w), x1 - folga)
    esquerda = max(0, min(largura - crop_w, esquerda))
    return esquerda, 0, esquerda + crop_w, altura
```

Use as caixas humanas reais da cena como alvo; não use somente a coordenada de
fala para autorizar o crop. Antes de escrever o frame, valide o crop. Se a
validação falhar, use o fallback central aberto. Se o fallback também não puder
conter uma pessoa válida, interrompa aquele clipe com `status="revisar"`,
preserve o motivo no checkpoint e não o coloque entre os concluídos.

- [ ] **Step 4: Run framing regressions and real smoke**

Run: `venv311\Scripts\python.exe -m unittest tests.test_core -v`

Expected: PASS nos testes existentes de margem, grupo e split, e nos três novos
casos de pessoa na borda, ausência de alvo e área vazia.

- [ ] **Step 5: Commit**

```bash
git add enquadramento.py pipeline.py tests/test_core.py
git commit -m "fix: keep people inside safe 9x16 framing"
```

### Task 4: Decisão de retomada e painel na interface

**Files:**
- Modify: `interface.py:485-640, 1000-1125`
- Modify: `pipeline.py:657-1040`
- Test: `tests/test_classic_ui_layout.py`
- Test: `tests/test_core.py`

**Interfaces:**
- Consumes: `inspecionar_retomada(...) -> dict` da Task 1 e eventos da Task 2.
- Produces: `montar_resumo_retomada(plano: dict) -> str` e `formatar_painel_progresso(evento: dict) -> str`.
- Produces: parâmetro `modo_retomada` com valores `"retomar"`, `"reprocessar"` ou `"cancelar"` para `ao_processar` e `etapa3_processar`.

- [ ] **Step 1: Write the failing tests**

```python
def test_resumo_retomada_informa_clipes_prontos_e_pendentes(self):
    texto = montar_resumo_retomada({"total": 5, "concluidos": {1: "a.mp4", 2: "b.mp4"},
                                    "pendentes": [3, 4], "invalidos": [5],
                                    "checkpoint_encontrado": True})
    self.assertIn("2 de 5 concluídos", texto)
    self.assertIn("2 pendentes", texto)
    self.assertIn("1 precisa ser refeito", texto)

def test_painel_progresso_mostra_calculando_sem_estimativa(self):
    texto = formatar_painel_progresso({"clipe_atual": 1, "total": 4, "concluidos": 0,
                                       "percentual_global": 0.0, "etapa": "corte",
                                       "decorrido_segundos": 12, "estimativa_segundos": None})
    self.assertIn("0%", texto)
    self.assertIn("calculando", texto)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv311\Scripts\python.exe -m unittest tests.test_core -v`

Expected: FAIL because the interface formatters and explicit resume mode do not exist.

- [ ] **Step 3: Implement the narrow UI change**

Add a compact `gr.Markdown` progress card beside the existing log, a readonly
resume summary and a radio input with these literal labels:

```python
modo_retomada = gr.Radio(
    ["Retomar trabalho", "Reprocessar tudo", "Cancelar"],
    value="Retomar trabalho", label="Trabalho anterior encontrado"
)
```

Map the labels to `retomar`, `reprocessar` and `cancelar`. On `cancelar`, return
without calling `etapa3_processar`. On `reprocessar`, do not delete existing
files; create a new checkpoint/output identity and expose the new destination
in the log. Update the progress card in the same callback cycle as the log,
using the structured event saved by the pipeline. Keep the main document scroll
and sidebar behavior covered by `test_classic_ui_layout.py`.

- [ ] **Step 4: Run UI, core and full regression suite**

Run: `venv311\Scripts\python.exe -m unittest discover -s tests -v`

Expected: PASS. Verify manually at 1366x768 that the card remains visible,
the page scrolls and a resumed job shows its completed/pending counts.

- [ ] **Step 5: Commit**

```bash
git add interface.py pipeline.py tests/test_core.py tests/test_classic_ui_layout.py
git commit -m "feat: show resumable work and live processing progress"
```

### Task 5: Release verification

**Files:**
- Modify: `gerar_release.ps1` only if the new tests expose a required build validation gap.
- Modify: `RELEASE_CLASSIC_2.3.2_FINAL.md` or create a new release manifest only after all checks pass.

**Interfaces:**
- Consumes: completed Tasks 1–4.
- Produces: validated `dist\\ViralCutter\\ViralCutter.exe` and portable ZIP containing the whole `ViralCutter` directory.

- [ ] **Step 1: Run the complete automated verification**

Run: `venv311\Scripts\python.exe -m unittest discover -s tests -v`

Expected: all tests pass, including checkpoint, progress, framing and UI regressions.

- [ ] **Step 2: Build and validate the real executable**

Run: `powershell -ExecutionPolicy Bypass -File .\gerar_release.ps1`

Expected: PyInstaller succeeds; the executable process remains alive and its
local HTTP interface responds with status 200.

- [ ] **Step 3: Validate a portable installation**

Run: extract the generated ZIP into `release\\validation-retomada-progresso`, run
`ViralCutter\\ViralCutter.exe`, wait for `status.json`, and request its local HTTP
URL. Confirm HTTP 200, then remove only that validation directory.

- [ ] **Step 4: Record validation and commit**

```bash
git add gerar_release.ps1 RELEASE_CLASSIC_2.3.2_FINAL.md
git commit -m "docs: record resumable processing release validation"
```

If neither file needs change, do not create an empty commit. Keep the portable
ZIP out of Git history and record its SHA-256 in the release manifest.
