# CHECKPOINT COMPLETO — VIRAL CUTTER CLASSIC 2.3.2

Data do checkpoint: 11/08/2026  
Projeto: Viral Cutter Classic  
Estado: em produção e em validação com vídeos reais  
Objetivo deste documento: permitir a retomada do trabalho sem perder decisões,
estado técnico, avaliação prática, pendências ou planos futuros.

## 1. Decisão principal

A versão atual será preservada como **Viral Cutter Classic 2.3.2**. Ela deve
continuar disponível para a produção diária enquanto uma versão Beta mais
completa é desenvolvida separadamente.

Não misturar a Classic com o Viralume Studio nem com experimentos futuros. A
Classic tem uma missão clara: baixar/importar vídeos, identificar participantes,
analisar conteúdo, produzir cortes e enquadrá-los com segurança.

## 2. Avaliação real do usuário

- Os cortes, sua disposição e o enquadramento atendem aproximadamente 90% da
  necessidade real.
- O resultado foi avaliado como próximo de 10/10.
- A qualidade atual foi considerada muito boa e o caminho do projeto é
  promissor.
- Esta versão deve ser tratada como baseline de qualidade. Qualquer versão
  futura precisa provar que não piorou cortes, enquadramentos ou confiabilidade.
- O usuário continua realizando testes reais antes do empacotamento definitivo.

## 3. Estado técnico exato

- Worktree: `E:\PROJETOS\viral-cutter-classic-build`
- Branch: `release/viral-cutter-classic`
- HEAD: `cf2d82cb6cdd6b11a4208fbbed603522c5574aea`
- Commit atual: `cf2d82c fix: allow classic page scrolling`
- Tag existente `classic-v2.3.2`: ainda aponta para o estado anterior às
  correções finais de rolagem. Atualizar a tag somente no fechamento da release.
- Versão exibida: `Viral Cutter Classic 2.3.2`
- Python de build: 3.11, ambiente `venv311`
- Formato do pacote: PyInstaller `onedir`, sem console.
- Executável atual:
  `E:\PROJETOS\viral-cutter-classic-build\dist\ViralCutter\ViralCutter.exe`
- Tamanho do executável: 51.706.506 bytes.
- SHA-256 do executável atual:
  `D15E08F1CB0E0ECC7F29479D2CE5BE5592E9515F8F3D7B04CE8D3E602DE40F37`
- Atalho:
  `C:\Users\theob\Desktop\Viral Cutter Classic 2.3.2.lnk`
- URL local: `http://127.0.0.1:7860/`
- No momento do checkpoint, a interface respondeu HTTP 200.

O executável é `onedir`: ele depende da pasta `_internal` ao lado. Não distribuir
somente o arquivo `.exe` isolado.

## 4. Funcionalidades presentes

- Upload de vídeo local.
- Download de vídeo por link, incluindo YouTube, via `yt-dlp`.
- Detecção de participantes com MediaPipe e fallback OpenCV.
- Busca adaptativa de rostos após introduções longas.
- Agrupamento de identidades e filtragem de falsos participantes.
- Seleção das pessoas que devem ser priorizadas.
- Transcrição com Whisper, GPU quando disponível e cache persistente.
- Análise de conteúdo online e modo offline.
- Seleção de segmentos/clipes.
- Perfis Rápido, Equilibrado e Máxima Qualidade.
- Exportação 720p, 1080p e 4K.
- Enquadramento vertical por cenas.
- Pessoa falando sozinha destacada após tempo suficiente.
- Tela dividida quando participantes conversam/alternam fala.
- Composição de dois painéis com crops independentes.
- Margens de segurança para evitar cortar rosto/cabeça nas bordas.
- Plano mais aberto quando o rosto é pequeno.
- Enquadramento de grupos e duas pessoas do mesmo lado.
- NVENC quando disponível, com fallback por CPU.
- Checkpoint persistente por trabalho e retomada de clipes já concluídos.
- Bloqueio de processamento duplicado do mesmo projeto.
- Logs gerais e logs individuais por trabalho.
- Abertura das pastas de saída e logs.
- Aba de legendas animadas preservada.

