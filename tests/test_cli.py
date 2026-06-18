from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from oecd_ai_visibility.cli import LIVE_PROVIDER_CONFIRMATION, app

ROOT = Path(__file__).resolve().parents[1]


def test_run_live_requires_explicit_confirmation_token() -> None:
    result = CliRunner().invoke(
        app,
        [
            "run",
            "--config",
            str(ROOT / "config" / "study.yaml"),
            "--live",
        ],
    )

    assert result.exit_code != 0
    assert LIVE_PROVIDER_CONFIRMATION in result.output
    assert "confirm-live" in result.output


def test_run_rejects_conflicting_live_and_dry_run_modes() -> None:
    result = CliRunner().invoke(
        app,
        [
            "run",
            "--config",
            str(ROOT / "config" / "study.yaml"),
            "--dry-run",
            "--live",
            "--confirm-live",
            LIVE_PROVIDER_CONFIRMATION,
        ],
    )

    assert result.exit_code != 0
    assert "either --dry-run or --live" in result.output


def test_status_command_surfaces_safe_local_workflow() -> None:
    result = CliRunner().invoke(
        app,
        [
            "status",
            "--config",
            str(ROOT / "config" / "study.yaml"),
        ],
    )

    assert result.exit_code == 0
    assert "Safe local commands" in result.output
    assert "validation-report" in result.output
    assert "score --heuristic-live-cache --aggregate" in result.output
    assert LIVE_PROVIDER_CONFIRMATION in result.output
