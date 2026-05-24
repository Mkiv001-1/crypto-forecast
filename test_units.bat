@echo off
setlocal
set LOG=test_units.log
set PYTHON=.venv312\Scripts\python.exe

echo. > %LOG%
echo ====================================================== >> %LOG%
echo  UNIT TEST RUN: %date% %time% >> %LOG%
echo ====================================================== >> %LOG%
echo. >> %LOG%

echo --- test_core_logic.py --- >> %LOG%
%PYTHON% -m pytest scripts/tests/test_core_logic.py -v --tb=short --no-header 2>&1 >> %LOG%
echo. >> %LOG%

echo --- test_integration_api.py --- >> %LOG%
%PYTHON% -m pytest scripts/tests/test_integration_api.py -v --tb=short --no-header 2>&1 >> %LOG%
echo. >> %LOG%

echo --- test_api_config_validation.py --- >> %LOG%
%PYTHON% -m pytest scripts/tests/test_api_config_validation.py -v --tb=short --no-header 2>&1 >> %LOG%
echo. >> %LOG%

echo --- test_capital_provider_failsafe.py --- >> %LOG%
%PYTHON% -m pytest scripts/tests/test_capital_provider_failsafe.py -v --tb=short --no-header 2>&1 >> %LOG%
echo. >> %LOG%

echo --- test_position_sizer_portfolio_mode.py --- >> %LOG%
%PYTHON% -m pytest scripts/tests/test_position_sizer_portfolio_mode.py -v --tb=short --no-header 2>&1 >> %LOG%
echo. >> %LOG%

echo --- test_mock_consensus_orders_gui.py --- >> %LOG%
%PYTHON% -m pytest scripts/tests/test_mock_consensus_orders_gui.py -v --tb=short --no-header 2>&1 >> %LOG%
echo. >> %LOG%

echo ====================================================== >> %LOG%
echo  DONE: %date% %time% >> %LOG%
echo ====================================================== >> %LOG%

echo Results written to %LOG%
