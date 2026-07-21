"""Friendly, idempotent first-run setup for a local ACE service.

The command deliberately keeps orchestration out of the MCP process.  It hides
the local service plumbing instead: create configuration, select one provider,
start SurrealDB, migrate it, launch the API, and mint the bearer token used by
both the CLI and the thin MCP adapter.
"""

from __future__ import annotations

import json
import os
import platform
import re
import secrets
import shutil
import signal
import statistics
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

import click
import httpx

from core.engine.cli.auth import get_config_path, get_headers, save_config
from core.engine.cli.commands.run import _submit_and_wait
from core.engine.cli.display import console, print_task_result

_API_URL = "http://localhost:3000"
_PLACEHOLDERS = {
    "",
    "replace-me-with-32-byte-hex-string",
    "local-dev-only-not-a-secret",
    "dev-insecure-change-me",
}
_MODEL_PLACEHOLDERS = {"", "sk-test", "sk-test-placeholder", "dev-placeholder-not-a-real-key"}
_PROVIDER_CHOICES = click.Choice(
    ["anthropic", "openai", "codex", "claude-token", "claude-cli", "ollama", "existing"],
    case_sensitive=False,
)
_ASSIGNMENT = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")


def _find_project_root(explicit: Path | None = None) -> Path:
    """Find a source checkout containing the local Compose assets."""
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit.expanduser().resolve())
    candidates.extend([Path.cwd(), *Path.cwd().parents])
    source_root = Path(__file__).resolve().parents[4]
    candidates.extend([source_root, *source_root.parents])

    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if (candidate / "infra" / "docker-compose.yml").is_file() and (candidate / ".env.example").is_file():
            return candidate
    raise click.ClickException(
        "ACE's local runtime assets were not found. Run `ace setup` from an ace-core source checkout "
        "or pass `--project-dir /path/to/ace-core`."
    )


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        if value[0] == '"':
            try:
                return str(json.loads(value))
            except json.JSONDecodeError:
                pass
        return value[1:-1]
    return value


