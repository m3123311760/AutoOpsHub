# AutoOpsHub

AutoOpsHub project repository.

## Project layout

- `main.py`, `autoopshub/`, `tests/`: backend application and tests.
- `frontend/`: Next.js frontend application, including its package files and UI source.

## Backend

Install dependencies and start local services from the repository root:

```powershell
pip install -r requirements.txt
docker compose -f docker-compose.yml up -d
```

Start the FastAPI application with Uvicorn:

```powershell
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

If authentication or MySQL-backed features are enabled, use the local Docker credentials:

```powershell
$env:AUTOOPSHUB_MYSQL_PASSWORD = "autoopshub"
```

The application defaults already match this local Docker password and include a local development JWT secret. Override `AUTOOPSHUB_MYSQL_PASSWORD` and `AUTOOPSHUB_JWT_SECRET` for non-local deployments.

When `databases-init.sql` is applied, it seeds a default local admin account for first login:

- Username: `admin`
- Password: `ChangeMe123!`

Replace this initial password hash in `auth_users` immediately after deployment.

## Frontend

Run frontend commands from the `frontend/` directory:

```powershell
cd frontend
npm run dev
```
