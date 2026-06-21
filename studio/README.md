# Viralume Studio

Aplicativo novo e separado do Viral Cutter Classic 2.3.1.

## Protótipo atual

- player vertical;
- upload de vídeo real no navegador;
- reprodução e velocidade;
- cartões sincronizados;
- edição de texto sem recarregar;
- estilo individual;
- efeito individual;
- destaque de palavras;
- timeline gerada;
- reprodução simulada;
- ação "Aplicar na timeline".
- salvamento do rascunho no navegador.
- inserts de JPEG, PNG e WEBP;
- inserts de MP4, MOV e WEBM;
- tempo de entrada e saída;
- posição e escala;
- trilha separada de inserts.

## Executar a prévia

```powershell
python -m http.server 8766 --bind 127.0.0.1 --directory studio
```

Acesse `http://127.0.0.1:8766`.

Para testar:

1. clique em `Carregar vídeo`;
2. selecione um MP4;
3. pressione `Reproduzir`;
4. clique nos cartões para navegar;
5. edite texto, estilo e ênfase;
6. clique em `Salvar rascunho`.

Para adicionar uma reportagem, print ou logo:

1. posicione o vídeo no instante desejado;
2. clique em `Adicionar insert`;
3. escolha uma imagem ou vídeo;
4. ajuste início, fim, posição e escala;
5. confira o bloco na trilha `INSERTS`.

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

O Viralume será construído futuramente em:

`D:\CORTE VIRAL\studio\dist\Viralume\Viralume.exe`
