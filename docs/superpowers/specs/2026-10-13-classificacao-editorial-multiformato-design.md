# Especificação: análise editorial multiformato

**Status:** proposta aprovada para documentação; aguardando revisão desta especificação antes da implementação.  
**Data:** 2026-10-13  
**Projeto:** Viral Cutter Classic

## Objetivo

Ampliar a seleção de trechos para funcionar com diferentes tipos de vídeo — incluindo telejornal e reportagem — sem pressupor que todo material seja podcast. A escolha editorial deve considerar o formato do conteúdo, mantendo o modo offline sem API e preservando integralmente o enquadramento atual.

## Problema observado

A interface oferece nichos editoriais, mas o padrão é Podcast. A segmentação com IA usa critérios associados ao nicho escolhido; no modo offline, a segmentação é principalmente genérica e depois recebe ajustes de pontuação por nicho. Não há hoje uma identificação explícita do formato do conteúdo nem um perfil editorial próprio para telejornal/reportagem. Assim, um vídeo jornalístico pode receber critérios inadequados se ficar no padrão Podcast.

## Experiência proposta

1. Renomear o campo da interface para **Formato do conteúdo** e acrescentar **Auto (IA)** e **Telejornal/Reportagem**, sem remover as opções atuais.
2. Manter a seleção manual como autoridade: quando o usuário escolhe um formato específico, a análise não o substitui por uma classificação automática.
3. Com **Auto (IA)** e análise por IA habilitada, classificar o formato e a densidade do conteúdo dentro da mesma solicitação já usada para selecionar os trechos. Não fazer uma chamada extra apenas para classificar.
4. Mostrar nos logs da análise o formato detectado e, se disponível, a densidade. Se a resposta vier ausente, inválida ou desconhecida, continuar com **Geral** e registrar esse fallback.
5. No modo offline, não tentar classificação automática nem fazer chamadas externas. Se **Auto (IA)** estiver selecionado, usar **Geral** e informar isso claramente no log; os formatos escolhidos manualmente continuam disponíveis sem custo de API.

## Critérios editoriais para telejornal/reportagem

O perfil deve favorecer trechos que sejam compreensíveis fora do contexto imediato e contenham uma declaração factual relevante, explicação, consequência, dado ou contexto jornalístico. Deve evitar:

- cortar a fala antes da conclusão necessária para entender a informação;
- transformar hipótese, opinião ou alegação em fato confirmado;
- premiar sensacionalismo sem relevância informativa;
- selecionar somente uma frase de transição sem conteúdo suficiente.

O perfil modifica a seleção e a pontuação dos trechos, não a transcrição nem o significado declarado pelo entrevistado. A classificação se baseia no conteúdo textual disponível; não promete reconhecer tarjas, gráficos, imagens de apoio ou a estrutura visual do programa.

## Limites de escopo

- **Incluído:** classificação editorial automática junto da segmentação por IA; opção manual Telejornal/Reportagem; fallback previsível para Geral; critérios jornalísticos na seleção; logs que informam o formato efetivamente usado; compatibilidade com uso offline.
- **Não incluído:** mudança no motor de enquadramento, detecção de rosto/falante, zoom, crop, split, layout 9:16 ou renderização FFmpeg; alteração dos limites de duração dos clipes; novas chamadas ou serviços externos; cópia do código do repositório de referência.
- As regras geométricas e os modos de enquadramento atuais devem permanecer intocados. Esta tarefa é exclusivamente editorial.

## Contrato técnico proposto

- Preservar o retorno público atual de `segmentar_por_assunto` como lista de segmentos, para não quebrar o pipeline e os consumidores existentes.
- Na resposta estruturada da solicitação de segmentação por IA, incluir `content_type`, `content_density` e `segments`. Validar os dois metadados; normalizar aliases conhecidos e mapear qualquer formato não suportado para `geral`.
- Acrescentar um canal opcional de metadados/classificação entre análise e interface (por exemplo, callback opcional), sem exigir que chamadores existentes o forneçam. Ele permite registrar o formato sem misturar metadados de vídeo em cada segmento.
- Para formatos manuais, usar a escolha manual nos critérios e no ajuste de pontuação. Para `Auto (IA)`, usar o tipo devolvido pela mesma resposta que contém os segmentos.
- Caso a IA falhe por resposta inválida ou erro já coberto pelo fallback existente, preservar o fluxo de fallback atual e usar Geral quando não houver escolha manual explícita.
- Atualizar a configuração editorial e o prompt de IA em `analise.py`; atualizar rótulos/opções e apresentação da classificação em `interface.py`; propagar apenas o metadado necessário pelo ponto de integração em `pipeline.py`.

