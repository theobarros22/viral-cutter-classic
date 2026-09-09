# -*- coding: utf-8 -*-
r"""A pasta temporaria do Gradio nunca pode depender de uma unidade ausente.

Este teste existe por causa de um bug real: iniciar.bat fixava
GRADIO_TEMP_DIR em D:\ViralCutter\gradio_temp, e D: e um leitor de cartao sem
midia. O app subia e morria na primeira escrita do Gradio.
"""
import os
import runtime


def test_caminho_invalido_e_descartado(monkeypatch, tmp_path):
    """Unidade inexistente nao pode derrubar a inicializacao."""
    monkeypatch.setenv("GRADIO_TEMP_DIR", r"Z:\NaoExiste\gradio_temp")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    escolhido = runtime.configurar_pasta_temporaria()

    assert not escolhido.startswith("Z:")
    assert os.path.isdir(escolhido)
    assert os.environ["GRADIO_TEMP_DIR"] == escolhido


def test_caminho_valido_e_respeitado(monkeypatch, tmp_path):
    """Um caminho que funciona continua valendo."""
    desejado = tmp_path / "meu_temp"
    monkeypatch.setenv("GRADIO_TEMP_DIR", str(desejado))

    assert runtime.configurar_pasta_temporaria() == str(desejado)


def test_padrao_fica_no_disco_do_sistema(monkeypatch, tmp_path):
    """Sem variavel definida, o destino e LOCALAPPDATA — sempre montado."""
    monkeypatch.delenv("GRADIO_TEMP_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    escolhido = runtime.configurar_pasta_temporaria()

    assert escolhido.startswith(str(tmp_path))
    assert os.path.isdir(escolhido)


def test_bootstrap_define_a_variavel(monkeypatch, tmp_path):
    """configurar_ambiente e o unico ponto de entrada: precisa deixar pronto."""
    monkeypatch.delenv("GRADIO_TEMP_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    runtime.configurar_ambiente()

    assert os.path.isdir(os.environ["GRADIO_TEMP_DIR"])


def test_discos_prontos_nao_inventa_unidade():
    """So entram raizes que respondem de verdade — nada de D: fantasma."""
    raizes = runtime.discos_prontos()

    assert raizes, "deveria achar ao menos o disco do sistema"
    for raiz in raizes:
        assert os.path.isdir(raiz)
