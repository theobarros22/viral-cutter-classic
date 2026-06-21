# Continuidade do projeto Viral Cutter

## Fonte principal

- Código de auditoria e desenvolvimento:
  `C:\Users\Theo Barros\Claude\Projects\CORTE VIRAL`
- Projeto principal e builds:
  `D:\CORTE VIRAL\files`
- Executável validado:
  `D:\CORTE VIRAL\files\dist\ViralCutter\ViralCutter.exe`
- Versão atual: `2.2.3`

## Visão atual do produto

O Viral Cutter é um aplicativo Windows local para:

1. identificar participantes nos primeiros cinco minutos;
2. transcrever vídeos longos com Whisper;
3. localizar segmentos com potencial viral;
4. enquadrar os participantes em formato vertical;
5. retomar processamentos interrompidos;
6. evoluir para um editor vertical focado em legendas virais e motion graphics.

O editor de legendas e motions será exclusivamente vertical `9:16`, com presets
para TikTok, Instagram Reels, YouTube Shorts e Facebook Reels.

## Funcionalidades implementadas no executável

- Detecção inicial em 30 amostras nos primeiros 5 minutos.
- MediaPipe com fallback OpenCV.
- Whisper Base, Small, Medium e Large.
- Whisper Base como padrão rápido.
- Perfis Rápido, Equilibrado e Máxima qualidade.
- Modo online e offline para seleção dos cortes.
- Enquadramento por cena.
- NVENC com fallback CPU.
- Exportação 720p, 1080p e 4K.
- Checkpoint e retomada por trabalho.
- Log persistente por trabalho.
- Percentual, estimativa e tempos por etapa.
- 12 testes automatizados.
- Build PyInstaller `onedir` validado por resposta HTTP.

## Prévia do novo frontend

- Arquivo: `frontend_preview\index.html`
- Servidor local utilizado: `http://127.0.0.1:8765`
- Identidade visual:
  - preto;
  - branco;
  - laranja Vollare aproximado `#C63200`;
  - tipografia Archivo;
  - rótulos técnicos em IBM Plex Mono;
  - grid técnico inspirado no site oficial.

Telas navegáveis:

- Projetos;
- Cortes com IA;
- Legendas & Motions;
- Editor;
- Recursos.

Essa prévia ainda não controla o backend Python.

## Foco prioritário

O principal diferencial do produto passa a ser:

- legendas palavra por palavra;
- templates animados;
- tipografia hierárquica;
- hooks virais;
- shake, spring, typewriter e contadores;
- overlays, pills, badges e logos;
- sincronização com beats;
- múltiplos motions no mesmo corte;
- aplicação em massa;
- presets por cliente.

## Próxima etapa técnica recomendada

1. Criar o frontend real em React.
2. Empacotar a janela com pywebview.
3. Criar API local entre React e Python.
4. Reconstruir o módulo Remotion descrito em
   `RESUMO-PROJETO-LEGENDAS-VIRAL-CUTTER.md`.
5. Começar com quatro templates funcionais:
   Hook Viral, TikTok Pop, Narrativo e Impacto Shake.
6. Implementar timestamps por palavra no Whisper.
7. Integrar preview Remotion ao editor.
8. Conectar renderização e checkpoint.

## Arquivos de planejamento

- `ROADMAP_PRODUTO.md`
- `FUNCIONALIDADES_ADOTAVEIS.md`
- `RESUMO-PROJETO-LEGENDAS-VIRAL-CUTTER.md`
- `PLANO_EXECUTAVEL_PROFISSIONAL.md`
- `MATRIZ_VALIDACAO.md`

## Como validar o código

```powershell
cd "C:\Users\Theo Barros\Claude\Projects\CORTE VIRAL"
& "D:\CORTE VIRAL\files\venv311\Scripts\python.exe" -m unittest discover -s tests -v
```

## Como gerar o executável

```powershell
cd "C:\Users\Theo Barros\Claude\Projects\CORTE VIRAL"
& ".\CORRIGIR_E_GERAR_EXECUTAVEL.bat"
```

O script:

1. cria backup dos arquivos alterados;
2. sincroniza para `D:\CORTE VIRAL\files`;
3. valida o ambiente;
4. executa testes;
5. gera o executável;
6. confirma a resposta HTTP.

## Cuidados

- Não apagar `D:\CORTE VIRAL\files\dist`.
- Não apagar `D:\CORTE VIRAL\files\build`.
- Não apagar `D:\CORTE VIRAL\files\venv311`.
- Criar backup antes de substituir arquivos no `D:`.
- Não considerar os arquivos `main.py`, `reframe.py`, `tracking.py`,
  `smart_cut.py` e `historico.py` como fluxo ativo sem revisar sua integração.

## Frase para iniciar uma nova sessão

> Continue o projeto Viral Cutter usando
> `C:\Users\Theo Barros\Claude\Projects\CORTE VIRAL\CONTINUAR_PROJETO.md`.
> A fonte final fica em `D:\CORTE VIRAL\files`. Revise o estado atual antes de
> editar e preserve builds, ambiente e backups.
## Atualizacao 2026-06-21 - Viralume Studio

- O Viral Cutter Classic 2.3.1 continua preservado e independente.
- O Studio esta em `D:\CORTE VIRAL\studio` e abre em `http://127.0.0.1:8766/`.
- O editor ja possui legendas, SRT, inserts, templates e direcao de efeitos.
- Projetos estruturados agora sao salvos em
  `D:\CORTE VIRAL\studio\projects\*.viralume.json`.
- Proxima etapa tecnica: transcricao Whisper com timestamps por palavra e fila
  de renderizacao final FFmpeg/Remotion usando esse arquivo de projeto.
