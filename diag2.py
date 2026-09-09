# -*- coding: utf-8 -*-
"""Dump completo dos grupos brutos: varios recortes por grupo, com posicao."""
import os, sys, json, time
R = r"H:\CORTE VIRAL\ViralCutter-Classic-Atualizado"
sys.path.insert(0, R); os.chdir(R)
import cv2, numpy as np, rostos

VIDEO = r"F:\Meu_Vídeo\RFNSL_BENY.mov"
SAIDA = os.path.join(R, "diagnostico-identidade2")
os.makedirs(SAIDA, exist_ok=True)

_fundir_original = rostos._fundir_grupos_da_mesma_pessoa
capturado = {"feito": False}

def fundir(grupos, reconhecedor, limiar):
    if not capturado["feito"] and len(grupos) >= 2:
        capturado["feito"] = True
        print("\n=== GRUPOS BRUTOS: %d ===" % len(grupos), flush=True)
        for i, g in enumerate(grupos):
            det = g["deteccoes"]
            xs = [float(d["posicao_x"]) for d in det]
            ys = [float(d.get("posicao_y", 0)) for d in det]
            tam = [float(d.get("tamanho", 0)) for d in det]
            print("g%d: %d deteccoes | x medio=%.3f (min %.3f max %.3f) | y=%.3f | tamanho=%.4f | frames=%s"
                  % (i, len(det), np.mean(xs), min(xs), max(xs), np.median(ys),
                     np.median(tam) if tam else 0, sorted(g["frames"])[:8]), flush=True)
            # salva ate 6 recortes deste grupo, em tamanho grande
            escolhidos = sorted(det, key=lambda d: -(d.get("recorte_identidade", d["recorte"]).shape[0]))[:6]
            for k, d in enumerate(escolhidos):
                img = d.get("recorte_identidade", d["recorte"])
                if img.shape[0] < 160:
                    img = cv2.resize(img, (160, 160), interpolation=cv2.INTER_LANCZOS4)
                cv2.imwrite(os.path.join(SAIDA, "g%d_%d_x%.2f_f%s.png"
                            % (i, k, float(d["posicao_x"]), d.get("frame_idx"))), img)
        # tira de contato: um mosaico por grupo
        for i, g in enumerate(grupos):
            det = sorted(g["deteccoes"], key=lambda d: -(d.get("recorte_identidade", d["recorte"]).shape[0]))[:6]
            tiras = [cv2.resize(d.get("recorte_identidade", d["recorte"]), (160,160),
                     interpolation=cv2.INTER_LANCZOS4) for d in det]
            if tiras:
                cv2.imwrite(os.path.join(SAIDA, "MOSAICO_g%d.png" % i), np.hstack(tiras))
        print("\n=== SCORES ===", flush=True)
        for i in range(len(grupos)):
            for j in range(i+1, len(grupos)):
                a, b = grupos[i], grupos[j]
                s = max(float(reconhecedor.match(ea, eb, cv2.FaceRecognizerSF_FR_COSINE))
                        for ea in a["embeddings"] for eb in b["embeddings"])
                compart = bool(a["frames"] & b["frames"])
                dx = abs(np.mean([d["posicao_x"] for d in a["deteccoes"]]) -
                         np.mean([d["posicao_x"] for d in b["deteccoes"]]))
                ta = np.median([float(d.get("tamanho",0)) for d in a["deteccoes"]])
                tb = np.median([float(d.get("tamanho",0)) for d in b["deteccoes"]])
                print("g%d x g%d: score=%.4f | mesmo frame=%s | distancia_x=%.3f | tamanhos %.4f vs %.4f"
                      % (i, j, s, compart, dx, ta, tb), flush=True)
    return _fundir_original(grupos, reconhecedor, limiar)

rostos._fundir_grupos_da_mesma_pessoa = fundir
pessoas = rostos.detectar_pessoas_no_video(VIDEO, max_amostras=30)
print("\n=== FINAL: %d pessoa(s) ===" % len(pessoas), flush=True)
for p in pessoas:
    print("  %s x=%.3f aparicoes=%d" % (p["nome"], p["posicao_x"], p["n_aparicoes"]), flush=True)
print("saida:", SAIDA, flush=True)
