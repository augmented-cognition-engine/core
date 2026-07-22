# engine/cli/commands/conflicts.py
"""ace conflicts — list and resolve intelligence conflicts."""

import click
import httpx

from core.engine.cli.auth import get_headers
from core.engine.cli.display import console


@click.group(invoke_without_command=True)
@click.option("--product", "--org", "-o", default=None, help="Product override (must match the authenticated product)")
@click.pass_context
def conflicts(ctx, product):
    """List unresolved conflicts."""
    if ctx.invoked_subcommand is None:
        url = ctx.obj["url"]
        headers = get_headers()

        params = {"status": "pending"}
        if product:
            params["product"] = product
        resp = httpx.get(
            f"{url}/conflicts",
            params=params,
            headers=headers,
            timeout=30,
        )

        if resp.status_code != 200:
            console.print(f"[red]Error {resp.status_code}:[/red] {resp.text}")
            return

        data = resp.json()
        conflict_list = data.get("conflicts", [])

        if not conflict_list:
            console.print("\n[green]No unresolved conflicts.[/green]\n")
            return

        console.print(f"\n[bold]Unresolved Conflicts ({len(conflict_list)})[/bold]\n")

        for i, c in enumerate(conflict_list, 1):
            cid = str(c.get("id", ""))
            a_content = c.get("insight_a_content", c.get("conflicting_content", "?"))
            a_conf = c.get("insight_a_confidence", 0)
            b_content = c.get("insight_b_content", "?")
            b_conf = c.get("insight_b_confidence", 0)
            explanation = c.get("explanation", "")

            console.print(f"  #{i}  {cid}")
            console.print(f'      A: "{_truncate(a_content, 80)}" (confidence: {a_conf:.2f})')
            console.print(f'      B: "{_truncate(b_content, 80)}" (confidence: {b_conf:.2f})')
            console.print(f"      Reason: {explanation}")
            console.print(f"      Resolve: ace conflicts resolve {cid} keep_a|keep_b|keep_both|merge")
            console.print()


@conflicts.command("resolve")
@click.argument("conflict_id")
@click.argument("action", type=click.Choice(["keep_a", "keep_b", "keep_both", "merge"]))
@click.option("--note", "-n", default="", help="Resolution note")
@click.option("--merged-content", "-m", default=None, help="Merged content (required for merge)")
@click.pass_context
def resolve_conflict(ctx, conflict_id, action, note, merged_content):
    """Resolve a conflict. Actions: keep_a, keep_b, keep_both, merge."""
    if action == "merge" and not merged_content:
        console.print("[red]Error:[/red] --merged-content is required for merge action.")
        return

    url = ctx.obj["url"]
    headers = get_headers()

    body = {
        "resolution_type": action,
        "resolution": note or f"Resolved via CLI: {action}",
    }
    if merged_content:
        body["merged_content"] = merged_content

    resp = httpx.post(
        f"{url}/conflicts/{conflict_id}/resolve",
        json=body,
        headers=headers,
        timeout=30,
    )

    if resp.status_code == 200:
        data = resp.json()
        console.print(f"\n[green]Resolved:[/green] {conflict_id}")
        console.print(f"  Action: {action}")
        console.print(f"  Resolved at: {data.get('resolved_at', 'now')}\n")
    else:
        console.print(f"[red]Error {resp.status_code}:[/red] {resp.text}")


def _truncate(text: str, max_len: int) -> str:
    if not text:
        return ""
    text = text.replace("\n", " ").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."
