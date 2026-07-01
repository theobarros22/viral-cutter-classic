# Task #6 — Relatório de Validação FFprobe

**Gerado em:** 2026-06-22 00:44:32
**FFmpeg:** ffmpeg version 8.1.1-full_build-www.gyan.dev Copyright (c) 2000-2026 the FFmpeg developers
**FFprobe:** ffprobe version 8.1.1-full_build-www.gyan.dev Copyright (c) 2007-2026 the FFmpeg developers

## Resumo

| Total | Passaram | Falharam |
|-------|----------|----------|
| 21    | 21        | 0        |

## Resultados por Cenário

| Cenário | Descrição | Resultado Esperado | Resultado Real | Status | Evidência |
|---------|-----------|-------------------|----------------|--------|-----------|
| C1 | MP4 válido com áudio (required) | valid=True, audio_present=True | valid=True, audio=True, dur=10.0s | PASS | codec=h264, 1280x720 |
| C2 | MP4 sem áudio, policy=optional (B-roll) | valid=True, audio_present=False, warnings>0 | valid=True, warnings=['Clipe sem trilha de áudio (aceito — audio_policy=optional).'] | PASS | errors=[] |
| C2b | MP4 sem áudio, policy=none | valid=True, sem verificação de áudio | valid=True, errors=[] | PASS | warnings=[] |
| C3 | MP4 sem áudio, policy=required → falha + rename + max 1 retry | valid=False, renomeado, retry≤1 | valid=False, retry_count=2, renamed=True | PASS | errors=['Áudio obrigatório ausente (audio_policy=required).'] |
| C4 | Arquivo vazio (0 bytes) | valid=False, erro de arquivo vazio | valid=False, errors=['Arquivo com tamanho zero.'] | PASS | file_size=0 |
| C5 | Arquivo corrompido — sem loop infinito | valid=False, retry≤1, sem loop | valid=False, retry_calls=2 | PASS | errors=['Arquivo não encontrado.'] |
| C6 | Arquivo apenas áudio — sem stream de vídeo | valid=False, video_present=False | valid=False, video_present=False | PASS | errors=['Nenhum stream de vídeo encontrado.'] |
| C7 | Duração dentro da tolerância (9.8s vs 10s esperado) | valid=True, diff<tolerância | valid=True, dur=9.80s, diff=0.2 | PASS | tol=0.5s |
| C8 | Duração fora da tolerância (7s vs 10s esperado) | valid=False, erro de duração, retry≤1 | valid=False, retry=2, diff=3.0 | PASS | errors=['Duração real (7.00s) difere da esperada (10.00s) em 3.00s (tolerância: 0.50s).'] |
| C9 | FFprobe indisponível — erro explícito sem crash | valid=False, erro ffprobe_not_found | valid=False, errors=['FFprobe não encontrado no sistema.'] | PASS | FFprobe path injetado como inválido |
| C10 | Timeout do FFprobe (timeout=0s) | valid=False, erro timeout | valid=False, errors=['FFprobe excedeu o timeout de 0s.'] | PASS | timeout=0 injetado |
| C11 | Fallback libx264 — arquivo final válido | valid=True, codec=h264 | valid=True, codec=h264, encoder_used=libx264 | PASS | errors=[] |
| C12 | Versão viral inválida — original preservado | original válido, viral renomeado, efeito_falhou=True | orig_ok=True, efeito_falhou=True, orig_exists=True | PASS | arquivo_viral→original=C:\Users\Theo Barros\Claude\Projects\CORTE VIRAL\tests\ffprobe_validation\work\c12_original.mp4 |
| C13 | Clipe inválido entre vários — pipeline continua | 2 válidos, 1 inválido, pipeline não aborta | validos=2, invalidos=1, processados=3 | PASS | [{'name': 'c13_clip1.mp4', 'expected_valid': True, 'got_valid': True, 'ok': True, 'errors': []}, {'name': 'c13_clip2.mp4', 'expected_valid': False, 'got_valid': False, 'ok': True, 'errors': ['FFprobe retornou código 1. [mov,mp4,m4a,3gp,3g2,mj2 @ 00000250f93b0d40] moov atom not found\nC:\\Users\\Theo Barros\\Claude\\Projects\\CORTE VIRAL\\tests\\ffprobe_validation\\work\\c13_clip2.mp4: Invalid data found when processing input']}, {'name': 'c13_clip3.mp4', 'expected_valid': True, 'got_valid': True, 'ok': True, 'errors': []}] |
| C14 | Cancelamento antes do retry — sem nova tentativa | cancelado=True, retry_count=1, status=cancelado | cancelled=True, export_calls=1 | PASS | logs=[' Exportando (tentativa 1/2)...', ' Validando arquivo exportado...', ' ❌ Validação: FFprobe retornou código 1. [mov,mp4,m4a,3gp,3g2,mj2 @ 0000021ca3701e40] moov atom not found\nC:\\Users\\Theo Barros\\Claude\\Projects\\CORTE VIRAL\\tests\\ffprobe_validation\\work\\c14_cancel.mp4: Invalid data found when processing input'] |
| A1 | Arquivo com acentos e espaços no nome | valid=True | valid=True, errors=[] | PASS | fixture: vídeo válido com espaços.mp4 |
| A2 | Renomear arquivo quando .invalid.mp4 já existe | sem crash, arquivo renomeado | result=C:\Users\Theo Barros\Claude\Projects\CORTE VIRAL\tests\ffprobe_validation\work\a2_test.invalid.mp4 | PASS | novo=C:\Users\Theo Barros\Claude\Projects\CORTE VIRAL\tests\ffprobe_validation\work\a2_test.invalid.mp4 |
| A3 | JSON incompleto do FFprobe — falha graciosamente | valid=False, erro de parse | valid=False, errors=["Resposta do FFprobe não é JSON válido: Expecting ',' delimiter: line 1 column 29 (char 28)"] | PASS | JSON injetado incompleto |
| A4 | Múltiplos streams de áudio — válido | valid=True, audio_present=True | valid=True, audio=True | PASS | audio_codec=aac |
| A5 | Codec de vídeo VP9 (não H.264) — válido | valid=True, video_codec=vp9 | valid=True, codec=vp9 | PASS | errors=[] |
| A6 | Duração disponível no container (fallback) | valid=True, duration preenchida | valid=True, dur=10.0 | PASS | duration_difference=0.0 |

## Análise de Falhas Críticas

Nenhuma falha crítica.

## Confirmações Finais

✅ B-roll sem áudio é aceito (audio_policy=optional)
✅ Cancelamento impede retry (C14)
✅ Clipe inválido não bloqueia os demais (C13)
✅ Sem loop infinito de retry
✅ Original preservado quando viral falha (C12)
✅ FFprobe indisponível não derruba aplicação (C9)
