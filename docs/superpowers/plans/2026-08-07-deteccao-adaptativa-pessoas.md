# Detecção Adaptativa de Participantes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fazer a detecção avançar por introduções longas e encerrar somente quando identidades faciais reais estiverem confirmadas e estáveis.

**Architecture:** `rostos.py` continuará responsável pela leitura do vídeo, mas separará seleção de rodadas, acumulação e decisão de estabilidade em funções puras testáveis. A detecção processará lotes temporais progressivos, reagrupará as detecções acumuladas a cada rodada e usará identidade facial como chave; posição será apenas cobertura lateral.

**Tech Stack:** Python 3.13, OpenCV 5, MediaPipe Tasks, NumPy, `unittest`.

## Global Constraints

- A interface e a assinatura pública de `etapa1_detectar_pessoas` permanecem compatíveis.
- A duração inteira é o limite final, mas nenhum quadro intermediário será decodificado desnecessariamente.
- A busca encerra após três rodadas estáveis, nunca apenas por ter encontrado esquerda e direita.
- Previews exigem recorte facial validado e persistência em quadros distintos.
- Não adicionar dependências.

---

### Task 1: Planejamento de rodadas e critério de estabilidade

**Files:**
- Modify: `rostos.py:117-283`
- Test: `tests/test_core.py`

**Interfaces:**
- Produces: `_planejar_rodadas_amostragem(total_frames: int, fps: float, max_amostras: int, limite_minutos: float) -> list[list[int]]`
- Produces: `_busca_esta_estavel(historico_assinaturas: list[tuple], rodadas_sem_novidade: int = 3) -> bool`
- Consumes: duração e FPS já obtidos pelo `VideoCapture`.

- [ ] **Step 1: Write failing tests for progressive coverage**

```python
def test_rodadas_adaptativas_chegam_depois_de_introducao_longa(self):
    rodadas = rostos._planejar_rodadas_amostragem(
        total_frames=30 * 60 * 60, fps=30.0, max_amostras=30, limite_minutos=5.0
    )
    self.assertLess(max(rodadas[0]), 5 * 60 * 30)
    self.assertGreater(max(max(r) for r in rodadas), 45 * 60 * 30)
    self.assertEqual(len({f for rodada in rodadas for f in rodada}), sum(map(len, rodadas)))

def test_busca_para_apos_tres_rodadas_sem_identidade_nova(self):
    historico = [("a", "b"), ("a", "b"), ("a", "b"), ("a", "b")]
    self.assertTrue(rostos._busca_esta_estavel(historico, rodadas_sem_novidade=3))

def test_busca_continua_quando_identidade_nova_aparece(self):
    historico = [("a",), ("a",), ("a", "b"), ("a", "b")]
    self.assertFalse(rostos._busca_esta_estavel(historico, rodadas_sem_novidade=3))
```

- [ ] **Step 2: Run tests and verify RED**

Run: `E:\PROJETOS\viral-cutter-v2\venv-local\Scripts\python.exe -X utf8 -m unittest tests.test_core.TestCore.test_rodadas_adaptativas_chegam_depois_de_introducao_longa tests.test_core.TestCore.test_busca_para_apos_tres_rodadas_sem_identidade_nova tests.test_core.TestCore.test_busca_continua_quando_identidade_nova_aparece -v`

Expected: errors because the two helper functions do not exist.

- [ ] **Step 3: Implement minimal pure helpers**

```python
def _planejar_rodadas_amostragem(total_frames, fps, max_amostras, limite_minutos):
    total = max(1, int(total_frames))
    lote = max(6, min(12, int(max_amostras // 3) or 6))
    primeira_faixa = min(total, int(max(1.0, limite_minutos) * 60 * fps))
    limites = np.linspace(0, total, max(2, int(np.ceil(total / primeira_faixa)) + 1), dtype=int)
    rodadas, usados = [], set()
    for ini, fim in zip(limites[:-1], limites[1:]):
        alvos = [int(x) for x in np.linspace(ini, max(ini, fim - 1), lote, dtype=int) if int(x) not in usados]
        usados.update(alvos)
        if alvos:
            rodadas.append(alvos)
    return rodadas

def _busca_esta_estavel(historico_assinaturas, rodadas_sem_novidade=3):
    if len(historico_assinaturas) < rodadas_sem_novidade + 1:
        return False
    ultimas = historico_assinaturas[-(rodadas_sem_novidade + 1):]
    return all(tuple(item) == tuple(ultimas[0]) for item in ultimas[1:])
```

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the command from Step 2. Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add rostos.py tests/test_core.py
git commit -m "feat: planejar busca facial adaptativa"
```

### Task 2: Acumulação por rodada e identidades persistentes

**Files:**
- Modify: `rostos.py:117-283,410-535`
- Test: `tests/test_core.py`

**Interfaces:**
- Consumes: `_planejar_rodadas_amostragem(...)` from Task 1.
- Produces: `_assinaturas_pessoas(pessoas: list) -> tuple` for stable comparison.
- Produces: `detectar_pessoas_no_video(...)` with the same public signature and progressive behavior.

- [ ] **Step 1: Write failing tests for late identities and same-side identities**

```python
def test_assinaturas_nao_colapsam_duas_identidades_do_mesmo_lado(self):
    pessoas = [
        {"id": 0, "lado": "esquerda", "n_aparicoes": 4},
        {"id": 1, "lado": "esquerda", "n_aparicoes": 5},
    ]
    self.assertEqual(len(rostos._assinaturas_pessoas(pessoas)), 2)

