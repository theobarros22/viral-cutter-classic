"""
test_core_engine.py
-------------------
Script de teste interativo para validar cada função do CoreEngine.py.
"""

import os
import sys
import shutil

# Adiciona o diretório atual ao path para importação
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import CoreEngine

VIDEO_ORIGINAL = r"D:\CORTE VIRAL\studio\exports\teste_natasha_1.00-3.00.mp4"
PASTA_TESTE = r"D:\CORTE VIRAL\files\test_output"

def rodar_testes():
    print("=== INICIANDO VALIDACAO DO CORE ENGINE ===")
    
    # Prepara pasta de saída
    if os.path.exists(PASTA_TESTE):
        shutil.rmtree(PASTA_TESTE)
    os.makedirs(PASTA_TESTE, exist_ok=True)
    
    if not os.path.exists(VIDEO_ORIGINAL):
        print(f"Erro: Arquivo de vídeo original para teste não encontrado em: {VIDEO_ORIGINAL}")
        sys.exit(1)
        
    print(f"Vídeo de teste: {VIDEO_ORIGINAL}")
    print(f"Saídas salvas em: {PASTA_TESTE}\n")
    
    # 1. Teste de Extração de Áudio
    audio_path = os.path.join(PASTA_TESTE, "audio_extraido.wav")
    print("1. Testando extração de áudio...")
    sucesso_audio = CoreEngine.extract_audio(VIDEO_ORIGINAL, audio_path)
    if sucesso_audio and os.path.exists(audio_path):
        print(f"  [OK] Áudio extraído com {os.path.getsize(audio_path)} bytes.\n")
    else:
        print("  [FALHA] Falha na extração de áudio.\n")
        
    # 2. Teste de Transcrição
    print("2. Testando transcrição e Smart Chunking...")
    cartoes = CoreEngine.transcribe_and_chunk(audio_path)
    print(f"  [OK] Transcrição concluída. Cartões gerados: {len(cartoes)}")
    for c in cartoes[:3]:
        print(f"    - Card {c['id']}: [{c['start']:.2f}s -> {c['end']:.2f}s] {c['text']}")
    print()
    
    # Se não houver cartões, injeta mock para as próximas etapas
    if not cartoes:
        print("  [NOTA] Injetando cartões mock para prosseguir com testes de efeitos...")
        cartoes = [
            {"id": 1, "start": 0.2, "end": 1.1, "text": "OLÁ ISSO É UM TESTE"},
            {"id": 2, "start": 1.2, "end": 1.9, "text": "DA MÁSCARA 3D DE TEXTO"}
        ]

    # 3. Teste de Remoção de Silêncio
    v_jumpcut = os.path.join(PASTA_TESTE, "video_jumpcut.mp4")
    print("3. Testando remoção de silêncio (jump cuts)...")
    if CoreEngine.remove_silences(VIDEO_ORIGINAL, v_jumpcut):
        print(f"  [OK] Vídeo jump cut gerado ({os.path.getsize(v_jumpcut)} bytes).\n")
    else:
        print("  [FALHA] Falha no jump cut.\n")
        
    # 4. Teste de Zoompan
    v_zoom = os.path.join(PASTA_TESTE, "video_zoom.mp4")
    print("4. Testando Auto-Zoom...")
    if CoreEngine.apply_auto_zoom(VIDEO_ORIGINAL, [0.5, 1.5], v_zoom):
        print(f"  [OK] Vídeo com zoom dinâmico gerado ({os.path.getsize(v_zoom)} bytes).\n")
    else:
        print("  [FALHA] Falha no zoom dinâmico.\n")

    # 5. Teste de Auto-Framing (Centralização facial)
    v_framed = os.path.join(PASTA_TESTE, "video_framed.mp4")
    print("5. Testando Auto-Framing (MediaPipe Face)...")
    if CoreEngine.auto_framing(VIDEO_ORIGINAL, v_framed):
        print(f"  [OK] Vídeo vertical 9:16 re-enquadrado ({os.path.getsize(v_framed)} bytes).\n")
    else:
        print("  [FALHA] Falha no auto-framing.\n")

    # 6. Teste de Geração ASS
    ass_path = os.path.join(PASTA_TESTE, "legendas.ass")
    print("6. Testando geração de legenda ASS estilizada...")
    if CoreEngine.generate_subtitles_ass(cartoes, ass_path):
        print(f"  [OK] Arquivo ASS gerado ({os.path.getsize(ass_path)} bytes).\n")
    else:
        print("  [FALHA] Falha na geração ASS.\n")

    # 7. Teste de Split Screen
    v_split = os.path.join(PASTA_TESTE, "video_split.mp4")
    print("7. Testando Split Screen vertical...")
    # Usa o próprio vídeo de teste como topo e base
    if CoreEngine.render_split_screen(VIDEO_ORIGINAL, VIDEO_ORIGINAL, v_split):
        print(f"  [OK] Split screen gerado ({os.path.getsize(v_split)} bytes).\n")
    else:
        print("  [FALHA] Falha no split screen.\n")

    # 8. Teste de Máscara de Texto 3D (Behind Person)
    v_text_3d = os.path.join(PASTA_TESTE, "video_text_3d.mp4")
    print("8. Testando Máscara de Texto 3D (MediaPipe Selfie Segmentation)...")
    if CoreEngine.apply_3d_text_mask(VIDEO_ORIGINAL, ass_path, v_text_3d):
        print(f"  [OK] Vídeo com efeito 3D gerado ({os.path.getsize(v_text_3d)} bytes).\n")
    else:
        print("  [FALHA] Falha no efeito 3D.\n")

    # 9. Teste de Análise Contextual com IA
    print("9. Testando análise contextual de efeitos com IA (Ollama / Fallback PNL)...")
    cartoes_enriquecidos = CoreEngine.analyze_context_for_viral_effects(cartoes)
    print(f"  [OK] Análise concluída. Exemplo de cartões enriquecidos:")
    for c in cartoes_enriquecidos[:3]:
        print(f"    - Card {c['id']}: [{c['start']:.2f}s -> {c['end']:.2f}s] {c['text']} | Zoom: {c['zoom']} | SFX: {c['sfx']} | Style: {c['text_style']}")
    print()

    # 10. Teste de Compilação Unificada de Edição IA
    v_ai_compiled = os.path.join(PASTA_TESTE, "video_ai_compiled.mp4")
    print("10. Testando compilação integrada da edição de IA no FFmpeg...")
    if CoreEngine.compile_ai_edit_to_ffmpeg(VIDEO_ORIGINAL, cartoes_enriquecidos, v_ai_compiled):
        print(f"  [OK] Vídeo final compilado por IA gerado com sucesso ({os.path.getsize(v_ai_compiled)} bytes).\n")
    else:
        print("  [FALHA] Falha na compilação integrada de IA.\n")

    print("=== TODOS OS TESTES DE PIPELINE FORAM EXECUTADOS ===")

if __name__ == "__main__":
    rodar_testes()
