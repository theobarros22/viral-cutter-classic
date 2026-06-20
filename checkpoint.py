"""Checkpoint recuperavel para processamentos longos do Viral Cutter."""

import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime


VERSAO_CHECKPOINT = 1


def criar_id_trabalho(caminho_video, segmentos, qualidade, pessoas_ids, perfil="equilibrado"):
    estatistica = os.stat(caminho_video)
    dados = {
        "video": os.path.abspath(caminho_video),
        "tamanho": estatistica.st_size,
        "modificado_ns": estatistica.st_mtime_ns,
        "qualidade": qualidade,
        "perfil": perfil,
        "pessoas": sorted(pessoas_ids or []),
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


def _agora():
    return datetime.now().astimezone().isoformat(timespec="seconds")
