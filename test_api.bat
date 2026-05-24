@echo off
setlocal
set BASE=http://localhost:8000
set KEY=31509e36-ef84-4116-b127-ceb1863a2e11
set LOG=test_api.log

echo. > %LOG%
echo ====================================================== >> %LOG%
echo  API TEST RUN: %date% %time% >> %LOG%
echo ====================================================== >> %LOG%

call :test GET  /health              ""                      200
call :test GET  /config              ""                      200
call :test GET  /tickers             ""                      200
call :test GET  /providers           ""                      200
call :test GET  /logs                "?limit=5"             200
call :test GET  /consensus           "?limit=5"             200
call :test GET  /price-data          "?limit=5"             200
call :test GET  /indicators          "?limit=5"             200
call :test GET  /prompts             "?limit=5"             200
call :test GET  /orders              "?limit=5"             200
call :test GET  /trades              "?limit=5"             200
call :test GET  /forecast-runs       "?limit=5"             200
call :test GET  /ib-config           ""                      200
call :test GET  /model-catalog       ""                      200
call :test GET  /accounts            ""                      200
call :test GET  /portfolio           ""                      200
call :test GET  /system-log          "?lines=5"             200
call :test GET  /run/status          ""                      200

echo. >> %LOG%
echo --- CONFIG roundtrip PUT /config/SCHEDULER_MAX_WORKERS --- >> %LOG%
curl -s -o tmp_cfg.json -w "PUT /config/SCHEDULER_MAX_WORKERS -> %%{http_code}" ^
  -X PUT "%BASE%/config/SCHEDULER_MAX_WORKERS" ^
  -H "X-API-Key: %KEY%" ^
  -H "Content-Type: application/json" ^
  -d "{\"key\":\"SCHEDULER_MAX_WORKERS\",\"value\":\"5\"}" >> %LOG%
echo. >> %LOG%
type tmp_cfg.json >> %LOG%
echo. >> %LOG%

echo. >> %LOG%
echo --- POST /consensus/evaluate --- >> %LOG%
curl -s -o tmp_eval.json -w "POST /consensus/evaluate -> %%{http_code}" ^
  -X POST "%BASE%/consensus/evaluate" ^
  -H "X-API-Key: %KEY%" >> %LOG%
echo. >> %LOG%
type tmp_eval.json >> %LOG%
echo. >> %LOG%

echo. >> %LOG%
echo --- AUTH: 401 with wrong key --- >> %LOG%
curl -s -o nul -w "GET /config with bad key -> %%{http_code}" ^
  "%BASE%/config" ^
  -H "X-API-Key: wrong-key" >> %LOG%
echo. >> %LOG%

echo. >> %LOG%
echo --- CONFIG validation: invalid RISK_MODE value --- >> %LOG%
curl -s -o tmp_val.json -w "PUT /config/RISK_MODE invalid -> %%{http_code}" ^
  -X PUT "%BASE%/config/RISK_MODE" ^
  -H "X-API-Key: %KEY%" ^
  -H "Content-Type: application/json" ^
  -d "{\"key\":\"RISK_MODE\",\"value\":\"invalid_value\"}" >> %LOG%
echo. >> %LOG%
type tmp_val.json >> %LOG%
echo. >> %LOG%

echo. >> %LOG%
echo ====================================================== >> %LOG%
echo  DONE: %date% %time% >> %LOG%
echo ====================================================== >> %LOG%

del /q tmp_cfg.json tmp_eval.json tmp_val.json 2>nul

echo Results written to %LOG%
type %LOG%
goto :eof

:test
set METHOD=%~1
set ENDPOINT=%~2
set PARAMS=%~3
set EXPECTED=%~4
curl -s -o nul -w "%METHOD% %ENDPOINT% -> %%{http_code}" ^
  "%BASE%%ENDPOINT%%PARAMS%" ^
  -H "X-API-Key: %KEY%" >> %LOG%
echo. >> %LOG%
goto :eof