def test_estabilidade_reinicia_quando_surje_pessoa_em_rodada_tardia(self):
    historico = [("id0",), ("id0",), ("id0", "id1"), ("id0", "id1")]
    self.assertFalse(rostos._busca_esta_estavel(historico, 3))
```

Add an integration-style unit test with patched frame reads where rounds 1–2 contain no faces and round 3 contains repeated face candidates; assert the detector consumes round 3 and returns the confirmed person.

- [ ] **Step 2: Run focused tests and verify RED**

Expected: `_assinaturas_pessoas` missing and the detector stops before the late round.

- [ ] **Step 3: Refactor the detector loop minimally**

```python
rodadas = _planejar_rodadas_amostragem(total_frames, fps, max_amostras, limite_minutos)
deteccoes = []
historico = []
for numero, alvos in enumerate(rodadas, 1):
    deteccoes.extend(_coletar_deteccoes_nos_frames(cap, alvos, detector, largura, altura))
    filtradas = _filtrar_candidatos_pessoas(deteccoes, total_amostras_analisadas, ...)
    pessoas = _agrupar_por_identidade(filtradas, reconhecedor, total_amostras_analisadas)
    historico.append(_assinaturas_pessoas(pessoas))
    if pessoas and _busca_esta_estavel(historico, 3):
        break
```

Extract `_coletar_deteccoes_nos_frames` only to remove duplicated random/sequential collection. Preserve `VideoIlegivelError` when no frame can be decoded.

- [ ] **Step 4: Run focused tests and verify GREEN**

Expected: late identity and same-side tests pass.

- [ ] **Step 5: Run existing core tests**

Run: `E:\PROJETOS\viral-cutter-v2\venv-local\Scripts\python.exe -X utf8 -m unittest tests.test_core -v`

Expected: all core tests pass.

- [ ] **Step 6: Commit**

```bash
git add rostos.py tests/test_core.py
git commit -m "feat: continuar detecção até identidades estabilizarem"
```

### Task 3: Previews faciais conservadores e progresso

**Files:**
- Modify: `rostos.py:264-283,410-551`
- Modify: `pipeline.py:287-348`
- Test: `tests/test_core.py`

**Interfaces:**
- Consumes: progressive detector from Task 2.
- Produces: log per round containing faixa, samples, confirmed identities and stop reason.
- Produces: previews only for identities whose best candidate has non-empty `recorte_identidade` and distinct-frame persistence.

- [ ] **Step 1: Write failing tests for invalid previews and progress**

```python
def test_identidade_sem_recorte_facial_valido_nao_vira_preview(self):
    deteccoes = [{"recorte": np.zeros((200, 200, 3), np.uint8),
                  "recorte_identidade": np.empty((0, 0, 3), np.uint8),
                  "posicao_x": 0.3, "frame_idx": 1}]
    self.assertEqual(rostos._remover_identidades_sem_rosto_valido(deteccoes), [])
```

Add a callback test asserting messages include `Rodada`, `amostras` and either `estável` or `fim do vídeo`.

- [ ] **Step 2: Run focused tests and verify RED**

Expected: helper missing and progress text absent.

- [ ] **Step 3: Implement conservative filtering and messages**

Filter empty/tiny identity crops before grouping. Emit one progress line after every round and a final stop-reason line. Update the pipeline docstring from fixed 30 frames/5 minutes to adaptive rounds.

- [ ] **Step 4: Run focused and full suites**

Run: `E:\PROJETOS\viral-cutter-v2\venv-local\Scripts\python.exe -X utf8 -m unittest discover -s tests -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add rostos.py pipeline.py tests/test_core.py
git commit -m "fix: rejeitar previews sem rosto validado"
```

### Task 4: Validação no podcast real e reinício

**Files:**
- Verify: `F:\CORTE VIRAL\files`
- Verify: `C:\Users\theob\Desktop\Viral Cutter Atualizado.lnk`

**Interfaces:**
- Consumes: podcast em `C:\Users\theob\AppData\Local\Temp\gradio\e8d2495d2506e7f473146c0464dccb6fb259ed9374a48fd481586e810e6b6a35\SUBTENENTES OMAR DAMAZIO E HONÓRIO ｜ #FalaGuerreiro434 [E2fI265ER2M].mp4`.
- Produces: galeria com previews faciais reais e participantes confirmados após a introdução.

- [ ] **Step 1: Back up modified production files**

Copy `rostos.py`, `pipeline.py`, and `tests/test_core.py` to a timestamped directory below `F:\CORTE VIRAL\files\_backups`.

- [ ] **Step 2: Run adaptive detection on the real podcast**

Run a Python command calling `detectar_pessoas_no_video` with production defaults. Record round logs, number of people, positions and preview dimensions.

Expected: search advances beyond the introduction; every returned preview is a face; identities are not represented only by left/center/right artifacts.

- [ ] **Step 3: Restart the app and verify HTTP**

Stop only the process listening on port 7860, launch `Viral Cutter Atualizado.lnk`, wait conditionally for the port, and request `http://127.0.0.1:7860/`.

Expected: HTTP 200.

- [ ] **Step 4: Final verification**

Run the full suite once more and inspect the real preview images before reporting completion.
