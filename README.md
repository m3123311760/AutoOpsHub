# AutoOpsHub

AutoOpsHub project repository.

## Project layout

- `main.py`, `autoopshub/`, `tests/`: backend application and tests.
- `frontend/`: Next.js frontend application, including its package files and UI source.

## Backend

Install dependencies and start local services from the repository root:

```powershell
pip install -r requirements.txt
docker compose -f compose-dev.yml up -d
```

Use `.env.example` as the reference list for supported environment variables. The application reads variables from the process environment.

Start the FastAPI application with Uvicorn:

```powershell
$env:AUTOOPSHUB_JWT_SECRET = "replace-with-a-long-random-secret"
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

If authentication or MySQL-backed features are enabled, use the local Docker credentials:

```powershell
$env:AUTOOPSHUB_MYSQL_PASSWORD = "autoopshub"
```

The application default matches this local Docker MySQL password. `AUTOOPSHUB_JWT_SECRET` has no default when authentication is enabled, so deployments fail closed unless an explicit signing secret is provided.

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

## Containers

The production-oriented Compose entrypoint is split into modules under `compose/`.
It currently packages the Next.js frontend and infrastructure services; the backend
still runs on the host so local automation runtimes such as Terraform, Ansible, and
SSH can use the host environment.

```powershell
docker compose -f compose.yml up -d --build
```

All production Compose settings use environment-variable interpolation with defaults.
Override values from your shell or an uncommitted `.env` file when needed.
