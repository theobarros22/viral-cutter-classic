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

    # ── Passo 1: Detecta os cortes de cena dentro do clipe ────────────────
    print("   🎞️ Detectando cortes de cena...")
    passo_cena = 4 if perfil == "rapido" else (1 if perfil == "qualidade" else 2)
    # 25/30: medido no Papo Reto que em plano aberto multicâmera o
    # MediaPipe só acha a pessoa mais distante/de perfil em ~16% dos
    # frames individuais (mic e ângulo atrapalham). Com 6 amostras a
    # chance de nunca pegá-la numa cena era ~34%; com 25 cai a ~1%. Custo
    # extra é pequeno (poucos ms de MediaPipe por amostra) e a mediana
    # dos clusters fica mais estável entre execuções.
    amostras_cena = 3 if perfil == "rapido" else (30 if perfil == "qualidade" else 25)
    cenas = _detectar_cenas_pyscene(caminho_entrada)
    if cenas is not None:
        print(f"   📊 {len(cenas)} cena(s) [PySceneDetect]")
    else:
        cenas = _detectar_cenas(caminho_entrada, fps, passo=passo_cena)
        print(f"   📊 {len(cenas)} cena(s) [detector interno — instale scenedetect p/ mais precisão]")

    # ── Passo 2: Analisa os rostos DENTRO de cada cena ────────────────────
    print("   🔍 Detectando rostos em cada cena...")
    cenas = _analisar_rostos_por_cena(
        caminho_entrada, cenas, amostras_por_cena=amostras_cena
    )

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

    print(f"   🎞️ Processando {total_frames} frames...")
    frame_idx = 0
    erro_pipe = False

    # Suavização do crop: dentro da mesma cena o crop desliza suavemente
    # até o alvo (sem tremer); em corte de cena ele salta seco — exatamente
    # como um editor humano trabalha.
    inicios_cena = {c["frame_ini"] for c in cenas}
    ALPHA_SUAVE = 0.18  # fração da distância percorrida por frame
    x_suave = None

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

        # Corte de cena: crop salta direto para o novo alvo (corte seco)
        if frame_idx in inicios_cena:
            x_suave = xa_suave = xb_suave = None

        # Único modo de crop: 9:16 de 1 alvo. "CENTRAL" (0 ou 2+ pessoas)
        # usa x=0.5 fixo; "SOLO_A" segue a pessoa única detectada.
        x_suave = _aproximar(x_suave, p["xa"])
        x_crop = _calcular_x_crop(x_suave, largura, crop_w_916)
        cortado = frame[0:altura, x_crop:x_crop + crop_w_916]
        frame_final = cv2.resize(cortado, (saida_w, saida_h), interpolation=INTERPOLACAO_EXPORT)

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
    stderr = processo_ffmpeg.stderr.read().decode("utf-8", errors="replace")
    codigo = processo_ffmpeg.wait()

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

        posicoes_x, posicoes_y = _filtrar_rostos_na_zona_de_cabeca(rostos_cena)

        # Agrupa as posições encontradas NESTA cena
        cena.update(_agrupar_posicoes_cena(posicoes_x, posicoes_y))

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
    return [r["x"] for r in usar], [r["y"] for r in usar]


def _agrupar_posicoes_cena(posicoes_x: list, posicoes_y: list = None) -> dict:
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
                "lado_a_y": Y_PADRAO, "lado_b_y": Y_PADRAO}

    pares = sorted(zip(
        posicoes_x,
        posicoes_y if posicoes_y and len(posicoes_y) == len(posicoes_x)
        else [Y_PADRAO] * len(posicoes_x),
    ))
    xs = [p[0] for p in pares]
    ys = [p[1] for p in pares]

    # Se todas as posições estão num intervalo estreito, é uma pessoa só.
    # 0.28 tolera movimentação na cadeira sem virar "duas pessoas".
    if xs[-1] - xs[0] < 0.28:
        centro = float(np.median(xs))
        centro_y = float(np.clip(np.median(ys), 0.15, 0.55))
        return {"n_pessoas": 1, "lado_a": centro, "lado_b": centro,
                "lado_a_y": centro_y, "lado_b_y": centro_y}

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
        return {"n_pessoas": 1, "lado_a": centro, "lado_b": centro,
                "lado_a_y": centro_y, "lado_b_y": centro_y}

    return {
        "n_pessoas": 2,
        "lado_a": _mediana(clusters[0], 0),
        "lado_b": _mediana(clusters[1], 0),
        "lado_a_y": float(np.clip(_mediana(clusters[0], 1), 0.15, 0.55)),
        "lado_b_y": float(np.clip(_mediana(clusters[1], 1), 0.15, 0.55)),
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

    for cena in cenas:
        ini, fim = cena["frame_ini"], cena["frame_fim"]
        xa, xb = cena["lado_a"], cena["lado_b"]
        ya = cena.get("lado_a_y", Y_PADRAO)
        yb = cena.get("lado_b_y", Y_PADRAO)

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
                                "ya": Y_PADRAO, "yb": Y_PADRAO}
                ultimo_modo_valido, ultimo_xa, ultimo_xb = "SOLO_A", x_falante, x_falante
            else:
                # Herda o enquadramento da última cena que tinha gente.
                for f in range(ini, min(fim, total_frames)):
                    plano[f] = {"modo": ultimo_modo_valido, "xa": ultimo_xa, "xb": ultimo_xb,
                                "ya": ultimo_ya, "yb": ultimo_yb}
            continue

        if cena["n_pessoas"] == 1:
            ultimo_modo_valido = "SOLO_A"
            ultimo_xa = xa
            ultimo_xb = xa
            ultimo_ya = ya
            ultimo_yb = ya
            for f in range(ini, min(fim, total_frames)):
                plano[f] = {"modo": "SOLO_A", "xa": xa, "xb": xa, "ya": ya, "yb": ya}
            continue

        # Duas ou mais pessoas: crop segue QUEM ESTÁ FALANDO (posicoes_falante
        # — voz + movimento labial, já validado), não a posição de rosto por
        # cena. A posição de rosto por cena (clustering em "lado A/lado B")
        # já mirou num objeto decorativo com formato de rosto (busto na
        # estante); quem-fala é o único sinal 100% confiável — decoração
        # nunca fala. Sem fala detectada no momento, mantém o último alvo
        # válido (nunca pula pro centro no meio de uma cena só por silêncio).
        # Ver seção 10/11 do RELATORIO_COMPLETO_2026-07-03.md.
        x_alvo_atual = ultimo_xa if ultimo_modo_valido != "CENTRAL" else 0.5
        for f in range(ini, min(fim, total_frames)):
            pos = posicoes_falante[f] if f < len(posicoes_falante) else None
            if pos is not None:
                x_alvo_atual = pos
            plano[f] = {"modo": "SOLO_A", "xa": x_alvo_atual, "xb": x_alvo_atual,
                        "ya": Y_PADRAO, "yb": Y_PADRAO}

        ultimo_modo_valido = "SOLO_A"
        ultimo_xa = ultimo_xb = x_alvo_atual
        ultimo_ya = ultimo_yb = Y_PADRAO

    # Preenche buracos — usa último modo válido, nunca CENTRAL
    ultimo = {"modo": ultimo_modo_valido, "xa": ultimo_xa, "xb": ultimo_xb,
              "ya": ultimo_ya, "yb": ultimo_yb}
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
