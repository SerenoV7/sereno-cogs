import asyncio
import logging
import re
from typing import Literal

import aiohttp
import discord
from redbot.core import app_commands, commands
from redbot.core.bot import Red

log = logging.getLogger("red.sereno-cogs.deadbyqueue")  # red.<repo name>.<cog name>
RequestType = Literal["discord_deleted_user", "owner", "user", "user_strict"]

API = "https://api.deadbyqueue.com/queuetime"
# code: (name as returned by the API, Discord flag shortcode)
REGIONS = {
    "eu-central-1": ("Frankfurt", ":flag_de:"),
    "eu-west-1": ("Dublin", ":flag_ie:"),
    "eu-west-2": ("London", ":flag_gb:"),
    "us-east-1": ("Virginia", ":flag_us:"),
    "us-east-2": ("Ohio", ":flag_us:"),
    "us-west-1": ("California", ":flag_us:"),
    "us-west-2": ("Oregon", ":flag_us:"),
    "ca-central-1": ("Montréal", ":flag_ca:"),
    "ap-south-1": ("Mumbai", ":flag_in:"),
    "ap-east-1": ("Hong Kong", ":flag_hk:"),
    "ap-northeast-1": ("Tokyo", ":flag_jp:"),
    "ap-northeast-2": ("Seoul", ":flag_kr:"),
    "ap-southeast-1": ("Singapore", ":flag_sg:"),
    "ap-southeast-2": ("Sydney", ":flag_au:"),
    "sa-east-1": ("São Paulo", ":flag_br:"),
}
FLAGS = dict(REGIONS.values())
CHOICES = [app_commands.Choice(name=n, value=c) for c, (n, _) in REGIONS.items()]


MODES = [
    app_commands.Choice(name="Live", value="live"),
    app_commands.Choice(name="Live Event", value="live-event"),
    app_commands.Choice(name="PTB", value="ptb"),
    app_commands.Choice(name="PTB Event", value="ptb-event"),
]
PAIR = re.compile(r"(\d[\dhms]*) / (\d[\dhms]*)")  # "5m35s / 12s"
NAME_END = re.compile(r"\s+(?=\d|❌|Event:)")  # names contain no digits


def parse(entry: str, mode: str) -> tuple[str, str, str]:
    # "Frankfurt 5m35s / 12s" -> ("Frankfurt", "5m35s", "12s"), killer first, survivor second
    name = NAME_END.split(entry, 1)[0]
    pairs = PAIR.findall(entry)
    if not pairs:  # e.g. "Ohio ❌ Offline"
        return name, "❌ Offline", "❌ Offline"
    # A "live, Event:" entry carries two pairs; take the one matching the requested mode.
    return name, *pairs[-1 if mode.endswith("-event") else 0]


def build_embed(
    text: str, mode: app_commands.Choice[str], region: str | None, colour: discord.Colour
) -> discord.Embed:
    rows = [parse(e, mode.value) for e in text.strip().split(" | ")]
    rows = [r for r in rows if region in (None, r[0])]
    e = discord.Embed(title=f"Queue Times · {mode.name}", colour=colour)
    e.set_footer(text="Data provided by deadbyqueue.com")
    if not rows:
        e.description = "No data returned."
        return e
    # Three inline fields = three columns; each row is one line per column, so they always line up.
    e.add_field(name="Region", value="\n".join(f"{FLAGS.get(n, ':earth_africa:')} {n}" for n, _, _ in rows))
    e.add_field(name=":knife: Killer", value="\n".join(k for _, k, _ in rows))
    e.add_field(name=":runner: Survivor", value="\n".join(s for _, _, s in rows))
    return e


class DeadByQueue(commands.Cog):
    """Check Dead by Daylight queue times by region and mode."""

    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.session: aiohttp.ClientSession | None = None

    async def cog_load(self) -> None:
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))

    async def cog_unload(self) -> None:
        if self.session:
            await self.session.close()

    @app_commands.command(description="Show Dead by Daylight queue times.")
    @app_commands.describe(region="Only show this region (default: all)", mode="Queue to show (default: Live)")
    @app_commands.choices(region=CHOICES, mode=MODES)
    async def queuetime(
        self,
        interaction: discord.Interaction,
        region: app_commands.Choice[str] | None = None,
        mode: app_commands.Choice[str] | None = None,
    ) -> None:
        """Show Dead by Daylight queue times."""
        await interaction.response.defer(ephemeral=True)
        colour = await self.bot.get_embed_color(interaction.channel)
        mode = mode or MODES[0]
        # Always fetch every region and filter locally: the single-region response has a different shape.
        params = {"region": ",".join(REGIONS), "mode": mode.value, "extras": "regionname"}
        try:
            async with self.session.get(API, params=params) as resp:
                resp.raise_for_status()
                text = await resp.text()
            embed = build_embed(text, mode, region and region.name, colour)
        except (aiohttp.ClientError, asyncio.TimeoutError):
            log.warning("deadbyqueue.com request failed", exc_info=True)
            embed = discord.Embed(title="Queue Times", description="The API is unreachable.", colour=colour)
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def red_delete_data_for_user(self, *, requester: RequestType, user_id: int) -> None:
        """Nothing to delete: this cog does not store any user data."""
        return
