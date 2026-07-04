"""
legendas.py
-----------
Ponte entre o pipeline Python e o Remotion para legendas animadas.

NOTA (03/07/2026): este módulo veio do viral-cutter-v2, onde o sistema
Remotion vive de fato. No Viralume ele existe para:
1. Destravar a interface (que importa TEMPLATES, FONTES etc.)
2. Fornecer as funções puras usadas pela etapa 4 (extrair_palavras_do_whisper,
   agrupar_palavras, importar_srt, exportar_srt)
O render Remotion (aplicar_legendas) só funciona se a pasta remotion/ com
node_modules existir — no Viralume ela não existe, e o produto de legendas
animadas é o v2. Ver ROADMAP_PRODUTO.md.

Fluxo:
1. Recebe: vídeo cortado + palavras com timestamps + template escolhido
2. Gera JSON de props para o Remotion
3. Copia vídeo para public/ do Remotion
4. Chama `npx remotion render` via subprocess
5. Retorna caminho do vídeo com legendas
"""

import os
import json
import shutil
import subprocess
import tempfile

# Caminho do módulo Remotion relativo a este arquivo
REMOTION_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "remotion")
REMOTION_PUBLIC = os.path.join(REMOTION_DIR, "public")

# Templates disponíveis
TEMPLATES = {
    "hook-viral":     "Hook Viral — grande, bold, pop",
    "palavra-vazada": "Palavra Vazada — metálico, transparente",
    "legenda-sutil":  "Legenda Sutil — pequena, discreta",
    "cta":            "CTA — cor de destaque, slide",
    "dado-numero":    "Dado/Número — destaque enorme",
    "impacto-shake":  "Impacto Shake — treme + escala",
    "minimalista":    "Minimalista — fade suave",
    "politico":       "Político — sólido, institucional",
    "cinema":         "Cinema — Bebas Neue, vazado elegante",
    "tiktok":         "TikTok — 2 cores, pop alternado",
    "narrativo":      "Narrativo — serifado limpo, estilo vlog",
    "typewriter":     "Typewriter — letra por letra, cursor piscando",
    "contador":       "Contador — número animado subindo",
    "hierarquia":     "Hierarquia — tamanhos mistos (número gigante + texto)",
    "infografico":    "Infográfico — badge/pill com borda e glow",
}


# Fontes disponíveis por categoria
FONTES = {
    # Bold/Impact
    "Montserrat":       "'Montserrat', sans-serif",
    "Bebas Neue":       "'Bebas Neue', Impact, sans-serif",
    "Oswald":           "'Oswald', sans-serif",
    "Anton":            "'Anton', sans-serif",
    "Archivo Black":    "'Archivo Black', sans-serif",
    "Bangers":          "'Bangers', cursive",
    "Russo One":        "'Russo One', sans-serif",
    "Righteous":        "'Righteous', cursive",
    # Clean/Modern
    "Inter":            "'Inter', sans-serif",
    "Poppins":          "'Poppins', sans-serif",
    "DM Sans":          "'DM Sans', sans-serif",
    "Space Grotesk":    "'Space Grotesk', sans-serif",
    # Serif/Elegante
    "Playfair Display": "'Playfair Display', serif",
    "Cormorant":        "'Cormorant Garamond', serif",
    "Lora":             "'Lora', serif",
    # Display/Handwritten
    "Caveat":           "'Caveat', cursive",
    "Permanent Marker": "'Permanent Marker', cursive",
    "Pacifico":         "'Pacifico', cursive",
    "Abril Fatface":    "'Abril Fatface', serif",
}


def verificar_remotion_instalado() -> bool:
    """Verifica se o Remotion está instalado (node_modules existe)."""
    return os.path.exists(os.path.join(REMOTION_DIR, "node_modules"))


def instalar_remotion(progresso_callback=None) -> bool:
    """Instala dependências do Remotion se necessário."""
    if verificar_remotion_instalado():
        return True

    def log(msg):
        print(msg)
        if progresso_callback:
            progresso_callback(msg)

    if not os.path.isdir(REMOTION_DIR):
        log("❌ Pasta remotion/ não existe neste projeto. Legendas animadas "
            "são do Viral Cutter v2 — use o Viralume para corte e o v2 para legendas.")
        return False

    log("📦 Instalando dependências do Remotion (primeira vez)...")

    resultado = subprocess.run(
        ["npm", "install"],
        cwd=REMOTION_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=True,
    )

    if resultado.returncode != 0:
        log(f"❌ Erro ao instalar Remotion:\n{resultado.stderr}")
        return False

    log("✅ Remotion instalado!")
    return True


