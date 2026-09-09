# Checkpoint — 09/09/2026 (tarde)

## O problema relatado

O programa achava **uma** pessoa num podcast com **dois** participantes.

## Diagnóstico medido

Instrumentando `detectar_pessoas_no_video` rodada a rodada em
`F:\Meu_Vídeo\RFNSL_BENY.mov`:

```
Rodada 1:  Pessoa 1 (esquerda) x=0.314  |  Pessoa 2 (direita) x=0.890   CERTO
Rodada 2:  Pessoa 1 (centro)   x=0.520                                  ERRADO
```

`0.520` é a média de `0.314` e `0.890`: a "pessoa no centro" era o ponto médio
entre dois homens separados por 57,6% da largura da tela.

As detecções do lado direito **nunca sumiram** — `DIREITA=6` sobreviveu a todos
os filtros em todas as cinco rodadas. A perda acontecia na fusão de grupos.

Prova visual: seis recortes do grupo 0 e três do grupo 1 mostram barba, cabelo,
cenário e **tatuagem no pescoço** distintos. São duas pessoas.

## Causa 1 — o máximo dos pares de embedding

`_fundir_grupos_da_mesma_pessoa` comparava dois grupos pelo **máximo** entre
todos os pares de embeddings. Com até oito poses de cada lado são 64 pares, e o
máximo de 64 amostras sobe só por haver mais amostra. Um grupo grande passava a
fundir com qualquer coisa, e bastava rodar mais rodadas para a fusão errada
acontecer — exatamente o que se via da rodada 2 em diante.

Passou a ser a **mediana**.

## Causa 2 — a geometria tinha sido descartada

`PARA-DESENVOLVEDORES.md`, regra 3, válida até a troca para identidade facial:

> Dois "lados" só viram duas pessoas se estiverem mais afastados que a soma dos
> meios-ombros **e** tiverem rostos de tamanho compatível.

E `VIRAL_CUTTER_PROJETO_COMPLETO.md` descreve o agrupamento original por
posição X (`x < 0.4` esquerda, `x > 0.6` direita).

O agrupamento por embedding jogou essa informação fora. A regra voltou como
**veto** em `_sao_participantes_distintos`: mesmo frame + separação ≥ 0,22 da
largura + tamanhos dentro de 1,7× ⇒ pessoas distintas, sem apelação.

O veto exige **co-ocorrência no mesmo frame** de propósito. Sem essa exigência,
a mesma pessoa filmada por duas câmeras em posições diferentes voltaria a virar
duas identidades — que foi o motivo de adotar o SFace. E sem dado de posição ou
tamanho ele não opina, então o caminho de fallback e a fusão de visões
duplicadas em split screen continuam valendo.

## Resultado

```
2 pessoas nas cinco rodadas:  esquerda x=0.396 (17 aparições)
                              direita  x=0.754 (8 aparições)
Alinhamento YuNet: 35 de 35 tentativas
```

170 testes passando. `tests/test_participantes_distintos.py` cobre os dois
lados da regra: o veto que separa e os três casos em que ele não deve agir.

## Também nesta sessão

- **Pasta temporária**: `iniciar.bat` fixava `D:\ViralCutter\gradio_temp`, e `D:`
  é um leitor de cartão sem mídia. Consolidado em
  `runtime.configurar_pasta_temporaria()`, com teste de escrita real.
- **faster-whisper** estava no `requirements` desde 04/07 e nunca instalado. O
  código caía em silêncio no openai-whisper. Medido: **2,41× mais rápido**
  (11,6s contra 28,0s em 300s de áudio, mesma GPU, mesmo modelo). Num podcast de
  144 min a transcrição cai de ~13,5 min para ~5,6 min.
- `diagnostico.py` agora avisa quando um pacote de desempenho falta, e diz o que
  custa — para a próxima perda silenciosa aparecer na abertura.
- **Repositório consolidado** nesta pasta. Antes era um worktree dependente do
  `F:`, e duas pastas diferentes dividiam o mesmo índice.

## Em aberto

- `gh auth login` — não há remote; os espelhos são locais (`C:` e `E:`).
- Comparar o enquadramento vertical atual com o do pacote de 26/08: o atual
  acrescenta câmera virtual (`_alvos_seguindo_falante`), fusão de shots curtos e
  reancoragem por rosto. São 291 linhas diferentes. Qual é melhor **na tela**
  ainda não foi medido — precisa de render lado a lado do mesmo trecho.
