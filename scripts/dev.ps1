# Start the API (port 8000) in a new window and the dashboard (port 5173) in this one.
# Assumes MongoDB is running and backend\.venv exists (see README).
$root = Split-Path -Parent $PSScriptRoot
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\backend'; .\.venv\Scripts\uvicorn app.main:app --reload --reload-dir app"
Set-Location "$root\frontend"
npm run dev
