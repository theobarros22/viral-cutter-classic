# Estabilização e empacotamento do Viral Cutter

**Data:** 11 de agosto de 2026

## Objetivo

Estabilizar o Viral Cutter atual, melhorar a segurança dos enquadramentos, provar seu funcionamento com testes automatizados e vídeos reais e, somente depois, preparar um pacote executável para Windows. O produto continua focado em baixar vídeos e gerar cortes verticais.

## Evidências do diagnóstico

- A interface exibiu perda de conexão porque não havia processo escutando a porta 7860.
- O atalho inicia o servidor em janela oculta e não redireciona `stdout` ou `stderr`; por isso a causa fatal desaparece quando o processo encerra.
- `F:\CORTE VIRAL\files\venv311` está inválido e referencia uma instalação antiga em `C:\Users\Theo Barros`.
- O atalho usa `E:\PROJETOS\viral-cutter-v2\venv-local`, que executa Python 3.13.14, enquanto o diagnóstico do projeto exige Python 3.11.
- A máquina tem GPU NVIDIA, mas o PyTorch instalado é CPU-only.
- O ambiente usado pelo atalho não contém `pytest`; a suíte `unittest` executou 77 testes e todos passaram, incluindo smoke test real com FFmpeg.
- O log de 10 de agosto mostra transcrição e chamadas repetidas de detecção de cenas durante várias horas, sem registrar a exceção ou o encerramento do processo.
- A inicialização monitorada respondeu HTTP 200 em `http://127.0.0.1:7860/`.
- Existem avisos de API depreciada do Gradio e mensagens com codificação corrompida em algumas saídas.
- A árvore principal está suja; mudanças do usuário e trabalho paralelo devem ser preservados.

## Escopo

### Incluído

1. Ambiente Python 3.11 reproduzível e independente de nomes de usuário.
2. Validação explícita de Python, módulos nativos, FFmpeg, FFprobe, modelos e diretórios graváveis.
3. Inicializador visível em caso de falha, com log persistente de inicialização e erro fatal.
4. Supervisor local para impedir instâncias duplicadas, detectar porta ocupada e oferecer reinício controlado.
5. Isolamento de falhas de tarefas para que um erro de vídeo não encerre o servidor Gradio.
6. Instrumentação de duração e progresso nas fronteiras: download, transcrição, análise de cenas, enquadramento e exportação.
7. Limites e cancelamento cooperativo para trabalhos excessivamente longos.
8. Revisão do caminho crítico de detecção de cenas para evitar repetição desnecessária por clipe quando resultados puderem ser reutilizados.
9. Padronização UTF-8 em console, logs, subprocessos e nomes de arquivos.
10. Atualização compatível dos parâmetros depreciados do Gradio.
11. Testes unitários, integração, smoke test e teste com vídeo real.
12. Congelamento de dependências e empacotamento Windows após a estabilização.
13. Calibração dos enquadramentos para preservar integralmente participantes, grupos e microfones relevantes.
14. Validação automática de segurança visual antes de aceitar cada cena exportada.

### Excluído

- Alterar a seleção editorial ou a pontuação de conteúdo dos cortes.
- Adicionar Lovable, Flow, Gemini, banco de mídia ou novas funções de edição.
- Reescrever o motor Python/FFmpeg.
- Comprar serviços ou créditos externos.
- Incorporar mudanças incompletas de outras worktrees.

## Arquitetura de estabilização

### 1. Ambiente e bootstrap

Um bootstrap único resolve caminhos a partir da pasta do aplicativo, configura UTF-8, acrescenta os binários empacotados ao `PATH`, valida dependências e inicia a interface. Nenhum arquivo pode conter caminho absoluto dependente do usuário atual.

O modo de desenvolvimento usa Python 3.11. O executável empacotado leva seu próprio runtime e não depende de Python instalado globalmente.

### 2. Inicializador e supervisor

O atalho chama um inicializador pequeno e rastreável. Ele:

- verifica se a porta 7860 já pertence a uma instância saudável;
- abre a instância existente quando aplicável;
- inicia uma nova instância com `stdout` e `stderr` persistidos;
- aguarda uma verificação HTTP de saúde, não apenas a abertura da porta;
- mostra ao usuário uma mensagem curta com o caminho do log quando a inicialização falhar;
- nunca deixa múltiplos processamentos do mesmo projeto ativos.

O servidor não deve reiniciar automaticamente em ciclo infinito. Uma nova tentativa exige uma causa registrada e um limite explícito.

### 3. Execução de tarefas

