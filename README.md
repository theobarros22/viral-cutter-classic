# Viral Cutter Classic

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)
![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)
![Platform: Windows](https://img.shields.io/badge/platform-Windows-lightgrey.svg)

**Turn long videos, podcasts and interviews into vertical 9:16 clips for Shorts, Reels and TikTok, entirely on your own computer.**

Most clipping tools are paid, cloud-only SaaS products that upload your footage to someone else's servers. Viral Cutter Classic runs locally: your video never leaves your machine, transcription runs on your own hardware, and it uses your NVIDIA GPU when available. It is built and documented in Portuguese first, for Brazilian and Portuguese-speaking creators who are poorly served by English-only tools.

> 🇧🇷 Documentação em português: veja [Português](#português) abaixo, o [LEIA-ME](LEIA-ME.md) e o guia [PARA-DESENVOLVEDORES](PARA-DESENVOLVEDORES.md).

## What it does

- Imports local videos and downloads authorized YouTube videos (`yt-dlp`).
- Transcribes audio locally with Whisper / faster-whisper.
- Detects and separates speakers, including two people sharing the same frame (MediaPipe face detection + tracking).
- Analyzes the content to find the strongest moments (optionally with the Claude API).
- Renders vertical 1080×1920 clips.
- **Safe framing invariant:** a clip is never marked done with the main subject out of frame or touching the edge without a safety margin. When no safe crop exists, the clip is flagged for review instead of exported badly.
- Highlights a solo speaker and switches to split-screen when two people are talking.
- Exports captions and Adobe Premiere-compatible files.
- Uses FFmpeg with NVENC hardware encoding when available, with a safe CPU fallback.
- Validates every exported file with `ffprobe`.
- Checkpoints transcription, analysis, speakers, cuts and progress so a job can resume after a crash or interruption.

## Pipeline

1. Import or download the video.
2. Detect participants.
3. Choose priority speakers.
4. Transcribe and analyze the content.
5. Generate the cuts.
6. Apply framing, captions and export.
7. Validate and review the results.

## Requirements

- Windows 10 or later (64-bit). Linux/macOS support is a welcome contribution.
- Python 3.11.
- FFmpeg and FFprobe on `PATH`.
- Optional: NVIDIA GPU for NVENC acceleration.
- Optional: `ANTHROPIC_API_KEY` for Claude-assisted moment selection.

## Install and run

```powershell
python -m venv venv311
.\venv311\Scripts\Activate.ps1
pip install -r requirements-lock.txt
python interface.py
```

## Tests

```powershell
python -m unittest discover -s tests
```

CI runs the suite on Windows for every push and pull request to `main` and `develop`.

## Contributing

Contributions are welcome: bug reports, testing with authorized media, cross-platform support, translations and pull requests.

1. Open an issue describing the problem or proposal.
2. Branch off `develop`.
3. Keep the change small, documented and tested.
4. Run the test suite.
5. Open a pull request against `develop`.

Changes to framing logic must add or update tests (`tests/test_enquadramento_seguro.py`). Never commit private videos, API keys, personal paths or client data. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Project status

Actively developed. Current release: **2.3.2**. Sibling project: [fast-clipper](https://github.com/theobarros22/fast-clipper), a live-stream clipping platform built on this engine.

## License

Copyright (C) 2026 Theo Barros.

Licensed under the **GNU Affero General Public License v3.0** ([`LICENSE`](LICENSE)). You may use, study, modify and redistribute it, including commercially, as long as modified versions, including those offered as a network service, are also released under the AGPL-3.0.

## Author

Theo Barros: [github.com/theobarros22](https://github.com/theobarros22) · [vollare.ia.br](https://vollare.ia.br)

---

## Português

Aplicativo local para transformar vídeos longos, podcasts e entrevistas em clipes verticais 9:16 para Shorts, Reels e TikTok.

### O que ele faz

- Importa vídeos locais e baixa vídeos autorizados do YouTube.
- Transcreve o áudio localmente com Whisper.
- Detecta e separa participantes, inclusive quando duas pessoas aparecem no mesmo quadro.
- Analisa o conteúdo e identifica possíveis momentos relevantes.
- Gera cortes verticais em 1080x1920.
- Centraliza rostos e preserva as pessoas sem cortes perigosos.
- Destaca quem fala sozinho e divide a tela quando há conversa entre participantes.
- Mantém o vídeo horizontal inteiro dentro do 9:16 quando o recorte não é seguro.
- Exporta legendas e arquivos compatíveis com Premiere.
- Usa FFmpeg/NVENC quando disponível e mantém fallback seguro por CPU.
- Valida os arquivos exportados.
- Salva transcrição, análise, participantes, cortes, progresso e erros para retomar o trabalho após interrupções.

### Fluxo de produção

1. Importar ou baixar o vídeo.
2. Detectar participantes.
3. Escolher pessoas prioritárias.
4. Transcrever e analisar o conteúdo.
5. Gerar os cortes.
6. Aplicar enquadramento, legendas e exportação.
7. Validar e revisar os resultados.

### Requisitos

- Windows 10 ou superior.
- Python 3.11.
- FFmpeg e FFprobe.
- GPU NVIDIA opcional para aceleração NVENC.

### Instalação e execução

```powershell
python -m venv venv311
.\venv311\Scripts\Activate.ps1
pip install -r requirements-lock.txt
python interface.py
```

### Testes

```powershell
.\venv311\Scripts\python.exe -m unittest discover -s tests
```

### Como contribuir

1. Faça um fork do projeto.
2. Crie uma branch para sua alteração.
3. Rode a suíte de testes.
4. Documente o problema e a solução.
5. Abra um Pull Request para `develop`.

Alterações na branch `main` passam por revisão e validação antes da integração.

### Imagens

As capturas de tela do programa ficam em [`docs/images/`](docs/images/). Não publique vídeos privados, chaves, caminhos pessoais ou dados de clientes.

### Apresentação e colaboração

Veja o [pacote de apresentação](docs/presentation/) com roteiro, storyboard e textos de divulgação. O projeto aceita Issues, relatos de bugs, testes com mídia autorizada e Pull Requests para `develop`.

Quando disponível, o vídeo de apresentação ficará em `docs/media/`.

### Status

O projeto está em desenvolvimento ativo. A versão atual inclui processamento local, detecção de participantes, enquadramento vertical, retomada por estado, validação de exportação e aceleração FFmpeg/NVENC.

### Autor

Theo Barros — https://github.com/theobarros22

### Licença

GNU Affero General Public License v3.0 (AGPL-3.0). Veja [`LICENSE`](LICENSE). Você pode usar, estudar, modificar e redistribuir, inclusive comercialmente, desde que versões modificadas, inclusive as oferecidas como serviço pela rede, também tenham o código aberto sob a AGPL-3.0.
