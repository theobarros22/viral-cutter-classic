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
- importação de arquivos SRT;
- exportação dos cartões editados para SRT.
- Viralume Quick com marcação de entrada e saída;
- corte rápido sem recodificação;
- atalhos de teclado para reprodução e marcação.
- painel de Direção Viral Automática;
- eventos de zoom e SFX baseados nos cartões com ênfase;
- filtro FFmpeg para barra de progresso;
- suporte técnico a LUT `.cube`;
- construção de mixagem SFX com atraso em milissegundos.

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

## SRT

- `Importar SRT`: transforma cada bloco em um cartão editável.
- Linhas múltiplas são unificadas no mesmo cartão.
- Tags simples de formatação são removidas na importação.
- `Exportar SRT`: baixa os textos e tempos atuais em formato universal.
- Estilos e motions continuam no projeto Viralume, pois o SRT armazena
  principalmente texto e sincronização.

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

## Viralume Quick

- Espaço: reproduzir ou pausar.
- `I`: marcar entrada.
- `O`: marcar saída.
- Setas esquerda/direita: navegar um segundo.
- Exportação atual usa `FFmpeg -c copy`.
- Cortes lossless respeitam keyframes e podem incluir alguns frames extras.
- A próxima opção será `Corte preciso`, com recodificação somente do necessário.

## Direção Viral

Estado atual:

- Auto-reenquadramento: já existe no motor Python do Classic.
- Inserts: disponíveis no Caption Studio.
- Zoom dinâmico: filtro FFmpeg e eventos implementados.
- SFX automático: construção de filtros `adelay` e `amix` implementada.
- Barra de progresso: filtro FFmpeg implementado.
- LUT em lote: validação e filtro `lut3d` implementados.
- Hook Master: controle e evento inicial disponíveis no protótipo.

Próxima integração:

1. enviar os eventos do navegador ao servidor local;
2. selecionar arquivos SFX reais licenciados;
3. executar o passe final FFmpeg;
4. combinar com a renderização Remotion das legendas.
