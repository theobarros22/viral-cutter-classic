# Estabilização e empacotamento do Viral Cutter

**Data:** 11 de agosto de 2026

## Objetivo

Estabilizar o Viral Cutter atual, provar seu funcionamento com testes automatizados e um vídeo real e, somente depois, preparar um pacote executável para Windows. O produto continua focado em baixar vídeos e gerar cortes verticais. Calibrações de seleção de cenas e enquadramento ficam fora deste trabalho.

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

### Excluído

- Alterar heurísticas de escolha de cortes ou calibração de enquadramento.
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

### 4. Observabilidade

Haverá dois tipos de log:

- log do aplicativo, rotativo por data;
- log do projeto/processamento, associado ao checkpoint.

Cada etapa registra início, fim, duração, entrada resumida, saída resumida e exceção completa. Os logs não armazenam tokens, cookies ou conteúdo sensível desnecessário.

## Desempenho

Primeiro será medido onde o vídeo real consome tempo. A hipótese inicial é repetição de detecção de cenas e execução integral em CPU, mas nenhuma otimização será aplicada sem medição.

A aceleração NVIDIA será opcional. O programa deve funcionar corretamente em CPU; CUDA melhora desempenho, mas não pode ser requisito para iniciar. A combinação de PyTorch/CUDA será escolhida apenas entre versões compatíveis com Python 3.11 e com o hardware instalado.

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
6. Testar o pacote em uma pasta limpa, sem depender do repositório ou de Python global.
7. Reiniciar o Windows ou simular sessão limpa e validar o atalho, abertura, processamento e retomada.

## Empacotamento

O empacotamento só começa após os testes de estabilização passarem. O pacote inclui runtime, código, modelos e binários licenciados necessários. Dados do usuário, downloads, logs, checkpoints e configurações ficam fora da pasta imutável do aplicativo.

Antes da distribuição serão verificados tamanho, tempo de abertura, licenças de terceiros, falsos positivos de antivírus, atualização e desinstalação. A primeira saída será um pacote de teste; a versão definitiva só será marcada depois do teste do usuário com vídeo real.

## Critérios de conclusão

- O atalho inicia a aplicação repetidamente sem depender de caminhos antigos.
- A interface permanece ativa quando uma tarefa falha.
- Toda queda inesperada deixa stack trace e contexto suficientes no log.
- A suíte automatizada e os testes reais definidos acima passam em Python 3.11.
- O processamento longo apresenta progresso e pode ser cancelado com segurança.
- O pacote funciona em ambiente limpo e preserva dados do usuário entre execuções.
- Nenhuma calibração de corte ou expansão de produto é incluída neste ciclo.
