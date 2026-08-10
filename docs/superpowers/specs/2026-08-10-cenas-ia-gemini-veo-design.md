# Cenas com IA — Integração Gemini e Veo

**Data:** 2026-08-10  
**Status:** Aprovado para planejamento

## Objetivo

Adicionar ao Viral Cutter geração de cenas de apoio para cortes de podcast. O Gemini analisa a transcrição e propõe cenas; o Veo gera vídeos verticais que substituem temporariamente apenas a imagem, preservando integralmente o áudio original.

## Escopo inicial

- Integração direta pela Gemini API com geração de vídeo Veo.
- Cenas de apoio em tela inteira, formato 9:16, com duração configurável entre 3 e 8 segundos.
- Modos manual e automático.
- Estilo e quantidade configuráveis por projeto.
- Preservação do áudio original do podcast.
- Arquitetura preparada para um adaptador futuro do Vertex AI.
- Flow continua disponível como ferramenta manual, mas não integra o fluxo automatizado inicial.

## Fluxo do usuário

1. O usuário conclui a análise dos cortes.
2. Abre a seção **Cenas com IA** antes da exportação final.
3. Ativa a função e escolhe:
   - modo Manual ou Automático;
   - estilo visual;
   - quantidade máxima por corte;
   - duração;
   - limite de gerações e custo.
4. O Gemini analisa a transcrição e sugere os momentos mais adequados.
5. Cada sugestão mostra trecho, horário, prompt, duração e custo estimado.
6. No modo Manual, nenhuma geração ocorre sem confirmação.
7. No modo Automático, o sistema gera dentro dos limites definidos.
8. O Veo gera o vídeo vertical.
9. O Viral Cutter valida a mídia, permite aprovação e aplica a cena em tela inteira.
10. O áudio original permanece inalterado.

## Arquitetura

### 1. Provedor de IA

Uma interface isolada de provedor separará o restante do programa das APIs externas:

- geração e refinamento de prompts pelo Gemini;
- geração assíncrona de vídeo pelo Veo;
- consulta de operação;
- download do resultado;
- classificação normalizada de falhas.

A primeira implementação usará Gemini API. Um provedor Vertex AI poderá ser adicionado depois sem mudar a interface do usuário ou a montagem.

### 2. Analisador de cenas

Recebe transcrição, duração do corte e estilo. Retorna sugestões estruturadas contendo:

- início e fim;
- trecho que motivou a sugestão;
- prompt visual;
- prompt negativo quando aplicável;
- duração;
- prioridade;
- justificativa curta.

O analisador deve evitar introduções genéricas, repetições e cenas que não acrescentem informação visual.

### 3. Gerenciador de gerações

Controla fila, limites, retomada e prevenção de duplicidade. Cada pedido terá um identificador persistente e estados:

- sugerida;
- aguardando aprovação;
- gerando;
- gerada;
- aprovada;
- rejeitada;
- falhou.

O modo automático respeitará quantidade máxima e teto financeiro. O modo manual exigirá confirmação antes de consumir créditos.

### 4. Compositor de vídeo

Insere somente cenas aprovadas:

- tela inteira;
- proporção 9:16;
- duração entre 3 e 8 segundos;
- áudio removido da geração;
- áudio original do podcast copiado sem alteração;
- retorno ao enquadramento original após a cena.

Se a cena estiver ausente, inválida ou falhar, o trecho original permanece no vídeo.

### 5. Interface

Nova seção **Cenas com IA**, situada depois da análise dos cortes e antes da exportação final, com:

- chave geral de ativação;
- modo Manual/Automático;
- estilo realista, cinematográfico, documental, tecnológico ou personalizado;
- quantidade máxima por corte;
- duração;
- limite de gerações/custo;
- botão **Analisar e sugerir cenas**;
- galeria de sugestões e resultados;
- ações Gerar, Gerar novamente, Aprovar e Excluir;
- botão **Aplicar cenas aprovadas**;
- progresso e estado de cada pedido.

## Dados persistidos

Cada cena manterá:

- ID estável;
- ID do corte;
- início e fim;
- trecho da transcrição;
- prompt;
- modelo;
- orientação e resolução;
- duração;
- estado;
- identificador da operação externa;
- caminho do arquivo local;
- custo estimado, calculado pelas tarifas configuradas e identificado explicitamente como estimativa;
- mensagem de erro;
- datas de criação e atualização.

A chave da API nunca será persistida nesses dados.

## Credenciais e segurança

- A chave será configurada localmente em campo protegido.
- Não será registrada em logs, checkpoints, nomes de arquivos ou mensagens de erro.
- O programa fará um teste de conexão sem geração paga.
- Erros externos serão sanitizados antes de chegar à interface.
- O vídeo original nunca será sobrescrito.

## Falhas e recuperação

- Falha do Gemini: permitir editar o prompt manualmente ou tentar novamente.
- Falha do Veo: marcar apenas a cena afetada e continuar.
- Bloqueio de conteúdo: mostrar motivo sanitizado sem repetir automaticamente.
- Quota ou saldo insuficiente: interromper novas gerações, preservar as concluídas.
- Fechamento do programa: retomar operações persistidas.
- Arquivo inválido: rejeitar a cena e manter o vídeo original.
- Pedido duplicado: retornar o pedido existente em vez de consumir créditos novamente.
- Indisponibilidade geral: exportar o corte sem cenas de IA.

## Limites iniciais

- Uma a três cenas sugeridas por corte como valor padrão, com quantidade configurável.
- Duração final permitida: 3 a 8 segundos. O provedor solicitará uma duração aceita pelo modelo (por exemplo, 4, 6 ou 8 segundos) e o compositor aparará o resultado quando a duração final escolhida for diferente.
- Orientação padrão: 9:16.
- Uma variação por sugestão como padrão.
- Nenhum gasto automático sem teto configurado.
- A geração de vídeos inteiramente sintéticos fica fora deste primeiro escopo.

## Testes e critérios de aceite

1. Teste de conexão não gera cobrança de vídeo.
2. Gemini devolve sugestões estruturadas e válidas.
3. Limites manual, automático, financeiro e de quantidade são respeitados.
4. Solicitações duplicadas não geram duas cobranças.
5. Estado sobrevive ao fechamento e permite retomada.
6. Arquivos do Veo são validados antes da composição.
7. Cena ocupa a tela vertical sem deformação.
8. Áudio gerado pelo Veo não entra na exportação.
9. Áudio original do podcast é preservado.
10. Falha em uma cena não bloqueia as demais nem a exportação.
11. Vídeo original não é sobrescrito.
12. Um corte real é comparado antes e depois antes da liberação em produção.

## Fora do escopo

- Automação da interface web do Flow.
- Vídeos completos criados integralmente por IA.
- Voz sintética e substituição da voz do podcast.
- Avatares.
- Publicação automática nas redes sociais.
- Provedor Vertex AI na primeira versão.


