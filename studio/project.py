"""Contrato e persistencia dos projetos Viralume."""

import json
import re
from datetime import datetime
from pathlib import Path
try:
    from studio.smart_layouts import plano_layout, validar_layout
except ModuleNotFoundError:
    from smart_layouts import plano_layout, validar_layout


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

    efeitos = dados.get("effects") if isinstance(dados.get("effects"), dict) else {}
    layout_ativo = efeitos.get("smart_layout_enabled") is not False
    layout_nome = validar_layout(efeitos.get("smart_layout"))
    efeitos["smart_layout"] = layout_nome
    efeitos["smart_layout_enabled"] = layout_ativo
    efeitos["smart_layout_format"] = "9:16"
    efeitos["smart_layout_plan"] = plano_layout(layout_nome) if layout_ativo else None

    return {
        "version": VERSAO_PROJETO,
        "name": str(dados.get("name") or "Projeto Viralume").strip()[:120],
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "video": dados.get("video") if isinstance(dados.get("video"), dict) else {},
        "captions": legendas,
        "inserts": insercoes,
        "effects": efeitos,
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
