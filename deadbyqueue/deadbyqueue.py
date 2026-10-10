import asyncio
import re

import aiohttp
import discord
from redbot.core import app_commands, commands
from redbot.core.bot import Red

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


# Single-region responses use a different shape: "Frankfurt Killer: 5m7s | Survivor: 6s"
SINGLE = re.compile(r"^(.+?) Killer: (.+?) \| Survivor: (.+)$")


def parse(entry: str) -> tuple[str, str, str]:
    # "Frankfurt 5m35s / 12s" -> ("Frankfurt", "5m35s", "12s"), killer first, survivor second
    parts = entry.rsplit(" ", 3)
    if len(parts) == 4 and parts[2] == "/":
        return parts[0], parts[1], parts[3]
    return entry.split(" ❌")[0], "❌ Offline", "❌ Offline"  # e.g. "Ohio ❌ Offline"


def build_embed(text: str) -> discord.Embed:
    text = text.strip()
    m = SINGLE.match(text)
    rows = [m.groups()] if m else [parse(e) for e in text.split(" | ")]
    # Three inline fields = three columns; each row is one line per column, so they always line up.
    e = discord.Embed(title="Queue Times", colour=discord.Colour.dark_red())
    e.add_field(name="Region", value="\n".join(f"{FLAGS.get(n, ':earth_africa:')} {n}" for n, _, _ in rows))
    e.add_field(name=":knife: Killer", value="\n".join(k for _, k, _ in rows))
    e.add_field(name=":runner: Survivor", value="\n".join(s for _, _, s in rows))
    return e.set_footer(text="Data provided by deadbyqueue.com")


class DeadByQueue(commands.Cog):
    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.session: aiohttp.ClientSession | None = None

    async def cog_load(self) -> None:
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))

    async def cog_unload(self) -> None:
        if self.session:
            await self.session.close()

    @app_commands.command(description="Show Dead by Daylight queue times.")
    @app_commands.describe(region="Only show this region (default: all)")
    @app_commands.choices(region=CHOICES)
    async def queuetime(
        self, interaction: discord.Interaction, region: app_commands.Choice[str] | None = None
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        params = {
            "region": region.value if region else ",".join(REGIONS),
            "mode": "live,live-event",
            "extras": "regionname",
        }
        try:
            async with self.session.get(API, params=params) as resp:
                resp.raise_for_status()
                text = await resp.text()
            embed = build_embed(text)
        except (aiohttp.ClientError, asyncio.TimeoutError):
            embed = discord.Embed(title="Queue Times", description="The API is unreachable.", colour=discord.Colour.dark_red())
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def red_delete_data_for_user(self, **kwargs):
        """Nothing to delete: this cog does not store any user data."""
        return