# engine/cli/commands/reasoning.py
"""ace frameworks — browse reasoning frameworks."""

import click
import httpx

from core.engine.cli.auth import get_headers
from core.engine.cli.display import console


@click.group(invoke_without_command=True)
@click.option("--org", "-o", default="product:default")
@click.pass_context
def frameworks(ctx, org):
    """List all available reasoning frameworks."""
    if ctx.invoked_subcommand is None:
        url = ctx.obj["url"]
        headers = get_headers()

        resp = httpx.get(f"{url}/frameworks", params={"product": org}, headers=headers, timeout=30)
        if resp.status_code != 200:
            console.print(f"[red]Error {resp.status_code}:[/red] {resp.text}")
            return

        data = resp.json()
        fw_list = data.get("frameworks", [])

        if not fw_list:
            console.print("\n[dim]No frameworks found. Run: python scripts/seed_frameworks.py[/dim]\n")
            return

        console.print(f"\n[bold]Reasoning Frameworks ({len(fw_list)})[/bold]\n")
        console.print(f"  {'Slug':<28s} {'Family':<14s} {'Tier':<10s} {'Signals'}")
        console.print(f"  {'─' * 80}")

        for fw in fw_list:
            slug = fw.get("slug", "?")[:28]
            family = fw.get("family", "?")[:14]
            tier = fw.get("tier", "?")[:10]
            signals = ", ".join(fw.get("activation_signals", [])[:3])
            if len(fw.get("activation_signals", [])) > 3:
                signals += "..."
            console.print(f"  {slug:<28s} {family:<14s} {tier:<10s} {signals}")

        console.print()


@frameworks.command("get")
@click.argument("slug")
@click.pass_context
def get_framework(ctx, slug):
    """Show detail for a specific framework."""
    url = ctx.obj["url"]
    headers = get_headers()

    resp = httpx.get(f"{url}/frameworks/{slug}", headers=headers, timeout=30)
    if resp.status_code != 200:
        console.print(f"[red]Error {resp.status_code}:[/red] {resp.text}")
        return

    fw = resp.json()
    console.print(f"\n[bold]{fw.get('name', '?')}[/bold] ({fw.get('slug', '?')})")
    console.print(f"  Family: {fw.get('family', '?')}")
    console.print(f"  Tier: {fw.get('tier', '?')}")
    console.print(f"  Signals: {', '.join(fw.get('activation_signals', []))}")

    arch = fw.get("archetype_affinity", {})
    if arch:
        arch_str = ", ".join(f"{k}: {v}" for k, v in sorted(arch.items(), key=lambda x: -x[1]))
        console.print(f"  Archetype affinity: {arch_str}")

    mode = fw.get("mode_affinity", {})
    if mode:
        mode_str = ", ".join(f"{k}: {v}" for k, v in sorted(mode.items(), key=lambda x: -x[1]))
        console.print(f"  Mode affinity: {mode_str}")

    prompt = fw.get("system_prompt", "")
    if prompt:
        console.print("\n  System Prompt:")
        for line in prompt.split("\n"):
            console.print(f"    {line}")

    console.print()
