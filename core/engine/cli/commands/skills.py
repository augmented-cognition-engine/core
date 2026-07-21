# engine/cli/commands/skills.py
"""Legacy experimental skill compatibility commands."""

import click
import httpx

from core.engine.cli.auth import get_headers
from core.engine.cli.display import console


@click.group(invoke_without_command=True, hidden=True)
@click.option("--org", "-o", default="product:default")
@click.pass_context
def skills(ctx, org):
    """List all available skills."""
    if ctx.invoked_subcommand is None:
        url = ctx.obj["url"]
        headers = get_headers()

        resp = httpx.get(
            f"{url}/skills",
            params={"product": org},
            headers=headers,
            timeout=30,
        )

        if resp.status_code != 200:
            console.print(f"[red]Error {resp.status_code}:[/red] {resp.text}")
            return

        data = resp.json()
        skill_list = data.get("skills", [])

        if not skill_list:
            console.print("\n[dim]No skills found. Run: python scripts/seed_skills.py[/dim]\n")
            return

        console.print(f"\n[bold]Skills ({len(skill_list)})[/bold]\n")
        console.print(f"  {'Slug':<28s} {'Tier':<10s} {'Steps':<8s} {'Domain':<24s} {'Signals'}")
        console.print(f"  {'─' * 90}")

        for s in skill_list:
            slug = s.get("slug", "?")[:28]
            tier = s.get("tier", "?")[:10]
            steps = str(len(s.get("steps", [])))
            domain = (s.get("domain_path") or "general")[:24]
            signals = ", ".join(s.get("activation_signals", [])[:3])
            if len(s.get("activation_signals", [])) > 3:
                signals += "..."
            console.print(f"  {slug:<28s} {tier:<10s} {steps:<8s} {domain:<24s} {signals}")

        console.print()


@skills.command("get")
@click.argument("slug")
@click.pass_context
def get_skill(ctx, slug):
    """Show detail for a specific skill."""
    url = ctx.obj["url"]
    headers = get_headers()

    resp = httpx.get(
        f"{url}/skills/{slug}",
        headers=headers,
        timeout=30,
    )

    if resp.status_code != 200:
        console.print(f"[red]Error {resp.status_code}:[/red] {resp.text}")
        return

    s = resp.json()
    console.print(f"\n[bold]{s.get('name', '?')}[/bold] ({s.get('slug', '?')})")
    console.print(f"  Tier: {s.get('tier', '?')}")
    console.print(f"  Domain: {s.get('domain_path') or 'general'}")
    console.print(f"  Description: {s.get('description', '')}")
    console.print(f"  Signals: {', '.join(s.get('activation_signals', []))}")

    steps = s.get("steps", [])
    if steps:
        console.print(f"\n  Steps ({len(steps)}):")
        for i, step in enumerate(steps, 1):
            name = step.get("name", "?")
            arch = step.get("archetype", "?")
            mode = step.get("mode", "?")
            desc = step.get("description", "")[:60]
            console.print(f"    {i}. {name} ({arch}/{mode})")
            if desc:
                console.print(f"       {desc}")

    console.print()
