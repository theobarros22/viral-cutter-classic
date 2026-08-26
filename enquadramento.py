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
from ffmpeg_utils import argumentos_encoder, localizar_ffmpeg, obter_info_video


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

# Teto de plausibilidade: num podcast nenhum rosto ocupa um terco da largura
# do quadro. Medido no clipe 13 do Papo Reto #60, um falso positivo de
# tam=0.358 na estante (x=0.81) fazia a cena inteira cair em "sem modo
# seguro" — descartar o alvo devolve o crop central aberto, que e o certo
# para um plano aberto.
MAX_TAMANHO_ROSTO = 0.32

# Um bloco de cena so pode conter posicoes de rosto que caibam TODAS no
# mesmo crop. O criterio nao e um limiar arbitrario: e a folga real que
# sobra no quadro depois da cabeca e das margens. Num 9:16 sobre fonte 16:9
# o crop ocupa 0.317 da largura e a cabeca 0.225 — sobram ~0.07 no total.
# Um limiar maior que essa folga (era 0.07) aceita como "mesmo plano"
# variacoes que ja cortam a pessoa.
PROPORCAO_SAIDA_PADRAO = 1080 / 1920  # todas as resolucoes de saida sao 9:16

# A analise visual amostra por TEMPO. Um numero fixo por cena deixava 6
# segundos entre amostras em cenas longas — tempo suficiente para o podcast
# trocar de camera varias vezes sem que a analise percebesse.
INTERVALO_AMOSTRA_PADRAO_S = 0.8
MAX_AMOSTRAS_POR_CENA = 400  # teto de seguranca para cenas muito longas
# Dividir o shot para nao cortar ninguem gera mais blocos; o grafo do
# FFmpeg da conta de bem mais que os 50 originais.
LIMITE_SHOTS_FFMPEG = 200

# Camera virtual: quanto o quadro persegue a pessoa a cada nova leitura e
# qual a velocidade maxima de deslocamento (em larguras de quadro por
# segundo). Valores altos tremem; baixos ficam para tras e cortam.
FATOR_SUAVIZACAO_CAMERA = 0.45
VELOCIDADE_MAXIMA_CAMERA = 0.25
MAX_PONTOS_TRAJETORIA = 60  # teto por shot, para a expressao nao explodir
# Salto de posicao que so um corte de camera explica. Abaixo disso o quadro
# acompanha; acima, corta seco.
SALTO_MAXIMO_MESMA_CAMERA = 0.12
LIMIAR_MUDANCA_PLANO_ZOOM = 1.35

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

# ── Enquadramento seguro (regra definitiva) ───────────────────────────────────
# Nenhum clipe é concluído com a pessoa principal fora do quadro ou encostada
# na borda. A caixa humana é estimada a partir do rosto detectado e precisa
# caber no crop com margem livre nas quatro bordas.
# A validação tem DOIS níveis. Só a CABEÇA é obrigatória: num close de
# podcast os ombros simplesmente não cabem num 9:16 e exigi-los reprovava
# até os quadros corretos. Os ombros entram como preferência, para escolher
# o melhor centro — nunca para reprovar o clipe.
MARGEM_SEGURA_BORDA = 0.035     # 3.5% do lado do crop livre em cada borda
LARGURA_CABECA_ROSTO = 1.5      # cabeça ≈ 1.5x a largura do rosto detectado
ALTURA_CABECA_META = 0.85       # meia altura da cabeça, em alturas de rosto
LARGURA_OMBROS_ROSTO = 2.4      # vão dos ombros ≈ 2.4x a largura do rosto
ALTURA_ROSTO_SOBRE_LARGURA = 1.3  # rosto é mais alto que largo
ALTURA_CABECA_ROSTO = 1.0       # topo da cabeça acima do centro do rosto
ALTURA_TRONCO_ROSTO = 3.0       # tronco abaixo do centro do rosto
TOLERANCIA_BORDA_PX = 2         # crop colado na borda da fonte conta como ok

# Dois "lados" so viram duas PESSOAS quando ficam mais afastados que a soma
# dos meios-ombros e tem rostos de tamanho plausivel entre si. Sem isso, um
# rosto espurio a poucos decimos do falante virava lado B e o split screen
# mostrava a MESMA pessoa nos dois paineis.
RAZAO_MINIMA_ROSTOS = 0.45

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
    # O usuário prioriza enquadramento aberto: em fonte horizontal o crop
    # usa toda a altura disponível, sem zoom adicional no rosto.
    largura_desejada = largura_max
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


def _caixa_humana(alvo, largura: int, altura: int):
    """Estima a caixa da pessoa (cabeça + ombros + tronco) a partir do rosto.

    Retorna (x0, y0, x1, y1) em pixels, já limitada ao quadro original, ou
    None quando o alvo não tem tamanho de rosto confiável.
    """
    try:
        tam = float(alvo[2])
    except (TypeError, IndexError, ValueError):
        return None
    if not MIN_TAMANHO_ROSTO <= tam <= MAX_TAMANHO_ROSTO:
        return None

    cx = float(alvo[0]) * largura
    cy = float(alvo[1]) * altura
    rosto_w = tam * largura
    rosto_h = rosto_w * ALTURA_ROSTO_SOBRE_LARGURA

    x0 = cx - rosto_w * LARGURA_OMBROS_ROSTO / 2.0
    x1 = cx + rosto_w * LARGURA_OMBROS_ROSTO / 2.0
    y0 = cy - rosto_h * ALTURA_CABECA_ROSTO
    y1 = cy + rosto_h * ALTURA_TRONCO_ROSTO

    return (
        max(0.0, min(float(largura), x0)),
        max(0.0, min(float(altura), y0)),
        max(0.0, min(float(largura), x1)),
        max(0.0, min(float(altura), y1)),
    )


