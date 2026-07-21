# engine/cli/main.py
"""ACE CLI — submit tasks, query intelligence, manage the system."""

import click

from core.engine.cli.auth import get_base_url, get_token


@click.group()
@click.option("--url", envvar="ACE_URL", default=None, help="ACE API URL")
@click.pass_context
def cli(ctx, url):
    """ACE — Augmented Cognition Engine. Turn product decisions into durable recommendations."""
    ctx.ensure_object(dict)
    ctx.obj["url"] = url or get_base_url()
    ctx.obj["token"] = get_token()


# Import and register command groups
from core.engine.cli.commands.assertions import assertion
from core.engine.cli.commands.briefing import briefing
from core.engine.cli.commands.conflicts import conflicts
from core.engine.cli.commands.doctor import doctor
from core.engine.cli.commands.evolve import evolve
from core.engine.cli.commands.flow import flow
from core.engine.cli.commands.graph import graph
from core.engine.cli.commands.ideas import idea, ideas
from core.engine.cli.commands.initiatives import init
from core.engine.cli.commands.intel import intel, search
from core.engine.cli.commands.landscape import landscape
from core.engine.cli.commands.login import login
from core.engine.cli.commands.model_policy import model_policy
from core.engine.cli.commands.proposals import proposals
from core.engine.cli.commands.reasoning import frameworks
from core.engine.cli.commands.run import quick, run
from core.engine.cli.commands.sentinel import sentinel
from core.engine.cli.commands.setup import onboarding, service, setup
from core.engine.cli.commands.skills import skills
from core.engine.cli.commands.status import status
from core.engine.cli.commands.templates import templates

cli.add_command(login)
cli.add_command(assertion)
cli.add_command(run)
cli.add_command(quick)
cli.add_command(intel)
cli.add_command(search)
cli.add_command(status)
cli.add_command(doctor)
cli.add_command(model_policy)
cli.add_command(landscape)
cli.add_command(graph)
cli.add_command(proposals)
cli.add_command(flow)
cli.add_command(sentinel)
cli.add_command(setup)
cli.add_command(service)
cli.add_command(onboarding)
cli.add_command(briefing)
cli.add_command(conflicts)
# Legacy experimental compatibility surface: callable, but no longer promoted
# alongside the 0.1.x product-builder path.
cli.add_command(skills)
cli.add_command(frameworks)
cli.add_command(init)
cli.add_command(idea)
cli.add_command(ideas)
cli.add_command(templates)
cli.add_command(evolve)