def extrair_palavras_do_whisper(transcricao: dict, inicio_clipe: float, fim_clipe: float) -> list:
    """
    Extrai palavras com timestamps da transcrição do Whisper,
    ajustando para o tempo relativo do clipe.

    Se o Whisper retornou word-level timestamps, usa direto.
    Senão, divide o texto do segmento uniformemente.
    """
    palavras = []

    for seg in transcricao.get("segments", []):
        seg_inicio = seg.get("start", 0)
        seg_fim = seg.get("end", 0)

        # Pula segmentos fora do clipe
        if seg_fim < inicio_clipe or seg_inicio > fim_clipe:
            continue

        # Tenta word-level timestamps (Whisper com word_timestamps=True)
        if "words" in seg and seg["words"]:
            for w in seg["words"]:
                w_inicio = w.get("start", 0)
                w_fim = w.get("end", 0)

                if w_fim < inicio_clipe or w_inicio > fim_clipe:
                    continue

                palavras.append({
                    "texto": w.get("word", w.get("text", "")).strip(),
                    "inicio": round(w_inicio - inicio_clipe, 3),
                    "fim": round(w_fim - inicio_clipe, 3),
                })
        else:
            # Fallback: divide texto do segmento uniformemente
            texto = seg.get("text", "").strip()
            if not texto:
                continue

            words = texto.split()
            if not words:
                continue

            # Ajusta ao intervalo do clipe
            s = max(seg_inicio, inicio_clipe)
            e = min(seg_fim, fim_clipe)
            duracao = e - s
            dur_por_palavra = duracao / len(words)

            for i, word in enumerate(words):
                w_inicio = s + i * dur_por_palavra
                w_fim = w_inicio + dur_por_palavra
                palavras.append({
                    "texto": word,
                    "inicio": round(w_inicio - inicio_clipe, 3),
                    "fim": round(w_fim - inicio_clipe, 3),
                })

    # Remove palavras vazias e ordena
    palavras = [p for p in palavras if p["texto"]]
    palavras.sort(key=lambda p: p["inicio"])

    return palavras


def agrupar_palavras(palavras: list, max_palavras: int = 3, max_duracao: float = 2.0) -> list:
    """
    Agrupa palavras individuais em blocos de 2-3 para leitura mais natural.
    Legendas palavra-por-palavra são ideais para templates como tiktok e impacto-shake.
    Para outros templates, agrupar fica mais legível.
    """
    if not palavras:
        return []

    grupos = []
    grupo_atual = []

    for p in palavras:
        grupo_atual.append(p)

        duracao_grupo = p["fim"] - grupo_atual[0]["inicio"]

        if len(grupo_atual) >= max_palavras or duracao_grupo >= max_duracao:
            grupos.append({
                "texto": " ".join(w["texto"] for w in grupo_atual),
                "inicio": grupo_atual[0]["inicio"],
                "fim": grupo_atual[-1]["fim"],
            })
            grupo_atual = []

    # Último grupo
    if grupo_atual:
        grupos.append({
            "texto": " ".join(w["texto"] for w in grupo_atual),
            "inicio": grupo_atual[0]["inicio"],
            "fim": grupo_atual[-1]["fim"],
        })

    return grupos