def _parse_env(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        match = _ASSIGNMENT.match(line)
        if match:
            values[match.group(1)] = _unquote(match.group(2))
    return values


def _dotenv_value(value: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_./:@+\-]*", value):
        return value
    return json.dumps(value)


def _update_env(text: str, updates: Mapping[str, str]) -> str:
    """Update active keys, activate matching templates, and append new keys."""
    lines = text.splitlines()
    for key, value in updates.items():
        rendered = f"{key}={_dotenv_value(value)}"
        active = re.compile(rf"^\s*(?:export\s+)?{re.escape(key)}\s*=")
        commented = re.compile(rf"^\s*#\s*{re.escape(key)}\s*=")
        index = next((i for i, line in enumerate(lines) if active.match(line)), None)
        if index is None:
            index = next((i for i, line in enumerate(lines) if commented.match(line)), None)
        if index is None:
            lines.append(rendered)
        else:
            lines[index] = rendered
    return "\n".join(lines).rstrip() + "\n"


def _usable(value: str | None, placeholders: set[str] = _PLACEHOLDERS) -> bool:
    return bool(value and value.strip() not in placeholders)


def _detect_provider(values: Mapping[str, str], environ: Mapping[str, str]) -> str | None:
    merged = {**values, **{key: value for key, value in environ.items() if value}}
    if _usable(merged.get("LITELLM_MODEL")) or _usable(merged.get("ANYLLM_MODEL")):
        return "existing router configuration"
    if _usable(merged.get("OLLAMA_HOST")):
        return "Ollama"
    if _usable(merged.get("OPENAI_COMPAT_BASE_URL")):
        return "OpenAI-compatible provider"
    if merged.get("SUBSCRIPTION_PROVIDER") == "codex" and shutil.which("codex"):
        return "Codex CLI / ChatGPT subscription"
    if _usable(merged.get("LLM_API_KEY"), _MODEL_PLACEHOLDERS):
        return "Anthropic API"
    if _usable(merged.get("CLAUDE_CODE_OAUTH_TOKEN")):
        return "Claude subscription token"
    if shutil.which("claude"):
        return "Claude CLI"
    return None


def _provider_updates(
    provider: str,
    current: Mapping[str, str],
    environ: Mapping[str, str],
    *,
    non_interactive: bool,
) -> dict[str, str]:
    """Return a single, explicit provider route without leaking secret values."""
    provider = provider.lower()
    if provider == "existing":
        if not _detect_provider(current, environ):
            raise click.ClickException("No usable existing provider was detected. Select a provider explicitly.")
        return {}

    # Clear routes that outrank or unexpectedly override the selected route.
    updates = {
        "LITELLM_MODEL": "",
        "ANYLLM_MODEL": "",
        "OLLAMA_HOST": "",
        "OPENAI_COMPAT_BASE_URL": "",
        "OPENAI_COMPAT_API_KEY": "",
        "SUBSCRIPTION_PROVIDER": "auto",
        "CLAUDE_CODE_OAUTH_TOKEN": "",
        "FORCE_CLI_PROVIDER": "0",
        "REQUIRE_SUBSCRIPTION": "0",
    }

    if provider == "anthropic":
        key = environ.get("LLM_API_KEY") or current.get("LLM_API_KEY", "")
        if not _usable(key, _MODEL_PLACEHOLDERS):
            if non_interactive:
                raise click.ClickException("Set LLM_API_KEY before using `--provider anthropic --non-interactive`.")
            key = click.prompt("Anthropic API key", hide_input=True)
        if len(key.strip()) <= 20:
            raise click.ClickException("The Anthropic API key looks incomplete. Paste the full key and rerun setup.")
        updates["LLM_API_KEY"] = key
    elif provider == "openai":
        key = (
            environ.get("OPENAI_COMPAT_API_KEY")
            or environ.get("OPENAI_API_KEY")
            or current.get("OPENAI_COMPAT_API_KEY", "")
        )
        if not _usable(key):
            if non_interactive:
                raise click.ClickException(
                    "Set OPENAI_COMPAT_API_KEY or OPENAI_API_KEY before using `--provider openai --non-interactive`."
                )
            key = click.prompt("OpenAI API key", hide_input=True)
        if len(key.strip()) <= 10:
            raise click.ClickException("The OpenAI API key looks incomplete. Paste the full key and rerun setup.")
        updates.update(
            {
                "LLM_API_KEY": "sk-test-placeholder",
                "OPENAI_COMPAT_BASE_URL": "https://api.openai.com/v1",
                "OPENAI_COMPAT_API_KEY": key,
                "OPENAI_COMPAT_MODEL": current.get("OPENAI_COMPAT_MODEL") or "gpt-5.6-terra",
            }
        )
    elif provider == "codex":
        if not shutil.which("codex"):
            raise click.ClickException("Codex CLI was not found. Install it and run `codex login`, then retry setup.")
        updates.update(
            {
                "LLM_API_KEY": "sk-test-placeholder",
                "SUBSCRIPTION_PROVIDER": "codex",
                "REQUIRE_SUBSCRIPTION": "1",
            }
        )
    elif provider == "claude-token":
        token = environ.get("CLAUDE_CODE_OAUTH_TOKEN") or current.get("CLAUDE_CODE_OAUTH_TOKEN", "")
        if not _usable(token):
            if non_interactive:
                raise click.ClickException(
                    "Set CLAUDE_CODE_OAUTH_TOKEN before using `--provider claude-token --non-interactive`."
                )
            token = click.prompt("Claude setup token", hide_input=True)
        if len(token.strip()) <= 20:
            raise click.ClickException("The Claude setup token looks incomplete. Run `claude setup-token` and retry.")
        updates.update(
            {
                "LLM_API_KEY": "sk-test-placeholder",
                "CLAUDE_CODE_OAUTH_TOKEN": token,
                "REQUIRE_SUBSCRIPTION": "1",
            }
        )
    elif provider == "claude-cli":
        if not shutil.which("claude"):
            raise click.ClickException("Claude CLI was not found. Install and authenticate it, then retry setup.")
        updates.update(
            {
                "LLM_API_KEY": "sk-test-placeholder",
                "SUBSCRIPTION_PROVIDER": "claude",
                "FORCE_CLI_PROVIDER": "1",
                "REQUIRE_SUBSCRIPTION": "1",
            }
        )
    elif provider == "ollama":
        updates.update(
            {
                "LLM_API_KEY": "sk-test-placeholder",
                "OLLAMA_HOST": environ.get("OLLAMA_HOST") or current.get("OLLAMA_HOST") or "http://localhost:11434",
                "OLLAMA_MODEL": environ.get("OLLAMA_MODEL") or current.get("OLLAMA_MODEL") or "llama3.2",
            }
        )
    else:  # Defensive for direct function calls; Click validates command-line input.
        raise click.ClickException(f"Unsupported provider: {provider}")
    return updates


def _provider_preflight(provider: str, configured: Mapping[str, str]) -> None:
    """Catch common no-cost provider failures before starting the ACE stack."""
    effective = provider.lower()
    if effective == "existing":
        if _usable(configured.get("OLLAMA_HOST")):
            effective = "ollama"
        elif configured.get("SUBSCRIPTION_PROVIDER") == "codex":
            effective = "codex"

    if effective == "codex":
        codex = shutil.which("codex")
        if not codex:
            raise click.ClickException("Codex CLI was not found. Install it, run `codex login`, and rerun setup.")
        try:
            status = subprocess.run(
                [codex, "login", "status"],
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
            )
        except subprocess.TimeoutExpired as exc:
            raise click.ClickException(
                "Codex sign-in status timed out. Run `codex login status` directly, then rerun setup."
            ) from exc
        if status.returncode != 0:
            raise click.ClickException(
                "Codex is installed but not signed in. Run `codex login`, then rerun `ace setup`."
            )
        console.print("[green]Codex subscription access is signed in.[/green]")
        return

    if effective == "ollama":
        host = configured.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        model = configured.get("OLLAMA_MODEL", "llama3.2")
        try:
            response = httpx.get(f"{host}/api/tags", timeout=5)
            response.raise_for_status()
            models = {
                str(item.get("name") or item.get("model"))
                for item in response.json().get("models", [])
                if item.get("name") or item.get("model")
            }
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            raise click.ClickException(
                f"Ollama is not reachable at {host}. Start it with `ollama serve`, then rerun `ace setup`."
            ) from exc
        model_base = model.split(":", 1)[0]
        if model not in models and not any(candidate.split(":", 1)[0] == model_base for candidate in models):
            raise click.ClickException(
                f"Ollama is running but model {model!r} is not installed. Run `ollama pull {model}`, then rerun setup."
            )
        console.print(f"[green]Ollama model {model} is available.[/green]")


def _compose_command() -> list[str] | None:
    docker = shutil.which("docker")
    if docker:
        result = subprocess.run(
            [docker, "compose", "version"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return [docker, "compose"]
    legacy = shutil.which("docker-compose")
    return [legacy] if legacy else None


def _runtime_paths() -> tuple[Path, Path]:
    config_dir = Path(os.environ.get("ACE_CONFIG_DIR", Path.home() / ".ace"))
    config_dir.mkdir(parents=True, exist_ok=True)
    config_dir.chmod(0o700)
    return config_dir / "api.pid", config_dir / "api.log"


def _record_onboarding_evidence(evidence: Mapping[str, object]) -> Path | None:
    """Append privacy-local setup evidence without credentials or prompt content."""
    config_dir = Path(os.environ.get("ACE_CONFIG_DIR", Path.home() / ".ace"))
    try:
        config_dir.mkdir(parents=True, exist_ok=True)
        config_dir.chmod(0o700)
        path = config_dir / "onboarding.jsonl"
        payload = json.dumps(dict(evidence), sort_keys=True) + "\n"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, payload.encode("utf-8"))
        finally:
            os.close(fd)
        path.chmod(0o600)
        return path
    except OSError:
        # Measurement must never become another onboarding failure mode.
        return None


def _load_onboarding_evidence() -> tuple[Path, list[dict[str, object]]]:
    config_dir = Path(os.environ.get("ACE_CONFIG_DIR", Path.home() / ".ace"))
    path = config_dir / "onboarding.jsonl"
    events: list[dict[str, object]] = []
    if not path.is_file():
        return path, events
    for line in path.read_text().splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("event") == "local_setup":
            events.append(event)
    return path, events


def _onboarding_summary(events: list[dict[str, object]]) -> dict[str, object]:
    runtime_attempts = [
        event for event in events if bool(event.get("start_requested", event.get("outcome") != "configured_only"))
    ]
    activation_attempts = [event for event in events if event.get("first_result_attempted")]
    trials = [event for event in events if event.get("maintainer_help_reported") is not None]
    ready_times = [float(event["time_to_ready_seconds"]) for event in events if "time_to_ready_seconds" in event]
    first_times = [
        float(event["time_to_first_result_seconds"]) for event in events if "time_to_first_result_seconds" in event
    ]
    setup_successes = sum(
        bool(event.get("setup_succeeded", event.get("success") and "time_to_ready_seconds" in event))
        for event in runtime_attempts
    )
    activation_successes = sum(bool(event.get("first_result_succeeded")) for event in activation_attempts)
    failures = Counter(str(event["failure_stage"]) for event in events if event.get("failure_stage"))
    return {
        "attempts": len(events),
        "runtime_attempts": len(runtime_attempts),
        "setup_successes": setup_successes,
        "setup_success_rate": round(setup_successes / len(runtime_attempts), 3) if runtime_attempts else None,
        "activation_attempts": len(activation_attempts),
        "activation_successes": activation_successes,
        "activation_success_rate": (
            round(activation_successes / len(activation_attempts), 3) if activation_attempts else None
        ),
        "median_time_to_ready_seconds": round(statistics.median(ready_times), 3) if ready_times else None,
        "median_time_to_first_result_seconds": round(statistics.median(first_times), 3) if first_times else None,
        "failure_stages": dict(sorted(failures.items())),
        "clean_user_trials": len(trials),
        "trials_without_maintainer_help": sum(event.get("maintainer_help_reported") is False for event in trials),
        "trials_without_architecture_knowledge": sum(
            event.get("architecture_knowledge_reported") is False for event in trials
        ),
        "platforms": dict(sorted(Counter(str(event.get("platform", "unknown")) for event in events).items())),
    }


def _pid_is_running(pid_file: Path) -> bool:
    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, 0)
        return True
    except (FileNotFoundError, ValueError, ProcessLookupError, PermissionError):
        return False


def _managed_api_pid(pid_file: Path) -> int | None:
    """Return the PID only when it still identifies ACE's managed Uvicorn."""
    if not _pid_is_running(pid_file):
        return None
    pid = int(pid_file.read_text().strip())
    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", "command="],
        capture_output=True,
        text=True,
        check=False,
    )
    command = result.stdout.strip()
    if result.returncode == 0 and "uvicorn" in command and "core.engine.api.main:app" in command:
        return pid
    return None


