@echo off
REM Load Test Runner Script for Windows
REM Runs various load test scenarios and generates reports

setlocal enabledelayedexpansion

set REPORTS_DIR=load_tests\reports
if not defined COGNIZANT_HOST set COGNIZANT_HOST=http://localhost:8000

echo ==========================================
echo Cognizant Load Test Runner
echo ==========================================
echo Target: %COGNIZANT_HOST%
echo Reports: %REPORTS_DIR%
echo.

REM Create reports directory
if not exist "%REPORTS_DIR%" mkdir "%REPORTS_DIR%"

REM Test 1: Steady State Load
echo === Test 1: Steady State Load ===
echo   Users: 10 ^| Spawn rate: 2/s ^| Duration: 60s
locust -f load_tests\locustfile.py --host=%COGNIZANT_HOST% --users=10 --spawn-rate=2 --run-time=60s --headless --html=%REPORTS_DIR%\steady_state_report.html --csv=%REPORTS_DIR%\steady_state_stats --loglevel=INFO
if errorlevel 1 (
    echo ERROR: Steady state test failed
) else (
    echo OK: Completed steady state test
)
echo.

REM Test 2: Spike Test
echo === Test 2: Spike Test ===
echo   Users: 50 ^| Spawn rate: 10/s ^| Duration: 30s
locust -f load_tests\locustfile.py --host=%COGNIZANT_HOST% --users=50 --spawn-rate=10 --run-time=30s --headless --html=%REPORTS_DIR%\spike_test_report.html --csv=%REPORTS_DIR%\spike_test_stats --loglevel=INFO
if errorlevel 1 (
    echo ERROR: Spike test failed
) else (
    echo OK: Completed spike test
)
echo.

REM Test 3: Cycle Execution Load
echo === Test 3: Cycle Execution Load ===
echo   Users: 20 ^| Spawn rate: 5/s ^| Duration: 90s
locust -f load_tests\scenarios\cycle_load_test.py --host=%COGNIZANT_HOST% --users=20 --spawn-rate=5 --run-time=90s --headless --html=%REPORTS_DIR%\cycle_load_report.html --csv=%REPORTS_DIR%\cycle_load_stats --loglevel=INFO
if errorlevel 1 (
    echo ERROR: Cycle load test failed
) else (
    echo OK: Completed cycle load test
)
echo.

REM Test 4: Concurrent Incidents
echo === Test 4: Concurrent Incidents ===
echo   Users: 15 ^| Spawn rate: 3/s ^| Duration: 60s
locust -f load_tests\scenarios\concurrent_incidents_test.py --host=%COGNIZANT_HOST% --users=15 --spawn-rate=3 --run-time=60s --headless --html=%REPORTS_DIR%\concurrent_incidents_report.html --csv=%REPORTS_DIR%\concurrent_incidents_stats --loglevel=INFO
if errorlevel 1 (
    echo ERROR: Concurrent incidents test failed
) else (
    echo OK: Completed concurrent incidents test
)
echo.

REM Test 5: Endurance Test
echo === Test 5: Endurance Test ===
echo   Users: 5 ^| Spawn rate: 1/s ^| Duration: 300s
locust -f load_tests\locustfile.py --host=%COGNIZANT_HOST% --users=5 --spawn-rate=1 --run-time=300s --headless --html=%REPORTS_DIR%\endurance_report.html --csv=%REPORTS_DIR%\endurance_stats --loglevel=INFO
if errorlevel 1 (
    echo ERROR: Endurance test failed
) else (
    echo OK: Completed endurance test
)
echo.

REM Generate analysis reports
echo === Generating Analysis Reports ===

for %%t in (steady_state spike_test cycle_load concurrent_incidents endurance) do (
    if exist "%REPORTS_DIR%\%%t_stats_stats_history.csv" (
        echo Analyzing: %%t
        python load_tests\scripts\analyze_results.py "%REPORTS_DIR%\%%t_stats_stats_history.csv" "%REPORTS_DIR%\%%t_analysis.json" > "%REPORTS_DIR%\%%t_analysis.txt"
    )
)

echo.
echo === All Load Tests Complete ===
echo.
echo Reports saved to: %REPORTS_DIR%
echo.
dir "%REPORTS_DIR%\*.html" 2>nul

endlocal
