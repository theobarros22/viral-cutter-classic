# Para desenvolvedores

Guia rápido para quem vai mexer no código do Viral Cutter Classic.

---

## Como o programa está organizado

O trabalho acontece em quatro etapas, e cada uma vive num módulo próprio.
`pipeline.py` é o maestro: ele chama os outros na ordem e cuida do checkpoint.

| Arquivo | Responsabilidade |
|---|---|
| `app_desktop.py` | ponto de entrada: sobe o servidor local e abre a janela nativa |
| `interface.py` | toda a interface (Gradio) |
| `pipeline.py` | orquestra as etapas, checkpoint, progresso e retomada |
| `analise.py` | transcrição (Whisper) e escolha dos trechos |
| `cortes.py` | corte dos segmentos, silêncios, hook |
| `rostos.py` | detecção de pessoas e de quem está falando |
| `enquadramento.py` | reenquadramento 9:16 — **leia a seção de regra abaixo** |
| `checkpoint.py` | estado do trabalho, retomada e leitura do log |
| `ffmpeg_utils.py` | chamadas de FFmpeg/FFprobe, escolha de encoder |
| `legendas.py` | legendas ASS |

Regra prática: **a interface não decide nada.** Se você precisa mudar
comportamento, o lugar é o módulo da etapa, não `interface.py`.

---

## Rodando

```bash
PREPARAR_AMBIENTE.bat
```

Depois:

```bash
venv311\Scripts\python.exe -m pytest tests -q
```

Os testes usam **pytest**, não unittest. Rodar `python -m unittest discover`
executa apenas parte da suíte e **ignora 41 testes em silêncio** — o que dá a
falsa impressão de que está tudo certo. Use sempre pytest.

Para abrir o app em modo desenvolvimento:

```bash
iniciar.bat
```

---

## A regra do enquadramento — não afrouxe sem ler

**Ordem de preferência**, definida com exemplos reais e validada nos clipes
do Papo Reto #60:

1. **Crop fechado com a pessoa centralizada** — o ideal. Cabeça inteira,
   folga em cima, plano médio.
2. **Dois painéis horizontais empilhados** — aceitável. Mostra tudo e nunca
   corta ninguém.
3. **Quadro aberto** — na dúvida. Usa a altura inteira da fonte, centraliza
   nas pessoas e não aperta o enquadramento.

O único resultado proibido é entregar a **pessoa principal cortada**.

### A câmera acompanha a pessoa

Esta é a parte que resolveu o problema, e o motivo é geométrico: num 9:16
sobre fonte 16:9 o quadro mostra **31,7% da largura** e a cabeça ocupa
**22%** — sobram ~7% de folga. Num podcast a pessoa gesticula e se inclina
mais que isso o tempo todo, então **um crop parado é matematicamente
incapaz de não cortar**. Nenhum ajuste de agrupamento resolve isso.

O quadro segue a pessoa dentro do shot via expressão de tempo no filtro
`crop` do FFmpeg — o filtro aceita, então isso roda no motor rápido, sem
cair no renderizador por pipe. A trajetória usa média exponencial contra
tremor e limite de velocidade para não disparar atrás de uma detecção
isolada errada.

Se for mexer aqui: o alvo de cada shot é **reancorado nos rostos reais** do
próprio intervalo (`_ajustar_segmentos_pelos_frames`). Isso existe porque o
resto do cálculo trabalha com medianas de amostras, e a validação conferia o
crop contra o **alvo** — nunca contra o frame. Com alvo errado, ela aprovava
com confiança um quadro que cortava a pessoa. Foi o bug que mais custou tempo
neste projeto.

### Como verificar de verdade

A suíte de testes **não pega problema visual**. O que pega é auditar os
clipes exportados com detecção facial em vários frames de cada um. Dois
cuidados aprendidos na prática:

- num plano com duas pessoas, enquadrar uma **corta a outra** na borda: isso
  é inevitável e não é defeito. Só conta como falha o **sujeito principal**
  aparecer cortado;
- o detector produz falsos positivos em quadro vertical — um "rosto"
  ocupando quase metade da largura começando exatamente na borda é detecção
  espúria, não corte. **Abra o frame antes de acreditar no número.**



Esta é a parte mais sensível do programa, e a que mais gerou retrabalho.
A regra é **invariante**: qualquer mudança precisa manter as quatro garantias
abaixo, todas cobertas por `tests/test_enquadramento_seguro.py`.

