"""Contrato e persistencia dos projetos Viralume."""

import json
import re
from datetime import datetime
from pathlib import Path


VERSAO_PROJETO = 1


def validar_projeto(dados):
    if not isinstance(dados, dict):
        raise ValueError("Projeto invalido.")

    legendas = []
    for item in dados.get("captions") or []:
        if not isinstance(item, dict):
            continue
        try:
            inicio = max(0.0, float(item.get("start", 0)))
            fim = float(item.get("end", inicio))
        except (TypeError, ValueError):
            continue
        texto = str(item.get("text") or "").strip()
        if not texto or fim <= inicio:
            continue
        legendas.append(
            {
                "start": round(inicio, 3),
                "end": round(fim, 3),
                "text": texto,
                "style": str(item.get("style") or "classic"),
                "effect": str(item.get("effect") or "none"),
                "highlight": str(item.get("highlight") or ""),
            }
        )

    insercoes = []
    for item in dados.get("inserts") or []:
        if not isinstance(item, dict):
            continue
        try:
            inicio = max(0.0, float(item.get("start", 0)))
            fim = float(item.get("end", inicio))
        except (TypeError, ValueError):
            continue
        if fim <= inicio:
            continue
        insercoes.append(
            {
                "id": str(item.get("id") or ""),
                "name": str(item.get("name") or "Midia"),
                "type": str(item.get("type") or "image"),
                "start": round(inicio, 3),
                "end": round(fim, 3),
                "position": str(item.get("position") or "center"),
                "scale": float(item.get("scale") or 1),
                "source_path": str(item.get("source_path") or ""),
            }
        )

    return {
        "version": VERSAO_PROJETO,
        "name": str(dados.get("name") or "Projeto Viralume").strip()[:120],
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "video": dados.get("video") if isinstance(dados.get("video"), dict) else {},
        "captions": legendas,
        "inserts": insercoes,
        "effects": dados.get("effects") if isinstance(dados.get("effects"), dict) else {},
    }


def salvar_projeto(dados, pasta):
    projeto = validar_projeto(dados)
    destino = Path(pasta)
    destino.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", projeto["name"]).strip("_") or "projeto"
    arquivo = destino / f"{slug}.viralume.json"
    temporario = arquivo.with_suffix(arquivo.suffix + ".tmp")
    temporario.write_text(json.dumps(projeto, ensure_ascii=False, indent=2), encoding="utf-8")
    temporario.replace(arquivo)
    return arquivo, projeto
