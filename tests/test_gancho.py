import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gancho


def _seg(inicio, score=None, notas=None, titulo=None):
    s = {"inicio": inicio, "fim": inicio + 30, "titulo": f"Corte {inicio}"}
    if score is not None:
        s["score_viral"] = score
    if notas is not None:
        s["notas"] = notas
    if titulo is not None:
        s["titulo_gancho"] = titulo
    return s


def test_nota_composta_pesa_mais_o_gancho():
    forte_no_gancho = {"gancho": 10, "engajamento": 5, "valor": 5, "compartilhamento": 5}
    forte_no_valor = {"gancho": 5, "engajamento": 5, "valor": 10, "compartilhamento": 5}
    assert gancho.nota_composta(forte_no_gancho) > gancho.nota_composta(forte_no_valor)


def test_aplicar_notas_recalcula_score_e_guarda_original():
    notas = {"gancho": 9, "engajamento": 8, "valor": 7, "compartilhamento": 8}
    [s] = gancho.aplicar_notas([_seg(0, score=5, notas=notas)])
    assert s["score_viral"] == 8          # 9*.35 + 8*.25 + 7*.2 + 8*.2 = 8.15
    assert s["nota_composta"] == 8.2
    assert s["score_viral_ia"] == 5


def test_notas_incompletas_ou_invalidas_nao_mexem_no_score():
    incompletas = {"gancho": 9, "engajamento": 8}
    invalidas = {"gancho": "alto", "engajamento": 8, "valor": 7, "compartilhamento": 8}
    a, b = gancho.aplicar_notas([_seg(0, 6, incompletas), _seg(10, 6, invalidas)])
    assert a["score_viral"] == 6 and "notas" not in a
    assert b["score_viral"] == 6 and "notas" not in b


def test_notas_fora_da_escala_sao_limitadas():
    notas = gancho.normalizar_notas({"gancho": 14, "engajamento": -3, "valor": 5, "compartilhamento": 5})
    assert notas["gancho"] == 10 and notas["engajamento"] == 1


def test_segmentos_offline_sem_notas_passam_intactos():
    original = _seg(0, score=7)
    [s] = gancho.aplicar_notas([original])
    assert s == original


def test_ordena_do_mais_forte_ao_mais_fraco_e_desempata_pelo_tempo():
    segs = [_seg(30, 6), _seg(0, 9), _seg(60, 9), _seg(90, 3)]
    ordem = [s["inicio"] for s in gancho.ordenar_por_viralidade(segs)]
    assert ordem == [0, 60, 30, 90]


def test_titulo_gancho_limpo_e_curto():
    t = gancho.limpar_titulo_gancho('  "Ele quase desistiu aqui, mas olha o que aconteceu depois disso tudo".  ')
    assert not t.startswith('"') and not t.endswith(".")
    assert len(t.split()) <= gancho.MAX_PALAVRAS_TITULO
    assert len(t) <= gancho.MAX_CARACTERES_TITULO
    assert gancho.limpar_titulo_gancho(None) == ""
    assert gancho.limpar_titulo_gancho("   ") == ""


def test_ass_do_titulo(tmp_path):
    caminho = tmp_path / "gancho.ass"
    assert gancho.gerar_ass_titulo_gancho("O erro que custou {tudo}", str(caminho))
    conteudo = caminho.read_text(encoding="utf-8-sig")
    assert "PlayResX: 1080" in conteudo and "PlayResY: 1920" in conteudo
    assert "0:00:00.00,0:00:03.00,Gancho" in conteudo
    assert "O ERRO QUE" in conteudo
    # Chaves do texto nao podem virar tags de override do ASS
    assert "{TUDO}" not in conteudo and "(TUDO)" in conteudo


def test_ass_sem_titulo_nao_gera_arquivo(tmp_path):
    caminho = tmp_path / "vazio.ass"
    assert not gancho.gerar_ass_titulo_gancho("", str(caminho))
    assert not caminho.exists()