## 5. Regras de enquadramento consolidadas

Estas regras representam o comportamento desejado e não devem regredir:

1. Todo corte de entrevista/podcast deve priorizar pessoas reais, nunca um centro
   vazio quando há participantes disponíveis.
2. A pessoa deve ficar centralizada com margem nas laterais e acima da cabeça.
3. Evitar zoom excessivo; preservar microfone, tronco, mãos e contexto quando
   possível.
4. Não cortar pessoa ao meio nem encostar rosto/cabeça na borda.
5. Quando uma pessoa fala sozinha por um período relevante, destacá-la.
6. Quando duas pessoas conversam com alternância frequente, usar tela dividida.
7. Em tela dividida, cada pessoa tem crop independente e deve ficar centralizada.
8. Duas pessoas do mesmo lado/câmera devem caber juntas quando a cena exigir.
9. Mudanças de câmera e de lado não devem criar uma nova identidade falsa.
10. Rostos passageiros, televisões, cartazes e estátuas não devem virar
    participantes prioritários.

## 6. Trabalho realizado nesta etapa

- Localização e preservação da versão correta com download por YouTube.
- Correção de problemas de ambiente e carregamento do OpenCV.
- Ampliação/refinamento da detecção de participantes.
- Busca adaptativa em rodadas para ultrapassar introduções longas.
- Critério de amostras suficientes por identidade/lado da entrevista.
- Refinamento de crops individuais, de grupos e de tela dividida.
- Validação de limites humanos e crops seguros.
- Correção de conflito de arquivos temporários em uso.
- Retomada por checkpoint, reaproveitando clipes concluídos.
- Bloqueio de duas execuções do mesmo trabalho.
- Organização da interface Classic em formato horizontal 16:9.
- Cabeçalho compacto e três áreas: fluxo, trabalho e configurações.
- Correção definitiva do acesso às ferramentas pela rolagem global da página.
- Criação de metadados Classic 2.3.2.
- Criação de ambiente Python 3.11 reproduzível.
- Inclusão de FFmpeg/FFprobe e configuração PyInstaller.
- Geração de executável `onedir` e atalho na Área de Trabalho.
- Validação automática do executável real por processo vivo e HTTP 200.

Commits principais desta fase:

- `6639238 feat: add classic 16x9 desktop layout`
- `fb7a382 build: version classic release 2.3.2`
- `cb6f8d8 fix: keep classic tools accessible with scroll`
- `cf2d82c fix: allow classic page scrolling`

## 7. Testes e evidências

- Suíte mais recente: 84/84 testes aprovados.
- Testes estruturais da interface: 5/5 aprovados.
- `py_compile interface.py`: aprovado.
- `git diff --check`: aprovado nas alterações de código.
- Smoke funcional real com FFmpeg: aprovado.
- Corte/enquadramento com espaços e acentos no caminho: aprovado.
- Retomada de trabalho: aprovado; clipe concluído foi pulado corretamente.
- Build PyInstaller: aprovado.
- Validador do build: processo vivo e interface HTTP respondendo.
- Após reinicialização do computador, o executável abriu e respondeu HTTP 200.
- Após a correção final da rolagem, o usuário confirmou: “Agora sim, deu tudo
  certo”.

Avisos opcionais do PyInstaller sobre TensorBoard, Tokenizers, Aiofiles, JAX e
TBB não impediram o build nem o teste de inicialização. Reavaliar antes de uma
distribuição externa, mas não adicionar dependências sem necessidade comprovada.

## 8. Problema conhecido prioritário — visibilidade de andamento

O processamento funciona, mas o usuário não consegue acompanhar claramente se
cada fase está começando, avançando, próxima de terminar ou concluída. Não
alterar isso durante os testes atuais; implementar depois, sem interromper a
produção.

