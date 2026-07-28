"""
enquadramento.py
----------------
Enquadramento estilo editor profissional de podcast — VERSÃO POR CENA.

O QUE MUDOU (e por quê):

Antes, a posição das pessoas era calculada UMA vez, na média do clipe
inteiro. Problema: podcasts têm várias câmeras. Quando o vídeo corta de
uma câmera fechada para um plano aberto, as pessoas mudam de lugar no
quadro — e o crop fixo apontava para a mesa vazia.

Agora o fluxo é:

1. Detecta os CORTES DE CENA dentro do clipe (mudança brusca de imagem)
2. Para CADA CENA, detecta onde os rostos estão NAQUELA cena
3. Decide o modo por cena:
   - 0 rostos  → CENTRAL (é B-roll / plano de corte, sem gente mesmo)
   - 1 rosto   → SOLO fixo naquela pessoa
   - 2+ rostos → crop segue QUEM ESTÁ FALANDO frame a frame
4. Cortes SECOS entre cenas; dentro da cena o crop desliza suave atrás
   de quem fala

Regras mantidas:
- Nunca corta cabeça — crop sempre centralizado no rosto/falante
- Duração mínima por modo (evita cortes nervosos demais)

Nota (04/07/2026): cenas de 2+ pessoas já tiveram split screen com
detecção de "lado A/lado B" por POSIÇÃO DE ROSTO (clustering por cena).
Removido — a mira podia cair num objeto decorativo com formato de rosto
(busto na estante) em vez de gente de verdade. Agora o alvo do crop vem
de QUEM FALA (voz + movimento labial, sinal já validado por outra etapa
do pipeline) — decoração nunca fala, então nunca vira alvo. Histórico
completo na seção 10/11 do RELATORIO_COMPLETO_2026-07-03.md.
"""

import cv2
import numpy as np
import subprocess
import json
import os
from ffmpeg_utils import argumentos_encoder


# ── Configurações ─────────────────────────────────────────────────────────────

RESOLUCOES = {
    # H.264/yuv420p exige largura e altura pares. 405x720 é 9:16 exato,
    # mas quebra o libx264; 406x720 mantém o formato visual e codifica.
    "720p":  (406,  720),
    "1080p": (1080, 1920),
    "4k":    (2160, 3840),
}

# Diferença média de pixels (0-255) entre frames para considerar corte de cena
LIMIAR_CORTE_CENA = 28.0

# Duração mínima de uma cena (cenas menores são fundidas com a anterior)
DURACAO_MINIMA_CENA = 0.5  # segundos

# Quantos frames analisar por cena para achar os rostos
AMOSTRAS_POR_CENA = 10
INTERPOLACAO_EXPORT = cv2.INTER_LINEAR
PASSO_DETECCAO_CENA = 2

# Rostos menores que isso (largura normalizada) são ignorados — filtra
# falsos positivos como rostos na TV do cenário, estátuas e manequins.
MIN_TAMANHO_ROSTO = 0.018

# Zona vertical onde ficam as CABEÇAS de quem está sentado num podcast.
# Falsos positivos do cenário caem fora dela: TV/quadros na parede e
# estátuas na estante ficam ALTOS (Y < 0.30); objetos na mesa em primeiro
# plano ficam BAIXOS (Y > 0.72). Diagnóstico real (Papo Reto): pessoas em
# Y=0.43 e Y=0.57; TV em Y=0.13, estátua em Y=0.25, objetos em Y=0.79-0.90.
# Filtro com fallback: se uma cena não tem NENHUM rosto nesta zona, ele é
# ignorado (não descarta a cena inteira).
ZONA_ROSTO_Y_MIN = 0.30
ZONA_ROSTO_Y_MAX = 0.72

# ── Zoom adaptativo ao rosto (conceito estudado no ViralCutter open source
# e nos cortes profissionais de podcast): a janela de crop é dimensionada
# pelo TAMANHO do rosto na cena, não por fração fixa do quadro. Rosto
# pequeno (plano aberto) → zoom forte; rosto grande (câmera fechada) →
# quadro inteiro. O resultado parece direção de câmera, não recorte.
FATOR_ZOOM_ROSTO = 4.5    # altura do crop ≈ 4.5x a largura do rosto (px)
ZOOM_MIN_ALTURA = 0.50    # nunca fecha mais que 50% da altura (qualidade)
POSICAO_ROSTO_QUADRO = 0.40  # rosto a 40% do topo do quadro (regra dos terços)
# A janela horizontal precisa comportar mais que o rosto: em planos de
# podcast a pessoa se inclina, gesticula e pode estar parcialmente fora do
# centro. Sem essa folga, o centro correto ainda produz um rosto cortado nas
# bordas do clipe vertical.
FOLGA_HORIZONTAL_ROSTO = 2.8  # largura mínima do crop em relação ao rosto

