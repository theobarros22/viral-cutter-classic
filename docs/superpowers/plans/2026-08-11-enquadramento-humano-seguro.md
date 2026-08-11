# Enquadramento Humano Seguro Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Garantir que os cortes 9:16 preservem participantes, cabeça, rosto e contexto, usem solo/grupo/split corretamente e rejeitem composições inseguras.

**Architecture:** Manter o pipeline existente e concentrar as regras geométricas em `enquadramento.py`. O plano por frame continua sendo um `dict`, mas passa por normalização, suavização e validação antes da composição. Uma cena insegura recebe uma única recomposição conservadora; se ainda falhar, o processamento retorna erro explicável em vez de usar crop central vazio.

**Tech Stack:** Python 3.11, OpenCV, NumPy, FFmpeg, `unittest`.

## Global Constraints

- Não alterar seleção editorial ou pontuação de conteúdo dos cortes.
- Saída prioritária 9:16; reduzir zoom antes de cortar uma pessoa.
- Solo sustentado começa após 3,0 segundos da mesma pessoa.
- Nunca usar centro vazio como fallback humano.
- Cada painel split possui crop independente.
- Uma falha visual não pode ser escondida como sucesso.
- Preservar compatibilidade da assinatura pública `aplicar_enquadramento(...) -> bool`; o único acréscimo permitido é `permitir_sem_pessoas: bool = False`.

---

### Task 1: Linha de base geométrica e contratos

**Files:**
- Modify: `enquadramento.py`
- Modify: `tests/test_core.py`

**Interfaces:**
- Produces: `_normalizar_alvo(alvo: tuple) -> tuple[float, float, float, float]`
- Produces: `_limites_humanos(alvos: list, largura: int, altura: int) -> tuple[float, float, float, float]`

- [ ] **Step 1: Write the failing tests**

```python
def test_limites_humanos_usam_tamanho_individual_do_rosto(self):
    limites = _limites_humanos(
        [(0.08, 0.38, 0.10, 0.12), (0.60, 0.42, 0.05, 0.06)], 1920, 1080
    )
    esquerda, topo, direita, base = limites
    self.assertLessEqual(esquerda, 0)
    self.assertGreater(direita, 0.60 * 1920)
    self.assertLess(topo, 0.38 * 1080)
    self.assertGreater(base, 0.42 * 1080)

def test_normalizar_alvo_aceita_formato_antigo_de_tres_valores(self):
    self.assertEqual(_normalizar_alvo((0.5, 0.4, 0.08)), (0.5, 0.4, 0.08, 0.08))
```

- [ ] **Step 2: Run the tests and verify failure**

Run: `python -m unittest tests.test_core.TestCore.test_limites_humanos_usam_tamanho_individual_do_rosto tests.test_core.TestCore.test_normalizar_alvo_aceita_formato_antigo_de_tres_valores -v`

Expected: `ImportError` for the new helpers.

- [ ] **Step 3: Implement normalized targets and proportional margins**

```python
MARGEM_CABECA_X = 1.35
MARGEM_CABECA_TOPO = 1.15
MARGEM_CORPO_BASE = 3.20

def _normalizar_alvo(alvo):
    x, y, w = map(float, alvo[:3])
    h = float(alvo[3]) if len(alvo) > 3 else w
    return x, y, max(0.01, w), max(0.01, h)

def _limites_humanos(alvos, largura, altura):
    caixas = []
    for alvo in alvos:
        x, y, w, h = _normalizar_alvo(alvo)
        cx, cy = x * largura, y * altura
        caixas.append((
            cx - w * largura * MARGEM_CABECA_X,
            cy - h * altura * MARGEM_CABECA_TOPO,
            cx + w * largura * MARGEM_CABECA_X,
            cy + h * altura * MARGEM_CORPO_BASE,
        ))
    return (
        min(c[0] for c in caixas), min(c[1] for c in caixas),
        max(c[2] for c in caixas), max(c[3] for c in caixas),
    )
```

- [ ] **Step 4: Run focused and baseline tests**

Run: `python -m unittest tests.test_core -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add enquadramento.py tests/test_core.py
git commit -m "test: define safe human bounds"
```

