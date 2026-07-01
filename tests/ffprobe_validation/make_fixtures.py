"""
make_fixtures.py
Gera todos os arquivos de fixture controlados para a Task #6.
Executa via: python tests/ffprobe_validation/make_fixtures.py
"""

import os
import subprocess
import sys

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
os.makedirs(FIXTURES_DIR, exist_ok=True)


def run(cmd, check=True, timeout=60):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if check and r.returncode != 0:
        raise RuntimeError(f"CMD failed: {' '.join(cmd)}\n{r.stderr[:400]}")
    return r


def path(name):
    return os.path.join(FIXTURES_DIR, name)


def make_all():
    ff = "ffmpeg"

    # ── F1: MP4 válido com áudio (10s, 1280x720, aac) ─────────────────────────
    f1 = path("valid_with_audio.mp4")
    if not os.path.exists(f1):
        run([ff, "-y",
             "-f", "lavfi", "-i", "testsrc=duration=10:size=1280x720:rate=25",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=10",
             "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
             "-shortest", f1])
        print(f"[OK] {os.path.basename(f1)}")

    # ── F2: MP4 válido sem áudio (10s) ────────────────────────────────────────
    f2 = path("valid_no_audio.mp4")
    if not os.path.exists(f2):
        run([ff, "-y",
             "-f", "lavfi", "-i", "testsrc=duration=10:size=1280x720:rate=25",
             "-c:v", "libx264", "-preset", "ultrafast",
             "-an", f2])
        print(f"[OK] {os.path.basename(f2)}")

    # ── F3: Arquivo vazio (0 bytes) ───────────────────────────────────────────
    f3 = path("empty.mp4")
    open(f3, "w").close()
    print(f"[OK] {os.path.basename(f3)}")

    # ── F4: Arquivo corrompido (primeiros 2 KB de bytes aleatórios) ───────────
    f4 = path("corrupt.mp4")
    with open(f4, "wb") as fh:
        fh.write(bytes(range(256)) * 8)  # 2 KB de lixo
    print(f"[OK] {os.path.basename(f4)}")

    # ── F5: Só áudio (sem stream de vídeo) ───────────────────────────────────
    f5 = path("audio_only.mp4")
    if not os.path.exists(f5):
        run([ff, "-y",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=10",
             "-c:a", "aac", f5])
        print(f"[OK] {os.path.basename(f5)}")

    # ── F6: Vídeo de 10s (para teste de duração dentro da tolerância) ─────────
    # Já coberto por F1

    # ── F7: Vídeo de 7s (para teste de duração fora da tolerância) ────────────
    f7 = path("short_7s.mp4")
    if not os.path.exists(f7):
        run([ff, "-y",
             "-f", "lavfi", "-i", "testsrc=duration=7:size=1280x720:rate=25",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=7",
             "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
             "-shortest", f7])
        print(f"[OK] {os.path.basename(f7)}")

    # ── F8: Vídeo 9.8s (duração dentro da tolerância de 10s esperado) ─────────
    f8 = path("near_10s.mp4")
    if not os.path.exists(f8):
        run([ff, "-y",
             "-f", "lavfi", "-i", "testsrc=duration=9.8:size=1280x720:rate=25",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=9.8",
             "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
             "-shortest", f8])
        print(f"[OK] {os.path.basename(f8)}")

    # ── F9: Múltiplos streams de áudio ────────────────────────────────────────
    f9 = path("multi_audio.mp4")
    if not os.path.exists(f9):
        run([ff, "-y",
             "-f", "lavfi", "-i", "testsrc=duration=5:size=640x360:rate=25",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=5",
             "-f", "lavfi", "-i", "sine=frequency=880:duration=5",
             "-c:v", "libx264", "-preset", "ultrafast",
             "-c:a:0", "aac", "-c:a:1", "aac",
             f9])
        print(f"[OK] {os.path.basename(f9)}")

    # ── F10: Nome com espaços e acentos ───────────────────────────────────────
    f10 = path("vídeo válido com espaços.mp4")
    if not os.path.exists(f10):
        run([ff, "-y",
             "-f", "lavfi", "-i", "testsrc=duration=5:size=640x360:rate=25",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=5",
             "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
             "-shortest", f10])
        print(f"[OK] {os.path.basename(f10)}")

    # ── F11: Codec de vídeo não H.264 (vp9) ──────────────────────────────────
    f11 = path("vp9_codec.webm")
    if not os.path.exists(f11):
        run([ff, "-y",
             "-f", "lavfi", "-i", "testsrc=duration=5:size=640x360:rate=25",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=5",
             "-c:v", "libvpx-vp9", "-c:a", "libopus",
             "-shortest", f11])
        print(f"[OK] {os.path.basename(f11)}")

    # ── F12: Válido com áudio — para cenário clipe entre inválidos ────────────
    f12 = path("valid_clip_for_batch.mp4")
    if not os.path.exists(f12):
        run([ff, "-y",
             "-f", "lavfi", "-i", "testsrc=duration=5:size=640x360:rate=25",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=5",
             "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
             "-shortest", f12])
        print(f"[OK] {os.path.basename(f12)}")

    print(f"\n✅ Todas as fixtures criadas em: {FIXTURES_DIR}")


if __name__ == "__main__":
    make_all()