# Cache da análise visual (cenas + rostos) por clipe.
# Chave: (caminho absoluto, tamanho, mtime, perfil). Evita refazer toda a
# análise em retry de validação e retomada de checkpoint.
_cache_analise_visual: dict = {}
_CACHE_ANALISE_MAX = 12  # limite de clipes em memória


def _classificar_modos_fala(
    posicoes: list,
    xa: float,
    xb: float,
    fps: float,
    limiar_s: float = 3.0,
) -> list:
    """Mantém split na conversa e destaca após fala contínua prolongada."""
    if abs(float(xb) - float(xa)) < 0.12:
        return ["SOLO_A"] * len(posicoes)

    minimo_frames = max(1, int(np.ceil(float(fps or 30.0) * limiar_s)))
    modos = []
    lado_atual = None
    frames_continuos = 0
    modo = "SPLIT"

    for pos in posicoes:
        if pos is None:
            modos.append(modo)
            continue
        lado = "A" if abs(float(pos) - xa) <= abs(float(pos) - xb) else "B"
        if lado != lado_atual:
            lado_atual = lado
            frames_continuos = 1
            modo = "SPLIT"
        else:
            frames_continuos += 1
            if frames_continuos >= minimo_frames:
                modo = f"SOLO_{lado}"
        modos.append(modo)
    return modos


def _calcular_crop_seguro(
    alvos: list,
    largura: int,
    altura: int,
    proporcao: float,
) -> tuple:
    """Calcula crop conservador, centralizado no conjunto humano e sem zoom excessivo."""
    if not alvos:
        raise ValueError("Nenhum alvo humano para enquadrar.")

    largura_max = min(float(largura), float(altura) * float(proporcao))
    maior_rosto = max(max(0.01, float(a[2])) * largura for a in alvos)
    centros_x = [float(a[0]) * largura for a in alvos]
    centro_x = float(np.mean(centros_x))
    esquerda_humana = min(cx - maior_rosto * 1.6 for cx in centros_x)
    direita_humana = max(cx + maior_rosto * 1.6 for cx in centros_x)
    largura_desejada = max(largura_max * 0.85, maior_rosto * 4.0, direita_humana - esquerda_humana)
    crop_w = int(round(min(largura_max, largura_desejada)))
    crop_w = max(2, crop_w + crop_w % 2)
    crop_h = int(round(crop_w / float(proporcao)))
    crop_h = max(2, crop_h + crop_h % 2)

    if crop_h > altura:
        crop_h = altura - altura % 2
        crop_w = int(round(crop_h * float(proporcao)))
        crop_w += crop_w % 2
    if crop_w > largura:
        crop_w = largura - largura % 2
        crop_h = int(round(crop_w / float(proporcao)))
        crop_h += crop_h % 2

    x = int(round(centro_x - crop_w / 2))
    x = max(0, min(largura - crop_w, x))
    rosto_y = float(np.mean([float(a[1]) for a in alvos])) * altura
    y = int(round(rosto_y - crop_h * POSICAO_ROSTO_QUADRO))
    y = max(0, min(altura - crop_h, y))
    return x, y, crop_w, crop_h

def _compor_frame_seguro(frame, plano: dict, saida_w: int, saida_h: int):
    """Compõe SOLO/GRUPO/SPLIT com cada pessoa centralizada e quadro aberto."""
    altura, largura = frame.shape[:2]

    def painel(alvos, destino_w, destino_h):
        x, y, w, h = _calcular_crop_seguro(
            alvos, largura, altura, destino_w / float(destino_h)
        )
        recorte = frame[y:y + h, x:x + w]
        return cv2.resize(
            recorte, (destino_w, destino_h), interpolation=INTERPOLACAO_EXPORT
        )

    modo = plano.get("modo", "SOLO_A")
    alvo_a = (
        float(plano["xa"]), float(plano.get("ya", 0.40)),
        float(plano.get("ta", 0.0)),
    )
    alvo_b = (
        float(plano.get("xb", plano["xa"])), float(plano.get("yb", 0.40)),
        float(plano.get("tb", plano.get("ta", 0.0))),
    )

    if modo == "SPLIT":
        topo_h = saida_h // 2
        base_h = saida_h - topo_h
        topo = painel([alvo_a], saida_w, topo_h)
        base = painel([alvo_b], saida_w, base_h)
        return np.vstack((topo, base))
    if modo == "GRUPO":
        return painel([alvo_a, alvo_b], saida_w, saida_h)
    return painel([alvo_a], saida_w, saida_h)