### Task 2: Crop conservador com validação explícita

**Files:**
- Modify: `enquadramento.py`
- Modify: `tests/test_core.py`

**Interfaces:**
- Consumes: `_limites_humanos(...)`
- Produces: `_validar_crop_seguro(alvos: list, crop: tuple, largura: int, altura: int) -> list[str]`
- Modifies: `_calcular_crop_seguro(...) -> tuple[int, int, int, int]`

- [ ] **Step 1: Write failing edge and group tests**

```python
def test_validador_rejeita_cabeca_fora_do_crop(self):
    erros = _validar_crop_seguro([(0.04, 0.35, 0.10, 0.12)], (40, 0, 600, 1080), 1920, 1080)
    self.assertIn("pessoa_fora_da_margem", erros)

def test_crop_prefere_quadro_aberto_a_zoom_excessivo(self):
    _x, _y, w, h = _calcular_crop_seguro([(0.50, 0.40, 0.22, 0.24)], 1920, 1080, 9 / 16)
    self.assertGreaterEqual(h, int(1080 * 0.85))
    self.assertEqual(w % 2, 0)
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m unittest tests.test_core.TestCore.test_validador_rejeita_cabeca_fora_do_crop tests.test_core.TestCore.test_crop_prefere_quadro_aberto_a_zoom_excessivo -v`

Expected: helper missing or assertion failure.

- [ ] **Step 3: Replace crop calculation with bounds-first geometry**

Implementation rules:

```python
def _validar_crop_seguro(alvos, crop, largura, altura):
    x, y, w, h = crop
    esquerda, topo, direita, base = _limites_humanos(alvos, largura, altura)
    erros = []
    if esquerda < x or topo < y or direita > x + w or base > y + h:
        erros.append("pessoa_fora_da_margem")
    if h < altura * 0.50:
        erros.append("zoom_excessivo")
    return erros
```

In `_calcular_crop_seguro`, start from `_limites_humanos`, expand to the requested aspect ratio around the human-bounds center, clamp to the source frame and return even dimensions. Do not average X before computing the bounds.

- [ ] **Step 4: Run all crop tests**

Run: `python -m unittest tests.test_core -k crop -v`

Expected: all crop tests pass.

- [ ] **Step 5: Commit**

```bash
git add enquadramento.py tests/test_core.py
git commit -m "fix: preserve human safety margins"
```

### Task 3: Layout seguro para solo, grupo e split

**Files:**
- Modify: `enquadramento.py`
- Modify: `tests/test_core.py`

**Interfaces:**
- Produces: `_layout_para_cena(cena: dict, posicoes_falante: list, fps: float) -> list[str]`
- Modifies: `_gerar_plano(...) -> list[dict]`

- [ ] **Step 1: Write failing layout tests**

```python
def test_duas_pessoas_distantes_usam_split_em_vez_de_grupo_cortado(self):
    cena = {"n_pessoas": 2, "lado_a": 0.18, "lado_b": 0.82,
            "lado_a_y": 0.40, "lado_b_y": 0.42,
            "lado_a_tam": 0.08, "lado_b_tam": 0.08}
    modos = _layout_para_cena(cena, [0.18, 0.82] * 30, 30.0)
    self.assertEqual(set(modos), {"SPLIT"})

def test_duas_pessoas_proximas_cabem_em_grupo_aberto(self):
    cena = {"n_pessoas": 2, "lado_a": 0.35, "lado_b": 0.55,
            "lado_a_y": 0.40, "lado_b_y": 0.42,
            "lado_a_tam": 0.08, "lado_b_tam": 0.08}
    self.assertEqual(_layout_para_cena(cena, [None] * 90, 30.0)[0], "GRUPO")
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m unittest tests.test_core.TestCore.test_duas_pessoas_distantes_usam_split_em_vez_de_grupo_cortado tests.test_core.TestCore.test_duas_pessoas_proximas_cabem_em_grupo_aberto -v`

Expected: new helper missing.

- [ ] **Step 3: Implement layout decision without center fallback**

Rules:

