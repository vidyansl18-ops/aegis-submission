# Runbook

## Windows PowerShell

```powershell
.\run.ps1
```

## Windows CMD

```cmd
run.bat
```

## Manual

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`.

API docs: `http://127.0.0.1:8000/docs`.

## Reset

Use **Data Studio → Reset to Demo Environment**.