def _caixa_cabeca(alvo, largura: int, altura: int):
    """Caixa OBRIGATÓRIA: cabeça inteira, do topo ao queixo, com folga.

    É o que nunca pode ser cortado. Ombros e tronco são tratados como
    preferência em `_caixa_humana`.
    """
    try:
        tam = float(alvo[2])
    except (TypeError, IndexError, ValueError):
        return None
    if not MIN_TAMANHO_ROSTO <= tam <= MAX_TAMANHO_ROSTO:
        return None

    cx = float(alvo[0]) * largura
    cy = float(alvo[1]) * altura
    rosto_w = tam * largura
    rosto_h = rosto_w * ALTURA_ROSTO_SOBRE_LARGURA

    meia_w = rosto_w * LARGURA_CABECA_ROSTO / 2.0
    meia_h = rosto_h * ALTURA_CABECA_META

    return (
        max(0.0, min(float(largura), cx - meia_w)),
        max(0.0, min(float(altura), cy - meia_h)),
        max(0.0, min(float(largura), cx + meia_w)),
        max(0.0, min(float(altura), cy + meia_h)),
    )


def _caixas_cabecas(alvos: list, largura: int, altura: int) -> list:
    """Caixas de cabeça válidas — o critério que reprova um enquadramento."""
    caixas = [_caixa_cabeca(a, largura, altura) for a in (alvos or [])]
    return [c for c in caixas if c is not None]


def _caixas_humanas(alvos: list, largura: int, altura: int) -> list:
    """Caixas humanas válidas dos alvos informados (descarta rostos duvidosos)."""
    caixas = [_caixa_humana(a, largura, altura) for a in (alvos or [])]
    return [c for c in caixas if c is not None]


def _validar_crop_alvos(crop, caixas: list, largura: int, altura: int) -> tuple:
    """Verifica se o crop contém as pessoas com margem segura nas bordas.

    Uma pessoa que já está encostada na borda da FONTE só é aceita quando o
    crop também encosta naquela borda — assim nada é cortado além do que o
    vídeo original já cortava.
    """
    if not caixas:
        return False, "sem_alvo_valido"

    x, y, w, h = crop
    margem_x = MARGEM_SEGURA_BORDA * w
    margem_y = MARGEM_SEGURA_BORDA * h

    for x0, y0, x1, y1 in caixas:
        if (x1 - x0) + 2 * margem_x > w or (y1 - y0) + 2 * margem_y > h:
            return False, "pessoa_maior_que_o_quadro"
        if x0 < x + margem_x and x > TOLERANCIA_BORDA_PX:
            return False, "pessoa_cortada_na_esquerda"
        if x1 > x + w - margem_x and (x + w) < largura - TOLERANCIA_BORDA_PX:
            return False, "pessoa_cortada_na_direita"
        if y0 < y + margem_y and y > TOLERANCIA_BORDA_PX:
            return False, "cabeca_cortada_no_topo"
        if y1 > y + h - margem_y and (y + h) < altura - TOLERANCIA_BORDA_PX:
            return False, "corpo_cortado_embaixo"
    return True, ""


def _ajustar_crop_para_caixas(crop, caixas: list, largura: int, altura: int):
    """Desloca o crop (sem mudar o tamanho) para cobrir as caixas humanas."""
    if not caixas:
        return crop
    x, y, w, h = crop
    margem_x = MARGEM_SEGURA_BORDA * w
    margem_y = MARGEM_SEGURA_BORDA * h

    alvo_x0 = min(c[0] for c in caixas) - margem_x
    alvo_x1 = max(c[2] for c in caixas) + margem_x
    alvo_y0 = min(c[1] for c in caixas) - margem_y
    alvo_y1 = max(c[3] for c in caixas) + margem_y

    if alvo_x1 - alvo_x0 <= w:
        centro = (alvo_x0 + alvo_x1) / 2.0
        x = int(round(centro - w / 2.0))
    if alvo_y1 - alvo_y0 <= h:
        centro = (alvo_y0 + alvo_y1) / 2.0
        y = int(round(centro - h / 2.0))

    x = max(0, min(largura - w, x))
    y = max(0, min(altura - h, y))
    return (x, y, w, h)


def _crop_validado(alvos: list, largura: int, altura: int, proporcao: float) -> tuple:
    """Crop conservador já corrigido e validado. Retorna (crop, ok, motivo)."""
    crop = _calcular_crop_seguro(alvos, largura, altura, proporcao)
    cabecas = _caixas_cabecas(alvos, largura, altura)
    if not cabecas:
        # Sem rosto confiável: mantém o crop central, mas sinaliza que a cena
        # não tem foco humano validado (B-roll ou detecção fraca).
        return crop, False, "sem_alvo_valido"

    # 1ª tentativa: enquadrar pessoa inteira (cabeça + ombros).
    corpos = _caixas_humanas(alvos, largura, altura)
    if corpos:
        candidato = _ajustar_crop_para_caixas(crop, corpos, largura, altura)
        if _validar_crop_alvos(candidato, cabecas, largura, altura)[0]:
            return candidato, True, ""

    # 2ª tentativa: garantir ao menos a cabeça inteira com margem.
    crop = _ajustar_crop_para_caixas(crop, cabecas, largura, altura)
    ok, motivo = _validar_crop_alvos(crop, cabecas, largura, altura)
    if not ok and motivo == "pessoa_maior_que_o_quadro":
        motivo = "cabeca_maior_que_o_quadro"
    return crop, ok, motivo