```python
DISTANCIA_MAX_GRUPO = 0.30

def _layout_para_cena(cena, posicoes_falante, fps):
    if cena["n_pessoas"] <= 0:
        return []
    if cena["n_pessoas"] == 1:
        return ["SOLO_A"] * len(posicoes_falante)
    if abs(cena["lado_b"] - cena["lado_a"]) <= DISTANCIA_MAX_GRUPO:
        return ["GRUPO"] * len(posicoes_falante)
    return _classificar_modos_fala(
        posicoes_falante, cena["lado_a"], cena["lado_b"], fps
    )
```

When `_layout_para_cena` returns `[]`, `_gerar_plano` must inherit the last validated human plan or raise `RuntimeError("Cena sem pessoa validada para enquadrar")` if none exists. It must not synthesize `xa=0.5`.

- [ ] **Step 4: Run layout and full core tests**

Run: `python -m unittest tests.test_core -v`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add enquadramento.py tests/test_core.py
git commit -m "fix: choose safe solo group and split layouts"
```

### Task 4: Estabilidade temporal do plano

**Files:**
- Modify: `enquadramento.py`
- Modify: `tests/test_core.py`

**Interfaces:**
- Produces: `_suavizar_plano(plano: list[dict], fps: float) -> list[dict]`

- [ ] **Step 1: Write failing temporal tests**

```python
def test_suavizacao_ignora_oscilacao_pequena(self):
    plano = [{"modo": "SOLO_A", "xa": 0.50 + (0.005 if i % 2 else 0), "ya": 0.4, "ta": 0.08}
             for i in range(60)]
    saida = _suavizar_plano(plano, 30.0)
    self.assertLess(max(p["xa"] for p in saida) - min(p["xa"] for p in saida), 0.004)

def test_troca_de_layout_exige_histerese(self):
    plano = ([{"modo": "SPLIT", "xa": .25, "xb": .75}] * 30 +
             [{"modo": "SOLO_A", "xa": .25, "xb": .75}] * 2 +
             [{"modo": "SPLIT", "xa": .25, "xb": .75}] * 30)
    self.assertNotIn("SOLO_A", {p["modo"] for p in _suavizar_plano(plano, 30.0)})
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m unittest tests.test_core.TestCore.test_suavizacao_ignora_oscilacao_pequena tests.test_core.TestCore.test_troca_de_layout_exige_histerese -v`

Expected: helper missing.

- [ ] **Step 3: Implement dead-zone, speed limit and layout hysteresis**

Use constants `ZONA_MORTA_X = 0.01`, `VELOCIDADE_MAX_X_POR_S = 0.30`, `HISTERESE_LAYOUT_S = 0.35`. Preserve `None` gaps by carrying the last valid plan. Apply an exponential moving average only after the dead-zone and clamp each frame delta to `VELOCIDADE_MAX_X_POR_S / fps`.

- [ ] **Step 4: Call smoothing once in `_gerar_plano` and run tests**

Run: `python -m unittest tests.test_core -v`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add enquadramento.py tests/test_core.py
git commit -m "fix: stabilize framing motion and layout changes"
```

### Task 5: Validação amostrada e recomposição única

**Files:**
- Modify: `enquadramento.py`
- Modify: `pipeline.py`
- Modify: `tests/test_core.py`

**Interfaces:**
- Produces: `_validar_plano_cena(cena: dict, planos: list[dict], largura: int, altura: int, proporcao: float) -> list[str]`
- Produces: `EnquadramentoInseguroError(RuntimeError)`
- Modifies: `aplicar_enquadramento(..., permitir_sem_pessoas: bool = False) -> bool`

- [ ] **Step 1: Write failing validation tests**

```python
def test_plano_split_exige_dois_paineis_validos(self):
    cena = {"n_pessoas": 2, "lado_a": .2, "lado_b": .8,
            "lado_a_y": .4, "lado_b_y": .4,
            "lado_a_tam": .08, "lado_b_tam": 0.0,
            "frame_ini": 0, "frame_fim": 90}
    erros = _validar_plano_cena(cena, [{"modo": "SPLIT", "xa": .2, "xb": .8}] * 90,
                                  1920, 1080, 9 / 16)
    self.assertIn("split_sem_dois_alvos", erros)
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m unittest tests.test_core.TestCore.test_plano_split_exige_dois_paineis_validos -v`