Cada trabalho possui identificador, estado, etapa, progresso, timestamps, cancelamento e erro serializável. Exceções de download, transcrição, análise, enquadramento ou FFmpeg são capturadas no limite da tarefa, registradas e devolvidas à interface. Apenas falhas de bootstrap podem encerrar o servidor.

Resultados reutilizáveis, como transcrição, análise de pessoas e cenas, permanecem associados ao checkpoint do vídeo. A implementação só reutiliza dados cuja assinatura de entrada e versão do algoritmo coincidam.

O checkpoint é um manifesto JSON versionado e gravado atomicamente (arquivo temporário seguido de substituição). Ele é a fonte de verdade da retomada; logs são evidência de diagnóstico, não são interpretados para reconstruir estado. O manifesto guarda identificador do trabalho, assinatura da entrada, configurações, etapa atual, itens concluídos, artefatos, timestamps, erro e um dos estados `em_andamento`, `interrompido` ou `concluido`.

Na abertura, trabalhos `em_andamento` sem processo proprietário vivo são classificados como `interrompido` e apresentados na interface com a ação **Continuar de onde parou**. Antes de reutilizar uma etapa ou clipe, o programa valida existência, assinatura e integridade do artefato com FFprobe quando aplicável. Artefato ausente, incompatível ou corrompido invalida somente a unidade correspondente e ela é refeita; unidades válidas permanecem preservadas.

A persistência ocorre nas fronteiras idempotentes: após download confirmado, transcrição válida, análise visual válida e cada clipe exportado e validado. Operações parciais escrevem em nome temporário e só são promovidas ao nome definitivo depois da validação. O programa nunca marca uma etapa como concluída antes de seu artefato estar durável.

### 4. Observabilidade

Haverá dois tipos de log:

- log do aplicativo, rotativo por data;
- log do projeto/processamento, associado ao checkpoint.

Cada etapa registra início, fim, duração, entrada resumida, saída resumida e exceção completa. Os logs não armazenam tokens, cookies ou conteúdo sensível desnecessário.

## Desempenho

Primeiro será medido onde o vídeo real consome tempo. A hipótese inicial é repetição de detecção de cenas e execução integral em CPU, mas nenhuma otimização será aplicada sem medição.

A aceleração NVIDIA será opcional. O programa deve funcionar corretamente em CPU; CUDA melhora desempenho, mas não pode ser requisito para iniciar. A combinação de PyTorch/CUDA será escolhida apenas entre versões compatíveis com Python 3.11 e com o hardware instalado.

## Enquadramento humano seguro

### Regras invariantes

- Nenhum corte é exportado sem pelo menos uma pessoa validada na cena, exceto quando o usuário escolher explicitamente um modo sem pessoas.
- Cabeça, rosto e queixo permanecem dentro do quadro, com margem superior e lateral de segurança.
- Ombros, braços e corpo visíveis não podem ser cortados de modo abrupto quando um plano mais aberto resolver o problema.
- O microfone permanece visível quando fizer parte do contexto do participante e couber no recorte seguro.
- O algoritmo prefere reduzir o zoom e mostrar mais cenário a cortar uma pessoa.
- O vazio entre participantes nunca pode ser escolhido como assunto principal.
- Detecções de telas, fotografias, cartazes e aparições esporádicas não podem deslocar o enquadramento de participantes reais.

As margens são calculadas proporcionalmente ao tamanho da cabeça e ao quadro de origem. Os valores iniciais serão definidos por testes de aceitação e mantidos como configuração versionada, não como números espalhados no código.

### Escolha de layout

- **Solo sustentado:** quando uma pessoa fala sozinha por pelo menos três segundos, usar plano individual centralizado nela.
- **Conversa alternada:** quando participantes alternam falas com frequência, usar split com crops independentes.
- **Duas pessoas no mesmo plano:** preservar o grupo em plano aberto quando ambas couberem com segurança.
- **Câmera frontal com pessoas lado a lado:** permitir split vertical com uma pessoa por painel quando o plano de grupo não oferecer leitura adequada.
- **Mais de duas pessoas:** priorizar participantes selecionados e usar plano de grupo quando necessário para não cortar pessoas relevantes.
- **Incerteza:** manter o último layout seguro ou usar plano mais aberto; nunca saltar para crop central vazio.

### Composição e estabilidade

Cada painel do split tem rastreamento e crop independentes. A posição desejada é filtrada no tempo, com limite de velocidade, zona morta para pequenos movimentos e histerese na troca de layout. Mudanças de solo para split e vice-versa exigem evidência sustentada, evitando piscadas e movimentos bruscos.

