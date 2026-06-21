# Viral Cutter Studio

Aplicativo novo e separado do Viral Cutter Classic 2.3.1.

## Protótipo atual

- player vertical;
- cartões sincronizados;
- edição de texto sem recarregar;
- estilo individual;
- efeito individual;
- destaque de palavras;
- timeline gerada;
- reprodução simulada;
- ação "Aplicar na timeline".

## Executar a prévia

```powershell
python -m http.server 8766 --bind 127.0.0.1 --directory studio
```

Acesse `http://127.0.0.1:8766`.

## Arquitetura de produção

1. React e TypeScript para o editor.
2. Whisper com timestamps por palavra.
3. Python local para transcrição e análise.
4. Remotion para preview e renderização das legendas.
5. FFmpeg para composição e codificação final.
6. pywebview para o executável Windows separado.

## Regra de produto

O Classic permanece em:

`D:\CORTE VIRAL\files\dist\ViralCutter\ViralCutter.exe`

O Studio será construído futuramente em:

`D:\CORTE VIRAL\studio\dist\ViralCutterStudio\ViralCutterStudio.exe`