O painel futuro deve mostrar:

- etapa atual e etapas concluídas;
- percentual da etapa e percentual geral;
- clipes concluídos e total previsto;
- tempo decorrido e estimativa restante;
- estados aguardando, processando, concluído, pausado e erro;
- indicação clara de quando é seguro avançar para a próxima etapa;
- retomada/checkpoint encontrado e o ponto exato recuperado;
- mensagem compreensível quando a estimativa ainda não puder ser calculada.

## 9. Checklist de validação real antes do pacote definitivo

- [ ] Download de um vídeo real por YouTube.
- [ ] Upload de vídeo local.
- [ ] Uma pessoa em close.
- [ ] Duas pessoas lado a lado.
- [ ] Duas pessoas frente a frente com cortes de câmera.
- [ ] Três ou quatro participantes.
- [ ] Introdução longa antes de aparecerem rostos.
- [ ] Plano aberto com rostos pequenos.
- [ ] Duas pessoas do mesmo lado/câmera.
- [ ] Alternância de fala e tela dividida.
- [ ] Fala solo longa e destaque individual.
- [ ] Nenhum rosto/cabeça cortado nas bordas.
- [ ] Microfone, tronco e contexto preservados quando possível.
- [ ] Transcrição e análise dos melhores trechos.
- [ ] Processamento de vários clipes.
- [ ] Fechar/reabrir e confirmar retomada por checkpoint.
- [ ] Abrir pastas de saída e logs.
- [ ] Conferir áudio, duração e reprodução dos arquivos finais.
- [ ] Testar legendas animadas se fizerem parte desta release.
- [x] Rolagem e acesso às configurações confirmado pelo usuário.
- [x] Reabertura após reinicialização do computador confirmada.

## 10. Critério para empacotamento definitivo

Empacotar a release final somente quando os testes reais acima não revelarem
falhas bloqueantes. Antes de fechar:

1. Registrar todos os resultados do checklist.
2. Corrigir apenas falhas necessárias, sem inserir funcionalidades Beta.
3. Rodar novamente os 84 testes e o smoke funcional.
4. Regerar o pacote com `gerar_release.ps1`.
5. Executar `validar_build.ps1`.
6. Conferir o hash do pacote final.
7. Atualizar a tag `classic-v2.3.2` para o commit final validado.
8. Criar arquivo ZIP/instalador de distribuição mantendo `_internal`.
9. Testar em uma máquina Windows limpa quando possível.
10. Preservar uma cópia imutável da release e seu hash.

## 11. Estratégia Classic e Beta

### Classic

- Estável, conservadora e destinada à produção diária.
- Recebe apenas correções de falhas, compatibilidade e calibração essencial.
- Não deve sofrer grandes mudanças de arquitetura durante a produção.
- É a referência funcional para comparar a Beta.

### Beta futura

- Desenvolvida em branch/worktree/pasta separada.
- Pode receber interface e fluxo mais completos.
- Só substitui a Classic após superar a mesma matriz de testes reais.
- Deve permitir revisar clipes e ajustar um enquadramento/crop específico sem
  reprocessar todo o projeto.
- Deve incorporar um painel de progresso completo.
- Deve manter checkpoint durável, histórico e retomada transparente.

## 12. Backlog futuro priorizado

### Prioridade A — depois dos testes atuais

1. Painel de progresso e estados por etapa.
2. Tela de resultados com preview de todos os clipes.
3. Edição de um clipe/crop específico e reprocessamento isolado.
4. Painel de trabalhos interrompidos com botão Continuar.
5. Cancelamento seguro/cooperativo entre clipes.
6. Validação FFprobe completa de cada saída.
7. Diagnóstico exportável sem conteúdo privado dos vídeos.

### Prioridade B — qualidade e controle