Expected: helper missing.

- [ ] **Step 3: Implement scene validation**

Validate indices `frame_ini`, midpoint and `frame_fim - 1`. For each sampled plan, build its target list and call `_validar_crop_seguro`. Add `centro_vazio`, `split_sem_dois_alvos` and `plano_instavel` when applicable. Return unique error codes in deterministic order.

- [ ] **Step 4: Add one conservative retry in `aplicar_enquadramento`**

On first validation failure, force a wider crop by setting `ta/tb` to zero and prefer `GRUPO` only when `_validar_crop_seguro` passes for both targets. Validate again. Raise `EnquadramentoInseguroError` with scene frames and error codes if the second result fails. In `pipeline.etapa3_processar`, preserve the exception message in the clip report and do not rename an unsafe result as valid.

- [ ] **Step 5: Run core and functional tests**

Run: `python -m unittest tests.test_core tests.test_functional_smoke -v`

Expected: all pass; update the synthetic no-person fixture to call `aplicar_enquadramento(..., permitir_sem_pessoas=True)` rather than relying on an implicit center crop.

- [ ] **Step 6: Commit**

```bash
git add enquadramento.py pipeline.py tests/test_core.py tests/test_functional_smoke.py
git commit -m "fix: reject unsafe scene framing"
```

### Task 6: Relatório visual e comparação real

**Files:**
- Create: `tools/gerar_relatorio_enquadramento.py`
- Create: `tests/test_framing_report.py`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `gerar_contato(caminho_video: str, caminho_saida: str, amostras: int = 9) -> str`

- [ ] **Step 1: Write the failing report test**

```python
def test_gera_folha_de_contato_com_nove_amostras(self):
    saida = gerar_contato(self.video_fixture, self.output_png, amostras=9)
    self.assertTrue(os.path.exists(saida))
    imagem = cv2.imread(saida)
    self.assertGreater(imagem.shape[0], 0)
    self.assertGreater(imagem.shape[1], 0)
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m unittest tests.test_framing_report -v`

Expected: module missing.

- [ ] **Step 3: Implement deterministic contact-sheet generation**

Read nine evenly spaced frames with OpenCV, resize each to 270x480 without distortion, label timecodes and assemble a 3x3 PNG. Store reports under the project's output directory, not the repository.

- [ ] **Step 4: Run automated framing suite**

Run: `python -m unittest tests.test_core tests.test_functional_smoke tests.test_framing_report -v`

Expected: all pass.

- [ ] **Step 5: Produce before/after evidence with a user-provided real video**

Run: `python tools/gerar_relatorio_enquadramento.py --antes <video_atual.mp4> --depois <video_novo.mp4> --saida <pasta_relatorio>`

Expected: `antes.png`, `depois.png` and `relatorio.json` with validation codes per sampled scene. Do not mark the task complete until the user approves the visual comparison.

- [ ] **Step 6: Commit**

```bash
git add tools/gerar_relatorio_enquadramento.py tests/test_framing_report.py .gitignore
git commit -m "test: add visual framing acceptance report"
```

### Task 7: Regression gate

**Files:**
- Modify: `docs/validation/enquadramento-humano-seguro.md`

- [ ] **Step 1: Run the complete existing suite**

Run: `python -m unittest discover -s tests -p "test*.py" -v`

Expected: all tests pass; baseline was 77 tests before this plan.

- [ ] **Step 2: Run media validation fixtures**

Run: `python -m unittest tests.ffprobe_validation.test_ffprobe_validation -v`

Expected: all pass.

- [ ] **Step 3: Record evidence**

Document commands, Python/OpenCV versions, test count, real-video input hash, generated report paths and user approval in `docs/validation/enquadramento-humano-seguro.md`.

- [ ] **Step 4: Commit**

```bash
git add docs/validation/enquadramento-humano-seguro.md
git commit -m "docs: record safe framing validation"
```