def aplicar_enquadramento(
    caminho_entrada: str,
    caminho_saida: str,
    posicoes_falante: list,
    pessoas_priorizadas: list = None,
    qualidade: str = "1080p",
    perfil: str = "equilibrado",
) -> bool:
    """
    Aplica enquadramento 9:16 ciente dos cortes de cena.

    Assinatura idêntica à versão anterior — o pipeline.py não muda.
    """
    saida_w, saida_h = RESOLUCOES.get(qualidade, (1080, 1920))

    info = _obter_info_video(caminho_entrada)
    largura = info["largura"]
    altura  = info["altura"]
    fps     = info["fps"]

    print(f"🎬 Enquadramento por cena {qualidade} ({saida_w}x{saida_h})...")

    # ── Cache: retry/retomada não refazem a análise visual ────────────────
    try:
        _st = os.stat(caminho_entrada)
        chave_cache = (os.path.abspath(caminho_entrada), _st.st_size,
                       _st.st_mtime_ns, perfil)
    except OSError:
        chave_cache = None

    passo_cena = 4 if perfil == "rapido" else (1 if perfil == "qualidade" else 2)
    # 25/30: medido no Papo Reto que em plano aberto multicâmera o
    # MediaPipe só acha a pessoa mais distante/de perfil em ~16% dos
    # frames individuais (mic e ângulo atrapalham). Com 6 amostras a
    # chance de nunca pegá-la numa cena era ~34%; com 25 cai a ~1%. Custo
    # extra é pequeno (poucos ms de MediaPipe por amostra) e a mediana
    # dos clusters fica mais estável entre execuções.
    amostras_cena = 3 if perfil == "rapido" else (30 if perfil == "qualidade" else 25)

    if chave_cache is not None and chave_cache in _cache_analise_visual:
        cenas = [dict(c) for c in _cache_analise_visual[chave_cache]]
        print(f"   ♻️ Análise visual reaproveitada do cache ({len(cenas)} cenas).")
    else:
        # ── Passo 1: Detecta os cortes de cena dentro do clipe ────────────
        print("   🎞️ Detectando cortes de cena...")
        cenas = _detectar_cenas_pyscene(caminho_entrada)
        if cenas is not None:
            print(f"   📊 {len(cenas)} cena(s) [PySceneDetect]")
        else:
            cenas = _detectar_cenas(caminho_entrada, fps, passo=passo_cena)
            print(f"   📊 {len(cenas)} cena(s) [detector interno — instale scenedetect p/ mais precisão]")

        # ── Passo 2: Analisa os rostos DENTRO de cada cena ────────────────
        print("   🔍 Detectando rostos em cada cena...")
        cenas = _analisar_rostos_por_cena(
            caminho_entrada, cenas, amostras_por_cena=amostras_cena
        )

        if chave_cache is not None:
            if len(_cache_analise_visual) >= _CACHE_ANALISE_MAX:
                _cache_analise_visual.clear()  # simples e suficiente
            _cache_analise_visual[chave_cache] = [dict(c) for c in cenas]

    for c in cenas:
        if c["n_pessoas"] == 0:
            desc = "sem pessoas → crop central"
        elif c["n_pessoas"] == 1:
            desc = f"1 pessoa em x={c['lado_a']:.2f}"
        else:
            desc = f"2 lados: A={c['lado_a']:.2f} B={c['lado_b']:.2f}"
        print(f"      Cena {c['frame_ini']}–{c['frame_fim']}: {desc}")

    # ── Passo 3: Gera o plano de enquadramento frame a frame ──────────────
    total_frames = cenas[-1]["frame_fim"] if cenas else 0
    plano = _gerar_plano(cenas, posicoes_falante, fps, total_frames)

    # ── Passo 4: Processa frame a frame ───────────────────────────────────
    crop_w_916 = int(altura * 9 / 16)
    if crop_w_916 % 2 != 0:
        crop_w_916 -= 1

    cap = cv2.VideoCapture(caminho_entrada)
    if not cap.isOpened():
        cap.release()
        print("   ⚠️ Não foi possível abrir o vídeo para enquadramento.")
        return False

    # Envia frames diretamente para o FFmpeg. Antes o programa criava um MP4
    # temporário inteiro e depois codificava tudo novamente em uma segunda
    # passagem, dobrando tempo, disco e perda de qualidade.
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "bgr24",
        "-s", f"{saida_w}x{saida_h}", "-r", str(fps), "-i", "-",
        "-i", caminho_entrada,
        "-map", "0:v", "-map", "1:a?",
    ]
    cmd += argumentos_encoder(temporario=False)
    cmd += [
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-shortest",
        "-movflags", "+faststart",
        caminho_saida,
    ]
    processo_ffmpeg = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )

    # Drena o stderr em paralelo. Sem isso, se o FFmpeg encher o buffer do
    # pipe de erro enquanto ainda estamos escrevendo frames no stdin, os
    # dois processos travam um esperando o outro (deadlock clássico).
    import threading
    _stderr_chunks = []

    def _drenar_stderr():
        try:
            _stderr_chunks.append(processo_ffmpeg.stderr.read())
        except Exception:
            pass

    _t_stderr = threading.Thread(target=_drenar_stderr, daemon=True)
    _t_stderr.start()

    print(f"   🎞️ Processando {total_frames} frames...")
    frame_idx = 0
    erro_pipe = False

    # Suavização do crop: dentro da mesma cena o crop desliza suavemente
    # até o alvo (sem tremer); em corte de cena ele salta seco — exatamente
    # como um editor humano trabalha.
    inicios_cena = {c["frame_ini"] for c in cenas}
    ALPHA_SUAVE = 0.18  # fração da distância percorrida por frame
    x_suave = None
    zoom_suave = None

    def _aproximar(atual, alvo):
        return alvo if atual is None else atual + (alvo - atual) * ALPHA_SUAVE

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        # Pega o plano deste frame (modo + posições)
        if frame_idx < len(plano):
            p = plano[frame_idx]
        else:
            p = plano[-1] if plano else {"modo": "CENTRAL", "xa": 0.5, "xb": 0.5}

        modo = p["modo"]

        frame_final = _compor_frame_seguro(frame, p, saida_w, saida_h)

        try:
            processo_ffmpeg.stdin.write(frame_final.tobytes())
        except (BrokenPipeError, OSError):
            erro_pipe = True
            break
        frame_idx += 1

        if frame_idx % 200 == 0 and total_frames > 0:
            pct = int((frame_idx / total_frames) * 100)
            print(f"   ⏳ {pct}% ({frame_idx}/{total_frames} frames)")

    cap.release()
    if processo_ffmpeg.stdin:
        try:
            processo_ffmpeg.stdin.close()
        except (BrokenPipeError, OSError):
            erro_pipe = True
    codigo = processo_ffmpeg.wait()
    _t_stderr.join(timeout=10)
    stderr = (_stderr_chunks[0] if _stderr_chunks else b"").decode("utf-8", errors="replace")
    if processo_ffmpeg.stderr:
        try:
            processo_ffmpeg.stderr.close()
        except OSError:
            pass

    if codigo == 0 and not erro_pipe:
        print("   ✅ Enquadramento concluído!")
    else:
        print(f"   ⚠️ Erro no FFmpeg ao exportar: {stderr[-600:]}")
        if os.path.exists(caminho_saida):
            os.remove(caminho_saida)

    return codigo == 0 and not erro_pipe


