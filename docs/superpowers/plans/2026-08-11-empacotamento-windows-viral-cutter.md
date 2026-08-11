# Empacotamento Windows do Viral Cutter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produzir um pacote Windows testável e independente do repositório ou de Python global, sem perder logs, configurações, checkpoints e vídeos do usuário.

**Architecture:** PyInstaller gera inicialmente um diretório `onedir`, adequado para modelos e bibliotecas nativas. O runtime resolve recursos imutáveis pela pasta do executável e dados mutáveis por `%LOCALAPPDATA%\ViralCutter`. Um script determinístico executa diagnóstico, testes, build, validação em pasta limpa e geração de artefato versionado.

**Tech Stack:** Python 3.11, PyInstaller, PowerShell, FFmpeg/FFprobe, Windows Shortcut, `unittest`.

## Global Constraints

- Este plano começa somente após aprovação visual do enquadramento e validação do runtime.
- O pacote não depende de Python global, worktree ou caminhos com nome de usuário.
- Logs, checkpoints e configurações ficam fora da pasta do aplicativo.
- Não sobrescrever instalação ou dados existentes durante o build de teste.
- Distribuir apenas binários e modelos com licença documentada.
- Primeira saída é candidata de teste, não versão definitiva.

---

### Task 1: Inventário de recursos e licenças

**Files:**
- Create: `packaging/manifest.json`
- Create: `packaging/THIRD_PARTY_NOTICES.md`
- Create: `tests/test_packaging_manifest.py`

**Interfaces:**
- Produces manifest keys: `files`, `models`, `binaries`, `licenses`, `excluded`

- [ ] **Step 1: Write failing manifest tests**

```python
def test_manifest_inclui_binarios_e_modelos_obrigatorios(self):
    data = json.loads(Path("packaging/manifest.json").read_text(encoding="utf-8"))
    self.assertEqual(set(data["binaries"]), {"tools/ffmpeg.exe", "tools/ffprobe.exe"})
    self.assertIn("face_detector.tflite", data["models"])
    self.assertNotIn("node_modules", data["files"])
```

- [ ] **Step 2: Run and verify failure**

Run: `.venv311\Scripts\python.exe -m unittest tests.test_packaging_manifest -v`

- [ ] **Step 3: Create explicit manifest and notices**

List every bundled model/binary with source, version, license and destination. Exclude worktrees, `.git`, tests, caches, user videos, logs, build history, Remotion `node_modules` and unrelated spreadsheets.

- [ ] **Step 4: Run test and commit**

```bash
git add packaging/manifest.json packaging/THIRD_PARTY_NOTICES.md tests/test_packaging_manifest.py
git commit -m "docs: inventory packaged runtime resources"
```

### Task 2: Resolver recursos e dados no executável

**Files:**
- Modify: `runtime.py`
- Modify: `rostos.py`
- Create: `tests/test_packaged_paths.py`

**Interfaces:**
- Produces: `pasta_recursos() -> str`
- Preserves: `pasta_dados() -> str`
- Produces: `caminho_recurso(nome: str) -> str`

- [ ] **Step 1: Write failing frozen-runtime tests**

```python
def test_recursos_frozen_usam_meipass_e_dados_usam_localappdata(self):
    with mock.patch.object(sys, "frozen", True, create=True), \
         mock.patch.object(sys, "_MEIPASS", r"C:\app-temp", create=True), \
         mock.patch.dict(os.environ, {"LOCALAPPDATA": r"C:\dados"}):
        self.assertEqual(pasta_recursos(), r"C:\app-temp")
        self.assertTrue(pasta_dados().startswith(r"C:\dados\ViralCutter"))
```

- [ ] **Step 2: Run and verify failure**

Run: `.venv311\Scripts\python.exe -m unittest tests.test_packaged_paths -v`

- [ ] **Step 3: Implement immutable/mutable path separation**

`pasta_recursos` uses `sys._MEIPASS` only when frozen, otherwise the source directory. `pasta_dados` uses `%LOCALAPPDATA%\ViralCutter`. Update model lookups to call `caminho_recurso`; never write inside `_MEIPASS` or `dist`.

- [ ] **Step 4: Run tests and commit**

```bash
git add runtime.py rostos.py tests/test_packaged_paths.py
git commit -m "fix: separate packaged resources from user data"
```

### Task 3: Spec PyInstaller mínima e determinística

**Files:**
- Modify: `viral_cutter.spec`
- Create: `packaging/pyinstaller_hooks/hook-mediapipe.py`
- Create: `tests/test_pyinstaller_spec.py`

- [ ] **Step 1: Write static spec tests**

```python
def test_spec_usa_launcher_e_manifesto(self):
    spec = Path("viral_cutter.spec").read_text(encoding="utf-8")
    self.assertIn('["launcher.py"]', spec)
    self.assertIn("packaging/manifest.json", spec.replace("\\", "/"))
    self.assertNotIn("collect_submodules(\"gradio\")", spec)
```

- [ ] **Step 2: Run and verify failure**

Run: `.venv311\Scripts\python.exe -m unittest tests.test_pyinstaller_spec -v`

- [ ] **Step 3: Make the spec consume the manifest**

Load `packaging/manifest.json`, fail if a required resource is missing, add only listed binaries/models and replace broad `collect_submodules` calls with documented hidden imports proven by build tests. Keep `console=False` for release and create a separate `ViralCutter-debug.spec` with `console=True` for diagnosis.

- [ ] **Step 4: Run static tests and a clean debug build**

Run: `.venv311\Scripts\python.exe -m PyInstaller ViralCutter-debug.spec --noconfirm --clean`

Expected: `dist\ViralCutter-debug\ViralCutter-debug.exe` exists.

- [ ] **Step 5: Commit**

