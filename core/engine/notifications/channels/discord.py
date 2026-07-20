"""Discord notification channel adapter.

Delivers notifications to a Discord server channel using embeds and action
buttons.  Each notification spawns a thread for follow-up discussion.
Replies in threads are captured as observations via ace_capture.

Bidirectional:
- **Outbound:** embeds + buttons pushed to server channel with auto-threads.
- **Inbound:** slash commands (/ace briefing, /ace status, etc.) and button
  clicks route to MCP tool implementations. Thread replies captured as
  observations.

Fallback: if no channel_id is configured, delivers via DM to user_id.

discord.py is optional — the adapter degrades gracefully when the library
is not installed.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from core.engine.notifications.audit_buffer import record
from core.engine.voice.audit import audit_or_warn

try:
    import discord
    from discord import app_commands
except ImportError:  # pragma: no cover
    discord = None  # type: ignore[assignment]
    app_commands = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tier → embed color
# ---------------------------------------------------------------------------

TIER_COLORS: dict[str, int] = {
    "critical": 0xDC3545,  # red
    "actionable": 0xFD7E14,  # orange
    "informational": 0x0D6EFD,  # blue
    "silent": 0x6C757D,  # gray
}

# ---------------------------------------------------------------------------
# Category → button configs  (label, action_id, style_name)
# ---------------------------------------------------------------------------

CATEGORY_BUTTONS: dict[str, list[tuple[str, str, str]]] = {
    "gap_detected": [
        ("Create Spec", "action:create_spec", "primary"),
        ("Dismiss", "action:dismiss", "secondary"),
    ],
    "conflict_detected": [
        ("Resolve", "action:resolve", "primary"),
        ("Dismiss", "action:dismiss", "secondary"),
    ],
    "idea_ready": [
        ("Create Spec", "action:create_spec", "primary"),
        ("Explore", "action:explore", "secondary"),
    ],
    "briefing": [
        ("Details", "action:details", "primary"),
        ("Gaps", "action:gaps", "secondary"),
        ("Recommend", "action:recommend", "secondary"),
    ],
    "spec_verified": [
        ("View Results", "action:view_results", "primary"),
    ],
}


# ---------------------------------------------------------------------------
# Embed builder
# ---------------------------------------------------------------------------


def _build_embed(notification: dict[str, Any]) -> Any:
    """Build a Discord Embed from a notification dict."""
    tier = notification.get("tier", "informational")
    color = TIER_COLORS.get(tier, TIER_COLORS["informational"])

    title = notification.get("title", "Notification")
    description = notification.get("body") or notification.get("description", "")

    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_footer(text=f"ACE • {tier}")
    return embed


# ---------------------------------------------------------------------------
# View (buttons) builder
# ---------------------------------------------------------------------------


def _build_view(notification: dict[str, Any]) -> Any | None:
    """Build a Discord View with buttons for the notification's category.

    Returns None if no buttons are defined for the category.
    """
    category = notification.get("category", "")
    button_configs = CATEGORY_BUTTONS.get(category)
    if not button_configs:
        return None

    source_record = notification.get("source_record", "")
    view = discord.ui.View()

    for label, action_id, style_name in button_configs:
        style = getattr(discord.ButtonStyle, style_name, discord.ButtonStyle.secondary)
        custom_id = f"{action_id}:{source_record}"
        button = discord.ui.Button(label=label, custom_id=custom_id, style=style)
        view.add_item(button)

    return view


# ---------------------------------------------------------------------------
# Inbound DM capture
# ---------------------------------------------------------------------------


async def _handle_dm_text(content: str, user_id: int, product_id: str = "product:platform") -> None:
    """Capture a DM reply as an observation via ace_capture."""
    try:
        from core.engine.mcp.tools import ace_capture

        await ace_capture(
            observation_type="feedback",
            content=f"[discord] {content}",
            domain_path="",
            confidence=0.5,
            product_id=product_id,
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("ace_capture failed for discord DM from user %s: %s", user_id, exc)


# ---------------------------------------------------------------------------
# Button action router
# ---------------------------------------------------------------------------

# Maps action prefixes to MCP tool calls
ACTION_HANDLERS: dict[str, str] = {
    "action:create_spec": "ace_create_spec",
    "action:details": "ace_load",
    "action:gaps": "ace_gaps",
    "action:recommend": "ace_recommend",
    "action:explore": "ace_ask_product",
    "action:view_results": "ace_load",
    "action:dismiss": "_dismiss",
    "action:resolve": "_resolve",
}


async def _handle_button(interaction: Any, product_id: str) -> None:
    """Route a button interaction to the appropriate MCP tool."""
    custom_id = interaction.data.get("custom_id", "")
    parts = custom_id.split(":", 2)
    action_key = ":".join(parts[:2]) if len(parts) >= 2 else custom_id
    source_record = parts[2] if len(parts) > 2 else ""

    handler_name = ACTION_HANDLERS.get(action_key)

    if handler_name == "_dismiss":
        await interaction.response.send_message("Dismissed.", ephemeral=True)
        return

    if handler_name == "_resolve":
        await interaction.response.send_message(
            "Reply in this thread with your resolution — it will be captured as a correction.",
            ephemeral=True,
        )
        return

    if not handler_name:
        await interaction.response.send_message(f"Unknown action: {action_key}", ephemeral=True)
        return

    # Defer while we call the MCP tool (may take a few seconds)
    await interaction.response.defer()

    try:
        result = await _call_tool(handler_name, source_record, product_id)
        embed = _format_tool_result(handler_name, result)
        await interaction.followup.send(embed=embed)
    except Exception as exc:
        logger.error("Button handler failed for %s: %s", action_key, exc)
        await interaction.followup.send(f"Error: {exc}")


async def _call_tool(tool_name: str, context: str, product_id: str) -> dict:
    """Call an MCP tool implementation by name."""
    from core.engine.mcp import tools

    if tool_name == "ace_create_spec":
        return await tools.ace_create_spec(description=context, source="discord", product_id=product_id)
    if tool_name == "ace_load":
        topic = context.split(":")[-1] if context else "general"
        return await tools.ace_load(topic=topic, product_id=product_id)
    if tool_name == "ace_gaps":
        dimension = context.split(":")[-1] if context else None
        return await tools.ace_gaps(product_id=product_id, dimension=dimension)
    if tool_name == "ace_recommend":
        return await tools.ace_recommend(product_id=product_id)
    if tool_name == "ace_ask_product":
        return await tools.ace_ask_product(question=context, product_id=product_id)
    return {"error": f"Unknown tool: {tool_name}"}


def _format_tool_result(tool_name: str, result: dict) -> Any:
    """Format an MCP tool result as a Discord embed."""
    title = tool_name.replace("ace_", "").replace("_", " ").title()
    # Truncate long results for Discord embed limit (4096 chars)
    body = json.dumps(result, indent=2, default=str)
    if len(body) > 3900:
        body = body[:3900] + "\n..."

    embed = discord.Embed(title=f"ACE — {title}", description=f"```json\n{body}\n```", color=0x0D6EFD)
    embed.set_footer(text="ACE | response")
    return embed


# ---------------------------------------------------------------------------
# Slash command registration
# ---------------------------------------------------------------------------


def _register_slash_commands(tree: Any, channel_id: int | None, product_id: str) -> None:
    """Register /ace slash commands on the command tree."""

    @tree.command(name="briefing", description="Get the latest ACE intelligence briefing")
    async def cmd_briefing(interaction: Any) -> None:
        await interaction.response.defer()
        try:
            from core.engine.mcp.tools import ace_briefing

            result = await ace_briefing(product_id=product_id)
            content = result.get("content", "No briefing available.")
            # Briefing content can be long — truncate for Discord
            if len(content) > 3900:
                content = content[:3900] + "\n\n... (truncated)"
            embed = discord.Embed(title="Intelligence Briefing", description=content, color=0xFD7E14)
            embed.set_footer(text="ACE | briefing")
            await interaction.followup.send(embed=embed)
        except Exception as exc:
            await interaction.followup.send(f"Error: {exc}")

    @tree.command(name="status", description="Check ACE status — initiatives, ideas, approvals")
    async def cmd_status(interaction: Any) -> None:
        await interaction.response.defer()
        try:
            from core.engine.mcp.tools import ace_start

            result = await ace_start(product_id=product_id)
            lines = [
                f"**Briefing available:** {result.get('briefing_available', False)}",
                f"**Active initiatives:** {result.get('active_initiatives', 0)}",
                f"**Ideas ready:** {result.get('ideas_ready', 0)}",
                f"**Pending approvals:** {result.get('pending_approvals', 0)}",
            ]
            embed = discord.Embed(title="ACE Status", description="\n".join(lines), color=0x0D6EFD)
            embed.set_footer(text="ACE | status")
            await interaction.followup.send(embed=embed)
        except Exception as exc:
            await interaction.followup.send(f"Error: {exc}")

    @tree.command(name="gaps", description="Show quality gaps, optionally filtered by discipline")
    @app_commands.describe(discipline="Filter by discipline (e.g. security, testing, performance)")
    async def cmd_gaps(interaction: Any, discipline: str | None = None) -> None:
        await interaction.response.defer()
        try:
            from core.engine.mcp.tools import ace_gaps

            result = await ace_gaps(product_id=product_id, dimension=discipline)
            gaps = result.get("gaps", [])
            if not gaps:
                await interaction.followup.send("No quality gaps found.")
                return
            lines = []
            for g in gaps[:15]:  # limit for Discord
                lines.append(f"- **{g.get('dimension', '?')}** ({g.get('score', '?')}): {g.get('capability', '?')}")
            embed = discord.Embed(
                title=f"Quality Gaps{f' — {discipline}' if discipline else ''}",
                description="\n".join(lines),
                color=0xDC3545,
            )
            embed.set_footer(text="ACE | gaps")
            await interaction.followup.send(embed=embed)
        except Exception as exc:
            await interaction.followup.send(f"Error: {exc}")

    @tree.command(name="recommend", description="Get prioritized work recommendations")
    async def cmd_recommend(interaction: Any) -> None:
        await interaction.response.defer()
        try:
            from core.engine.mcp.tools import ace_recommend

            result = await ace_recommend(product_id=product_id)
            body = json.dumps(result, indent=2, default=str)
            if len(body) > 3900:
                body = body[:3900] + "\n..."
            embed = discord.Embed(title="Recommendations", description=f"```json\n{body}\n```", color=0x0D6EFD)
            embed.set_footer(text="ACE | recommend")
            await interaction.followup.send(embed=embed)
        except Exception as exc:
            await interaction.followup.send(f"Error: {exc}")

    @tree.command(name="health", description="Product health — capabilities and quality scores")
    async def cmd_health(interaction: Any) -> None:
        await interaction.response.defer()
        try:
            from core.engine.mcp.tools import ace_product_health

            result = await ace_product_health(product_id=product_id)
            body = json.dumps(result, indent=2, default=str)
            if len(body) > 3900:
                body = body[:3900] + "\n..."
            embed = discord.Embed(title="Product Health", description=f"```json\n{body}\n```", color=0x0D6EFD)
            embed.set_footer(text="ACE | health")
            await interaction.followup.send(embed=embed)
        except Exception as exc:
            await interaction.followup.send(f"Error: {exc}")


# ---------------------------------------------------------------------------
# Channel adapter
# ---------------------------------------------------------------------------


class DiscordChannel:
    """Discord notification channel adapter.

    Supports two delivery modes:
    - **Server channel** (preferred): posts to a channel, creates a thread
      per notification for follow-up discussion.
    - **DM fallback**: sends directly to user DM if no channel_id configured.
    """

    name: str = "discord"

    def __init__(
        self,
        user_id: int,
        product_id: str = "product:platform",
        channel_id: int | None = None,
    ) -> None:
        self.user_id = user_id
        self._org_id = product_id
        self._channel_id = channel_id
        self._bot: Any = None
        self._connected: bool = False

    async def send(self, notification: dict[str, Any]) -> bool:
        """Deliver *notification* via server channel (with thread) or DM fallback.

        Returns True on success, False if the bot is not connected or
        delivery fails.
        """
        if not self._connected or self._bot is None:
            logger.debug("Discord channel not connected — skipping send")
            return False

        # Extract and audit message before transmit try/except
        message_text = notification.get("body") or notification.get("description", "")
        product_id = notification.get(
            "product_id", self._org_id
        )  # _org_id must be a product:*-shaped record id; ring buffer key drift if not
        if message_text:
            audit_or_warn(message_text, label="discord")
            record("discord", product_id, message_text)

        try:
            embed = _build_embed(notification)
            view = _build_view(notification)

            if self._channel_id:
                return await self._send_to_channel(embed, view, notification)
            return await self._send_dm(embed, view)
        except Exception as exc:
            logger.error("Discord delivery failed: %s", exc)
            return False

    async def _send_to_channel(self, embed: Any, view: Any, notification: dict[str, Any]) -> bool:
        """Post embed to server channel and create a thread."""
        channel = self._bot.get_channel(self._channel_id)
        if channel is None:
            channel = await self._bot.fetch_channel(self._channel_id)

        msg = await channel.send(embed=embed, view=view)

        # Create a thread from the message for follow-up discussion
        category = notification.get("category", "notification")
        title = notification.get("title", "ACE Notification")
        thread_name = f"{category}: {title}"[:100]  # Discord thread name limit
        await msg.create_thread(name=thread_name)

        logger.info("Discord channel post + thread: [%s] %s", notification.get("tier"), title)
        return True

    async def _send_dm(self, embed: Any, view: Any) -> bool:
        """Fallback: send via DM."""
        user = await self._bot.fetch_user(self.user_id)
        await user.send(embed=embed, view=view)
        return True

    async def health_check(self) -> bool:
        """Return True when the bot is connected and ready."""
        return self._connected

    async def start_bot(self) -> None:
        """Create and start the Discord bot with slash commands.

        Token is read from the ACE_DISCORD_BOT_TOKEN environment variable.
        The bot is started as an asyncio background task.
        """
        if discord is None:  # pragma: no cover
            logger.error("discord.py is not installed — cannot start Discord bot")
            return

        token = os.environ.get("ACE_DISCORD_BOT_TOKEN", "")
        if not token:
            logger.warning("ACE_DISCORD_BOT_TOKEN not set — Discord bot not started")
            return

        intents = discord.Intents.default()
        intents.message_content = True
        intents.dm_messages = True

        bot = discord.Client(intents=intents)
        tree = app_commands.CommandTree(bot)
        self._bot = bot

        # Register /briefing, /status, /gaps, /recommend, /health
        _register_slash_commands(tree, self._channel_id, self._org_id)

        product_id = self._org_id

        @bot.event
        async def on_ready() -> None:
            self._connected = True
            # Sync slash commands with Discord API
            try:
                synced = await tree.sync()
                logger.info("Discord bot ready as %s — synced %d slash commands", bot.user, len(synced))
            except Exception as exc:
                logger.warning("Failed to sync slash commands: %s", exc)
                logger.info("Discord bot ready as %s (commands not synced)", bot.user)

        @bot.event
        async def on_disconnect() -> None:
            self._connected = False
            logger.warning("Discord bot disconnected")

        @bot.event
        async def on_message(message: Any) -> None:
            # Ignore messages from the bot itself
            if message.author == bot.user:
                return
            # Capture DM replies
            if str(message.channel.type) == "private":
                await _handle_dm_text(message.content, message.author.id, product_id=product_id)
            # Capture thread replies in the configured channel
            elif (
                str(message.channel.type) == "public_thread"
                and hasattr(message.channel, "parent_id")
                and message.channel.parent_id == self._channel_id
            ):
                await _handle_dm_text(message.content, message.author.id, product_id=product_id)

        @bot.event
        async def on_interaction(interaction: Any) -> None:
            """Handle button clicks — slash commands are handled by CommandTree automatically."""
            if interaction.type == discord.InteractionType.component:
                await _handle_button(interaction, product_id)

        asyncio.create_task(bot.start(token))

    async def stop_bot(self) -> None:
        """Shut down the Discord bot client."""
        if self._bot is not None:
            await self._bot.close()
            self._connected = False