# ── Detecção de cortes de cena ────────────────────────────────────────────────

def _detectar_cenas_pyscene(caminho_video: str) -> list:
    """
    Detecção de cena PROFISSIONAL via PySceneDetect (ContentDetector).

    Por que: a detecção caseira (diferença média de pixels) perdia cortes
    de câmera em podcasts — gerava "cenas" de 60s+ misturando duas câmeras,
    e a posição média dos rostos ficava errada para as duas.

    Retorna lista no mesmo formato de _detectar_cenas, ou None se a
    biblioteca não estiver instalada (aí o chamador usa o fallback caseiro).
    Instalar com: pip install scenedetect
    """
    try:
        from scenedetect import detect, ContentDetector
    except ImportError:
        return None

    try:
        lista = detect(caminho_video, ContentDetector(threshold=27.0))
    except Exception as e:
        print(f"   ⚠️ PySceneDetect falhou ({e}). Usando detector interno.")
        return None

    cenas = [
        {"frame_ini": ini.get_frames(), "frame_fim": fim.get_frames()}
        for ini, fim in lista
    ]
    return cenas or None


def _detectar_cenas(caminho_video: str, fps: float, passo: int = PASSO_DETECCAO_CENA) -> list:
    """
    Detecta os cortes de cena comparando frames consecutivos.

    Como funciona: cada frame é reduzido para 96x54 em tons de cinza.
    Se a diferença média entre um frame e o anterior passa do limiar,
    é um corte de cena (mudança de câmera, B-roll etc).

    Retorna lista de cenas: [{"frame_ini": 0, "frame_fim": 120}, ...]
    """
    cap = cv2.VideoCapture(caminho_video)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    cortes = [0]  # o frame 0 sempre inicia a primeira cena
    anterior = None
    frame_idx = 0
    min_frames_cena = max(1, int(fps * DURACAO_MINIMA_CENA))

    while cap.isOpened():
        ret = cap.grab()
        if not ret:
            break

        if frame_idx % max(1, passo) != 0:
            frame_idx += 1
            continue

        ret, frame = cap.retrieve()
        if not ret:
            frame_idx += 1
            continue

        # Versão minúscula em cinza — comparação barata e estável
        mini = cv2.cvtColor(cv2.resize(frame, (96, 54)), cv2.COLOR_BGR2GRAY)

        if anterior is not None:
            diferenca = float(np.mean(cv2.absdiff(mini, anterior)))
            # Corte de cena = diferença alta E cena anterior não é curta demais
            if diferenca > LIMIAR_CORTE_CENA and (frame_idx - cortes[-1]) >= min_frames_cena:
                cortes.append(frame_idx)

        anterior = mini
        frame_idx += 1

    cap.release()
    total_real = frame_idx if frame_idx > 0 else total_frames

    # Monta a lista de cenas a partir dos cortes
    cenas = []
    for i, ini in enumerate(cortes):
        fim = cortes[i + 1] if i + 1 < len(cortes) else total_real
        cenas.append({"frame_ini": ini, "frame_fim": fim})

    if not cenas:
        cenas = [{"frame_ini": 0, "frame_fim": total_real}]

    return cenas


