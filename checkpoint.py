"""Checkpoint recuperavel para processamentos longos do Viral Cutter."""

import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime


VERSAO_CHECKPOINT = 1


def criar_id_trabalho(
    caminho_video, segmentos, qualidade, pessoas_ids, perfil="equilibrado",
    remover_pausas=False, min_silencio_ms=700, margem_silencio_ms=120,
    aplicar_hook=False,
):
    estatistica = os.stat(caminho_video)
    dados = {
        "video": os.path.abspath(caminho_video),
        "tamanho": estatistica.st_size,
        "modificado_ns": estatistica.st_mtime_ns,
        "qualidade": qualidade,
        "perfil": perfil,
        "pessoas": sorted(pessoas_ids or []),
        "remover_pausas": bool(remover_pausas),
        "min_silencio_ms": int(min_silencio_ms),
        "margem_silencio_ms": int(margem_silencio_ms),
        "aplicar_hook": bool(aplicar_hook),
    }
    texto = json.dumps(
        dados, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:16]


def caminho_checkpoint(pasta_saida, id_trabalho):
    return os.path.join(pasta_saida, f".viral_cutter_checkpoint_{id_trabalho}.json")


def novo_checkpoint(id_trabalho, caminho_video, segmentos, qualidade, pessoas_ids, perfil="equilibrado"):
    agora = _agora()
    return {
        "versao": VERSAO_CHECKPOINT,
        "id_trabalho": id_trabalho,
        "status": "iniciado",
        "video": os.path.abspath(caminho_video),
        "qualidade": qualidade,
        "perfil": perfil,
        "pessoas_priorizadas_ids": pessoas_ids or [],
        "total_clipes": len(segmentos),
        "segmentos": segmentos,
        "clipes": {},
        "criado_em": agora,
        "atualizado_em": agora,
        "ultimo_erro": None,
    }


def carregar_checkpoint(caminho):
    try:
        with open(caminho, "r", encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
        return dados if dados.get("versao") == VERSAO_CHECKPOINT else None
    except (OSError, ValueError, TypeError):
        return None


def salvar_checkpoint(caminho, dados):
    """Grava de forma atomica para sobreviver a fechamento e falta de energia."""
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    dados["atualizado_em"] = _agora()
    temporario = f"{caminho}.tmp"
    with open(temporario, "w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False, indent=2)
        arquivo.flush()
        os.fsync(arquivo.fileno())
    os.replace(temporario, caminho)


def resultado_valido(resultado):
    if not resultado:
        return False
    caminho = resultado.get("arquivo")
    try:
        if not caminho or not os.path.isfile(caminho) or os.path.getsize(caminho) < 65536:
            return False
        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            return True
        verificacao = subprocess.run(
            [
                ffprobe, "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=codec_type",
                "-of", "default=noprint_wrappers=1:nokey=1", caminho,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        return verificacao.returncode == 0 and "video" in verificacao.stdout.lower()
    except (OSError, subprocess.SubprocessError):
        return False


def resultados_concluidos(dados):
    concluidos = {}
    for indice, item in dados.get("clipes", {}).items():
        resultado = item.get("resultado") if item.get("status") == "concluido" else None
        if resultado_valido(resultado):
            concluidos[int(indice)] = resultado
    return concluidos


def inspecionar_retomada(checkpoint, pasta_saida, segmentos):
    """Classifica saídas existentes sem renderizar novamente mídia válida."""
    concluidos = {}
    pendentes = []
    invalidos = []
    em_revisao = []
    clipes = (checkpoint or {}).get("clipes", {})

    for indice, _segmento in enumerate(segmentos, 1):
        item = clipes.get(str(indice), {})
        resultado = item.get("resultado") or {}
        arquivo = item.get("arquivo") or resultado.get("arquivo")
        if not arquivo:
            prefixo = f"{indice:02d}_"
            encontrados = [
                entrada.path for entrada in os.scandir(pasta_saida)
                if entrada.is_file() and entrada.name.startswith(prefixo)
                and entrada.name.lower().endswith(".mp4")
            ] if os.path.isdir(pasta_saida) else []
            arquivo = encontrados[0] if len(encontrados) == 1 else None

        if arquivo and resultado_valido({"arquivo": arquivo}):
            concluidos[indice] = arquivo
            # Clipe renderizado, mas sem enquadramento seguro: fica separado
            # dos prontos ate alguem revisar.
            if item.get("status") == "revisar" or resultado.get("revisar"):
                em_revisao.append(indice)
        else:
            pendentes.append(indice)
            if arquivo and os.path.exists(arquivo):
                invalidos.append(indice)

    return {
        "checkpoint_encontrado": checkpoint is not None,
        "concluidos": concluidos,
        "pendentes": pendentes,
        "invalidos": invalidos,
        "em_revisao": em_revisao,
        "prontos": [i for i in concluidos if i not in em_revisao],
        "total": len(segmentos),
    }


def atualizar_progresso(
    checkpoint, *, indice, etapa, concluidos, total,
    inicio_sessao, agora, amostras,
):
    """Registra progresso sem estimar tempo antes de haver uma amostra real."""
    decorrido = max(0.0, agora - inicio_sessao)
    estimativa = None
    if amostras:
        estimativa = round(sum(amostras) / len(amostras) * max(0, total - concluidos))
    evento = {
        "tipo": "progresso",
        "clipe_atual": indice,
        "etapa": etapa,
        "concluidos": concluidos,
        "total": total,
        "percentual_global": round(100 * concluidos / total, 1) if total else 100.0,
        "percentual_etapa": 100.0 if etapa == "concluido" else 0.0,
        "decorrido_segundos": round(decorrido),
        "estimativa_segundos": estimativa,
    }
    checkpoint["progresso"] = evento
    return evento


def _agora():
    return datetime.now().astimezone().isoformat(timespec="seconds")
