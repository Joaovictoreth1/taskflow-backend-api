"""Build and exercise the deployed API on an isolated, disposable Compose stack."""

import csv
import json
import os
import secrets
import subprocess
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def main() -> None:
    name = f"taskflow-smoke-{secrets.token_hex(5)}"
    password = secrets.token_hex(32)
    env = {
        **os.environ,
        "SECRET_KEY": secrets.token_hex(32),
        "POSTGRES_PASSWORD": password,
        "COMPOSE_DATABASE_URL": f"postgresql+psycopg://taskflow:{password}@db:5432/taskflow",
        "API_PORT": "0",
    }

    def compose(*args: str, capture: bool = False) -> str:
        result = subprocess.run(
            ["docker", "compose", "-p", name, *args],
            env=env,
            text=True,
            stdout=subprocess.PIPE if capture else None,
            check=True,
        )
        return result.stdout.strip() if capture else ""

    try:
        compose("up", "--build", "--wait", "--wait-timeout", "120", "api")
        address = f"http://{compose('port', 'api', '8000', capture=True)}"

        def call(method: str, path: str, status: int, body=None, token=None):
            headers = {"Content-Type": "application/json"} if body is not None else {}
            if token:
                headers["Authorization"] = f"Bearer {token}"
            request = Request(
                address + path,
                method=method,
                headers=headers,
                data=json.dumps(body).encode() if body is not None else None,
            )
            try:
                response = urlopen(request, timeout=10)
            except HTTPError as exc:
                response = exc
            with response:
                assert response.status == status, (method, path, response.status, status)
                data = response.read().decode()
                return (
                    json.loads(data)
                    if response.headers.get_content_type() == "application/json"
                    else data
                )

        assert call("GET", "/ready", 200)["status"] == "ready"
        assert compose("exec", "-T", "api", "id", "-u", capture=True) == "10001"
        tokens = []
        for username in ("smoke_owner", "smoke_peer"):
            credentials = {"username": username, "password": password}
            call(
                "POST", "/auth/register", 201, {**credentials, "email": f"{username}@example.test"}
            )
            tokens.append(call("POST", "/auth/login", 200, credentials)["access_token"])
        owner, peer = tokens
        project = call("POST", "/projects", 201, {"name": "Smoke project"}, owner)
        tasks_path = f"/projects/{project['id']}/tasks"
        task = call("POST", tasks_path, 201, {"title": "Smoke task", "status": "done"}, owner)
        assert call("GET", "/analytics/overview", 200, token=owner)["completed_tasks"] == 1
        assert call("GET", "/analytics/overview", 200, token=peer)["total_tasks"] == 0
        call("GET", f"/tasks/{task['id']}", 404, token=peer)
        export = call("GET", f"/projects/{project['id']}/export/csv", 200, token=owner)
        assert next(csv.DictReader(export.splitlines()))["Title"] == "Smoke task"
        print(
            "Compose smoke passed: migrations, readiness, non-root, auth, tenant isolation, KPIs, CSV."
        )
    except Exception:
        compose("ps", "-a")
        compose("logs", "--tail", "40")
        raise
    finally:
        compose("down", "--volumes", "--remove-orphans")


if __name__ == "__main__":
    main()
