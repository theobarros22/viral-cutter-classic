# Viral Cutter Classic

Transforma um podcast longo em clipes verticais 9:16 prontos para Reels,
Shorts e TikTok: transcreve, escolhe os melhores trechos, corta e reenquadra
seguindo quem está falando.

Abre em **janela própria** — não é uma aba de navegador.

---

## Qual pacote você recebeu

| Pacote | Para quem | O que fazer |
|---|---|---|
| `ViralCutter-Portatil-*.zip` | só quero **usar** o programa | descompactar e abrir o `.exe` |
| `ViralCutter-Codigo-*.zip` | quero **mexer no código** e ajudar a melhorar | seguir "Instalação para desenvolvimento" |

---

## Requisitos

- **Windows 10 ou 11** (64 bits).
- **8 GB de RAM** no mínimo; 16 GB é confortável.
- **Espaço em disco:** 15 GB livres. Vídeo é pesado, e os arquivos temporários
  do processamento ficam na pasta de saída.
- **Placa NVIDIA é opcional, mas muda tudo.** Com GPU NVIDIA o programa usa
  NVENC para exportar e CUDA para transcrever. Sem ela, funciona igual pela CPU,
  só que várias vezes mais lento.
- **Chave da Anthropic é opcional.** Sem ela o programa entra em modo offline:
  continua cortando e enquadrando, mas escolhe os trechos por heurística em vez
  de IA. Para ligar a IA, crie a variável de ambiente `ANTHROPIC_API_KEY`.

---

## Usar o pacote portátil

1. Descompacte o ZIP inteiro numa pasta — por exemplo `C:\ViralCutter`.
   **Não** rode o `.exe` de dentro do ZIP.
2. Abra `ViralCutter.exe`.
3. **A primeira abertura demora cerca de 1 minuto** e não mostra nada nesse
   tempo. É normal: o programa está carregando as bibliotecas de vídeo e IA.
   Não clique de novo, senão você abre duas instâncias.

### O Windows pode bloquear na primeira vez

O executável não tem assinatura digital paga, então o Windows pode barrá-lo:

- **SmartScreen:** aparece uma tela azul. Clique em **"Mais informações"** e
  depois em **"Executar assim mesmo"**.
- **Controle Inteligente de Aplicativos (Smart App Control):** se estiver
  ligado, ele pode recusar sem oferecer opção. Para verificar: Segurança do
  Windows → Controle de aplicativo e navegador → Configurações do Controle
  Inteligente de Aplicativos. Desligar resolve, **mas é permanente** — só
  reinstalando o Windows dá para religar. Se não quiser mexer nisso, use o
  pacote de código, que roda pelo Python e não sofre esse bloqueio.

---

## Como usar o programa

O fluxo tem quatro etapas, na ordem das abas:

1. **Detectar pessoas** — escolha o vídeo. O programa acha quem aparece e você
   marca quem deve ser priorizado no enquadramento.
2. **Transcrever e analisar** — gera a transcrição e propõe os trechos com mais
   chance de viralizar. É a etapa mais demorada da parte de IA.
3. **Processar** — corta e reenquadra em 9:16. É aqui que o tempo é gasto.
4. **Efeitos** — legendas e ajustes finais (opcional).

Os clipes saem em `Área de Trabalho\viral-clipes\<nome do vídeo>\`.

### Se o processamento for interrompido

Pode fechar o programa, faltar energia, dar erro no meio: **nada se perde.**
Ao reabrir e apontar o mesmo vídeo, ele mostra quantos clipes já estão prontos
e continua do primeiro pendente. Não refaz o que já ficou bom.

### Como o programa decide o enquadramento

O quadro **acompanha a pessoa** enquanto ela se mexe, como um operador de
câmera. A ordem de preferência é:

1. crop fechado com a pessoa centralizada — o normal;
2. dois painéis horizontais empilhados, quando as pessoas não cabem juntas;
3. quadro aberto, na dúvida.

Nunca entrega a pessoa principal cortada. Se um trecho aparecer em painéis
ou em plano aberto, foi escolha deliberada do programa, não falha.

---

## Quando algo der errado

O programa grava tudo em dois lugares:

- **Log do aplicativo:** `%LOCALAPPDATA%\ViralCutter\logs\` — erros de abertura.
- **Log do processamento:** dentro da pasta de saída dos clipes, um arquivo
  `viral_cutter_*.log` — o que aconteceu com cada clipe, com tempos por etapa.

Para relatar um problema, rode isto na pasta do programa e mande o arquivo:

```bash
python coletar_ambiente.py relatorio.txt
```

Ele junta hardware, versões, se o NVENC está disponível e os tempos já medidos.
Não coleta nada pessoal.

---

## Instalação para desenvolvimento

Serve para mexer no código e para rodar sem esbarrar no bloqueio do Windows.

1. Copie a pasta do código para o computador (ex.: `C:\ViralCutter-dev`).
2. Dê **duplo clique em `PREPARAR_AMBIENTE.bat`**. Ele faz tudo sozinho:
   instala o Python 3.11 se faltar, cria o ambiente virtual, instala as
   dependências, detecta placa NVIDIA e instala a versão CUDA do PyTorch,
   instala o FFmpeg e por fim roda o diagnóstico e os testes.
   Pode levar de 15 a 40 minutos, quase tudo download.
3. Terminando com "Ambiente preparado e validado", abra com
   **`iniciar.bat`**.

Se quiser gerar o executável: `gerar_exe.bat`. Ele só empacota se os testes
passarem.

Mais detalhes de arquitetura, o que testar e como contribuir estão em
[PARA-DESENVOLVEDORES.md](PARA-DESENVOLVEDORES.md).

---

## Dois pacotes opcionais que valem a pena

Não são obrigatórios — o programa funciona sem eles e cai para alternativas
internas — mas melhoram bastante:

```bash
venv311\Scripts\python.exe -m pip install faster-whisper scenedetect
```

- `faster-whisper`: transcrição bem mais rápida.
- `scenedetect`: detecção de cortes de cena mais precisa, o que melhora
  diretamente a qualidade do enquadramento.
