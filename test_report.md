# VIRALUME v2.3 — Relatório de Testes FFprobe

Data: 2026-06-22T00:20:56

FFmpeg: `C:\Users\Theo Barros\AppData\Local\Microsoft\WinGet\Links\ffmpeg.EXE`  |  FFprobe: `C:\Users\Theo Barros\AppData\Local\Microsoft\WinGet\Links\ffprobe.EXE`

## Tabela de Resultados

| Cenário | Descrição | Resultado Esperado | Status | Evidência |
| ------- | --------- | ------------------ | ------ | --------- |
| 01 | MP4 válido com áudio (audio_policy=required) | valid=True, áudio presente | ✅ PASS | ok |
| 02 | MP4 sem áudio (audio_policy=optional) → warni | valid=True, warning sem áudio | ✅ PASS | ok |
| 03 | MP4 sem áudio (audio_policy=required) → invál | valid=False, renomeado .invalid | ✅ PASS | ok |
| 04 | Arquivo vazio → inválido, sem crash | valid=False, arquivo vazio | ✅ PASS | ok |
| 05 | Arquivo corrompido → inválido, erro capturado | valid=False, erro capturado | ✅ PASS | ok |
| 06 | Sem stream de vídeo → inválido, video_present | valid=False, sem vídeo | ✅ PASS | ok |
| 07 | Duração dentro da tolerância → válido | valid=True, diff < tolerância | ✅ PASS | ok |
| 08 | Duração fora da tolerância → inválido | valid=False, diff > tolerância | ✅ PASS | ok |
| 09 | FFprobe indisponível → inválido, erro explíci | valid=False, ffprobe ausente | ✅ PASS | ok |
| 10 | Timeout do FFprobe → retorno estruturado, sem | retorno estruturado, sem crash | ✅ PASS | ok |
| 11 | libx264 fallback → arquivo válido detectado | libx264 → valid=True | ✅ PASS | ok |
| 12 | Viral inválido → original preservado, efeito_ | original preservado, efeito_falhou | ✅ PASS | ok |
| 13 | Um clipe inválido entre três → pipeline não a | 2 válidos, 1 inválido, sem abort | ✅ PASS | ok |
| 14 | Cancelamento antes do retry → retry não execu | cancelamento impede retry | ✅ PASS | ok |
| X1 | audio_policy=none com arquivo mudo → válido | audio_policy=none → válido | ✅ PASS | ok |
| X2 | Nome com espaços e acentos → válido | espaços/acentos → válido | ✅ PASS | ok |
| X3 | _renomear_invalido com colisão → sem crash | colisão rename → sem crash | ✅ PASS | ok |

## Sumário

- **Total de testes:** 17
- **Passaram:** 17
- **Falharam:** 0
- **Falhas críticas:** 0
- **Falhas não críticas:** 0

## Confirmações Obrigatórias

- B-roll sem áudio aceito (audio_policy=optional): ✅
- Cancelamento impede retry: ✅
- Um clipe inválido não bloqueia os demais: ✅
- Original preservado quando viral falha: ✅
- Sem loop infinito (MAX_EXPORT_RETRIES=1, sem while): ✅

## Arquivos Modificados Durante Testes

- `pipeline.py` — nenhuma modificação (leitura apenas via import)
- Fixtures geradas em `tests/ffprobe_validation/fixtures/`
- Arquivos `.invalid.mp4` gerados pelos próprios cenários de teste