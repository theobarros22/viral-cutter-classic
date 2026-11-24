# Fast Clipper — plano de produto e arquitetura multiusuário

**Status:** proposta para revisão
**Data:** 2026-11-16
**Projeto-base:** Viral Cutter Classic
**Codinome da campanha:** Fast Clipper — GTA

## 1. Decisão de produto

O novo produto será uma plataforma multiusuário para monitorar transmissões ao vivo, identificar momentos relevantes, produzir clipes verticais, permitir revisão humana e publicar rapidamente em redes sociais. O Viral Cutter Classic permanece como produto local estável e como origem do motor de transcrição, enquadramento e renderização.

“Fast Clipper — GTA” é codinome temporário da campanha de validação relacionada ao lançamento de GTA VI. Não será a razão social, o domínio nem a marca permanente. O produto deve funcionar com jogos, podcasts, telejornais, entrevistas, esportes, eventos e outras transmissões autorizadas. A interface pública deverá declarar que o produto é independente e não associado à Rockstar Games ou à Take-Two Interactive.

## 2. Proposta de valor

> Da live ao clipe revisado e pronto para publicar em poucos minutos, com processamento controlado pela própria equipe.

O produto não tentará competir apenas por “gerar cortes com IA”. Seus diferenciais serão:

- clipping durante a transmissão, não apenas depois do VOD;
- enquadramento 9:16 consciente de pessoas, facecam, gameplay e mudanças de câmera;
- revisão e correção de um clipe sem refazer o trabalho inteiro;
- retomada após reinício e persistência de cada etapa concluída;
- operação multiusuário com isolamento por organização;
- workers próprios ou dedicados, reduzindo dependência de créditos por minuto;
- análise multimodal por sinais combinados, com fallback local quando a IA estiver indisponível;
- publicação controlada: revisão por padrão e automação somente após consentimento explícito.

## 3. Usuários e permissões

### 3.1 Entidades

- **Usuário:** pessoa autenticada.
- **Organização:** equipe, agência ou criador que possui projetos, canais e contas sociais.
- **Workspace:** área operacional de uma organização.
- **Canal monitorado:** Twitch, YouTube Live ou Kick autorizado.
- **Worker:** máquina que executa transcrição, análise e renderização.

### 3.2 Papéis mínimos

- **Proprietário:** cobrança, segurança, exclusão e conexões sociais.
- **Administrador:** usuários, canais, workers e regras de publicação.
- **Editor:** revisa, recorta, reenquadra e aprova clipes.
- **Publicador:** agenda e publica em contas autorizadas.
- **Revisor:** visualiza, comenta e aprova, sem publicar.

Toda consulta e mutação deve receber `organization_id` do contexto autenticado, nunca diretamente do navegador. Arquivos, tokens, filas e logs devem permanecer isolados por organização.

## 4. Arquitetura recomendada

### 4.1 Plano de controle web

Responsável por autenticação, organizações, permissões, projetos, canais, contas sociais, fila, status, revisão e publicação. Deve expor API versionada e eventos de progresso em tempo real. O banco transacional recomendado é PostgreSQL.

### 4.2 Worker de mídia

Serviço separado do servidor web. Consome trabalhos de uma fila durável, executa FFmpeg, transcrição, análise, enquadramento e renderização, e grava resultados no armazenamento autorizado. O primeiro worker será Windows/NVIDIA, reutilizando o motor do Viral Cutter. A interface entre central e worker deve ser um contrato de trabalho versionado, não importações diretas entre aplicações.

### 4.3 Armazenamento

- metadados e permissões no PostgreSQL;
- originais, buffers, transcrições, proxies e clipes em armazenamento por organização;
- desenvolvimento com disco local; produção com armazenamento compatível com S3 ou volume privado;
- URLs temporárias e escopadas para reprodução/download;
- política de retenção configurável para buffers e originais;
- nunca guardar tokens OAuth junto de arquivos de mídia.

### 4.4 Fila e eventos

Cada trabalho será uma máquina de estados persistente:

`criado → capturando → analisando → candidato → renderizando → aguardando_revisão → aprovado → agendado → publicado`

Estados de exceção: `pausado`, `cancelado`, `falhou`, `requer_ação` e `expirado`.

Cada etapa possuirá percentual, descrição, início, última atividade, estimativa opcional, tentativas e erro sanitizado. Reexecução deve ser idempotente: um trabalho já concluído não poderá gerar publicação ou arquivo duplicado.

## 5. Pipeline de live

### 5.1 Ingestão e buffer