def aplicar_legendas(
    caminho_video: str,
    caminho_saida: str,
    palavras: list,
    template: str = "palavra-vazada",
    config: dict = None,
    fps: int = 30,
    progresso_callback=None,
) -> bool:
    """
    Aplica legendas animadas ao vídeo usando Remotion.

    Parâmetros:
        caminho_video: vídeo de entrada (já cortado e enquadrado)
        caminho_saida: onde salvar o vídeo com legendas
        palavras: lista de {texto, inicio, fim}
        template: ID do template (ver TEMPLATES)
        config: dict com corTexto, corDestaque, posicao, fonte, tamanhoBase
        fps: frames por segundo do vídeo
        progresso_callback: função para reportar progresso

    Retorna:
        True se sucesso, False se erro
    """
    def log(msg):
        print(msg)
        if progresso_callback:
            progresso_callback(msg)

    if not palavras:
        log("⚠️ Nenhuma palavra para legendar. Copiando vídeo sem legendas.")
        shutil.copy2(caminho_video, caminho_saida)
        return True

    # Verifica instalação
    if not instalar_remotion(progresso_callback):
        return False

    # Templates que funcionam melhor palavra por palavra
    templates_por_palavra = {"tiktok", "impacto-shake", "hook-viral", "dado-numero", "contador", "hierarquia"}

    # Agrupa se não for template de palavra única
    if template not in templates_por_palavra:
        palavras_render = agrupar_palavras(palavras)
    else:
        palavras_render = palavras

    # Obtém duração do vídeo
    from analise import _obter_duracao_segundos
    duracao = _obter_duracao_segundos(caminho_video)
    if duracao <= 0:
        log("❌ Não foi possível determinar a duração do vídeo.")
        return False

    duration_frames = int(duracao * fps)

    # Prepara public/ dir
    os.makedirs(REMOTION_PUBLIC, exist_ok=True)

    # Copia vídeo para public/
    nome_video = "input_video.mp4"
    destino_video = os.path.join(REMOTION_PUBLIC, nome_video)
    log(f"📋 Preparando vídeo para renderização...")
    shutil.copy2(caminho_video, destino_video)

    # Gera props JSON
    props = {
        "videoSrc": nome_video,
        "template": template,
        "palavras": palavras_render,
        "config": config or {},
    }

    props_path = os.path.join(REMOTION_DIR, "_render_props.json")
    with open(props_path, "w", encoding="utf-8") as f:
        json.dump(props, f, ensure_ascii=False, indent=2)

    # Chama Remotion render
    log(f"🎨 Renderizando legendas ({TEMPLATES.get(template, template)})...")

    cmd = [
        "npx", "remotion", "render",
        "SubtitleVideo",
        caminho_saida,
        f"--props={props_path}",
        f"--frames=0-{duration_frames - 1}",
        "--codec=h264",
        "--overwrite",
    ]

    log(f"   ⏳ Isso pode levar alguns minutos...")

    resultado = subprocess.run(
        cmd,
        cwd=REMOTION_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=True,
    )

    # Limpa arquivos temporários
    try:
        os.remove(destino_video)
        os.remove(props_path)
    except OSError:
        pass

    if resultado.returncode != 0:
        log(f"❌ Erro no Remotion:\n{resultado.stderr[-500:]}")
        return False

    if os.path.exists(caminho_saida):
        log(f"✅ Legendas aplicadas com sucesso!")
        return True

    log("❌ Arquivo de saída não foi gerado.")
    return False


def importar_srt(caminho_srt: str) -> list:
    """Importa legenda em formato SRT e retorna lista de palavras/frases formatadas."""
    if not os.path.exists(caminho_srt):
        return []

    with open(caminho_srt, "r", encoding="utf-8", errors="ignore") as f:
        conteudo = f.read()

    import re
    # Expressão regular para capturar blocos SRT
    pattern = re.compile(
        r"(\d+)\s*\n"
        r"(\d{2}:\d{2}:\d{2}[.,]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[.,]\d{3})\s*\n"
        r"([\s\S]*?)(?=\n\s*\n|\n\s*$|\Z)"
    )

    def srt_time_to_seconds(t_str):
        t_str = t_str.replace(",", ".")
        h, m, s = t_str.split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)

    palavras = []
    for match in pattern.finditer(conteudo):
        inicio_str, fim_str, texto = match.group(2), match.group(3), match.group(4)
        inicio = srt_time_to_seconds(inicio_str)
        fim = srt_time_to_seconds(fim_str)
        texto = texto.strip().replace("\n", " ")
        if texto:
            palavras.append({
                "texto": texto,
                "inicio": round(inicio, 3),
                "fim": round(fim, 3)
            })
    return palavras


def exportar_srt(palavras: list, caminho_saida: str) -> bool:
    """Exporta lista de palavras para formato SRT."""
    def seconds_to_srt_time(s):
        hrs = int(s // 3600)
        mins = int((s % 3600) // 60)
        secs = int(s % 60)
        msecs = int(round((s % 1) * 1000))
        if msecs == 1000:
            msecs = 0
            secs += 1
            if secs == 60:
                secs = 0
                mins += 1
                if mins == 60:
                    mins = 0
                    hrs += 1
        return f"{hrs:02d}:{mins:02d}:{secs:02d},{msecs:03d}"

    try:
        with open(caminho_saida, "w", encoding="utf-8") as f:
            for i, p in enumerate(palavras, 1):
                inicio_str = seconds_to_srt_time(p["inicio"])
                fim_str = seconds_to_srt_time(p["fim"])
                f.write(f"{i}\n")
                f.write(f"{inicio_str} --> {fim_str}\n")
                f.write(f"{p['texto']}\n\n")
        return True
    except Exception as e:
        print(f"Erro ao exportar SRT: {e}")
        return False
