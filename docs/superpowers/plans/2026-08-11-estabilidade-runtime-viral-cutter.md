# Estabilidade do Runtime do Viral Cutter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Executar o Viral Cutter de forma repetível em Python 3.11, manter a interface ativa quando tarefas falharem e registrar toda queda com contexto suficiente.

**Architecture:** `runtime.py` continua responsável por ambiente, logs, instância e porta. Um novo `launcher.py` realiza bootstrap e health check; `interface.py` expõe a criação/execução do app sem esconder exceções. `checkpoint.py` mantém um manifesto atômico e versionado para retomada idempotente. Erros de trabalho são capturados na fronteira da interface e não encerram o processo Gradio.

**Tech Stack:** Python 3.11, Gradio, FastAPI/Uvicorn, PowerShell, `unittest`.

## Global Constraints

- Python de desenvolvimento deve ser 3.11; o caminho não pode conter usuário fixo.
- CPU é suportada; CUDA é aceleração opcional.
- Porta ocupada por processo desconhecido nunca é encerrada automaticamente.
- Toda falha fatal grava stack trace em UTF-8.
- O mesmo projeto não executa duas vezes simultaneamente.
- Logs servem para diagnóstico; somente o checkpoint estruturado pode governar a retomada.
- Não alterar seleção editorial ou enquadramento nesta fase.

---

### Task 1: Diagnóstico estruturado do ambiente

**Files:**
- Modify: `diagnostico.py`
- Create: `tests/test_diagnostico.py`

**Interfaces:**
- Produces: `ProblemaAmbiente(codigo: str, mensagem: str, fatal: bool)`
- Produces: `coletar_diagnostico() -> list[ProblemaAmbiente]`
- Preserves: `executar_diagnostico() -> bool`

- [ ] **Step 1: Write failing tests**

```python
def test_python_incompativel_retorna_codigo_estavel(self):
    with mock.patch.object(sys, "version_info", (3, 13, 0)):
        problemas = coletar_diagnostico()
    self.assertIn("python_incompativel", {p.codigo for p in problemas})

def test_cuda_cpu_only_e_aviso_nao_bloqueio(self):
    problema = ProblemaAmbiente("cuda_indisponivel", "CPU", fatal=False)
    self.assertFalse(problema.fatal)
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m unittest tests.test_diagnostico -v`

Expected: imports missing.

- [ ] **Step 3: Implement dataclass and separate collection from printing**

```python
@dataclass(frozen=True)
class ProblemaAmbiente:
    codigo: str
    mensagem: str
    fatal: bool = True
```

Python mismatch, missing native module, missing FFmpeg/FFprobe and unwritable data directory are fatal. CUDA unavailable is non-fatal. `executar_diagnostico()` prints deterministic UTF-8 lines and returns false only when a fatal problem exists.

- [ ] **Step 4: Run tests and commit**

Run: `python -m unittest tests.test_diagnostico -v`

```bash
git add diagnostico.py tests/test_diagnostico.py
git commit -m "fix: report runtime diagnostics structurally"
```

### Task 2: Logging fatal e metadados de execução

**Files:**
- Modify: `runtime.py`
- Create: `tests/test_runtime.py`

**Interfaces:**
- Produces: `configurar_logs() -> str`
- Produces: `registrar_falha_fatal(exc_type, exc_value, traceback) -> None`
- Produces: `caminho_ultimo_erro() -> str`

- [ ] **Step 1: Write failing tests**

```python
def test_falha_fatal_grava_stack_trace_utf8(self):
    with self.assertRaisesRegex(ValueError, "ação inválida"):
        try:
            raise ValueError("ação inválida")
        except ValueError:
            registrar_falha_fatal(*sys.exc_info())
            raise
    self.assertIn("ação inválida", Path(caminho_ultimo_erro()).read_text(encoding="utf-8"))
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m unittest tests.test_runtime.TestRuntime.test_falha_fatal_grava_stack_trace_utf8 -v`

- [ ] **Step 3: Implement rotating logs and fatal pointer**

Use `logging.handlers.RotatingFileHandler(maxBytes=5_000_000, backupCount=5, encoding="utf-8")`. Write fatal exceptions to the application logger and update `ultimo_erro.json` atomically with timestamp, PID, Python version and log path. Do not store video contents or credentials.