```bash
git add viral_cutter.spec ViralCutter-debug.spec packaging/pyinstaller_hooks/hook-mediapipe.py tests/test_pyinstaller_spec.py
git commit -m "build: define deterministic pyinstaller bundle"
```

### Task 4: Validador do pacote em pasta limpa

**Files:**
- Modify: `validar_build.ps1`
- Create: `tests/test_build_validator.py`

**Interfaces:**
- Produces command: `validar_build.ps1 -DistPath <path> -TimeoutSeconds 90`

- [ ] **Step 1: Write validator contract test**

```python
def test_validador_nao_referencia_repositorio(self):
    texto = Path("validar_build.ps1").read_text(encoding="utf-8")
    self.assertIn("-DistPath", texto)
    self.assertNotIn("F:\\CORTE VIRAL", texto)
    self.assertNotIn("E:\\PROJETOS", texto)
```

- [ ] **Step 2: Run and verify failure**

Run: `.venv311\Scripts\python.exe -m unittest tests.test_build_validator -v`

- [ ] **Step 3: Implement isolated validation**

Copy the dist directory to a new `%TEMP%\ViralCutter-validation-<guid>`, clear inherited project-specific environment variables, start the executable, poll HTTP health for 90 seconds, validate bundled FFmpeg/FFprobe, run a 2-second synthetic-video smoke job through a dedicated `--self-test` command, then stop only the PID started by the script. Preserve logs on failure.

- [ ] **Step 4: Run debug validation and commit**

Run: `powershell -NoProfile -ExecutionPolicy Bypass -File validar_build.ps1 -DistPath dist\ViralCutter-debug -TimeoutSeconds 90`

```bash
git add validar_build.ps1 tests/test_build_validator.py
git commit -m "test: validate bundle outside repository"
```

### Task 5: Pipeline de release com gates

**Files:**
- Modify: `gerar_release.ps1`
- Modify: `gerar_exe_release.bat`
- Create: `tests/test_release_script.py`

- [ ] **Step 1: Write release-order test**

```python
def test_release_exige_validacoes_antes_do_pyinstaller(self):
    texto = Path("gerar_release.ps1").read_text(encoding="utf-8")
    self.assertLess(texto.index("diagnostico.py"), texto.index("PyInstaller"))
    self.assertLess(texto.index("unittest discover"), texto.index("PyInstaller"))
    self.assertIn("enquadramento-humano-seguro.md", texto)
    self.assertIn("runtime-estavel.md", texto)
```

- [ ] **Step 2: Run and verify failure**

Run: `.venv311\Scripts\python.exe -m unittest tests.test_release_script -v`

- [ ] **Step 3: Implement release gates**

The script must verify Python 3.11, clean index for tracked source files, both validation documents, complete unittest suite, diagnostics, resource hashes, clean PyInstaller build and isolated validation. It must not force-close arbitrary `ViralCutter.exe`; if an instance is running, print PID and stop with instructions.

- [ ] **Step 4: Generate versioned candidate archive**

After validation, create `release\ViralCutter-<version>-windows-x64-test.zip`, `SHA256SUMS.txt` and `build-report.json` containing commit SHA, dependency lock hash, test count and build timestamp.

- [ ] **Step 5: Run script tests and commit**

```bash
git add gerar_release.ps1 gerar_exe_release.bat tests/test_release_script.py
git commit -m "build: gate and report Windows release"
```

### Task 6: Atalho e primeira execução

**Files:**
- Create: `packaging/criar_atalho.ps1`
- Create: `tests/test_shortcut_script.py`
- Modify: `GUIA_RAPIDO.md`

- [ ] **Step 1: Write shortcut safety test**

```python
def test_atalho_aponta_para_exe_e_nao_python(self):
    texto = Path("packaging/criar_atalho.ps1").read_text(encoding="utf-8")
    self.assertIn("ViralCutter.exe", texto)
    self.assertNotIn("python.exe", texto.lower())
    self.assertNotIn("F:\\", texto)
```

- [ ] **Step 2: Run and verify failure**

Run: `.venv311\Scripts\python.exe -m unittest tests.test_shortcut_script -v`

- [ ] **Step 3: Implement shortcut creation**

Accept `-InstallDir`, validate the executable with `Test-Path`, create/update `Viral Cutter.lnk` on the current user's Desktop using `WScript.Shell`, set working directory to the install directory and never embed the build-machine path.

- [ ] **Step 4: Test in a temporary install directory and commit**

```bash
git add packaging/criar_atalho.ps1 tests/test_shortcut_script.py GUIA_RAPIDO.md
git commit -m "feat: create portable desktop shortcut"
```

### Task 7: Candidato de teste e aprovação final

**Files:**
- Create: `docs/validation/pacote-windows.md`

- [ ] **Step 1: Run complete release pipeline**

Run: `powershell -NoProfile -ExecutionPolicy Bypass -File gerar_release.ps1 -Channel test`

Expected: versioned ZIP, SHA256 file and build report.

- [ ] **Step 2: Validate clean-session workflow**

Install/extract into a new folder, create shortcut, open twice, confirm one healthy instance, process a real short video, close, reopen and verify logs/checkpoints persist in `%LOCALAPPDATA%\ViralCutter`.

- [ ] **Step 3: Record evidence**

Document package hash, Windows version, test count, startup time, output video validation, antivirus scan result and known limitations in `docs/validation/pacote-windows.md`.

- [ ] **Step 4: Obtain user approval**

Deliver the test candidate only. Do not rename it as final or replace the existing desktop shortcut until the user approves the real-video result.

- [ ] **Step 5: Commit validation record**

```bash
git add docs/validation/pacote-windows.md
git commit -m "docs: validate Windows test candidate"
```