def _api_is_ready(url: str = _API_URL) -> bool:
    try:
        return httpx.get(f"{url}/health/live", timeout=1).status_code == 200
    except httpx.HTTPError:
        return False


def _api_port_is_occupied(url: str = _API_URL) -> bool:
    """Return true when something answers on the API origin but is not ACE."""
    try:
        httpx.get(url, timeout=1)
        return True
    except httpx.HTTPError:
        return False


def _start_local_runtime(root: Path, env_values: Mapping[str, str]) -> None:
    compose = _compose_command()
    if not compose:
        raise click.ClickException(
            "Docker Compose was not found. Install Docker Desktop or Docker Engine with Compose v2."
        )

    compose_file = root / "infra" / "docker-compose.yml"
    console.print("Starting SurrealDB…")
    try:
        subprocess.run(
            [*compose, "-f", str(compose_file), "up", "-d", "--wait", "surrealdb"],
            cwd=root,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise click.ClickException(
            f"SurrealDB failed to start (Docker Compose exited {exc.returncode}). "
            "Open Docker, then rerun `ace setup`; your saved configuration will be reused."
        ) from exc

    runtime_env = os.environ.copy()
    runtime_env.update(env_values)
    console.print("Applying the ACE schema…")
    try:
        subprocess.run(
            [sys.executable, str(root / "scripts" / "schema_apply.py")],
            cwd=root,
            env=runtime_env,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise click.ClickException(
            f"Schema migration failed (exited {exc.returncode}). SurrealDB is running and your configuration is saved; "
            "rerun `ace setup`."
        ) from exc

    if _api_is_ready():
        console.print("ACE API is already running.")
        return

    if _api_port_is_occupied():
        raise click.ClickException(
            "Port 3000 is already used by another application. Stop that application or set up ACE on a free port, "
            "then rerun `ace setup`."
        )

    pid_file, log_file = _runtime_paths()
    if _managed_api_pid(pid_file):
        console.print("Waiting for the existing ACE API process…")
    else:
        console.print("Starting the ACE API…")
        log_handle = log_file.open("ab")
        try:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "core.engine.api.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "3000",
                ],
                cwd=root,
                env=runtime_env,
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        finally:
            log_handle.close()
        pid_file.write_text(f"{process.pid}\n")
        pid_file.chmod(0o600)

    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if _api_is_ready():
            return
        time.sleep(0.25)
    raise click.ClickException(f"ACE API did not become ready. Inspect {log_file} for startup details.")


def _stop_local_runtime(root: Path) -> None:
    pid_file, _ = _runtime_paths()
    pid = _managed_api_pid(pid_file)
    if pid is not None:
        os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and _pid_is_running(pid_file):
            time.sleep(0.1)
        if _pid_is_running(pid_file):
            raise click.ClickException(f"ACE API process {pid} did not stop after SIGTERM.")
        pid_file.unlink(missing_ok=True)
        console.print("ACE API stopped.")
    elif _api_is_ready():
        console.print("An ACE API is running but was not started by this setup; leaving it running.")
    else:
        pid_file.unlink(missing_ok=True)
        console.print("ACE API is already stopped.")

    compose = _compose_command()
    if not compose:
        raise click.ClickException("Docker Compose was not found; the ACE API is stopped but SurrealDB may still run.")
    try:
        subprocess.run(
            [*compose, "-f", str(root / "infra" / "docker-compose.yml"), "stop", "surrealdb"],
            cwd=root,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise click.ClickException(f"The ACE API stopped, but SurrealDB did not (exit {exc.returncode}).") from exc
    console.print("SurrealDB stopped. Its Docker volume was preserved.")


def _login_local(api_key: str) -> None:
    try:
        response = httpx.post(f"{_API_URL}/auth/token", json={"api_key": api_key}, timeout=10)
        response.raise_for_status()
        token = response.json().get("token")
    except (httpx.HTTPError, ValueError) as exc:
        raise click.ClickException(f"ACE started, but automatic login failed: {exc}") from exc
    if not token:
        raise click.ClickException("ACE started, but automatic login returned no bearer token.")
    save_config(_API_URL, str(token))


def _run_first_task(description: str) -> tuple[bool, float]:
    """Run and render the activation outcome: one useful reasoning result."""
    started = time.monotonic()
    console.print("\n[bold]ACE is assembling the right perspectives for your decision…[/bold]")
    result, error = _submit_and_wait(
        _API_URL,
        {"description": description, "workspace_id": "workspace:default"},
        get_headers(),
    )
    elapsed = time.monotonic() - started
    if error:
        console.print(
            "[yellow]ACE is installed, but the first reasoning task did not finish.[/yellow] "
            f'{error}\nRun `ace doctor`, then retry with `ace run "your product decision"`.'
        )
        return False, elapsed
    if not result or result.get("status") not in {None, "completed"}:
        status = result.get("status", "unknown") if result else "no response"
        console.print(
            f"[yellow]ACE is installed, but the first reasoning task ended as {status}.[/yellow] "
            'Run `ace doctor`, then retry with `ace run "your product decision"`.'
        )
        return False, elapsed
    console.print("\n[green bold]Your first ACE recommendation[/green bold]")
    print_task_result(result)
    return True, elapsed


def _configured_project(project_dir: Path | None) -> tuple[Path, dict[str, str]]:
    root = _find_project_root(project_dir)
    env_path = root / ".env"
    if not env_path.is_file():
        raise click.ClickException("ACE is not configured yet. Run `ace setup` first.")
    return root, _parse_env(env_path.read_text())


@click.command("setup")
@click.option("--project-dir", type=click.Path(path_type=Path, file_okay=False), help="Path to the ace-core checkout")
@click.option("--provider", type=_PROVIDER_CHOICES, help="Model route to configure")
@click.option("--non-interactive", is_flag=True, help="Fail instead of prompting for missing choices or credentials")
@click.option("--no-start", is_flag=True, help="Write configuration without starting the local services")
@click.option("--first-task", help="Product decision or problem to reason through after setup")
@click.option("--skip-first-task", is_flag=True, help="Finish after setup without offering a first reasoning task")
@click.option(
    "--onboarding-trial",
    is_flag=True,
    help="Record self-reported maintainer-help and architecture-knowledge evidence",
)
def setup(
    project_dir: Path | None,
    provider: str | None,
    non_interactive: bool,
    no_start: bool,
    first_task: str | None,
    skip_first_task: bool,
    onboarding_trial: bool,
) -> None:
    """Configure and start a usable local ACE installation.

    Safe to rerun: existing credentials are retained unless their provider is
    explicitly replaced, while generated placeholders are repaired.
    """
    if first_task and skip_first_task:
        raise click.ClickException("Use either `--first-task` or `--skip-first-task`, not both.")
    started = time.monotonic()
    stage = "configuration"
    selected_provider = provider
    interventions: list[str] = []
    evidence: dict[str, object] = {
        "schema_version": 1,
        "event": "local_setup",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "platform": platform.system().lower(),
        "machine": platform.machine().lower(),
        "python": platform.python_version(),
        "start_requested": not no_start,
        "success": False,
        "configuration_succeeded": False,
        "setup_succeeded": False,
        "first_result_attempted": False,
        "first_result_succeeded": False,
        "path_succeeded": False,
        "maintainer_help_reported": None,
        "architecture_knowledge_reported": None,
    }
    console.print("[bold]Let's get ACE ready to help with your first product decision.[/bold]")
    try:
        root = _find_project_root(project_dir)
        env_path = root / ".env"
        env_text = env_path.read_text() if env_path.exists() else (root / ".env.example").read_text()
        current = _parse_env(env_text)

        detected = _detect_provider(current, os.environ)
        if selected_provider is None:
            if detected:
                selected_provider = "existing"
                console.print(f"Using your existing model access: [cyan]{detected}[/cyan]")
            elif non_interactive:
                raise click.ClickException("No provider was detected. Pass `--provider` or configure one in .env.")
            else:
                interventions.append("provider_selection_prompt")
                console.print("How should ACE access a model? Choose an account or local model you already use.")
                console.print("Options: anthropic, openai, codex, claude-token, claude-cli, or ollama.")
                selected_provider = click.prompt("Model access", type=_PROVIDER_CHOICES)

        credential_missing = {
            "anthropic": not _usable(os.environ.get("LLM_API_KEY") or current.get("LLM_API_KEY"), _MODEL_PLACEHOLDERS),
            "openai": not _usable(
                os.environ.get("OPENAI_COMPAT_API_KEY")
                or os.environ.get("OPENAI_API_KEY")
                or current.get("OPENAI_COMPAT_API_KEY")
            ),
            "claude-token": not _usable(
                os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") or current.get("CLAUDE_CODE_OAUTH_TOKEN")
            ),
        }
        if not non_interactive and credential_missing.get(selected_provider, False):
            interventions.append("credential_prompt")
        updates = _provider_updates(selected_provider, current, os.environ, non_interactive=non_interactive)
        jwt_secret = current.get("JWT_SECRET", "")
        api_key = current.get("API_KEY", "")
        if not _usable(jwt_secret):
            updates["JWT_SECRET"] = secrets.token_hex(32)
        if not _usable(api_key):
            updates["API_KEY"] = secrets.token_urlsafe(32)

        updated_text = _update_env(env_text, updates)
        env_path.write_text(updated_text)
        env_path.chmod(0o600)
        configured = _parse_env(updated_text)
        console.print("[green]Secure local configuration is ready.[/green]")
        evidence["provider"] = selected_provider
        evidence["configuration_succeeded"] = True

        if no_start:
            console.print("Services were not started. Rerun `ace setup` without `--no-start` when ready.")
            evidence["success"] = True
            evidence["outcome"] = "configured_only"
            return

        stage = "provider_preflight"
        _provider_preflight(selected_provider, {**configured, **os.environ})
        stage = "local_services"
        _start_local_runtime(root, configured)
        stage = "authentication"
        _login_local(configured["API_KEY"])
        evidence["setup_succeeded"] = True
        evidence["time_to_ready_seconds"] = round(time.monotonic() - started, 3)
        console.print("\n[green bold]ACE is ready to reason with you.[/green bold]")

        if first_task is None and not skip_first_task and not non_interactive:
            interventions.append("first_task_offer")
            if click.confirm("Work through your first product decision now?", default=True):
                interventions.append("first_task_prompt")
                first_task = click.prompt("What decision or problem are you working through?")

        if first_task:
            stage = "first_result"
            evidence["first_result_attempted"] = True
            first_ok, first_elapsed = _run_first_task(first_task)
            evidence["first_result_succeeded"] = first_ok
            evidence["path_succeeded"] = first_ok
            evidence["first_result_seconds"] = round(first_elapsed, 3)
            evidence["time_to_first_result_seconds"] = round(time.monotonic() - started, 3)
            evidence["outcome"] = "first_result" if first_ok else "first_result_failed"
        else:
            evidence["outcome"] = "ready_without_first_result"
            console.print(
                "Get your first recommendation whenever you're ready:\n"
                '  [cyan]ace run "What is the riskiest assumption in my product plan?"[/cyan]'
            )

        if onboarding_trial:
            evidence["maintainer_help_reported"] = click.confirm(
                "Did you need maintainer help outside this setup flow?", default=False
            )
            evidence["architecture_knowledge_reported"] = click.confirm(
                "Did you need to understand ACE's architecture to finish?", default=False
            )

        mcp_command = shutil.which("ace-mcp-client") or "ace-mcp-client"
        console.print("\n[dim]Optional next steps[/dim]")
        console.print(f"Use ACE inside your AI client with MCP command: [cyan]{mcp_command}[/cyan]")
        console.print(f"Authentication: {get_config_path()} · Diagnostics: `ace doctor`")
        evidence["success"] = True
    except Exception as exc:
        evidence["failure_stage"] = stage
        evidence["failure_type"] = type(exc).__name__
        raise
    finally:
        evidence["setup_interventions"] = interventions
        evidence["elapsed_seconds"] = round(time.monotonic() - started, 3)
        evidence["completed_at"] = datetime.now(timezone.utc).isoformat()
        evidence_path = _record_onboarding_evidence(evidence)
        if onboarding_trial and evidence_path:
            console.print(f"[dim]Onboarding evidence saved locally to {evidence_path}.[/dim]")


@click.group("service")
def service() -> None:
    """Start, stop, or inspect ACE's local background service."""


@service.command("start")
@click.option("--project-dir", type=click.Path(path_type=Path, file_okay=False), help="Path to the ace-core checkout")
def service_start(project_dir: Path | None) -> None:
    """Start a previously configured local ACE installation."""
    root, configured = _configured_project(project_dir)
    if not _detect_provider(configured, os.environ):
        raise click.ClickException("No usable model provider is configured. Rerun `ace setup --provider <provider>`.")
    _provider_preflight("existing", {**configured, **os.environ})
    _start_local_runtime(root, configured)
    _login_local(configured["API_KEY"])
    console.print("[green]ACE is ready.[/green]")


@service.command("stop")
@click.option("--project-dir", type=click.Path(path_type=Path, file_okay=False), help="Path to the ace-core checkout")
def service_stop(project_dir: Path | None) -> None:
    """Stop ACE and SurrealDB while preserving all stored data."""
    root = _find_project_root(project_dir)
    _stop_local_runtime(root)


@service.command("status")
def service_status() -> None:
    """Report whether the local ACE API is reachable."""
    pid_file, log_file = _runtime_paths()
    ready = _api_is_ready()
    managed_pid = _managed_api_pid(pid_file)
    if ready:
        ownership = f"managed process {managed_pid}" if managed_pid else "externally managed process"
        console.print(f"[green]ACE API is ready[/green] at {_API_URL} ({ownership}).")
        console.print(f"Logs: {log_file}")
        return
    console.print(f"[red]ACE API is not reachable[/red] at {_API_URL}.")
    raise SystemExit(1)


@service.command("logs")
@click.option("--lines", type=click.IntRange(1, 1000), default=80, show_default=True)
def service_logs(lines: int) -> None:
    """Show recent local ACE API logs for guided recovery."""
    _, log_file = _runtime_paths()
    if not log_file.is_file():
        raise click.ClickException(f"No managed API log exists at {log_file}. Run `ace setup` first.")
    recent = log_file.read_text(errors="replace").splitlines()[-lines:]
    click.echo("\n".join(recent))


@click.group("onboarding")
def onboarding() -> None:
    """Inspect privacy-local first-run evidence."""


@onboarding.command("report")
@click.option("--json-output", is_flag=True, help="Emit machine-readable JSON")
def onboarding_report(json_output: bool) -> None:
    """Summarize setup reliability and time to first useful result."""
    path, events = _load_onboarding_evidence()
    if not events:
        raise click.ClickException(f"No onboarding evidence found at {path}. Run `ace setup` first.")
    summary = _onboarding_summary(events)
    if json_output:
        click.echo(json.dumps({"path": str(path), **summary}, indent=2, sort_keys=True))
        return
    console.print(f"[bold]Onboarding evidence[/bold] · {path}")
    console.print(
        f"Setup: {summary['setup_successes']}/{summary['runtime_attempts']} successful "
        f"({summary['setup_success_rate']})"
    )
    console.print(
        f"First useful result: {summary['activation_successes']}/{summary['activation_attempts']} successful "
        f"({summary['activation_success_rate']})"
    )
    console.print(
        f"Median time: ready={summary['median_time_to_ready_seconds']}s · "
        f"first result={summary['median_time_to_first_result_seconds']}s"
    )
    console.print(f"Failure stages: {summary['failure_stages'] or 'none'}")
    console.print(
        f"Clean-user trials: {summary['clean_user_trials']} · "
        f"without maintainer help={summary['trials_without_maintainer_help']} · "
        f"without architecture knowledge={summary['trials_without_architecture_knowledge']}"
    )