## Áreas previstas de alteração

- `interface.py`: opções e rótulo do campo, tratamento de Auto versus escolha manual, mensagem/log do formato efetivamente aplicado.
- `pipeline.py`: propagação opcional dos metadados da análise mantendo a assinatura compatível com os chamadores atuais.
- `analise.py`: validação/normalização do tipo e densidade, critérios do formato jornalístico e seleção dos critérios correspondentes.
- `tests/`: testes unitários novos para classificação, fallback, override manual e modo offline.

Os nomes e assinaturas definitivos serão confirmados no código durante a implementação TDD; este documento define o contrato comportamental, não exige uma estrutura interna específica além das garantias descritas.

## Critérios de aceitação

1. A opção Telejornal/Reportagem existe e funciona manualmente com IA e no modo offline.
2. Em Auto (IA), o formato é inferido na mesma chamada de segmentação; os logs mostram o resultado normalizado.
3. A seleção manual sempre prevalece sobre uma classificação sugerida.
4. Resposta inválida, tipo desconhecido ou ausência de metadados não interrompe a análise: usa Geral e informa o fallback.
5. Auto (IA) em modo offline não faz chamada externa, usa Geral e deixa isso explícito; formato manual continua funcionando offline.
6. O modo Podcast e os demais formatos atuais preservam comportamento compatível, ressalvadas correções necessárias para suportar o novo contrato.
7. Testes cobrem parsing/normalização, densidade opcional, fallback, precedência manual, ausência de chamadas no modo offline e formato jornalístico.
8. A suíte de enquadramento não apresenta regressão; nenhuma fórmula ou regra geométrica é alterada.
9. A validação automatizada não será apresentada como prova de desempenho editorial real: antes de declarar a melhoria validada para uso jornalístico, testar com transcrições representativas e conferir manualmente relevância, contexto e integridade das falas.

## Estratégia de testes

- Testes unitários com respostas válidas, alias, tipo desconhecido, JSON malformado e metadado de densidade ausente.
- Teste de precedência manual usando resposta automática propositalmente diferente.
- Teste offline com mock/spy garantindo zero chamadas de IA e verificando fallback Auto → Geral.
- Testes para confirmar que a saída de segmentos permanece compatível com consumidores antigos.
- Testes de regressão existentes para segmentação, pipeline e enquadramento.
- Revisão manual de uma amostra de telejornal/reportagem antes de promover o perfil como confiável; se não houver fixture local autorizada, registrar essa validação como pendente, sem enviar mídia pessoal a serviços externos.

## Riscos e mitigação

- **Transcrição ambígua:** classificação errada pode orientar a seleção de forma inadequada. Mitigação: override manual, fallback para Geral e exibição do formato detectado.
- **Metadados inválidos do modelo:** schema ou categoria inesperada. Mitigação: validação estrita, normalização por allowlist e fallback sem interromper a análise.
- **Mudança incompatível no retorno:** consumidores esperam uma lista. Mitigação: preservar o retorno e transportar classificação por canal opcional separado.
- **Expectativa de análise visual:** o classificador opera sobre transcrição. Mitigação: explicitar essa limitação; não alegar leitura de elementos visuais.
- **Regressão de enquadramento:** não modificar os módulos de geometria/renderização e executar testes relacionados como guarda de regressão.

## Inspiração externa

O projeto AI-Youtube-Shorts-Generator serve apenas como referência para a ideia de identificar formato e densidade antes de aplicar critérios editoriais. A implementação será adaptada ao pipeline existente; não se copiará seu detector Haar, seu algoritmo de crop nem código de terceiros.
