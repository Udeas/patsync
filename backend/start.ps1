# Start Patsync API using this project's venv (avoids wrong global/flotrack uvicorn).
Set-Location $PSScriptRoot
if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    uv sync
}
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