def _geometria_fallback_split(largura: int, altura: int, saida_w: int, saida_h: int) -> dict:
    """Dois painéis horizontais empilhados preenchendo todo o 9:16, sem blur."""
    topo_h = saida_h // 2
    base_h = saida_h - topo_h

    def painel(destino_h, esquerda):
        proporcao = saida_w / float(destino_h)
        crop_h = min(altura, int(round(largura / proporcao)))
        crop_h = max(2, crop_h - crop_h % 2)
        crop_w = min(largura, int(round(crop_h * proporcao)))
        crop_w = max(2, crop_w - crop_w % 2)
        x = max(0, min(largura - crop_w, esquerda))
        y = max(0, (altura - crop_h) // 2)
        return (x, y, crop_w, crop_h)

    return {
        "tipo": "split",
        "modo_final": "FALLBACK_SPLIT",
        "top_crop": painel(topo_h, 0),
        "top_scale": (saida_w, topo_h),
        "bot_crop": painel(base_h, largura),
        "bot_scale": (saida_w, base_h),
    }


def _detalhar_erro_ffmpeg(stderr: str, codigo: int) -> str:
    """Nunca devolve mensagem vazia.

    Com -loglevel error o FFmpeg pode morrer sem escrever nada no stderr — foi
    o que aconteceu no clipe 14 do Papo Reto #60, e os dois motores relataram
    "falhou: " sem uma pista sequer. Sem o codigo de saida nao da para separar
    disputa por encoder de erro de parametro.
    """
    texto = (stderr or "").strip()
    if texto:
        return texto[-600:]
    if codigo in (-1073741819, 3221225477):
        return "processo encerrado pelo sistema (acesso invalido)"
    return (
        f"sem mensagem no stderr; codigo {codigo}. "
        "Causas comuns: encoder NVENC ocupado por outro processo, "
        "arquivo de saida em uso ou disco sem espaco."
    )


def _registrar(relatorio, motivo: str, revisar: bool = False, instante=None) -> None:
    """Acumula motivos de segurança do enquadramento para o pipeline.

    `instante` (segundos) marca ONDE o problema acontece — sem isso a revisão
    manual tinha de assistir o clipe inteiro procurando o quadro ruim.
    """
    if relatorio is None or not motivo:
        return
    motivos = relatorio.setdefault("motivos", [])
    if motivo not in motivos:
        motivos.append(motivo)
    if revisar:
        relatorio["revisar"] = True
        if instante is not None:
            instantes = relatorio.setdefault("instantes", [])
            marca = round(float(instante), 1)
            if marca not in instantes:
                instantes.append(marca)


def _compor_frame_seguro(frame, plano: dict, saida_w: int, saida_h: int, relatorio: dict = None):
    """Compõe o frame usando o MESMO layout validado do motor FFmpeg."""
    altura, largura = frame.shape[:2]
    filtros = _calcular_filtros_shot(
        plano, largura, altura, saida_w, saida_h, relatorio=relatorio
    )

    def recortar(crop, escala):
        x, y, w, h = crop
        return cv2.resize(
            frame[y:y + h, x:x + w], escala, interpolation=INTERPOLACAO_EXPORT
        )

    if filtros["tipo"] == "solo":
        return recortar(filtros["crop"], filtros["scale"])

    topo = recortar(filtros["top_crop"], filtros["top_scale"])
    base = recortar(filtros["bot_crop"], filtros["bot_scale"])
    return np.vstack((topo, base))


def aplicar_enquadramento(
    caminho_entrada: str,
    caminho_saida: str,
    posicoes_falante: list,
    pessoas_priorizadas: list = None,
    qualidade: str = "1080p",
    perfil: str = "equilibrado",
    relatorio: dict = None,
) -> bool:
    """
    Aplica enquadramento 9:16 ciente dos cortes de cena.

    `relatorio` (opcional) é preenchido com o resultado da validação de
    enquadramento seguro: {"revisar": bool, "motivos": [...]}. Quando
    `revisar` volta True, a pessoa principal não coube com margem segura em
    NENHUM modo e o clipe não deve ser considerado concluído.
    """
    saida_w, saida_h = RESOLUCOES.get(qualidade, (1080, 1920))
    if relatorio is None:
        relatorio = {}
    relatorio.setdefault("revisar", False)
    relatorio.setdefault("motivos", [])

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
    amostras_cena = 3 if perfil == "rapido" else (30 if perfil == "qualidade" else 25)
    intervalo_amostra = (
        1.5 if perfil == "rapido" else (0.4 if perfil == "qualidade" else 0.8)
    )

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
            caminho_entrada, cenas, amostras_por_cena=amostras_cena,
            intervalo_amostra_s=intervalo_amostra,
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

    # ── Passo 4: Renderização de Alta Performance (FFmpeg direto ou Pipe Fallback)
    segmentos = _agrupar_planos_em_segmentos(plano, fps)
    # Reancora cada shot no que realmente aparece no video naquele intervalo,
    # reaproveitando as amostras densas ja coletadas pela analise de cena.
    mapa_amostras = {
        quadro: rostos
        for cena in cenas
        for quadro, rostos in (cena.get("amostras") or [])
    }
    segmentos = _ajustar_segmentos_pelos_frames(
        caminho_entrada, segmentos, largura, altura, fps, mapa_amostras
    )

    # Render rápido quando o plano é composto por blocos estáveis (<= 50 shots)
    if segmentos and len(segmentos) <= LIMITE_SHOTS_FFMPEG:
        print(f"   🚀 Renderizando {total_frames} frames ({len(segmentos)} bloco(s) estáveis) via FFmpeg nativo...")
        sucesso_ffmpeg = _renderizar_enquadramento_ffmpeg(
            caminho_entrada, caminho_saida, segmentos, largura, altura,
            saida_w, saida_h, perfil=perfil, relatorio=relatorio
        )
        if sucesso_ffmpeg and os.path.isfile(caminho_saida) and os.path.getsize(caminho_saida) > 1000:
            _reportar_seguranca(relatorio)
            return True
        print("   ⚠️ Grafo FFmpeg indisponível/falhou. Acionando fallback frame a frame seguro...")
    else:
        print("   ℹ️ Transições complexas detectadas. Usando renderizador seguro por pipe...")

    # Fallback seguro frame a frame via pipe
    sucesso = _renderizar_enquadramento_pipe(
        caminho_entrada, caminho_saida, plano, largura, altura, fps,
        saida_w, saida_h, total_frames, perfil=perfil, relatorio=relatorio
    )
    if sucesso:
        _reportar_seguranca(relatorio)
    return sucesso


def _reportar_seguranca(relatorio: dict) -> None:
    """Imprime o resultado da validação de enquadramento seguro."""
    motivos = relatorio.get("motivos") or []
    if relatorio.get("revisar"):
        instantes = relatorio.get("instantes") or []
        onde = f" em {', '.join(f'{t:.1f}s' for t in instantes[:6])}" if instantes else ""
        print(f"   ⚠️ Enquadramento marcado para REVISAR: {', '.join(motivos)}{onde}")
        return
    if motivos:
        print(f"   ✅ Enquadramento concluído (ajustes: {', '.join(motivos)}).")
    else:
        print("   ✅ Enquadramento concluído com sucesso!")


def _agrupar_planos_em_segmentos(plano: list, fps: float) -> list:
    """Agrupa frames contíguos com mesmo enquadramento em shots temporais estáveis."""
    if not plano:
        return []
    fps = fps if fps and fps > 0 else 30.0
    segmentos = []
    seg_atual = None

    def _chave_plano(p):
        return (
            p.get("modo", "SOLO_A"),
            round(float(p.get("xa", 0.5)), 4),
            round(float(p.get("ya", 0.4)), 4),
            round(float(p.get("ta", 0.0)), 4),
            round(float(p.get("xb", p.get("xa", 0.5))), 4),
            round(float(p.get("yb", p.get("ya", 0.4))), 4),
            round(float(p.get("tb", p.get("ta", 0.0))), 4),
        )

    for f_idx, p in enumerate(plano):
        chave = _chave_plano(p)
        if seg_atual is None or chave != seg_atual["chave"]:
            if seg_atual is not None:
                seg_atual["frame_fim"] = f_idx
                seg_atual["end_s"] = f_idx / fps
                segmentos.append(seg_atual)
            seg_atual = {
                "chave": chave,
                "plano": p,
                "frame_ini": f_idx,
                "frame_fim": f_idx + 1,
                "start_s": f_idx / fps,
                "end_s": (f_idx + 1) / fps,
            }
        else:
            seg_atual["frame_fim"] = f_idx + 1
            seg_atual["end_s"] = (f_idx + 1) / fps

    if seg_atual is not None:
        segmentos.append(seg_atual)

    return segmentos


def _ajustar_segmentos_pelos_frames(
    caminho_video: str, segmentos: list, largura: int, altura: int, fps: float,
    amostras_por_frame: dict = None,
) -> list:
    """Reancora cada shot nos rostos que realmente aparecem no seu intervalo.

    Todo o resto do calculo trabalha com medianas: se a analise errar o alvo,
    a validacao aprova um crop que corta a pessoa, porque ela confere o crop
    contra o ALVO — nunca contra o frame. Aqui o alvo vem do que existe de
    fato no video, e o shot se divide quando as posicoes observadas nao cabem
    num crop unico.

    Reaproveita as amostras que a analise de cena ja coletou (uma a cada
    ~0.8s). Amostrar de novo so tres frames por shot deixava passar o
    movimento entre eles — foi assim que sobraram cortes na auditoria.
    """
    if not segmentos:
        return segmentos

    amostras_por_frame = amostras_por_frame or {}
    largura_crop = _largura_crop_normalizada(largura, altura)
    ajustados = []
    detector = None
    cap = None

    def _posicoes_do_intervalo(ini_frame, fim_frame):
        encontradas = []
        for quadro in sorted(amostras_por_frame):
            if quadro < ini_frame:
                continue
            if quadro >= fim_frame:
                break
            rostos = [
                r for r in amostras_por_frame[quadro]
                if MIN_TAMANHO_ROSTO <= r.get("w", 0) <= MAX_TAMANHO_ROSTO
            ]
            if rostos:
                maior = max(rostos, key=lambda r: r["w"])
                encontradas.append((quadro, float(maior["x"]),
                                    float(maior["y"]), float(maior["w"])))
        return encontradas

    try:
        for seg in segmentos:
            ini, fim = seg["frame_ini"], seg["frame_fim"]
            posicoes = _posicoes_do_intervalo(ini, fim)

            if not posicoes:
                # Shot curto entre duas amostras: le o proprio video.
                if detector is None:
                    from rostos import _inicializar_detector, detectar_rostos_robusto
                    detector = _inicializar_detector()
                    cap = cv2.VideoCapture(caminho_video)
                if detector is not None and cap is not None:
                    from rostos import detectar_rostos_robusto
                    meio = (ini + fim) // 2
                    cap.set(cv2.CAP_PROP_POS_FRAMES, meio)
                    ok, frame = cap.read()
                    if ok:
                        rostos = [
                            r for r in detectar_rostos_robusto(frame, detector)
                            if MIN_TAMANHO_ROSTO <= r.get("w", 0) <= MAX_TAMANHO_ROSTO
                        ]
                        if rostos:
                            maior = max(rostos, key=lambda r: r["w"])
                            posicoes = [(meio, float(maior["x"]),
                                         float(maior["y"]), float(maior["w"]))]

            if not posicoes:
                ajustados.append(seg)
                continue

            modo = seg["plano"].get("modo", "SOLO_A")
            if modo == "FALLBACK_SPLIT":
                ajustados.append(seg)
                continue

            if modo == "SPLIT":
                # Cada painel tem seu proprio alvo. Sem reancorar, os dois
                # lados seguem a mediana da cena e podem mirar em ninguem.
                ajustados.append(_reancorar_split(seg, amostras_por_frame, ini, fim))
                continue

            def _shot(p_ini, p_fim, grupo):
                xs = [p[1] for p in grupo]
                plano = dict(seg["plano"])
                plano["xa"] = plano["xb"] = (min(xs) + max(xs)) / 2.0
                plano["ya"] = plano["yb"] = float(np.median([p[2] for p in grupo]))
                plano["ta"] = plano["tb"] = max(p[3] for p in grupo)
                trajetoria = _suavizar_trajetoria(grupo, fps)
                if len(trajetoria) > MAX_PONTOS_TRAJETORIA:
                    passo = len(trajetoria) // MAX_PONTOS_TRAJETORIA + 1
                    trajetoria = trajetoria[::passo] + [trajetoria[-1]]
                return {
                    **seg,
                    "plano": plano,
                    "trajetoria": trajetoria,
                    "frame_ini": p_ini,
                    "frame_fim": p_fim,
                    "start_s": p_ini / fps,
                    "end_s": p_fim / fps,
                    "fps": fps,
                }

            # Acumula enquanto for a MESMA camera. Deslocamento dentro do
            # plano nao quebra mais o shot: o quadro acompanha a pessoa pela
            # trajetoria. So um salto brusco (corte de camera que passou
            # despercebido) justifica um corte seco.
            grupo = [posicoes[0]]
            inicio_bloco = ini
            for anterior, posicao in zip(posicoes, posicoes[1:]):
                salto = abs(posicao[1] - anterior[1])
                mudou_zoom = _mudou_de_zoom(
                    (anterior[1], anterior[3]), (posicao[1], posicao[3])
                )
                if salto <= SALTO_MAXIMO_MESMA_CAMERA and not mudou_zoom:
                    grupo.append(posicao)
                    continue
                ajustados.append(_shot(inicio_bloco, posicao[0], grupo))
                inicio_bloco = posicao[0]
                grupo = [posicao]
            ajustados.append(_shot(inicio_bloco, fim, grupo))
    finally:
        if cap is not None:
            cap.release()
        if detector is not None:
            from rostos import _fechar_detector
            _fechar_detector(detector)

    return ajustados


def _reancorar_split(seg: dict, amostras_por_frame: dict, ini: int, fim: int) -> dict:
    """Aponta cada painel do split para o rosto que realmente esta daquele lado."""
    esquerda, direita = [], []
    for quadro in range(ini, fim):
        rostos = amostras_por_frame.get(quadro)
        if not rostos:
            continue
        validos = [
            r for r in rostos
            if MIN_TAMANHO_ROSTO <= r.get("w", 0) <= MAX_TAMANHO_ROSTO
        ]
        if len(validos) < 2:
            continue
        validos.sort(key=lambda r: r["x"])
        esquerda.append(validos[0])
        direita.append(validos[-1])

    if not esquerda or not direita:
        return seg

    plano = dict(seg["plano"])
    plano["xa"] = float(np.median([r["x"] for r in esquerda]))
    plano["ya"] = float(np.median([r["y"] for r in esquerda]))
    plano["ta"] = float(np.median([r["w"] for r in esquerda]))
    plano["xb"] = float(np.median([r["x"] for r in direita]))
    plano["yb"] = float(np.median([r["y"] for r in direita]))
    plano["tb"] = float(np.median([r["w"] for r in direita]))
    return {**seg, "plano": plano}


def _suavizar_trajetoria(posicoes: list, fps: float) -> list:
    """Transforma posicoes observadas numa trajetoria estavel de camera.

    Duas coisas importam aqui: nao tremer (o rosto oscila alguns pixels entre
    deteccoes) e nao ficar para tras quando a pessoa se desloca de verdade.
    Uma media exponencial resolve o tremor; o limite de velocidade impede
    que o quadro dispare atras de uma deteccao isolada e errada.
    """
    if not posicoes:
        return []

    suave = []
    atual = posicoes[0][1]
    for quadro, x, _y, _w in posicoes:
        alvo = float(x)
        atual += (alvo - atual) * FATOR_SUAVIZACAO_CAMERA
        if suave:
            quadros = max(1, quadro - suave[-1][0])
            limite = VELOCIDADE_MAXIMA_CAMERA * quadros / max(1.0, fps)
            anterior = suave[-1][1]
            atual = max(anterior - limite, min(anterior + limite, atual))
        suave.append((quadro, atual))
    return suave


def _expressao_crop_x(trajetoria: list, largura: int, crop_w: int,
                      fps: float, inicio_frame: int) -> str:
    """Expressao de tempo para o filtro crop do FFmpeg.

    Permite que o quadro acompanhe a pessoa dentro do mesmo shot, em vez de
    ficar preso num ponto fixo. Sem isso, qualquer deslocamento maior que a
    folga do quadro corta a pessoa — e num podcast ela se mexe o tempo todo.
    """
    if len(trajetoria) < 2:
        return None

    limite = max(0, largura - crop_w)
    pontos = []
    for quadro, x in trajetoria:
        tempo = max(0.0, (quadro - inicio_frame) / max(1.0, fps))
        posicao = int(round(x * largura - crop_w / 2.0))
        pontos.append((tempo, max(0, min(limite, posicao))))

    # Interpolacao linear encadeada: entre dois pontos-chave o quadro desliza.
    expressao = f"{pontos[-1][1]}"
    for (t0, x0), (t1, x1) in reversed(list(zip(pontos, pontos[1:]))):
        duracao = max(1e-3, t1 - t0)
        trecho = f"{x0}+({x1}-{x0})*(t-{t0:.3f})/{duracao:.3f}"
        expressao = f"if(lt(t,{t1:.3f}),{trecho},{expressao})"
    return expressao


def _calcular_filtros_shot(
    plano: dict,
    largura: int,
    altura: int,
    saida_w: int,
    saida_h: int,
    relatorio: dict = None,
    instante=None,
):
    """Resolve o layout do shot já VALIDADO contra corte de pessoa.

    Fonte única de verdade para os dois motores (grafo FFmpeg e pipe frame a
    frame). Degrada em cascata: modo pedido → SPLIT → dois painéis horizontais.
    Se nenhum modo for seguro, marca o clipe para revisão.
    """
    modo = plano.get("modo", "SOLO_A")
    alvo_a = (
        float(plano.get("xa", 0.5)),
        float(plano.get("ya", 0.40)),
        float(plano.get("ta", 0.0)),
    )
    alvo_b = (
        float(plano.get("xb", plano.get("xa", 0.5))),
        float(plano.get("yb", 0.40)),
        float(plano.get("tb", plano.get("ta", 0.0))),
    )

    def _solo(alvos, rotulo):
        crop, ok, motivo = _crop_validado(
            alvos, largura, altura, saida_w / float(saida_h)
        )
        layout = {
            "tipo": "solo",
            "modo_final": rotulo,
            "crop": crop,
            "scale": (saida_w, saida_h),
        }
        return layout, ok, motivo

    def _split():
        topo_h = saida_h // 2
        base_h = saida_h - topo_h
        crop_a, ok_a, motivo_a = _crop_validado(
            [alvo_a], largura, altura, saida_w / float(topo_h)
        )
        crop_b, ok_b, motivo_b = _crop_validado(
            [alvo_b], largura, altura, saida_w / float(base_h)
        )
        layout = {
            "tipo": "split",
            "modo_final": "SPLIT",
            "top_crop": crop_a,
            "top_scale": (saida_w, topo_h),
            "bot_crop": crop_b,
            "bot_scale": (saida_w, base_h),
        }
        return layout, (ok_a and ok_b), (motivo_a or motivo_b)

    def _fallback():
        layout = _geometria_fallback_split(largura, altura, saida_w, saida_h)
        caixas = _caixas_cabecas([alvo_a, alvo_b], largura, altura)
        if not caixas:
            # Sem gente detectada: os dois painéis cobrem a largura inteira,
            # então não há o que cortar — é B-roll, não é falha.
            return layout, True, ""
        # Basta a pessoa caber INTEIRA em um dos painéis para o quadro ser seguro.
        for caixa in caixas:
            seguro = any(
                _validar_crop_alvos(layout[chave], [caixa], largura, altura)[0]
                for chave in ("top_crop", "bot_crop")
            )
            if not seguro:
                return layout, False, "sem_modo_seguro"
        return layout, True, ""

    if modo == "FALLBACK_SPLIT":
        layout, ok, motivo = _fallback()
        if not ok:
            _registrar(relatorio, motivo, revisar=True, instante=instante)
        return layout

    if modo in ("SOLO_A", "SOLO_B"):
        layout, ok, motivo = _solo(
            [alvo_a if modo == "SOLO_A" else alvo_b], modo
        )
    elif modo == "GRUPO":
        layout, ok, motivo = _solo([alvo_a, alvo_b], "GRUPO")
    elif modo == "SPLIT":
        layout, ok, motivo = _split()
    else:
        layout, ok, motivo = _solo([alvo_a], "SOLO_A")

    if ok:
        return layout

    # Cena sem rosto confiável: o crop central segue válido (B-roll / herança).
    if motivo == "sem_alvo_valido":
        _registrar(relatorio, "cena_sem_rosto_confiavel")
        return layout

    _registrar(relatorio, motivo)

    # SPLIT só faz sentido com duas pessoas distintas — com um alvo só ele
    # duplicaria a mesma pessoa nos dois painéis.
    tem_dois_alvos = (
        len(_caixas_humanas([alvo_a, alvo_b], largura, altura)) == 2
        and abs(alvo_a[0] - alvo_b[0]) > 0.02
    )
    if modo != "SPLIT" and tem_dois_alvos:
        layout_split, ok_split, motivo_split = _split()
        if ok_split:
            _registrar(relatorio, "degradado_para_split")
            return layout_split
        motivo = motivo_split or motivo

    layout_fb, ok_fb, motivo_fb = _fallback()
    if ok_fb:
        _registrar(relatorio, "degradado_para_paineis_horizontais")
        return layout_fb

    _registrar(relatorio, motivo_fb or motivo or "sem_modo_seguro", revisar=True, instante=instante)
    return layout_fb


def _construir_grafo_enquadramento(segmentos: list, largura: int, altura: int, saida_w: int, saida_h: int, relatorio: dict = None) -> str:
    """Monta o filter_complex completo otimizado para o FFmpeg."""
    n_seg = len(segmentos)
    if n_seg == 0:
        return ""

    if n_seg == 1:
        shot = _calcular_filtros_shot(segmentos[0]["plano"], largura, altura, saida_w, saida_h, relatorio=relatorio, instante=segmentos[0].get("start_s"))
        if shot["tipo"] == "solo":
            x, y, w, h = shot["crop"]
            sw, sh = shot["scale"]
            expressao = _expressao_crop_x(
                segmentos[0].get("trajetoria") or [], largura, w,
                segmentos[0].get("fps", 30.0), segmentos[0].get("frame_ini", 0),
            )
            posicao_x = f"'{expressao}'" if expressao else f"{x}"
            return f"[0:v]crop={w}:{h}:{posicao_x}:{y},scale={sw}:{sh}:flags=bilinear,setsar=1[vout]"
        else:
            tx, ty, tw, th = shot["top_crop"]
            tsw, tsh = shot["top_scale"]
            bx, by, bw, bh = shot["bot_crop"]
            bsw, bsh = shot["bot_scale"]
            return (
                f"[0:v]split=2[top_in][bot_in];"
                f"[top_in]crop={tw}:{th}:{tx}:{ty},scale={tsw}:{tsh}:flags=bilinear,setsar=1[top];"
                f"[bot_in]crop={bw}:{bh}:{bx}:{by},scale={bsw}:{bsh}:flags=bilinear,setsar=1[bot];"
                f"[top][bot]vstack,setsar=1[vout]"
            )

    linhas = []
    ramos_in = "".join(f"[in{k}]" for k in range(n_seg))
    linhas.append(f"[0:v]split={n_seg}{ramos_in}")

    for k, seg in enumerate(segmentos):
        start_s = seg["start_s"]
        end_s = seg["end_s"]
        shot = _calcular_filtros_shot(seg["plano"], largura, altura, saida_w, saida_h, relatorio=relatorio, instante=seg.get("start_s"))

        if shot["tipo"] == "solo":
            x, y, w, h = shot["crop"]
            sw, sh = shot["scale"]
            # O trim reinicia o relogio do shot, entao a expressao usa tempo
            # relativo ao proprio shot.
            expressao = _expressao_crop_x(
                seg.get("trajetoria") or [], largura, w,
                seg.get("fps", 30.0), seg.get("frame_ini", 0),
            )
            posicao_x = f"'{expressao}'" if expressao else f"{x}"
            linhas.append(
                f"[in{k}]trim=start={start_s:.3f}:end={end_s:.3f},setpts=PTS-STARTPTS,"
                f"crop={w}:{h}:{posicao_x}:{y},scale={sw}:{sh}:flags=bilinear,setsar=1[v{k}]"
            )
        else:
            tx, ty, tw, th = shot["top_crop"]
            tsw, tsh = shot["top_scale"]
            bx, by, bw, bh = shot["bot_crop"]
            bsw, bsh = shot["bot_scale"]
            linhas.append(
                f"[in{k}]trim=start={start_s:.3f}:end={end_s:.3f},setpts=PTS-STARTPTS,split=2[top_in{k}][bot_in{k}]"
            )
            linhas.append(
                f"[top_in{k}]crop={tw}:{th}:{tx}:{ty},scale={tsw}:{tsh}:flags=bilinear,setsar=1[top{k}]"
            )
            linhas.append(
                f"[bot_in{k}]crop={bw}:{bh}:{bx}:{by},scale={bsw}:{bsh}:flags=bilinear,setsar=1[bot{k}]"
            )
            linhas.append(
                f"[top{k}][bot{k}]vstack,setsar=1[v{k}]"
            )

    concat_in = "".join(f"[v{k}]" for k in range(n_seg))
    linhas.append(f"{concat_in}concat=n={n_seg}:v=1:a=0[vout]")
    return ";".join(linhas)


def _renderizar_enquadramento_ffmpeg(
    caminho_entrada: str,
    caminho_saida: str,
    segmentos: list,
    largura: int,
    altura: int,
    saida_w: int,
    saida_h: int,
    perfil: str = "equilibrado",
    relatorio: dict = None,
) -> bool:
    """Renderiza diretamente pelo FFmpeg filter_complex acelerado por hardware."""
    try:
        filtro_complexo = _construir_grafo_enquadramento(
            segmentos, largura, altura, saida_w, saida_h, relatorio=relatorio
        )
        if not filtro_complexo:
            return False

        cmd = [
            localizar_ffmpeg(), "-y", "-loglevel", "error",
            "-i", caminho_entrada,
            "-filter_complex", filtro_complexo,
            "-map", "[vout]", "-map", "0:a?",
        ]
        cmd += argumentos_encoder(temporario=False, perfil=perfil)
        cmd += [
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-shortest",
            "-movflags", "+faststart",
            caminho_saida,
        ]

        resultado = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if resultado.returncode != 0:
            print(
                "   ⚠️ FFmpeg filter_complex falhou "
                f"(codigo {resultado.returncode}): "
                f"{_detalhar_erro_ffmpeg(resultado.stderr, resultado.returncode)}"
            )
            if os.path.exists(caminho_saida):
                os.remove(caminho_saida)
            return False

        return True
    except Exception as e:
        print(f"   ⚠️ Exceção na renderização direta FFmpeg: {e}")
        if os.path.exists(caminho_saida):
            os.remove(caminho_saida)
        return False


def _renderizar_enquadramento_pipe(
    caminho_entrada: str,
    caminho_saida: str,
    plano: list,
    largura: int,
    altura: int,
    fps: float,
    saida_w: int,
    saida_h: int,
    total_frames: int,
    perfil: str = "equilibrado",
    relatorio: dict = None,
) -> bool:
    """Fallback: processamento frame a frame em Python conectado por pipe ao FFmpeg."""
    cap = cv2.VideoCapture(caminho_entrada)
    if not cap.isOpened():
        cap.release()
        print("   ⚠️ Não foi possível abrir o vídeo para enquadramento.")
        return False

    cmd = [
        localizar_ffmpeg(), "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "bgr24",
        "-s", f"{saida_w}x{saida_h}", "-r", str(fps), "-i", "-",
        "-i", caminho_entrada,
        "-map", "0:v", "-map", "1:a?",
    ]
    cmd += argumentos_encoder(temporario=False, perfil=perfil)
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

    import threading
    _stderr_chunks = []

    def _drenar_stderr():
        try:
            _stderr_chunks.append(processo_ffmpeg.stderr.read())
        except Exception:
            pass

    _t_stderr = threading.Thread(target=_drenar_stderr, daemon=True)
    _t_stderr.start()

    frame_idx = 0
    erro_pipe = False

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx < len(plano):
            p = plano[frame_idx]
        else:
            p = plano[-1] if plano else {"modo": "CENTRAL", "xa": 0.5, "xb": 0.5}

        frame_final = _compor_frame_seguro(
            frame, p, saida_w, saida_h, relatorio=relatorio
        )

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
        print("   ✅ Enquadramento concluído (pipe fallback)!")
    else:
        print(
            f"   ⚠️ Erro no FFmpeg ao exportar (pipe) (codigo {codigo}): "
            f"{_detalhar_erro_ffmpeg(stderr, codigo)}"
        )
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

def _plano_da_amostra(rostos: list):
    """Assinatura do enquadramento numa amostra: posicao e tamanho do maior rosto."""
    validos = [r for r in rostos if r.get("w", 0) > 0]
    if not validos:
        return None
    maior = max(validos, key=lambda r: r["w"])
    return (float(maior["x"]), float(maior["w"]))


def _largura_crop_normalizada(largura: int, altura: int) -> float:
    """Fracao da largura da fonte que o crop 9:16 consegue mostrar."""
    if largura <= 0 or altura <= 0:
        return 1.0
    return min(1.0, (altura * PROPORCAO_SAIDA_PADRAO) / float(largura))


def _cabe_no_mesmo_crop(amostras_x: list, maior_rosto: float,
                        largura_crop: float) -> bool:
    """Todas as posicoes do bloco cabem num unico crop, com a cabeca inteira?"""
    if not amostras_x:
        return True
    amplitude = max(amostras_x) - min(amostras_x)
    cabeca = maior_rosto * LARGURA_CABECA_ROSTO
    margens = 2 * MARGEM_SEGURA_BORDA * largura_crop
    return amplitude + cabeca + margens <= largura_crop


def _mudou_de_zoom(anterior, atual) -> bool:
    """Rosto muda de tamanho o bastante para ser outra camera."""
    if anterior is None or atual is None:
        return False
    maior, menor = max(anterior[1], atual[1]), min(anterior[1], atual[1])
    return menor > 0 and maior / menor > LIMIAR_MUDANCA_PLANO_ZOOM


def _subdividir_cena_por_plano(cena: dict, amostras: list,
                               largura: int = 1920, altura: int = 1080) -> list:
    """Divide a cena onde o enquadramento deixa de caber num crop unico.

    Sem isso, uma cena longa que na verdade contem varias cameras — ou uma
    pessoa que se desloca — vira uma mediana unica, e o crop aponta para um
    lugar onde ninguem esta.
    """
    if len(amostras) < 2:
        return [{
            "frame_ini": cena["frame_ini"],
            "frame_fim": cena["frame_fim"],
            "amostras": amostras,
        }]

    largura_crop = _largura_crop_normalizada(largura, altura)
    blocos = [[amostras[0]]]
    referencia = _plano_da_amostra(amostras[0][1])
    xs_bloco = [referencia[0]] if referencia else []
    maior_bloco = referencia[1] if referencia else 0.0

    for item in amostras[1:]:
        assinatura = _plano_da_amostra(item[1])
        if assinatura is None:
            blocos[-1].append(item)
            continue

        candidatos_x = xs_bloco + [assinatura[0]]
        candidato_w = max(maior_bloco, assinatura[1])
        quebrar = (
            _mudou_de_zoom(referencia, assinatura)
            or not _cabe_no_mesmo_crop(candidatos_x, candidato_w, largura_crop)
        )
        if quebrar:
            blocos.append([item])
            referencia = assinatura
            xs_bloco = [assinatura[0]]
            maior_bloco = assinatura[1]
        else:
            blocos[-1].append(item)
            xs_bloco = candidatos_x
            maior_bloco = candidato_w
            if referencia is None:
                referencia = assinatura

    pedacos = []
    for indice, bloco in enumerate(blocos):
        inicio = cena["frame_ini"] if indice == 0 else bloco[0][0]
        fim = cena["frame_fim"] if indice == len(blocos) - 1 else blocos[indice + 1][0][0]
        if fim <= inicio:
            continue
        pedacos.append({"frame_ini": inicio, "frame_fim": fim, "amostras": bloco})
    return pedacos or [{
        "frame_ini": cena["frame_ini"],
        "frame_fim": cena["frame_fim"],
        "amostras": amostras,
    }]


def _analisar_rostos_por_cena(
    caminho_video: str,
    cenas: list,
    amostras_por_cena: int = AMOSTRAS_POR_CENA,
    intervalo_amostra_s: float = INTERVALO_AMOSTRA_PADRAO_S,
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
    largura_fonte = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1920)
    altura_fonte = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 1080)
    fps_fonte = cap.get(cv2.CAP_PROP_FPS) or 30.0

    cenas_finais = []

    for cena in cenas:
        amostras = []  # [(frame, [rostos daquele frame])]

        if detector is not None:
            # Amostragem por TEMPO, nao um numero fixo por cena. Com 25
            # amostras numa cena de 150s havia 6 segundos entre uma e outra:
            # o podcast troca de camera varias vezes nesse intervalo, cada
            # bloco misturava planos e o crop ia parar num ponto medio onde
            # ninguem estava.
            n_frames_cena = cena["frame_fim"] - cena["frame_ini"]
            passo = max(1, int(round(fps_fonte * intervalo_amostra_s)))
            n_amostras = min(
                MAX_AMOSTRAS_POR_CENA, max(1, (n_frames_cena + passo - 1) // passo)
            )
            if n_amostras >= MAX_AMOSTRAS_POR_CENA:
                passo = max(1, n_frames_cena // MAX_AMOSTRAS_POR_CENA)

            for k in range(n_amostras):
                alvo = cena["frame_ini"] + k * passo
                if alvo >= cena["frame_fim"]:
                    break
                cap.set(cv2.CAP_PROP_POS_FRAMES, alvo)
                ret, frame = cap.read()
                if not ret:
                    continue
                rostos = [
                    r for r in detectar_rostos_robusto(frame, detector)
                    # Descarta rosto minusculo (TV, estatua, manequim) e rosto
                    # grande demais para ser real (falso positivo no cenario).
                    if MIN_TAMANHO_ROSTO <= r.get("w", 0) <= MAX_TAMANHO_ROSTO
                ]
                amostras.append((alvo, rostos))

        # Uma "cena" longa de podcast multicamera guarda varios enquadramentos
        # quando o detector de cortes perde a troca de camera. A mediana de
        # todos eles nao corresponde a plano nenhum e o crop fixo corta a
        # pessoa nos dois. Aqui a cena e quebrada onde o plano muda de fato.
        for pedaco in _subdividir_cena_por_plano(cena, amostras, largura_fonte, altura_fonte):
            rostos_pedaco = [r for _f, rostos in pedaco["amostras"] for r in rostos]
            posicoes = _filtrar_rostos_na_zona_de_cabeca(rostos_pedaco)
            dados = dict(cena)
            dados["frame_ini"] = pedaco["frame_ini"]
            dados["frame_fim"] = pedaco["frame_fim"]
            dados["amostras"] = pedaco["amostras"]
            dados.update(_agrupar_posicoes_cena(*posicoes))
            cenas_finais.append(dados)

    cenas = cenas_finais
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


def _sao_pessoas_distintas(clusters: list, mediana) -> bool:
    """Confere se os dois lados sao mesmo duas pessoas, e nao a mesma duas vezes."""
    xa, xb = mediana(clusters[0], 0), mediana(clusters[1], 0)
    ta, tb = mediana(clusters[0], 2), mediana(clusters[1], 2)
    if ta <= 0 or tb <= 0:
        return True  # sem tamanho confiavel, mantem o comportamento anterior

    maior, menor = max(ta, tb), min(ta, tb)
    if menor / maior < RAZAO_MINIMA_ROSTOS:
        return False

    separacao_minima = LARGURA_OMBROS_ROSTO / 2.0 * (ta + tb)
    return abs(xb - xa) >= separacao_minima


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

    if not _sao_pessoas_distintas(clusters, _mediana):
        # Lados sobrepostos ou rostos de tamanhos incompativeis: e uma pessoa
        # so, vista com uma deteccao espuria ao lado.
        principal = max(clusters, key=len)
        centro = _mediana(principal, 0)
        centro_y = float(np.clip(_mediana(principal, 1), 0.15, 0.55))
        tam = _mediana(principal, 2)
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
                # Sem rosto e sem falante confiável: não aponta para o centro
                # vazio; preenche o vertical com dois painéis horizontais.
                for f in range(ini, min(fim, total_frames)):
                    plano[f] = {"modo": "FALLBACK_SPLIT", "xa": 0.5, "xb": 0.5,
                                "ya": Y_PADRAO, "yb": Y_PADRAO, "ta": 0.0}
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
    return obter_info_video(caminho_video)
# fim do arquivo — enquadramento por cena v2