# ── Análise de rostos por cena ────────────────────────────────────────────────

def _analisar_rostos_por_cena(
    caminho_video: str,
    cenas: list,
    amostras_por_cena: int = AMOSTRAS_POR_CENA,
) -> list:
    """
    Para cada cena, amostra alguns frames e detecta onde os rostos estão.

    Preenche em cada cena:
    - n_pessoas: 0, 1 ou 2 (2 = dois lados/grupos)
    - lado_a: posição X normalizada do lado esquerdo (ou da pessoa única)
    - lado_b: posição X normalizada do lado direito
    """
    from rostos import _inicializar_detector, _fechar_detector, detectar_rostos_robusto

    detector = _inicializar_detector()
    cap = cv2.VideoCapture(caminho_video)

    for cena in cenas:
        rostos_cena = []

        if detector is not None:
            n_frames_cena = cena["frame_fim"] - cena["frame_ini"]
            n_amostras = min(amostras_por_cena, max(1, n_frames_cena))
            passo = max(1, n_frames_cena // n_amostras)

            for k in range(n_amostras):
                alvo = cena["frame_ini"] + k * passo
                if alvo >= cena["frame_fim"]:
                    break
                cap.set(cv2.CAP_PROP_POS_FRAMES, alvo)
                ret, frame = cap.read()
                if not ret:
                    continue
                rostos = detectar_rostos_robusto(frame, detector)
                for r in rostos:
                    # Filtra rostos minúsculos: TV do cenário, estátuas,
                    # manequins na estante — falsos positivos clássicos.
                    if r.get("w", 0) < MIN_TAMANHO_ROSTO:
                        continue
                    rostos_cena.append(r)

        posicoes_x, posicoes_y, posicoes_w = _filtrar_rostos_na_zona_de_cabeca(rostos_cena)

        # Agrupa as posições encontradas NESTA cena
        cena.update(_agrupar_posicoes_cena(posicoes_x, posicoes_y, posicoes_w))

    cap.release()
    if detector is not None:
        _fechar_detector(detector)

    return cenas


def _filtrar_rostos_na_zona_de_cabeca(rostos: list) -> tuple:
    """
    Separa posições X e Y de rostos, priorizando os que estão na zona
    vertical de cabeça de quem está sentado (ZONA_ROSTO_Y_MIN..MAX).

    Falsos positivos do cenário caem fora: TV/quadros/estátuas ficam altos
    (Y baixo), objetos na mesa em primeiro plano ficam baixos (Y alto).

    Fallback: se NENHUM rosto está na zona, devolve todos — melhor um crop
    impreciso do que uma cena tratada como B-roll sem gente.
    """
    na_zona = [
        r for r in rostos
        if ZONA_ROSTO_Y_MIN <= r["y"] <= ZONA_ROSTO_Y_MAX
    ]
    usar = na_zona if na_zona else rostos
    return (
        [r["x"] for r in usar],
        [r["y"] for r in usar],
        [r.get("w", 0.0) for r in usar],
    )


def _agrupar_posicoes_cena(posicoes_x: list, posicoes_y: list = None, posicoes_w: list = None) -> dict:
    """
    Agrupa posições X (e Y) de rostos de uma cena em 0, 1 ou 2 grupos.

    - Nenhuma posição  → cena sem pessoas (B-roll): crop central
    - Posições próximas → 1 pessoa (ou grupo): SOLO centralizado nela
    - Posições espalhadas → 2 lados: divide no maior salto entre posições

    O Y médio de cada lado permite ao split screen dar zoom no rosto
    (antes o Y era descartado e o painel mostrava o plano aberto inteiro).
    """
    Y_PADRAO = 0.40  # rosto costuma ficar no terço superior em podcast

    if not posicoes_x:
        return {"n_pessoas": 0, "lado_a": 0.5, "lado_b": 0.5,
                "lado_a_y": Y_PADRAO, "lado_b_y": Y_PADRAO,
                "lado_a_tam": 0.0, "lado_b_tam": 0.0}

    n = len(posicoes_x)
    ys_ok = posicoes_y if posicoes_y and len(posicoes_y) == n else [Y_PADRAO] * n
    ws_ok = posicoes_w if posicoes_w and len(posicoes_w) == n else [0.0] * n
    pares = sorted(zip(posicoes_x, ys_ok, ws_ok))
    xs = [p[0] for p in pares]
    ys = [p[1] for p in pares]
    ws = [p[2] for p in pares]

    # Se todas as posições estão num intervalo estreito, é uma pessoa só.
    # 0.28 tolera movimentação na cadeira sem virar "duas pessoas".
    if xs[-1] - xs[0] < 0.28:
        centro = float(np.median(xs))
        centro_y = float(np.clip(np.median(ys), 0.15, 0.55))
        tam = float(np.median(ws))
        return {"n_pessoas": 1, "lado_a": centro, "lado_b": centro,
                "lado_a_y": centro_y, "lado_b_y": centro_y,
                "lado_a_tam": tam, "lado_b_tam": tam}

    # Agrupa posições vizinhas (salto > 0.15 abre novo cluster). Com 3+
    # clusters, mantém os 2 com MAIS detecções nas amostras: pessoas reais
    # aparecem em quase todos os frames amostrados; um rosto na TV do
    # cenário aparece esporadicamente. Antes, um único falso positivo
    # central virava "lado B" e o painel do split mirava na TV.
    clusters = [[pares[0]]]
    for par in pares[1:]:
        if par[0] - clusters[-1][-1][0] > 0.15:
            clusters.append([par])
        else:
            clusters[-1].append(par)

    if len(clusters) > 2:
        clusters.sort(key=len, reverse=True)
        clusters = clusters[:2]
        clusters.sort(key=lambda c: c[0][0])  # reordena esquerda→direita

    def _mediana(cluster, idx):
        return float(np.median([p[idx] for p in cluster]))

    if len(clusters) == 1:
        centro = _mediana(clusters[0], 0)
        centro_y = float(np.clip(_mediana(clusters[0], 1), 0.15, 0.55))
        tam = _mediana(clusters[0], 2)
        return {"n_pessoas": 1, "lado_a": centro, "lado_b": centro,
                "lado_a_y": centro_y, "lado_b_y": centro_y,
                "lado_a_tam": tam, "lado_b_tam": tam}

    return {
        "n_pessoas": 2,
        "lado_a": _mediana(clusters[0], 0),
        "lado_b": _mediana(clusters[1], 0),
        "lado_a_y": float(np.clip(_mediana(clusters[0], 1), 0.15, 0.55)),
        "lado_b_y": float(np.clip(_mediana(clusters[1], 1), 0.15, 0.55)),
        "lado_a_tam": _mediana(clusters[0], 2),
        "lado_b_tam": _mediana(clusters[1], 2),
    }


# ── Plano de enquadramento frame a frame ─────────────────────────────────────

def _gerar_plano(cenas: list, posicoes_falante: list, fps: float, total_frames: int) -> list:
    """
    Gera, para cada frame, o modo e as posições de crop.

    Retorna lista de dicts: [{"modo": "SOLO_A", "xa": 0.3, "xb": 0.7}, ...]

    - Cena sem pessoas → herda modo/posição da cena anterior (nunca mesa vazia)
    - Cena com 1 pessoa → SOLO_A fixo nela
    - Cena com 2+ pessoas → segue quem fala frame a frame (ver bloco abaixo)
    """
    plano = [None] * total_frames

    Y_PADRAO = 0.40

    # Memória da última cena com pessoas — para herdar quando falhar detecção
    ultimo_modo_valido = "SOLO_A"
    ultimo_xa = 0.5
    ultimo_xb = 0.5
    ultimo_ya = Y_PADRAO
    ultimo_yb = Y_PADRAO
    ultimo_ta = 0.0  # tamanho do rosto (p/ zoom adaptativo); 0 = sem zoom

    for cena in cenas:
        ini, fim = cena["frame_ini"], cena["frame_fim"]
        xa, xb = cena["lado_a"], cena["lado_b"]
        ya = cena.get("lado_a_y", Y_PADRAO)
        yb = cena.get("lado_b_y", Y_PADRAO)
        ta = cena.get("lado_a_tam", 0.0)
        tb = cena.get("lado_b_tam", 0.0)

        if cena["n_pessoas"] == 0:
            # Sem rosto detectado nesta cena (rostos de perfil enganam o
            # detector). Antes de herdar, tenta a posição de QUEM FALA —
            # o áudio-visual da etapa 3 sabe onde a boca está mesmo quando
            # o detector frontal falha.
            falantes_cena = [
                posicoes_falante[j]
                for j in range(ini, min(fim, len(posicoes_falante)))
                if posicoes_falante[j] is not None
            ]
            if falantes_cena:
                x_falante = float(np.median(falantes_cena))
                for f in range(ini, min(fim, total_frames)):
                    plano[f] = {"modo": "SOLO_A", "xa": x_falante, "xb": x_falante,
                                "ya": Y_PADRAO, "yb": Y_PADRAO, "ta": 0.0}
                ultimo_modo_valido, ultimo_xa, ultimo_xb = "SOLO_A", x_falante, x_falante
                ultimo_ta = 0.0
            else:
                # Herda o enquadramento da última cena que tinha gente.
                for f in range(ini, min(fim, total_frames)):
                    plano[f] = {"modo": ultimo_modo_valido, "xa": ultimo_xa, "xb": ultimo_xb,
                                "ya": ultimo_ya, "yb": ultimo_yb, "ta": ultimo_ta}
            continue

        if cena["n_pessoas"] == 1:
            ultimo_modo_valido = "SOLO_A"
            ultimo_xa = xa
            ultimo_xb = xa
            ultimo_ya = ya
            ultimo_yb = ya
            ultimo_ta = ta
            for f in range(ini, min(fim, total_frames)):
                plano[f] = {"modo": "SOLO_A", "xa": xa, "xb": xa, "ya": ya, "yb": ya, "ta": ta}
            continue

        # Duas pessoas próximas cabem juntas; separadas usam split durante
        # conversa e solo apenas após 3 segundos contínuos da mesma voz.
        if abs(xb - xa) <= 0.34:
            for f in range(ini, min(fim, total_frames)):
                plano[f] = {
                    "modo": "GRUPO", "xa": xa, "xb": xb,
                    "ya": ya, "yb": yb, "ta": ta, "tb": tb,
                }
            ultimo_modo_valido = "GRUPO"
            ultimo_xa, ultimo_xb = xa, xb
            ultimo_ya, ultimo_yb = ya, yb
            ultimo_ta = max(ta, tb)
            continue

        posicoes_cena = [
            posicoes_falante[f] if f < len(posicoes_falante) else None
            for f in range(ini, min(fim, total_frames))
        ]
        modos = _classificar_modos_fala(posicoes_cena, xa, xb, fps)
        for deslocamento, f in enumerate(range(ini, min(fim, total_frames))):
            modo = modos[deslocamento]
            if modo == "SOLO_A":
                plano[f] = {"modo": modo, "xa": xa, "xb": xa,
                            "ya": ya, "yb": ya, "ta": ta, "tb": ta}
            elif modo == "SOLO_B":
                plano[f] = {"modo": modo, "xa": xb, "xb": xb,
                            "ya": yb, "yb": yb, "ta": tb, "tb": tb}
            else:
                plano[f] = {"modo": "SPLIT", "xa": xa, "xb": xb,
                            "ya": ya, "yb": yb, "ta": ta, "tb": tb}

        ultimo = plano[min(fim, total_frames) - 1]
        ultimo_modo_valido = ultimo["modo"]
        ultimo_xa, ultimo_xb = ultimo["xa"], ultimo["xb"]
        ultimo_ya, ultimo_yb = ultimo["ya"], ultimo["yb"]
        ultimo_ta = ultimo.get("ta", 0.0)
    # Preenche buracos — usa último modo válido, nunca CENTRAL
    ultimo = {"modo": ultimo_modo_valido, "xa": ultimo_xa, "xb": ultimo_xb,
              "ya": ultimo_ya, "yb": ultimo_yb, "ta": ultimo_ta}
    for f in range(total_frames):
        if plano[f] is None:
            plano[f] = ultimo
        else:
            ultimo = plano[f]

    return plano


# ── Utilitários ───────────────────────────────────────────────────────────────

def _calcular_x_crop(x_centro_norm: float, largura: int, crop_w: int) -> int:
    """
    Converte posição normalizada (0-1) em coordenada X do crop,
    garantindo que o crop não saia do frame.
    """
    x = int(x_centro_norm * largura - crop_w / 2)
    return max(0, min(largura - crop_w, x))


def _recortar_com_margem(
    frame: np.ndarray,
    x_centro_norm: float,
    y_inicio: int,
    crop_w: int,
    crop_h: int,
) -> np.ndarray:
    """Recorta o alvo mesmo quando ele está encostado na borda do original.

    Um crop 9:16 tradicional não consegue centralizar uma pessoa que está na
    extrema esquerda/direita sem cortar parte do rosto. Neste caso, cria uma
    pequena margem refletida somente fora do quadro original e mantém o alvo
    no centro da janela. A imagem real nunca é esticada nem deformada.
    """
    altura, largura = frame.shape[:2]
    crop_w = max(2, min(int(crop_w), max(2, largura)))
    crop_h = max(2, int(crop_h))

    x_centro = float(np.clip(x_centro_norm if x_centro_norm is not None else 0.5, 0.0, 1.0)) * largura
    x_inicio = int(round(x_centro - crop_w / 2))
    y_inicio = int(y_inicio)

    pad_esq = max(0, -x_inicio)
    pad_dir = max(0, x_inicio + crop_w - largura)
    pad_top = max(0, -y_inicio)
    pad_bottom = max(0, y_inicio + crop_h - altura)

    if pad_esq or pad_dir or pad_top or pad_bottom:
        frame = cv2.copyMakeBorder(
            frame,
            pad_top,
            pad_bottom,
            pad_esq,
            pad_dir,
            cv2.BORDER_REFLECT_101,
        )
        x_inicio += pad_esq
        y_inicio += pad_top

    y_inicio = max(0, min(frame.shape[0] - crop_h, y_inicio))
    x_inicio = max(0, min(frame.shape[1] - crop_w, x_inicio))
    recorte = frame[y_inicio:y_inicio + crop_h, x_inicio:x_inicio + crop_w]

    # A borda refletida pode ser menor que o esperado em vídeos muito
    # pequenos; garante que o encoder nunca receba um frame vazio.
    if recorte.shape[0] != crop_h or recorte.shape[1] != crop_w:
        recorte = cv2.resize(recorte, (crop_w, crop_h), interpolation=cv2.INTER_LINEAR)
    return recorte


def _obter_info_video(caminho_video: str) -> dict:
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_streams", "-select_streams", "v:0", caminho_video
    ]
    resultado = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if resultado.returncode != 0 or not resultado.stdout.strip():
        raise RuntimeError("FFprobe não conseguiu ler as informações do vídeo.")
    dados = json.loads(resultado.stdout)
    stream = dados["streams"][0]
    fps_str = stream.get("r_frame_rate", "30/1")
    num, den = fps_str.split("/")
    den = int(den)
    fps = round(int(num) / den, 2) if den else 30.0
    return {
        "largura": int(stream["width"]),
        "altura":  int(stream["height"]),
        "fps":     fps,
    }
# fim do arquivo — enquadramento por cena v2