- [ ] **Step 4: Run tests and commit**

Run: `python -m unittest tests.test_runtime -v`

```bash
git add runtime.py tests/test_runtime.py
git commit -m "fix: persist fatal runtime errors"
```

### Task 3: Health check e porta segura

**Files:**
- Modify: `runtime.py`
- Create: `launcher.py`
- Modify: `tests/test_runtime.py`

**Interfaces:**
- Produces: `verificar_saude(url: str, timeout_s: float = 1.0) -> bool`
- Produces: `inspecionar_porta(porta: int) -> dict` with keys `livre`, `pid`, `viral_cutter`

- [ ] **Step 1: Write failing tests for healthy, foreign and unavailable ports**

```python
def test_processo_estranho_na_porta_nao_e_encerrado(self):
    estado = inspecionar_porta(self.porta_servidor_estranho)
    self.assertFalse(estado["livre"])
    self.assertFalse(estado["viral_cutter"])
    self.assertEqual(estado["pid"], self.pid_estranho)
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m unittest tests.test_runtime -v`

- [ ] **Step 3: Implement HTTP health check**

`verificar_saude` must request `/` and require HTTP 200 plus the marker `Viral Cutter` in the body. `inspecionar_porta` uses the native Windows command `Get-NetTCPConnection` through a bounded PowerShell subprocess and compares its PID with the PID recorded in the status file. Do not add `psutil`, and do not perform any kill operation in these functions.

- [ ] **Step 4: Implement launcher decision**

`launcher.main()` performs diagnosis, opens an already healthy instance, refuses a foreign occupied port with PID in the message, or starts `interface.py` with redirected stdout/stderr and polls `verificar_saude` for at most 60 seconds.

- [ ] **Step 5: Run tests and commit**

Run: `python -m unittest tests.test_runtime -v`

```bash
git add launcher.py runtime.py tests/test_runtime.py
git commit -m "feat: add observable local launcher"
```

### Task 4: Isolar exceções das tarefas Gradio

**Files:**
- Modify: `interface.py`
- Create: `tests/test_interface_errors.py`

**Interfaces:**
- Produces: `_executar_tarefa_segura(nome: str, func: Callable, *args, **kwargs) -> tuple`
- Produces: `_formatar_erro_usuario(nome: str, exc: Exception, log_path: str) -> str`

- [ ] **Step 1: Write failing boundary tests**

```python
def test_erro_de_processamento_vira_estado_sem_encerrar_servidor(self):
    resultado = _executar_tarefa_segura("enquadramento", lambda: 1 / 0)
    self.assertEqual(resultado[0], "erro")
    self.assertIn("enquadramento", resultado[1])
    self.assertIn("ZeroDivisionError", Path(resultado[2]).read_text(encoding="utf-8"))
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m unittest tests.test_interface_errors -v`

- [ ] **Step 3: Implement one exception boundary**

The boundary catches `Exception`, logs with `LOGGER.exception`, returns status/message/log path, and never catches `KeyboardInterrupt` or `SystemExit`. Apply it to download, detect people, analyze and process callbacks without changing their successful return shapes.

- [ ] **Step 4: Run interface and baseline tests**

Run: `python -m unittest tests.test_interface_errors tests.test_core -v`

- [ ] **Step 5: Commit**

```bash
git add interface.py tests/test_interface_errors.py
git commit -m "fix: isolate task failures from gradio server"
```

### Task 5: Cancelamento e progresso por etapa

**Files:**
- Modify: `pipeline.py`
- Modify: `enquadramento.py`
- Create: `tests/test_pipeline_progress.py`

**Interfaces:**
- Produces: `ProgressoEtapa(etapa: str, atual: int, total: int, mensagem: str)`
- Produces: `_emitir_progresso(callback, etapa, atual, total, mensagem) -> None`

- [ ] **Step 1: Write failing tests**

```python
def test_progresso_e_monotonico_por_etapa(self):
    eventos = []
    _emitir_progresso(eventos.append, "cenas", 3, 10, "analisando")
    _emitir_progresso(eventos.append, "cenas", 2, 10, "atraso")
    self.assertEqual([e.atual for e in eventos], [3, 3])
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m unittest tests.test_pipeline_progress -v`

