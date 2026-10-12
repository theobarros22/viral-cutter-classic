# Viral Cutter Classic

Aplicativo local para transformar vídeos longos, podcasts e entrevistas em clipes verticais 9:16 para Shorts, Reels e TikTok.

## O que ele faz

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

## Fluxo de produção

1. Importar ou baixar o vídeo.
2. Detectar participantes.
3. Escolher pessoas prioritárias.
4. Transcrever e analisar o conteúdo.
5. Gerar os cortes.
6. Aplicar enquadramento, legendas e exportação.
7. Validar e revisar os resultados.

## Requisitos

- Windows 10 ou superior.
- Python 3.11.
- FFmpeg e FFprobe.
- GPU NVIDIA opcional para aceleração NVENC.

## Instalação e execução

```powershell
python -m venv venv311
.\venv311\Scripts\Activate.ps1
pip install -r requirements-lock.txt
python interface.py
```

## Testes

```powershell
.\venv311\Scripts\python.exe -m unittest discover -s tests
```

## Como contribuir

1. Faça um fork do projeto.
2. Crie uma branch para sua alteração.
3. Rode a suíte de testes.
4. Documente o problema e a solução.
5. Abra um Pull Request para `develop`.

Alterações na branch `main` passam por revisão e validação antes da integração.

## Imagens

As capturas de tela do programa ficam em `docs/images/`. Não publique vídeos privados, chaves, caminhos pessoais ou dados de clientes.

## Status

O projeto está em desenvolvimento ativo. A versão atual inclui processamento local, detecção de participantes, enquadramento vertical, retomada por estado, validação de exportação e aceleração FFmpeg/NVENC.

## Autor

Theo Barros — https://github.com/theobarros22

## Licença

Consulte `LICENSE.md`. O uso comercial, venda, sublicenciamento ou incorporação em produto comercial exige autorização expressa do autor.
