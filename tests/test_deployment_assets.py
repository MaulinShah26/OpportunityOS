from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_staging_compose_keeps_services_private() -> None:
    compose = (ROOT / "docker-compose.staging.yml").read_text(encoding="utf-8")

    assert "127.0.0.1:${STAGING_PORT:-8000}:8000" in compose
    assert "5432:5432" not in compose
    assert "cap_drop:" in compose
    assert "read_only: true" in compose
    assert "AUTO_CREATE_SCHEMA: \"false\"" in compose


def test_container_starts_with_migrations_and_non_root_user() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    entrypoint = (ROOT / "scripts/container-entrypoint.sh").read_text(encoding="utf-8")

    assert "USER opportunityos" in dockerfile
    assert "ENTRYPOINT" in dockerfile
    assert "alembic upgrade head" in entrypoint
    assert "exec uvicorn" in entrypoint


def test_staging_secrets_and_backups_are_ignored() -> None:
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert ".env.staging" in gitignore
    assert "backups/" in gitignore
