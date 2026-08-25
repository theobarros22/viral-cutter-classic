"""Persistencia de transcricao, pessoas e segmentos entre execucoes do app."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import checkpoint as ckp
import pipeline


def _video_falso(tmp_path):
    caminho = tmp_path / "podcast.mp4"
    caminho.write_bytes(b"\0" * 4096)
    return str(caminho)


def test_signature_changes_when_the_video_changes(tmp_path):
    video = _video_falso(tmp_path)
    assinatura = ckp.assinatura_video(video)
    with open(video, "ab") as arquivo:
        arquivo.write(b"\0" * 10)
    assert ckp.assinatura_video(video) != assinatura


def test_analysis_state_survives_a_restart(tmp_path):
    video = _video_falso(tmp_path)
    estado = str(tmp_path / "estado")
    dados = {
        "pessoas": [{"id": 0}, {"id": 1}],
        "transcricao": {"texto": "ola mundo", "palavras": [{"inicio": 0.0}]},
        "segmentos": [{"inicio": 1.0, "fim": 20.0}],
    }

    ckp.salvar_estado_analise(estado, video, dados)
    lido = ckp.carregar_estado_analise(estado, video)

    assert lido["transcricao"]["texto"] == "ola mundo"
    assert len(lido["pessoas"]) == 2
    assert lido["segmentos"][0]["fim"] == 20.0


def test_missing_state_returns_empty(tmp_path):
    video = _video_falso(tmp_path)
    assert ckp.carregar_estado_analise(str(tmp_path / "vazio"), video) == {}


def test_pipeline_rehydrates_cache_from_disk(tmp_path, monkeypatch):
    video = _video_falso(tmp_path)
    estado = str(tmp_path / "estado")
    monkeypatch.setattr(pipeline, "_pasta_estado", lambda: estado)
    ckp.salvar_estado_analise(estado, video, {
        "pessoas": [{"id": 0}],
        "transcricao": {"texto": "conteudo"},
        "segmentos": [{"inicio": 0.0, "fim": 30.0}],
    })

    pipeline._cache.clear()
    reaproveitado = pipeline.restaurar_estado_analise(video)

    assert set(reaproveitado) == {"pessoas", "transcricao", "segmentos"}
    assert pipeline._cache["transcricao"]["texto"] == "conteudo"
    assert pipeline._cache["caminho_video"] == video
    pipeline._cache.clear()


def test_rehydrate_does_not_override_a_live_session(tmp_path, monkeypatch):
    video = _video_falso(tmp_path)
    estado = str(tmp_path / "estado")
    monkeypatch.setattr(pipeline, "_pasta_estado", lambda: estado)
    ckp.salvar_estado_analise(estado, video, {"transcricao": {"texto": "antigo"}})

    pipeline._cache.clear()
    pipeline._cache.update({"caminho_video": video, "transcricao": {"texto": "atual"}})
    assert pipeline.restaurar_estado_analise(video) == {}
    assert pipeline._cache["transcricao"]["texto"] == "atual"
    pipeline._cache.clear()
