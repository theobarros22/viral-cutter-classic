# Viral Cutter Classic 2.3.2 — Release definitiva

Data: 11/08/2026

## Fonte congelada

- Branch: `release/viral-cutter-classic`
- Commit: `f3e2907`
- Tag: `classic-v2.3.2`

## Validação

- Testes automatizados: 84/84 aprovados.
- Smoke real de corte e enquadramento: aprovado.
- Retomada por checkpoint: aprovada.
- Build PyInstaller `onedir`: aprovado.
- Executável da pasta `dist`: processo vivo e HTTP 200.
- ZIP listado e extraído em pasta separada.
- Executável extraído do ZIP: HTTP 200.
- Testes reais do usuário: aprovados.

## Artefatos

### Executável dentro do pacote

`dist\ViralCutter\ViralCutter.exe`

- Tamanho: 51.706.506 bytes
- SHA-256: `657D0F62463C46DB2A94F483C6B59B696D3B72BF8A2DE20973FDDAEE4AED3D51`

### ZIP portátil definitivo

`release\Viral-Cutter-Classic-2.3.2-Windows-x64.zip`

- Tamanho: 2.808.862.262 bytes
- SHA-256: `C2A64BD442FC0114E1A06C803DD53AFD7CBD702D0A956F5E7DD613614B93A5C3`

## Uso

Extrair o ZIP inteiro e abrir `ViralCutter\ViralCutter.exe`. Não mover somente
o `.exe`: a pasta `_internal` faz parte obrigatória do programa.

## Baseline preservado

O usuário avaliou cortes, disposição e enquadramento como atendendo cerca de
90% da necessidade, próximos de 10/10. Esta release é a referência estável para
a futura versão Beta.
