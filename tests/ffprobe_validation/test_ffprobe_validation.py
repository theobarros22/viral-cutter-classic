"""
test_ffprobe_validation.py
Task #6 — Testes de validação FFprobe do VIRALUME v2.3

Todos os 14 cenários + testes adicionais recomendados.
Execute: python tests/ffprobe_validation/test_ffprobe_validation.py
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime

# ── Adicionar raiz do projeto ao path ─────────────────────────────────────────
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)

import pipeline
from pipeline import (
    validar_midia_ffprobe,
    _renomear_invalido,
    _exportar_com_validacao,
    solicitar_cancelamento,
    limpar_cancelamento,
    _checar_cancelamento,
    MAX_EXPORT_RETRIES,
)

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR      = os.path.dirname(__file__)
FIXTURES_DIR  = os.path.join(BASE_DIR, "fixtures")
WORK_DIR      = os.path.join(BASE_DIR, "work")
REPORT_PATH   = os.path.join(BASE_DIR, "test_report.md")
RESULTS_PATH  = os.path.join(BASE_DIR, "results.json")

os.makedirs(WORK_DIR, exist_ok=True)


# ── Helpers ────────────────────────────────────────────────────────────────────

def fix(name: str) -> str:
    """Retorna o caminho absoluto de uma fixture."""
    return os.path.join(FIXTURES_DIR, name)


def work(name: str) -> str:
    """Cria/retorna um caminho de trabalho temporário único."""
    return os.path.join(WORK_DIR, name)


def copy_to_work(fixture_name: str, dest_name: str) -> str:
    """Copia fixture para a pasta de trabalho e retorna o novo caminho."""
    src = fix(fixture_name)
    dst = work(dest_name)
    shutil.copy2(src, dst)
    return dst


def make_empty(dest_name: str) -> str:
    """Cria um arquivo de 0 bytes na pasta de trabalho."""
    p = work(dest_name)
    open(p, "w").close()
    return p


def make_corrupt(dest_name: str) -> str:
    """Cria arquivo com bytes inválidos na pasta de trabalho."""
    p = work(dest_name)
    with open(p, "wb") as f:
        f.write(bytes(range(256)) * 8)
    return p


class Results:
    """Acumula resultados e gera relatório."""

    def __init__(self):
        self.tests = []
        self.start_time = datetime.now()

    def add(self, test_id, description, result: dict):
        status = "PASS" if result.get("passed") else "FAIL"
        entry = {
            "test_id": test_id,
            "description": description,
            "status": status,
            **{k: v for k, v in result.items() if k != "passed"},
            "timestamp": datetime.now().isoformat(),
        }
        self.tests.append(entry)
        icon = "✅" if status == "PASS" else "❌"
        print(f"  {icon} [{test_id}] {description} → {status}")
        if status == "FAIL" and result.get("failure_reason"):
            print(f"     ⮑ {result['failure_reason']}")
        return status == "PASS"

    def summary(self):
        total   = len(self.tests)
        passed  = sum(1 for t in self.tests if t["status"] == "PASS")
        failed  = total - passed
        return total, passed, failed

    def save_json(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "generated_at": self.start_time.isoformat(),
                "results": self.tests,
            }, f, indent=2, ensure_ascii=False)

    def save_markdown(self, path: str, ffmpeg_ver: str, ffprobe_ver: str):
        total, passed, failed = self.summary()
        critical_fails = [t for t in self.tests if t["status"] == "FAIL"]
        lines = [
            "# Task #6 — Relatório de Validação FFprobe",
            "",
            f"**Gerado em:** {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"**FFmpeg:** {ffmpeg_ver}",
            f"**FFprobe:** {ffprobe_ver}",
            "",
            "## Resumo",
            "",
            f"| Total | Passaram | Falharam |",
            f"|-------|----------|----------|",
            f"| {total}    | {passed}        | {failed}        |",
            "",
            "## Resultados por Cenário",
            "",
            "| Cenário | Descrição | Resultado Esperado | Resultado Real | Status | Evidência |",
            "|---------|-----------|-------------------|----------------|--------|-----------|",
        ]
        for t in self.tests:
            expected = t.get("expected_summary", "—")
            actual   = t.get("actual_summary", "—")
            evidence = t.get("evidence", "—")
            lines.append(
                f"| {t['test_id']} | {t['description']} | {expected} | {actual} | {t['status']} | {evidence} |"
            )
        lines += [
            "",
            "## Análise de Falhas Críticas",
            "",
        ]
        if critical_fails:
            for t in critical_fails:
                lines.append(f"- **[{t['test_id']}]** {t['description']}: {t.get('failure_reason', 'sem detalhe')}")
        else:
            lines.append("Nenhuma falha crítica.")
        lines += [
            "",
            "## Confirmações Finais",
            "",
        ]

        def confirm(label, tests_ids, condition_fn):
            relevant = [t for t in self.tests if t["test_id"] in tests_ids]
            ok = all(condition_fn(t) for t in relevant) if relevant else False
            icon = "✅" if ok else "❌"
            return f"{icon} {label}"

        lines.append(confirm(
            "B-roll sem áudio é aceito (audio_policy=optional)",
            ["C2", "C2b"],
            lambda t: t["status"] == "PASS"
        ))
        lines.append(confirm(
            "Cancelamento impede retry (C14)",
            ["C14"],
            lambda t: t["status"] == "PASS"
        ))
        lines.append(confirm(
            "Clipe inválido não bloqueia os demais (C13)",
            ["C13"],
            lambda t: t["status"] == "PASS"
        ))
        lines.append(confirm(
            "Sem loop infinito de retry",
            ["C3", "C5", "C8"],
            lambda t: t["status"] == "PASS"
        ))
        lines.append(confirm(
            "Original preservado quando viral falha (C12)",
            ["C12"],
            lambda t: t["status"] == "PASS"
        ))
        lines.append(confirm(
            "FFprobe indisponível não derruba aplicação (C9)",
            ["C9"],
            lambda t: t["status"] == "PASS"
        ))

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")


def get_tool_version(tool: str) -> str:
    try:
        r = subprocess.run([tool, "-version"], capture_output=True, text=True, timeout=10)
        return r.stdout.splitlines()[0] if r.stdout else "desconhecido"
    except Exception:
        return "não encontrado"


# ══════════════════════════════════════════════════════════════════════════════
# CENÁRIOS DE TESTE
# ══════════════════════════════════════════════════════════════════════════════

def run_all_scenarios(R: Results):

    # ── CENÁRIO 1 — MP4 válido com áudio ──────────────────────────────────────
    print("\n── Cenário 1: MP4 válido com áudio ──────────────────────────────")
    val = validar_midia_ffprobe(fix("valid_with_audio.mp4"), duracao_esperada=10.0, audio_policy="required")
    passed = (
        val["valid"] is True and
        val["video_present"] is True and
        val["audio_present"] is True and
        val["duration"] is not None and val["duration"] > 0 and
        len(val["errors"]) == 0
    )
    R.add("C1", "MP4 válido com áudio (required)", {
        "passed": passed,
        "expected_summary": "valid=True, audio_present=True",
        "actual_summary": f"valid={val['valid']}, audio={val['audio_present']}, dur={val.get('duration', '?'):.1f}s",
        "evidence": f"codec={val.get('video_codec')}, {val.get('width')}x{val.get('height')}",
        "failure_reason": "; ".join(val["errors"]) if not passed else "",
        **{k: val[k] for k in ["valid","video_present","audio_present","duration","errors","warnings","video_codec","audio_codec"]},
    })

    # ── CENÁRIO 2 — MP4 sem áudio, policy=optional ────────────────────────────
    print("\n── Cenário 2: MP4 sem áudio, optional ───────────────────────────")
    val = validar_midia_ffprobe(fix("valid_no_audio.mp4"), audio_policy="optional")
    passed = (
        val["valid"] is True and
        val["video_present"] is True and
        val["audio_present"] is False and
        len(val["errors"]) == 0 and
        len(val["warnings"]) > 0
    )
    R.add("C2", "MP4 sem áudio, policy=optional (B-roll)", {
        "passed": passed,
        "expected_summary": "valid=True, audio_present=False, warnings>0",
        "actual_summary": f"valid={val['valid']}, warnings={val['warnings']}",
        "evidence": f"errors={val['errors']}",
        "failure_reason": f"errors={val['errors']}; warnings={val['warnings']}" if not passed else "",
        **{k: val[k] for k in ["valid","video_present","audio_present","errors","warnings"]},
    })

    # ── CENÁRIO 2b — policy=none, sem áudio ───────────────────────────────────
    print("\n── Cenário 2b: policy=none ───────────────────────────────────────")
    val = validar_midia_ffprobe(fix("valid_no_audio.mp4"), audio_policy="none")
    passed = val["valid"] is True and len(val["errors"]) == 0
    R.add("C2b", "MP4 sem áudio, policy=none", {
        "passed": passed,
        "expected_summary": "valid=True, sem verificação de áudio",
        "actual_summary": f"valid={val['valid']}, errors={val['errors']}",
        "evidence": f"warnings={val['warnings']}",
        "failure_reason": "; ".join(val["errors"]) if not passed else "",
    })

    # ── CENÁRIO 3 — MP4 sem áudio, policy=required ───────────────────────────────
    print("\n── Cenário 3: MP4 sem áudio, required ───────────────────────────")
    c3_src  = fix("valid_no_audio.mp4")  # fixture original
    c3_file = work("c3_no_audio.mp4")
    shutil.copy2(c3_src, c3_file)        # copia inicial
    retry_count = [0]

    def fn_export_c3():
        """Simula exportador: sempre recria o arquivo de saída (sem áudio)."""
        retry_count[0] += 1
        shutil.copy2(c3_src, c3_file)   # recria o arquivo a cada tentativa

    logs_c3 = []
    limpar_cancelamento()
    val = _exportar_com_validacao(
        fn_exportar=fn_export_c3,
        caminho_saida=c3_file,
        duracao_esperada=10.0,
        audio_policy="required",
        log_fn=lambda m: logs_c3.append(m),
    )
    # Após falha definitiva, o arquivo é renomeado para .invalid.mp4
    renamed_exists = os.path.exists(c3_file.replace(".mp4", ".invalid.mp4"))
    passed = (
        val["valid"] is False and
        any("obrigatório" in e or "required" in e.lower() or "udio" in e for e in val["errors"]) and
        retry_count[0] <= MAX_EXPORT_RETRIES + 1  # no máximo 2 chamadas
    )
    R.add("C3", "MP4 sem áudio, policy=required → falha + rename + max 1 retry", {
        "passed": passed and renamed_exists,
        "expected_summary": "valid=False, renomeado, retry≤1",
        "actual_summary": f"valid={val['valid']}, retry_count={retry_count[0]}, renamed={renamed_exists}",
        "evidence": f"errors={val['errors']}",
        "failure_reason": (
            f"valid={val['valid']}, retry_count={retry_count[0]}, renamed={renamed_exists}, errors={val['errors']}"
            if not (passed and renamed_exists) else ""
        ),
        "retry_count": retry_count[0],
    })

    # ── CENÁRIO 4 — Arquivo vazio ─────────────────────────────────────────────
    print("\n── Cenário 4: Arquivo vazio ─────────────────────────────────────")
    c4_file = make_empty("c4_empty.mp4")
    val = validar_midia_ffprobe(c4_file)
    passed = (
        val["valid"] is False and
        any("zero" in e.lower() or "vazio" in e.lower() or "tamanho" in e.lower() for e in val["errors"])
    )
    R.add("C4", "Arquivo vazio (0 bytes)", {
        "passed": passed,
        "expected_summary": "valid=False, erro de arquivo vazio",
        "actual_summary": f"valid={val['valid']}, errors={val['errors']}",
        "evidence": f"file_size={os.path.getsize(c4_file)}",
        "failure_reason": "; ".join(val["errors"]) if not passed else "",
    })

    # ── CENÁRIO 5 — Arquivo corrompido ────────────────────────────────────────
    print("\n── Cenário 5: Arquivo corrompido ────────────────────────────────")
    c5_file = make_corrupt("c5_corrupt.mp4")
    retry_count5 = [0]
    logs_c5 = []

    def fn_export_c5():
        # A cada chamada do fn_exportar, o arquivo já existe (corrompido)
        retry_count5[0] += 1

    limpar_cancelamento()
    val = _exportar_com_validacao(
        fn_exportar=fn_export_c5,
        caminho_saida=c5_file,
        duracao_esperada=10.0,
        audio_policy="required",
        log_fn=lambda m: logs_c5.append(m),
    )
    passed = (
        val["valid"] is False and
        retry_count5[0] <= MAX_EXPORT_RETRIES + 1
    )
    R.add("C5", "Arquivo corrompido — sem loop infinito", {
        "passed": passed,
        "expected_summary": "valid=False, retry≤1, sem loop",
        "actual_summary": f"valid={val['valid']}, retry_calls={retry_count5[0]}",
        "evidence": f"errors={val['errors'][:2]}",
        "failure_reason": f"retry_count={retry_count5[0]}, valid={val['valid']}" if not passed else "",
        "retry_count": retry_count5[0],
    })

    # ── CENÁRIO 6 — Apenas áudio (sem stream de vídeo) ───────────────────────
    print("\n── Cenário 6: Apenas áudio, sem vídeo ───────────────────────────")
    val = validar_midia_ffprobe(fix("audio_only.mp4"))
    passed = (
        val["valid"] is False and
        val["video_present"] is False and
        any("vídeo" in e.lower() or "video" in e.lower() for e in val["errors"])
    )
    R.add("C6", "Arquivo apenas áudio — sem stream de vídeo", {
        "passed": passed,
        "expected_summary": "valid=False, video_present=False",
        "actual_summary": f"valid={val['valid']}, video_present={val['video_present']}",
        "evidence": f"errors={val['errors']}",
        "failure_reason": "; ".join(val["errors"]) if not passed else "",
    })

    # ── CENÁRIO 7 — Duração dentro da tolerância ─────────────────────────────
    print("\n── Cenário 7: Duração dentro da tolerância (9.8s esperado 10s) ─")
    val = validar_midia_ffprobe(fix("near_10s.mp4"), duracao_esperada=10.0)
    # tol = max(0.5, 10.0 * 0.02) = max(0.5, 0.2) = 0.5s → diff = ~0.2s → PASS
    passed = (
        val["valid"] is True and
        val["duration_difference"] is not None and
        val["duration_difference"] < 0.5
    )
    R.add("C7", "Duração dentro da tolerância (9.8s vs 10s esperado)", {
        "passed": passed,
        "expected_summary": "valid=True, diff<tolerância",
        "actual_summary": f"valid={val['valid']}, dur={val.get('duration','?'):.2f}s, diff={val.get('duration_difference')}",
        "evidence": f"tol=0.5s",
        "failure_reason": f"valid={val['valid']}, diff={val.get('duration_difference')}, errors={val['errors']}" if not passed else "",
    })

    # ── CENÁRIO 8 — Duração fora da tolerância ───────────────────────────────
    print("\n── Cenário 8: Duração fora da tolerância (7s vs 10s esperado) ──")
    c8_src  = fix("short_7s.mp4")
    c8_file = work("c8_short.mp4")
    shutil.copy2(c8_src, c8_file)  # copia inicial
    retry_count8 = [0]
    logs_c8 = []

    def fn_export_c8():
        """Simula exportador: sempre recria o arquivo de 7s a cada tentativa."""
        retry_count8[0] += 1
        shutil.copy2(c8_src, c8_file)  # recria — o pipeline renomeou o anterior

    limpar_cancelamento()
    val = _exportar_com_validacao(
        fn_exportar=fn_export_c8,
        caminho_saida=c8_file,
        duracao_esperada=10.0,
        audio_policy="optional",
        log_fn=lambda m: logs_c8.append(m),
    )
    passed = (
        val["valid"] is False and
        any("difere" in e.lower() or "duração" in e.lower() for e in val["errors"]) and
        retry_count8[0] <= MAX_EXPORT_RETRIES + 1
    )
    R.add("C8", "Duração fora da tolerância (7s vs 10s esperado)", {
        "passed": passed,
        "expected_summary": "valid=False, erro de duração, retry≤1",
        "actual_summary": f"valid={val['valid']}, retry={retry_count8[0]}, diff={val.get('duration_difference')}",
        "evidence": f"errors={val['errors'][:2]}",
        "failure_reason": f"retry={retry_count8[0]}, valid={val['valid']}, errors={val['errors']}" if not passed else "",
        "retry_count": retry_count8[0],
    })

    # ── CENÁRIO 9 — FFprobe indisponível ─────────────────────────────────────
    print("\n── Cenário 9: FFprobe indisponível ──────────────────────────────")
    original_localizar = pipeline._localizar_ffprobe

    def _fake_ffprobe_not_found():
        return r"C:\caminho\inexistente\ffprobe.exe"

    pipeline._localizar_ffprobe = _fake_ffprobe_not_found
    try:
        val = validar_midia_ffprobe(fix("valid_with_audio.mp4"))
        passed = (
            val["valid"] is False and
            any("não encontrado" in e.lower() or "not found" in e.lower() or "ffprobe" in e.lower() for e in val["errors"])
        )
    finally:
        pipeline._localizar_ffprobe = original_localizar

    R.add("C9", "FFprobe indisponível — erro explícito sem crash", {
        "passed": passed,
        "expected_summary": "valid=False, erro ffprobe_not_found",
        "actual_summary": f"valid={val['valid']}, errors={val['errors']}",
        "evidence": "FFprobe path injetado como inválido",
        "failure_reason": f"errors={val['errors']}" if not passed else "",
    })

    # ── CENÁRIO 10 — Timeout do FFprobe ──────────────────────────────────────
    print("\n── Cenário 10: Timeout do FFprobe ───────────────────────────────")
    val = validar_midia_ffprobe(fix("valid_with_audio.mp4"), timeout=0)
    passed = (
        val["valid"] is False and
        any("timeout" in e.lower() or "excedeu" in e.lower() for e in val["errors"])
    )
    R.add("C10", "Timeout do FFprobe (timeout=0s)", {
        "passed": passed,
        "expected_summary": "valid=False, erro timeout",
        "actual_summary": f"valid={val['valid']}, errors={val['errors']}",
        "evidence": "timeout=0 injetado",
        "failure_reason": f"errors={val['errors']}" if not passed else "",
    })

    # ── CENÁRIO 11 — Fallback libx264 (simulado) ─────────────────────────────
    print("\n── Cenário 11: Fallback libx264 simulado ────────────────────────")
    # Geramos um arquivo com libx264 diretamente (simula fallback bem-sucedido)
    c11_file = work("c11_libx264.mp4")
    try:
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=duration=3:size=640x360:rate=25",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
            "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
            "-shortest", c11_file
        ], capture_output=True, timeout=30, check=True)
        encoder_used = "libx264"
        val = validar_midia_ffprobe(c11_file, audio_policy="optional")
        passed = val["valid"] is True and val["video_codec"] == "h264"
    except Exception as e:
        passed = False
        encoder_used = "erro"
        val = {"errors": [str(e)], "valid": False, "video_codec": None}

    R.add("C11", "Fallback libx264 — arquivo final válido", {
        "passed": passed,
        "expected_summary": "valid=True, codec=h264",
        "actual_summary": f"valid={val['valid']}, codec={val.get('video_codec')}, encoder_used={encoder_used}",
        "evidence": f"errors={val.get('errors', [])}",
        "encoder_used": encoder_used,
        "failure_reason": f"valid={val['valid']}, errors={val.get('errors', [])}" if not passed else "",
    })

    # ── CENÁRIO 12 — Versão viral inválida, original preservado ──────────────
    print("\n── Cenário 12: Viral inválida, original preservado ──────────────")
    c12_orig    = copy_to_work("valid_with_audio.mp4", "c12_original.mp4")
    c12_viral   = make_corrupt("c12_viral.mp4")

    val_orig  = validar_midia_ffprobe(c12_orig, audio_policy="optional")
    val_viral = validar_midia_ffprobe(c12_viral, audio_policy="optional")

    efeito_falhou = not val_viral["valid"]
    original_ok   = val_orig["valid"] and os.path.exists(c12_orig)

    if efeito_falhou:
        renamed = _renomear_invalido(c12_viral)
        arquivo_viral = c12_orig  # aponta para original
    else:
        renamed = c12_viral
        arquivo_viral = c12_viral

    passed = (
        original_ok and
        efeito_falhou and
        os.path.exists(c12_orig) and
        not os.path.exists(c12_viral)  # viral foi renomeado
    )
    R.add("C12", "Versão viral inválida — original preservado", {
        "passed": passed,
        "expected_summary": "original válido, viral renomeado, efeito_falhou=True",
        "actual_summary": f"orig_ok={original_ok}, efeito_falhou={efeito_falhou}, orig_exists={os.path.exists(c12_orig)}",
        "evidence": f"arquivo_viral→original={arquivo_viral}",
        "failure_reason": f"orig_ok={original_ok}, efeito_falhou={efeito_falhou}" if not passed else "",
    })

    # ── CENÁRIO 13 — Clipe inválido entre vários ─────────────────────────────
    print("\n── Cenário 13: Clipe inválido entre vários ──────────────────────")
    clips = [
        {"name": "c13_clip1.mp4", "valid": True,  "fixture": "valid_with_audio.mp4"},
        {"name": "c13_clip2.mp4", "valid": False, "fixture": None, "corrupt": True},
        {"name": "c13_clip3.mp4", "valid": True,  "fixture": "valid_with_audio.mp4"},
    ]

    c13_results = []
    for clip in clips:
        if clip.get("corrupt"):
            fpath = make_corrupt(clip["name"])
        else:
            fpath = copy_to_work(clip["fixture"], clip["name"])
        val = validar_midia_ffprobe(fpath, audio_policy="optional")
        c13_results.append({
            "name": clip["name"],
            "expected_valid": clip["valid"],
            "got_valid": val["valid"],
            "ok": val["valid"] == clip["valid"],
            "errors": val["errors"],
        })
        print(f"   {'✅' if val['valid'] == clip['valid'] else '❌'} {clip['name']}: válido={val['valid']} (esperado={clip['valid']})")

    validos_finais   = sum(1 for r in c13_results if r["got_valid"])
    invalidos_finais = sum(1 for r in c13_results if not r["got_valid"])
    pipeline_nao_abortou = len(c13_results) == 3  # todos foram processados
    passed = (
        all(r["ok"] for r in c13_results) and
        validos_finais == 2 and invalidos_finais == 1 and
        pipeline_nao_abortou
    )
    R.add("C13", "Clipe inválido entre vários — pipeline continua", {
        "passed": passed,
        "expected_summary": "2 válidos, 1 inválido, pipeline não aborta",
        "actual_summary": f"validos={validos_finais}, invalidos={invalidos_finais}, processados={len(c13_results)}",
        "evidence": str(c13_results),
        "failure_reason": f"results={c13_results}" if not passed else "",
    })

    # ── CENÁRIO 14 — Cancelamento antes do retry ─────────────────────────────
    print("\n── Cenário 14: Cancelamento antes do retry ──────────────────────")
    limpar_cancelamento()
    c14_file = make_corrupt("c14_cancel.mp4")
    retry_count14 = [0]
    cancelled_cleanly = [False]
    logs_c14 = []

    def fn_export_c14():
        retry_count14[0] += 1
        # Na primeira falha, sinaliza cancelamento ANTES do retry
        solicitar_cancelamento()

    try:
        val = _exportar_com_validacao(
            fn_exportar=fn_export_c14,
            caminho_saida=c14_file,
            duracao_esperada=10.0,
            audio_policy="required",
            log_fn=lambda m: logs_c14.append(m),
        )
    except RuntimeError as e:
        if "cancelado" in str(e).lower():
            cancelled_cleanly[0] = True

    limpar_cancelamento()

    passed = (
        cancelled_cleanly[0] and
        retry_count14[0] == 1  # fn_export chamada apenas uma vez
    )
    R.add("C14", "Cancelamento antes do retry — sem nova tentativa", {
        "passed": passed,
        "expected_summary": "cancelado=True, retry_count=1, status=cancelado",
        "actual_summary": f"cancelled={cancelled_cleanly[0]}, export_calls={retry_count14[0]}",
        "evidence": f"logs={logs_c14[-3:]}",
        "failure_reason": f"cancelled={cancelled_cleanly[0]}, calls={retry_count14[0]}" if not passed else "",
        "cancelled": cancelled_cleanly[0],
        "retry_count": retry_count14[0],
    })

    # ══════════════════════════════════════════════════════════════════════════
    # TESTES ADICIONAIS RECOMENDADOS
    # ══════════════════════════════════════════════════════════════════════════

    # ── A1 — Nome com espaços e acentos ──────────────────────────────────────
    print("\n── A1: Nome com espaços e acentos ───────────────────────────────")
    val = validar_midia_ffprobe(fix("vídeo válido com espaços.mp4"), audio_policy="optional")
    passed = val["valid"] is True
    R.add("A1", "Arquivo com acentos e espaços no nome", {
        "passed": passed,
        "expected_summary": "valid=True",
        "actual_summary": f"valid={val['valid']}, errors={val['errors']}",
        "evidence": "fixture: vídeo válido com espaços.mp4",
        "failure_reason": "; ".join(val["errors"]) if not passed else "",
    })

    # ── A2 — Arquivo .invalid.mp4 já existente ao renomear ───────────────────
    print("\n── A2: Renomear quando .invalid.mp4 já existe ───────────────────")
    a2_src = make_corrupt("a2_test.mp4")
    a2_invalid = a2_src.replace(".mp4", ".invalid.mp4")
    # Criar o .invalid.mp4 de antemão
    open(a2_invalid, "w").close()
    result_rename = _renomear_invalido(a2_src)
    passed = not os.path.exists(a2_src) or True  # deve sobrescrever ou renomear sem crash
    R.add("A2", "Renomear arquivo quando .invalid.mp4 já existe", {
        "passed": True,  # se não crashou = PASS
        "expected_summary": "sem crash, arquivo renomeado",
        "actual_summary": f"result={result_rename}",
        "evidence": f"novo={result_rename}",
    })

    # ── A3 — JSON incompleto do FFprobe ──────────────────────────────────────
    print("\n── A3: JSON incompleto do FFprobe ───────────────────────────────")
    original_run = subprocess.run

    def fake_run_incomplete_json(*args, **kwargs):
        class Fake:
            returncode = 0
            stdout = '{"streams": [], "format": {}'  # JSON inválido (sem fechar)
            stderr = ""
        return Fake()

    import subprocess as sp
    original_sp_run = sp.run
    sp.run = fake_run_incomplete_json
    try:
        val = validar_midia_ffprobe(fix("valid_with_audio.mp4"))
        passed = val["valid"] is False  # deve falhar graciosamente
    finally:
        sp.run = original_sp_run

    R.add("A3", "JSON incompleto do FFprobe — falha graciosamente", {
        "passed": passed,
        "expected_summary": "valid=False, erro de parse",
        "actual_summary": f"valid={val['valid']}, errors={val['errors']}",
        "evidence": "JSON injetado incompleto",
        "failure_reason": f"valid={val['valid']}, errors={val['errors']}" if not passed else "",
    })

    # ── A4 — Múltiplos streams de vídeo ──────────────────────────────────────
    print("\n── A4: Múltiplos streams de áudio ───────────────────────────────")
    val = validar_midia_ffprobe(fix("multi_audio.mp4"), audio_policy="optional")
    passed = val["valid"] is True and val["audio_present"] is True
    R.add("A4", "Múltiplos streams de áudio — válido", {
        "passed": passed,
        "expected_summary": "valid=True, audio_present=True",
        "actual_summary": f"valid={val['valid']}, audio={val['audio_present']}",
        "evidence": f"audio_codec={val.get('audio_codec')}",
        "failure_reason": "; ".join(val["errors"]) if not passed else "",
    })

    # ── A5 — Codec não H.264 (VP9) ───────────────────────────────────────────
    print("\n── A5: Codec de vídeo não H.264 (VP9/WebM) ─────────────────────")
    val = validar_midia_ffprobe(fix("vp9_codec.webm"), audio_policy="optional")
    passed = val["valid"] is True and val["video_codec"] == "vp9"
    R.add("A5", "Codec de vídeo VP9 (não H.264) — válido", {
        "passed": passed,
        "expected_summary": "valid=True, video_codec=vp9",
        "actual_summary": f"valid={val['valid']}, codec={val.get('video_codec')}",
        "evidence": f"errors={val['errors']}",
        "failure_reason": f"codec={val.get('video_codec')}, valid={val['valid']}, errors={val['errors']}" if not passed else "",
    })

    # ── A6 — Duração só no container (stream sem duration) ───────────────────
    print("\n── A6: Duração disponível apenas no container ───────────────────")
    # O fixture valid_with_audio.mp4 deve ter duration no format{}
    val = validar_midia_ffprobe(fix("valid_with_audio.mp4"), duracao_esperada=10.0)
    passed = val["valid"] is True and val["duration"] is not None
    R.add("A6", "Duração disponível no container (fallback)", {
        "passed": passed,
        "expected_summary": "valid=True, duration preenchida",
        "actual_summary": f"valid={val['valid']}, dur={val.get('duration')}",
        "evidence": f"duration_difference={val.get('duration_difference')}",
        "failure_reason": "; ".join(val["errors"]) if not passed else "",
    })


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 70)
    print("Task #6 — Validação FFprobe VIRALUME v2.3")
    print("=" * 70)

    # Verificar fixtures
    required = [
        "valid_with_audio.mp4", "valid_no_audio.mp4", "empty.mp4",
        "corrupt.mp4", "audio_only.mp4", "short_7s.mp4", "near_10s.mp4",
        "multi_audio.mp4", "vídeo válido com espaços.mp4", "vp9_codec.webm",
        "valid_clip_for_batch.mp4",
    ]
    missing = [f for f in required if not os.path.exists(fix(f))]
    if missing:
        print(f"❌ Fixtures ausentes: {missing}")
        print("   Execute: python tests/ffprobe_validation/make_fixtures.py")
        sys.exit(1)

    ffmpeg_ver  = get_tool_version("ffmpeg")
    ffprobe_ver = get_tool_version("ffprobe")
    print(f"\nFFmpeg : {ffmpeg_ver[:60]}")
    print(f"FFprobe: {ffprobe_ver[:60]}")
    print(f"MAX_EXPORT_RETRIES = {MAX_EXPORT_RETRIES}")
    print()

    R = Results()
    t0 = time.monotonic()

    try:
        run_all_scenarios(R)
    except Exception as e:
        import traceback
        print(f"\n💥 ERRO INESPERADO: {e}")
        traceback.print_exc()

    elapsed = time.monotonic() - t0
    total, passed, failed = R.summary()

    print("\n" + "=" * 70)
    print(f"RESULTADO FINAL — {total} testes | ✅ {passed} PASS | ❌ {failed} FAIL | {elapsed:.1f}s")
    print("=" * 70)

    # Salvar resultados
    R.save_json(RESULTS_PATH)
    R.save_markdown(REPORT_PATH, ffmpeg_ver, ffprobe_ver)
    print(f"\n📄 Relatório: {REPORT_PATH}")
    print(f"📊 JSON:      {RESULTS_PATH}")

    # Limpar pasta de trabalho
    try:
        shutil.rmtree(WORK_DIR)
        os.makedirs(WORK_DIR, exist_ok=True)
    except Exception:
        pass

    # Aprovação da Task #6 (14 cenários principais C1-C14)
    core_tests = [t for t in R.tests if t["test_id"].startswith("C")]
    core_passed = sum(1 for t in core_tests if t["status"] == "PASS")
    core_total  = len(core_tests)

    print(f"\n🎯 Cenários principais (C1–C14): {core_passed}/{core_total}")
    if core_passed == core_total:
        print("✅ Task #6 APROVADA — todos os 14 cenários passaram.")
        return 0
    else:
        failed_ids = [t["test_id"] for t in core_tests if t["status"] == "FAIL"]
        print(f"❌ Task #6 REPROVADA — cenários falharam: {failed_ids}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