- aceitar inicialmente uma fonte: YouTube Live;
- adicionar Twitch e Kick após estabilização do contrato de ingestão;
- manter buffer segmentado e rolante, com manifesto e checksums;
- preservar margem anterior e posterior ao evento para não cortar contexto;
- sobreviver a desconexões temporárias com reconexão e continuidade;
- registrar autorização, origem, horário e política de retenção.

### 5.2 Sinais de interesse

O sistema não deve confundir barulho com relevância. A pontuação combinará:

- picos de volume normalizados pelo histórico do canal;
- aceleração do chat em relação à linha de base daquele canal;
- palavras, entidades, emoção e fechamento narrativo da transcrição;
- mudanças visuais, movimento e cortes de cena;
- eventos específicos do perfil selecionado;
- marcação manual por botão, atalho ou moderador.

Cada candidato manterá explicação dos sinais que motivaram sua criação. A ausência de IA externa acionará fallback determinístico por chat, áudio e marcações manuais.

### 5.3 Seleção editorial

O motor deve ser orientado por perfis, não preso a GTA ou podcast. Perfis iniciais:

- gaming;
- conversa/podcast;
- telejornal/reportagem;
- esporte/evento;
- geral.

Gaming poderá usar vocabulário e sinais configuráveis por jogo, mas regras específicas de GTA VI serão um pacote de configuração, não condicionais espalhadas pelo código.

### 5.4 Composição 9:16

Prioridades:

1. manter pessoa, facecam ou sujeito principal integralmente visível;
2. preservar a região relevante do gameplay;
3. usar composição empilhada quando um crop único destruir informação;
4. evitar fundo desfocado quando duas regiões úteis puderem ocupar a tela;
5. marcar como `requer_ação` quando não existir enquadramento seguro.

O motor atual do Viral Cutter continuará como autoridade para geometria humana. Layouts de gameplay serão adicionados como estratégias isoladas, com zonas configuráveis de facecam e conteúdo.

## 6. Revisão e edição

Antes da publicação, o editor poderá:

- ajustar início e fim;
- trocar o candidato selecionado;
- corrigir transcrição e legenda;
- escolher ou ajustar layout;
- reposicionar pessoa, facecam e gameplay;
- alterar hook, título, descrição e hashtags;
- reprocessar somente o clipe atual;
- comparar versões e restaurar uma versão anterior.

Toda alteração produzirá uma nova versão. Publicação automática será opt-in por organização, canal e destino, com limite diário e botão de emergência para suspender a fila.

## 7. Contas sociais e publicação

Destinos planejados: YouTube Shorts, TikTok e Instagram Reels. Cada integração deve usar OAuth oficial, escopos mínimos, criptografia de tokens, rotação e revogação. Nenhuma senha social será armazenada.

O publicador deverá oferecer:

- publicar agora ou agendar;
- calendário por organização;
- limite por plataforma e conta;
- tentativas idempotentes;
- estado e URL da publicação;
- fila de falhas com ação humana;
- registro de quem aprovou e publicou.

## 8. Segurança, direitos e abuso

- somente fontes próprias, autorizadas ou legalmente utilizáveis;
- confirmação de direitos antes de monitorar canal de terceiro;
- bloqueio de URLs não permitidas e proteção contra SSRF;
- limites por usuário, organização, worker, disco e duração;
- varredura e validação de arquivos recebidos;
- segredos fora do Git e logs;
- trilha de auditoria para conexões, downloads, aprovações e publicações;
- exclusão e exportação de dados por organização;
- política específica para conteúdo pré-lançamento, spoilers e material protegido;
- nenhuma marca, arte ou alegação de associação com GTA, Rockstar ou Take-Two.

## 9. Fases de entrega

### Fase 0 — fundação e prova de risco

- congelar o Classic como baseline testado;
- definir contratos de trabalho, mídia e eventos;
- criar banco multiusuário, organizações e RBAC;
- provar comunicação central ↔ worker com um arquivo local;
- medir tempo e custo de um clipe real;
- configurar telemetria, logs e auditoria.

**Saída:** um usuário envia um vídeo, acompanha o progresso e recebe um clipe produzido por worker separado, sem acesso cruzado entre organizações.

### Fase 1 — alpha Fast Clipper

- monitoramento de um canal YouTube Live;
- buffer rolante;
- transcrição incremental;
- candidatos por áudio, chat e marcação manual;
- renderização 9:16 com legenda;
- revisão obrigatória e download;
- até três organizações piloto, sem cobrança e sem autopost.

**Saída:** clipe revisável poucos minutos após um evento ao vivo, com rastreabilidade completa.

### Fase 2 — beta multiusuário

