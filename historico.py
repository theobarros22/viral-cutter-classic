"""
historico.py
------------
Salva e carrega o histórico de projetos processados.
Guarda as informações em um arquivo JSON na pasta do usuário.
"""

import json
import os
from datetime import datetime


# Arquivo onde o histórico é salvo
ARQUIVO_HISTORICO = os.path.join(
    os.path.expanduser("~"), ".viral_cutter_historico.json"
)


def salvar_projeto(caminho_video: str, pasta_saida: str, resultados: list) -> None:
    """
    Salva um projeto processado no histórico.

    Parâmetros:
        caminho_video: caminho do vídeo original
        pasta_saida: pasta onde os clipes foram salvos
        resultados: lista de clipes gerados
    """
    historico = carregar_historico()

    projeto = {
        "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "video_original": os.path.basename(caminho_video),
        "pasta_saida": pasta_saida,
        "total_clipes": len(resultados),
        "clipes": [
            {
                "titulo": r["titulo"],
                "arquivo": r["arquivo"],
                "score_viral": r["score_viral"],
                "duracao": r["duracao"],
                "resumo": r["resumo"],
            }
            for r in resultados
        ]
    }

    # Adiciona no início da lista (mais recente primeiro)
    historico.insert(0, projeto)

    # Mantém apenas os últimos 20 projetos
    historico = historico[:20]

    with open(ARQUIVO_HISTORICO, "w", encoding="utf-8") as f:
        json.dump(historico, f, ensure_ascii=False, indent=2)


def carregar_historico() -> list:
    """Carrega o histórico de projetos do arquivo JSON."""
    if not os.path.exists(ARQUIVO_HISTORICO):
        return []
    try:
        with open(ARQUIVO_HISTORICO, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def formatar_historico_para_exibicao() -> str:
    """
    Formata o histórico para exibir na interface.
    Retorna uma string formatada com todos os projetos.
    """
    historico = carregar_historico()

    if not historico:
        return "Nenhum projeto processado ainda."

    texto = ""
    for i, proj in enumerate(historico, 1):
        texto += f"{'═'*50}\n"
        texto += f"  [{i}] {proj['video_original']}\n"
        texto += f"      📅 {proj['data']}\n"
        texto += f"      📁 {proj['pasta_saida']}\n"
        texto += f"      🎬 {proj['total_clipes']} clipes gerados\n\n"

        for clipe in proj['clipes']:
            # Verifica se o arquivo ainda existe
            existe = "✅" if os.path.exists(clipe['arquivo']) else "❌ (arquivo removido)"
            texto += f"      {existe} {clipe['titulo']}\n"
            texto += f"           ⏱️ {clipe['duracao']}s | ⭐ {clipe['score_viral']}/10\n"
            texto += f"           💡 {clipe['resumo']}\n"

        texto += "\n"

    return texto


def limpar_historico() -> None:
    """Remove todo o histórico salvo."""
    if os.path.exists(ARQUIVO_HISTORICO):
        os.remove(ARQUIVO_HISTORICO)
