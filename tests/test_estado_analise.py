"""Persistencia de transcricao, pessoas e segmentos entre execucoes do app."""

import json
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


def test_log_recovery_finds_saved_clips(tmp_path):
    """Sem checkpoint, o log aponta os candidatos ja exportados."""
    log = tmp_path / "trabalho.log"
    log.write_text(
        "2026-08-25T07:22:20-03:00    [1/3] Enquadrando...\n"
        "2026-08-25T07:28:16-03:00    [1/3] Validado: 164.7s | 1080x1920 | h264\n"
        "2026-08-25T07:28:16-03:00    Salvo: 01_primeiro.mp4\n"
        "2026-08-25T07:32:58-03:00    [2/3] Salvo: 02_segundo.mp4\n"
        "2026-08-25T07:33:00-03:00    [2/3] REVISAR enquadramento: pessoa_cortada_na_direita, sem_modo_seguro\n",
        encoding="utf-8",
    )

    candidatos = ckp.recuperar_do_log(str(log), total=3)

    assert candidatos[1]["arquivo"] == "01_primeiro.mp4"
    assert candidatos[1]["revisar"] is False
    assert candidatos[2]["revisar"] is True
    assert "sem_modo_seguro" in candidatos[2]["motivos"]
    assert 3 not in candidatos


def test_log_recovery_ignores_out_of_range_and_missing_log(tmp_path):
    log = tmp_path / "trabalho.log"
    log.write_text("x    Salvo: 99_fora_do_intervalo.mp4\n", encoding="utf-8")
    assert ckp.recuperar_do_log(str(log), total=3) == {}
    assert ckp.recuperar_do_log(str(tmp_path / "nao_existe.log"), total=3) == {}


def test_log_is_never_trusted_without_media_validation(tmp_path, monkeypatch):
    """Clipe citado no log mas ausente na pasta continua pendente."""
    log = tmp_path / "trabalho.log"
    log.write_text("x    Salvo: 01_fantasma.mp4\n", encoding="utf-8")
    segmentos = [{"inicio": 0, "fim": 10, "titulo": "a"}]

    inventario = ckp.inspecionar_retomada(
        None, str(tmp_path), segmentos, caminho_log=str(log)
    )

    assert inventario["pendentes"] == [1]
    assert inventario["concluidos"] == {}


def test_log_recovers_a_clip_when_the_checkpoint_is_gone(tmp_path, monkeypatch):
    monkeypatch.setattr(ckp, "resultado_valido", lambda r: bool(r and r.get("arquivo")))
    arquivo = tmp_path / "01_existe.mp4"
    arquivo.write_bytes(b"\0" * 70000)
    log = tmp_path / "trabalho.log"
    log.write_text(
        "x    Salvo: 01_existe.mp4\n"
        "x    [1/1] REVISAR enquadramento: sem_modo_seguro\n",
        encoding="utf-8",
    )

    inventario = ckp.inspecionar_retomada(
        None, str(tmp_path), [{"inicio": 0, "fim": 10}], caminho_log=str(log)
    )

    assert inventario["concluidos"] == {1: str(arquivo)}
    assert inventario["em_revisao"] == [1]
    assert inventario["prontos"] == []


def test_stage3_rehydrates_people_before_detecting_the_speaker(tmp_path, monkeypatch):
    """Regressao real: retomar num processo novo deixava a lista de pessoas vazia."""
    import inspect
    fonte = inspect.getsource(pipeline.etapa3_processar)
    posicao_restauracao = fonte.find("restaurar_estado_analise")
    posicao_uso = fonte.find('_cache.get("pessoas"')
    assert posicao_restauracao != -1, "etapa3 precisa reidratar o estado salvo"
    assert posicao_restauracao < posicao_uso, "reidratar antes de usar as pessoas"


def test_checkpoint_save_retries_when_windows_locks_the_file(tmp_path, monkeypatch):
    """PermissionError transitorio derrubou um lote de 56 clipes com 45 prontos."""
    destino = tmp_path / "checkpoint.json"
    chamadas = {"n": 0}
    replace_real = os.replace

    def replace_teimoso(origem, alvo):
        chamadas["n"] += 1
        if chamadas["n"] < 3:
            raise PermissionError("Acesso negado")
        return replace_real(origem, alvo)

    monkeypatch.setattr(ckp.os, "replace", replace_teimoso)
    monkeypatch.setattr(ckp.time, "sleep", lambda _s: None)

    ckp.salvar_checkpoint(str(destino), {"status": "processando"})

    assert chamadas["n"] == 3
    gravado = json.loads(destino.read_text(encoding="utf-8"))
    assert gravado["status"] == "processando"


def test_checkpoint_falls_back_to_direct_write(tmp_path, monkeypatch):
    """Se a troca atomica nunca liberar, ainda assim grava o progresso."""
    destino = tmp_path / "checkpoint.json"
    monkeypatch.setattr(ckp.os, "replace", lambda *a: (_ for _ in ()).throw(PermissionError()))
    monkeypatch.setattr(ckp.time, "sleep", lambda _s: None)

    ckp.salvar_checkpoint(str(destino), {"status": "processando"}, tentativas=2)

    gravado = json.loads(destino.read_text(encoding="utf-8"))
    assert gravado["status"] == "processando"