- Twitch e Kick;
- fila durável e múltiplos workers;
- editor de recorte, legenda e layout;
- versionamento e reprocessamento unitário;
- contas sociais OAuth;
- publicação manual e agendamento;
- cotas e painel operacional.

### Fase 3 — automação controlada

- perfis editoriais por jogo/formato;
- aprendizado com aprovações e rejeições;
- regras por canal;
- publicação automática opt-in;
- notificações e relatórios;
- kit de marca e templates.

### Fase 4 — operação comercial

- cobrança e planos;
- termos, privacidade e suporte;
- recuperação de desastre;
- métricas de custo e margem;
- moderação, abuso e resposta a incidentes;
- SLA compatível com a infraestrutura disponível.

## 10. Campanha GTA VI

A campanha não prometerá uma plataforma pública completa no dia 19. Seu objetivo será recrutar streamers e equipes para uma alpha fechada e coletar material autorizado.

Entregáveis imediatos:

- landing page independente de marcas oficiais;
- formulário de interesse e autorização;
- vídeo demonstrativo usando material próprio ou licenciado;
- seleção de três pilotos;
- roteiro de teste de live;
- critérios de sucesso e canal de feedback.

Métricas da alpha:

- latência evento → candidato;
- latência candidato → clipe pronto;
- taxa de candidatos aprovados;
- taxa de reenquadramentos manuais;
- erros de legenda;
- falhas por hora capturada;
- custo computacional por hora de live;
- tempo humano por clipe aprovado.

## 11. Critérios de aceitação do MVP

1. Nenhum usuário acessa projeto, arquivo, token ou log de outra organização.
2. Reiniciar central ou worker não perde buffer confirmado, transcrição, candidatos nem clipes concluídos.
3. Percentual e etapa refletem trabalho persistido, não animação simulada.
4. Um evento manual produz candidato com contexto anterior e posterior configurável.
5. O clipe final tem vídeo, áudio, duração e resolução válidos e decodifica integralmente.
6. Pessoa/facecam não fica cortada; casos inseguros exigem revisão.
7. Reprocessar um clipe não repete transcrição ou análise já válidas.
8. Publicação exige autorização e não duplica postagem após timeout/retry.
9. Tokens não aparecem em logs, banco em texto puro ou respostas da API.
10. Testes de isolamento, retomada, idempotência e carga passam antes de usuários externos.

## 12. Estratégia de testes

- unitários para estados, permissões, pontuação e contratos;
- integração com banco, fila, armazenamento e worker reais em ambiente descartável;
- testes de interrupção forçada em cada etapa e retomada posterior;
- testes de segurança para IDOR, SSRF, upload abusivo e vazamento de tokens;
- fixtures sintéticas e material autorizado para layouts de gameplay;
- testes visuais de enquadramento por amostragem e vídeos completos;
- testes ponta a ponta: live simulada → candidato → revisão → publicação sandbox;
- teste de carga com múltiplas organizações e fila saturada;
- canário fechado antes de qualquer autopost.

## 13. Riscos principais

- **Prazo do GTA VI:** três dias não permitem SaaS público seguro. Mitigação: campanha e recrutamento, não promessa de disponibilidade geral.
- **Custo de GPU:** múltiplos usuários podem eliminar margem. Mitigação: workers dedicados, cotas, medição por etapa e fila adaptativa.
- **Detecção ruim:** áudio alto sozinho gera falsos positivos. Mitigação: sinais combinados e feedback explícito.
- **Direitos autorais:** clipping de terceiros pode gerar remoções. Mitigação: autorização, auditoria e política de uso.
- **OAuth e autopost:** falhas podem publicar conteúdo errado. Mitigação: revisão padrão, idempotência e kill switch.
- **Regressão do Classic:** evolução web pode quebrar produção atual. Mitigação: repositório/módulos separados e contrato versionado com o worker.
- **Escopo excessivo:** live, editor, contas, IA e publicação são produtos distintos. Mitigação: marcos com portas de saída e critérios mensuráveis.

## 14. Fora do MVP

- aplicativo móvel nativo;
- marketplace público de clippers;
- campanhas remuneradas por visualização;
- suporte irrestrito a qualquer plataforma de live;
- geração de vídeo por IA;
- edição multipista completa;
- autopost habilitado por padrão;
- uso de material ou identidade visual oficial de GTA VI.

## 15. Decisões ainda necessárias

- marca definitiva do produto;
- infraestrutura inicial: servidor próprio, provedor gerenciado ou híbrido;
- primeiro provedor de autenticação;
- política de armazenamento e retenção;
- plataforma social priorizada para publicação;
- modelo de worker: centralizado, dedicado por cliente ou ambos;
- limites da alpha e critérios para abrir a beta.