- [ ] **Step 3: Implement progress events and cancellation checks**

Emit at download, transcription, scene detection, face sampling, framing and export boundaries. Call `_checar_cancelamento()` inside long scene/frame loops at least once per second of processed media. Cancellation raises the existing controlled runtime error and preserves checkpoints.

- [ ] **Step 4: Run tests and commit**

Run: `python -m unittest tests.test_pipeline_progress tests.test_core -v`

```bash
git add pipeline.py enquadramento.py tests/test_pipeline_progress.py
git commit -m "feat: report progress and cancel long stages"
```

### Task 6: Medir e eliminar análise de cenas repetida

**Files:**
- Modify: `enquadramento.py`
- Modify: `checkpoint.py`
- Create: `tests/test_visual_analysis_cache.py`

**Interfaces:**
- Produces: `assinatura_analise_visual(caminho: str, perfil: str, versao: str) -> str`
- Produces checkpoint field: `analise_visual`

- [ ] **Step 1: Write failing cache test**

```python
def test_retry_reutiliza_analise_visual_persistida(self):
    primeira = analisar_com_contador(self.video, self.checkpoint)
    segunda = analisar_com_contador(self.video, self.checkpoint)
    self.assertEqual(primeira.chamadas_detector_cenas, 1)
    self.assertEqual(segunda.chamadas_detector_cenas, 0)
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m unittest tests.test_visual_analysis_cache -v`

- [ ] **Step 3: Persist cache using input signature**

The signature includes absolute path, size, nanosecond mtime, profile and `VERSAO_ANALISE_VISUAL`. Persist only serializable scene/face summaries. Invalid signature means recompute. Log cache hit/miss and elapsed seconds.

- [ ] **Step 4: Run cache and functional tests**

Run: `python -m unittest tests.test_visual_analysis_cache tests.test_functional_smoke -v`

- [ ] **Step 5: Commit**

```bash
git add enquadramento.py checkpoint.py tests/test_visual_analysis_cache.py
git commit -m "perf: reuse persisted visual analysis"
```

### Task 7: Retomada durável e idempotente de trabalhos interrompidos

**Files:**
- Modify: `checkpoint.py`
- Modify: `pipeline.py`
- Modify: `interface.py`
- Create: `tests/test_resume_checkpoint.py`

**Interfaces:**
- Produces: `salvar_manifesto_atomico(caminho: Path, manifesto: dict) -> None`
- Produces: `descobrir_trabalhos_interrompidos() -> list[dict]`
- Produces: `validar_artefato_retomada(artefato: dict) -> tuple[bool, str]`
- Modifies: `etapa3_processar(..., checkpoint=None, retomar=False)`

- [ ] **Step 1: Write failing tests for atomic persistence and stale-work discovery**

Create literal manifests for `em_andamento`, `interrompido` and `concluido`. Assert that a simulated write failure preserves the last valid JSON, that an orphaned `em_andamento` becomes discoverable as `interrompido`, and that completed work is not offered for resumption.

- [ ] **Step 2: Run and verify the expected failures**

Run: `python -m unittest tests.test_resume_checkpoint.ResumeManifestTests -v`

Expected: failures because atomic manifest persistence and discovery do not exist yet.

- [ ] **Step 3: Implement the minimal versioned manifest**

Use the existing checkpoint location and standard-library JSON/path primitives. Write to a sibling temporary file, flush and `os.fsync`, then `os.replace`. Store schema version, job ID, input signature, settings signature, owner PID, state, current stage, completed units, artifact metadata, timestamps and serialized error. Never infer resumable state by parsing log text.

- [ ] **Step 4: Write failing tests for selective artifact reuse**

Build a job with three exported clips: two valid media files and one deliberately truncated file. Assert that resume schedules only the corrupt clip. Add a changed-input-signature case that invalidates all derived units and a changed-settings case that invalidates only affected downstream units.

- [ ] **Step 5: Run and verify the expected failures**

Run: `python -m unittest tests.test_resume_checkpoint.ResumeArtifactTests -v`

Expected: failures because integrity and signature validation are not yet connected to scheduling.

