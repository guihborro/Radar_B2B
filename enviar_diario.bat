@echo off
REM ============================================================================
REM  FinIntegra - envio diario automatico (para o Agendador de Tarefas)
REM  - Roda SOMENTE em dias uteis (pula sabado e domingo).
REM  - Envia ate o limite diario (operacao.limite_diario no config.yaml).
REM  - Registra tudo em data\enviados.csv e loga em data\log_envios.txt.
REM
REM  COMO AGENDAR (uma vez):
REM   1) Abra o "Agendador de Tarefas" do Windows.
REM   2) Criar Tarefa Basica -> Diariamente -> escolha o horario (ex.: 09:00).
REM   3) Acao: "Iniciar um programa" -> aponte para este .bat.
REM   (o proprio .bat ja pula fim de semana, entao pode deixar "Diariamente")
REM ============================================================================

cd /d "%~dp0"

REM --- pula fim de semana (0=domingo, 6=sabado) ---
for /f %%d in ('powershell -NoProfile -Command "(Get-Date).DayOfWeek.value__"') do set DOW=%%d
if "%DOW%"=="0" ( echo [%date% %time%] domingo - nao envia >> data\log_envios.txt & exit /b 0 )
if "%DOW%"=="6" ( echo [%date% %time%] sabado - nao envia  >> data\log_envios.txt & exit /b 0 )

REM --- localiza o Python ---
set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not exist "%PY%" (
  echo [%date% %time%] ERRO: Python nao encontrado em %PY% >> data\log_envios.txt
  exit /b 1
)

REM --- 1) checa a INBOX: marca quem respondeu (para a cadencia) e bounces ---
echo [%date% %time%] ---- checando respostas ---- >> data\log_envios.txt
"%PY%" -m finintegra.cli checar-respostas >> data\log_envios.txt 2>&1

REM --- 2) envia (follow-ups primeiro, depois leads novos; respeita limite) ---
echo [%date% %time%] ---- inicio do envio ---- >> data\log_envios.txt
"%PY%" -m finintegra.cli rodar >> data\log_envios.txt 2>&1
echo [%date% %time%] ---- fim ---- >> data\log_envios.txt

exit /b %ERRORLEVEL%
