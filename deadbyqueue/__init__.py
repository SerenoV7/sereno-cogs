from redbot.core.bot import Red

from .deadbyqueue import DeadByQueue

__red_end_user_data_statement__ = "This cog does not persistently store any end user data."


async def setup(bot: Red) -> None:
    await bot.add_cog(DeadByQueue(bot))