1. **Cabeça inteira é obrigatória.** A caixa da cabeça precisa caber no crop
   com margem livre nas quatro bordas. Quem já aparece cortado na fonte só é
   aceito se o crop encostar na mesma borda — nunca se corta mais do que o
   vídeo original já cortava.

2. **Ombros e tronco são preferência, não critério de reprovação.** Num close
   de podcast os ombros não cabem num 9:16. Exigir isso reprova até os quadros
   corretos — foi medido com clipes reais. Eles servem só para escolher o
   melhor centro do crop.

3. **Foco em pessoa válida.** Dois "lados" só viram duas pessoas se estiverem
   mais afastados que a soma dos meios-ombros **e** tiverem rostos de tamanho
   compatível. Sem isso, uma detecção espúria ao lado do falante virava "lado B"
   e o split screen mostrava a mesma pessoa nos dois painéis. Há também um piso
   e um teto de tamanho de rosto: abaixo do piso é ruído, acima do teto é falso
   positivo (rosto ocupando um terço do quadro não existe em podcast).

4. **Um único ponto de decisão.** `_calcular_filtros_shot` é a fonte única de
   layout para o motor rápido (FFmpeg) **e** para o fallback frame a frame.
   Nenhum motor pode calcular crop por conta própria, senão os dois divergem e
   o bug só aparece num deles.

Quando nenhum modo é seguro, o clipe recebe status `revisar`, com o motivo e o
**segundo exato** registrados — e **não conta como concluído**.

A justificativa completa, com os casos reais que motivaram cada regra, está em
`docs/superpowers/specs/2026-08-20-retomada-progresso-enquadramento-seguro-design.md`.

---

## Retomada e checkpoint

Um trabalho longo precisa sobreviver a qualquer interrupção. O estado vem de
três fontes, nesta ordem de confiança:

1. **Checkpoint** (`.viral_cutter_checkpoint_*.json` na pasta de saída).
2. **Log persistente** — se o checkpoint sumiu ou ficou defasado,
   `recuperar_do_log()` extrai os candidatos das linhas `Salvo:` e `REVISAR`.
3. **Varredura da pasta** de saída.

O log **nunca é prova sozinho**: todo candidato passa por FFprobe antes de
contar como pronto. Se mexer nas mensagens de log, cuide para não quebrar esse
parser — há testes para isso.

Transcrição, pessoas detectadas e segmentos são persistidos em disco por
assinatura do vídeo. Sem isso, fechar o programa obriga a re-transcrever tudo.

---

## Desempenho

Há dois motores de exportação:

- **Rápido:** um único `filter_complex` do FFmpeg com todos os shots. É o
  caminho normal, e usa NVENC quando existe GPU NVIDIA.
- **Seguro:** frame a frame por pipe. Entra quando o plano é complexo demais
  ou o grafo falha.

Os dois obedecem ao mesmo layout validado. Se você mudar a matemática do crop,
mude no ponto único — e rode os testes, que comparam os dois.

Referência de ganho: o motor rápido derrubou o enquadramento de cerca de
**430 s para 96 s por clipe** na mesma máquina.

---

## Comparando desempenho entre máquinas

```bash
python coletar_ambiente.py relatorio.txt
```

Gera hardware, versões, disponibilidade de NVENC e as médias por etapa
extraídas dos logs reais. Para comparar duas máquinas de forma honesta:

- use **o mesmo vídeo** e o **mesmo perfil** nos dois computadores;
- compare a média por clipe, não o total — o número de clipes varia;
- registre se `CUDA ativo` estava sim ou não; é a maior variável isolada;
- rode com a máquina sem outro trabalho pesado (uma exportação de vídeo em
  outro programa disputa o mesmo encoder e distorce a medição — isso já
  causou uma falha real aqui).

---

## Antes de propor uma mudança

1. `venv311\Scripts\python.exe -m pytest tests -q` — tudo verde.
2. Processe um vídeo real de verdade. A suíte não pega problema visual.
3. Se mexeu em enquadramento, **olhe os quadros**: extraia um frame de vários
   clipes e confira se ninguém ficou cortado. Foi assim que quatro defeitos
   distintos apareceram, e nenhum deles quebrava teste nenhum.
4. Se mexeu em retomada, teste interrompendo de verdade no meio.

Um teste passando não é prova de que o clipe está bonito. Os dois importam.