1. Preview de baixa resolução antes da exportação final.
2. Marcadores de entrada/saída e edição de título, início e fim.
3. Testes visuais de regressão para 1, 2, 3 e 4 pessoas, grupos e B-roll.
4. Rastreamento de identidade ainda mais persistente entre câmeras.
5. Zonas de segurança para cabeça, mãos, microfone e legendas.
6. Calibrações adicionais somente quando um caso real provar a necessidade.

### Prioridade C — desempenho

1. Renderizar crops fixos por cena diretamente com filtros FFmpeg.
2. Eliminar encode intermediário quando tecnicamente seguro.
3. MediaPipe em modo VIDEO com tracking.
4. Paralelizar clipes somente após medir VRAM/NVENC e preservar estabilidade.

### Prioridade D — produto distribuível

1. Janela nativa via `pywebview` quando a Beta estiver madura.
2. Instalador Inno Setup.
3. Assinatura digital do executável e instalador.
4. Atualização automática assinada.
5. Testes em máquina Windows limpa.

## 13. Ideias futuras que não pertencem à Classic agora

As ideias abaixo são válidas para o Viralume Studio/Beta, mas não devem ser
implementadas na Classic durante esta estabilização:

- integração com Gemini/Google Flow/Veo para geração de imagens e vídeos;
- banco de imagens acumulado ao longo do tempo;
- Remotion como motor avançado de composição/motion;
- timeline multif faixa, biblioteca, inspector e editor completo;
- ponte local entre uma nova interface e o motor Python/FFmpeg;
- modo agente/MCP para operar o pipeline por linguagem natural;
- exportação para Premiere/Filmora via XML/EDL quando viável.

Não automatizar o site do Google Flow por meios frágeis ou contrários aos seus
termos. Preferir integrações oficiais quando existirem e analisar custos antes.

## 14. Arquivos e locais importantes

- Código/branch Classic: `E:\PROJETOS\viral-cutter-classic-build`
- Interface principal: `interface.py`
- Pipeline: `pipeline.py`
- Enquadramento: `enquadramento.py`
- Detecção de rostos: `rostos.py`
- Runtime/checkpoint/logs: `runtime.py` e funções do pipeline
- Spec PyInstaller: `viral_cutter.spec`
- Metadados: `version_info.txt`
- Script de release: `gerar_release.ps1`
- Validador: `validar_build.ps1`
- Testes: `tests\`
- Roadmap: `ROADMAP_PRODUTO.md`
- Matriz: `MATRIZ_VALIDACAO.md`
- Relatório da interface: `CLASSIC_UI_16X9_REPORT.md`
- Logs do usuário: `%LOCALAPPDATA%\ViralCutter\logs`
- Saída padrão: `C:\Users\theob\Desktop\viral-clipes`
- ZIP do frontend anteriormente preparado:
  `E:\PROJETOS\viral-cutter-frontend-2026-08-11.zip`

## 15. Como retomar em uma nova conversa

Mensagem recomendada:

> Continue o Viral Cutter Classic usando
> `E:\PROJETOS\viral-cutter-classic-build\CHECKPOINT_COMPLETO_CLASSIC_2026-08-11.md`
> como fonte de verdade. A Classic 2.3.2 está em produção e em testes reais.
> Não misture com Viralume Studio/Beta. Primeiro leia o checkpoint, confira
> `git status`, confirme o executável ativo e preserve o baseline de qualidade
> de enquadramento avaliado em 90%, próximo de 10/10. Não implemente melhorias
> durante a produção sem aprovação explícita.

## 16. Regra final de segurança

Enquanto o usuário estiver produzindo/testando:

- não fechar ou reiniciar o programa sem solicitação;
- não reconstruir o executável sem necessidade aprovada;
- não misturar alterações da Beta na Classic;
- registrar observações antes de agir;
- preservar vídeos, saídas, checkpoints e logs;
- preferir mudanças mínimas, testadas e reversíveis.