- [ ] **Step 6: Implement validation and idempotent stage boundaries**

Validate existence, size and stored signature; use the existing FFprobe helper for media integrity. Persist only after download, transcription, visual analysis or clip export has produced and validated its durable artifact. Partial output keeps a temporary name and is never recorded as complete. On resume, preserve valid units and recompute only missing, incompatible or corrupt units.

- [ ] **Step 7: Write failing interface test for the resume offer**

Assert that startup state lists interrupted jobs with input name, last confirmed stage, timestamp and the action `Continuar de onde parou`. Choosing it must call the pipeline with the selected checkpoint and `retomar=True`; dismissing it must not delete the checkpoint.

- [ ] **Step 8: Implement the minimal recovery UI and error transition**

When the interface starts, call `descobrir_trabalhos_interrompidos`. A job recorded as `em_andamento` is stale only when its owner PID is absent or does not match the recorded process identity. A controlled failure persists `interrompido` plus its error before returning control to Gradio. Successful completion persists `concluido`.

- [ ] **Step 9: Run resume and regression tests**

Run: `python -m unittest tests.test_resume_checkpoint tests.test_pipeline_progress tests.test_interface_errors tests.test_visual_analysis_cache tests.test_core -v`

Expected: all pass, including simulated interruption after every persisted boundary.

- [ ] **Step 10: Commit**

```bash
git add checkpoint.py pipeline.py interface.py tests/test_resume_checkpoint.py
git commit -m "feat: resume interrupted jobs from durable checkpoints"
```

### Task 8: Ambiente Python 3.11 reproduzível

**Files:**
- Modify: `requirements-lock.txt`
- Create: `requirements-cuda.txt`
- Modify: `PREPARAR_AMBIENTE.bat`
- Modify: `preparar_ambiente.ps1`
- Create: `tests/test_environment_files.py`

- [ ] **Step 1: Write static configuration tests**

```python
def test_scripts_reject_non_311_and_no_user_path(self):
    textos = Path("preparar_ambiente.ps1").read_text(encoding="utf-8")
    self.assertIn("3.11", textos)
    self.assertNotIn("Theo Barros", textos)
    self.assertNotIn("theob", textos)
```

- [ ] **Step 2: Run and verify failure against current scripts**

Run: `python -m unittest tests.test_environment_files -v`

- [ ] **Step 3: Make environment creation location-independent**

Resolve Python with `py -3.11`, create `.venv311` relative to the worktree for development, install the lock file and verify imports. Keep CUDA requirements in `requirements-cuda.txt`; default CPU installation must remain valid. Do not mutate the broken historical `F:\...\venv311` in place.

- [ ] **Step 4: Build a fresh environment and run diagnosis**

Run: `powershell -NoProfile -ExecutionPolicy Bypass -File preparar_ambiente.ps1`

Expected: `.venv311\Scripts\python.exe diagnostico.py` exits 0; CUDA warning is non-fatal on CPU install.

- [ ] **Step 5: Run the complete suite in the fresh environment and commit**

Run: `.venv311\Scripts\python.exe -m unittest discover -s tests -p "test*.py" -v`

```bash
git add requirements-lock.txt requirements-cuda.txt PREPARAR_AMBIENTE.bat preparar_ambiente.ps1 tests/test_environment_files.py
git commit -m "build: reproduce Python 3.11 environment"
```

### Task 9: Runtime regression gate

**Files:**
- Create: `docs/validation/runtime-estavel.md`

- [ ] **Step 1: Start through launcher and verify health**

Run: `.venv311\Scripts\python.exe launcher.py`

Expected: HTTP 200 at `http://127.0.0.1:7860/` and one server process.

- [ ] **Step 2: Trigger a controlled task failure**

Use an invalid/corrupt fixture through the processing callback. Expected: UI remains reachable, error contains log path, stack trace is present.

- [ ] **Step 3: Run complete tests**

Run: `.venv311\Scripts\python.exe -m unittest discover -s tests -p "test*.py" -v`

- [ ] **Step 4: Record versions, commands, counts and log evidence, then commit**

```bash
git add docs/validation/runtime-estavel.md
git commit -m "docs: record stable runtime validation"
```