O crop é calculado a partir do conjunto de caixas humanas válidas, expandidas pelas margens de segurança e limitado às bordas da imagem. Quando a proporção 9:16 não comportar o conjunto com segurança, o sistema usa plano mais aberto, composição dividida ou marca a cena para revisão em vez de cortar alguém.

### Validação antes da exportação

Uma cena só é aceita quando amostras do início, meio e fim confirmarem:

- participantes esperados presentes;
- nenhuma cabeça ou rosto cruzando as áreas proibidas da borda;
- ocupação humana mínima sem zoom excessivo;
- ausência de centro vazio como foco;
- estabilidade entre amostras;
- dois painéis válidos quando o layout for split.

Quando a validação falhar, o sistema tenta uma única recomposição mais aberta. Se continuar insegura, a cena é marcada para revisão e o relatório explica a regra violada. O programa não oculta a falha usando crop central.

## Tratamento de erros

- Erro recuperável de um vídeo: manter servidor e interface ativos, preservar checkpoint e permitir nova tentativa da etapa.
- Arquivo temporário bloqueado: registrar, adiar limpeza e não mascarar o erro original.
- Dependência ausente ou incompatível: interromper bootstrap com diagnóstico objetivo.
- Porta ocupada por processo desconhecido: não matar o processo; informar PID e solicitar ação do usuário.
- Falta de espaço ou permissão: falhar antes do processamento quando detectável.
- Encerramento inesperado: o próximo início aponta para o último log fatal e oferece retomada do projeto.

## Estratégia de testes

1. Preservar os 77 testes atuais como linha de base.
2. Adicionar testes que falham antes de cada correção: resolução de runtime, captura de erro fatal, health check, porta ocupada, isolamento de exceção, cancelamento e UTF-8.
3. Executar smoke test com FFmpeg e nomes contendo espaços e acentos.
4. Executar um vídeo real curto para validar todo o fluxo.
5. Executar um vídeo real longo para medir transcrição e detecção de cenas, com critérios de progresso e cancelamento.
6. Criar fixtures e testes de enquadramento para pessoa nas bordas, diferenças de altura, microfone, duas pessoas no mesmo plano, duas pessoas lado a lado em câmera frontal, conversa alternada, mais de duas pessoas e detecção falsa em tela ou cartaz.
7. Validar em frames de início, meio e fim que nenhuma cabeça ou rosto foi cortado e que o centro vazio não foi escolhido.
8. Medir estabilidade temporal e limitar deslocamentos e trocas de layout em sequências com pequenas oscilações de detecção.
9. Comparar vídeos reais de referência antes/depois e exigir aprovação visual do usuário.
10. Testar o pacote em uma pasta limpa, sem depender do repositório ou de Python global.
11. Reiniciar o Windows ou simular sessão limpa e validar o atalho, abertura, processamento e retomada.
12. Simular interrupção após cada fronteira persistida, corromper um único artefato e confirmar que a retomada preserva os válidos e refaz somente o inválido.

## Empacotamento

O empacotamento só começa após os testes de estabilização passarem. O pacote inclui runtime, código, modelos e binários licenciados necessários. Dados do usuário, downloads, logs, checkpoints e configurações ficam fora da pasta imutável do aplicativo.

Antes da distribuição serão verificados tamanho, tempo de abertura, licenças de terceiros, falsos positivos de antivírus, atualização e desinstalação. A primeira saída será um pacote de teste; a versão definitiva só será marcada depois do teste do usuário com vídeo real.

## Critérios de conclusão

- O atalho inicia a aplicação repetidamente sem depender de caminhos antigos.
- A interface permanece ativa quando uma tarefa falha.
- Toda queda inesperada deixa stack trace e contexto suficientes no log.
- A suíte automatizada e os testes reais definidos acima passam em Python 3.11.
- O processamento longo apresenta progresso e pode ser cancelado com segurança.
- Participantes permanecem inteiros e centralizados dentro das áreas seguras nos casos de aceitação.
- Planos de grupo e splits preservam todas as pessoas priorizadas e não focam o centro vazio.
- Mudanças de crop e layout permanecem visualmente estáveis.
- Cenas que não admitem composição segura são rejeitadas ou marcadas para revisão, nunca mascaradas por crop central.
- O pacote funciona em ambiente limpo e preserva dados do usuário entre execuções.
- Nenhuma alteração na seleção editorial de conteúdo ou expansão de produto é incluída neste ciclo.
