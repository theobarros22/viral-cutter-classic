# Matriz de validação do Corte Viral

## Inicialização

- Duplo clique abre sem console.
- Interface aparece em até 8 segundos em SSD.
- Segunda instância é bloqueada.
- Porta ocupada não impede abertura.
- Falhas são registradas em `%LOCALAPPDATA%\ViralCutter\logs`.

## Entrada

- MP4 H.264 com áudio.
- MP4 sem áudio.
- MOV.
- Vídeo vertical.
- Vídeo 4K.
- Vídeo com nome contendo espaços e acentos.
- Arquivo corrompido apresenta erro compreensível.

## Participantes e câmeras

- Uma pessoa em close.
- Duas pessoas lado a lado.
- Três pessoas.
- Plano aberto com rostos pequenos.
- Cortes entre câmeras.
- B-roll sem pessoas.
- Pessoa parcialmente fora do quadro.

## Transcrição e análise

- GPU NVIDIA disponível.
- Somente CPU.
- Modo online.
- API sem créditos ou sem internet cai para offline.
- Segunda análise do mesmo vídeo usa cache.
- Vídeo superior a 20 minutos.

## Exportação

- 720p, 1080p e 4K.
- Codificação NVENC.
- Fallback libx264.
- Cancelamento e espaço em disco insuficiente.
- Arquivo final abre, tem áudio e duração correta.
- Não deixa arquivos temporários após falha.

## Build

- Diagnóstico passa.
- Testes unitários passam.
- PyInstaller termina sem avisos críticos.
- `validar_build.ps1` mantém o executável aberto por 35 segundos.
- Executável funciona em uma máquina Windows limpa.
