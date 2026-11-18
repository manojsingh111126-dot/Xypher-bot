import traceback

import discord

# Xypher palette (knight theme). RED/BLUE names are kept so every cog keeps working:
#   RED  = primary brand colour (royal gold)   BLUE = secondary (steel blue)   DARK = night stone
GOLD = 0xC9A227
STEEL = 0x5B7C99
DARK = 0x1B2029
CRIMSON = 0xA63D34
RED = GOLD
BLUE = STEEL
FOOTER = "🛡️ Xypher • Sworn to guard your realm"


def knight_embed(title: str, description: str = "", color: int = GOLD) -> discord.Embed:
    """Every embed goes through here so the theme stays consistent."""
    embed = discord.Embed(
        title=f"⚔️ {title} ⚔️",
        description=description,
        color=color,
    )
    embed.set_footer(text=FOOTER)
    return embed


async def safe_dm(user, title: str, description: str = "", color: int = STEEL):
    """DM a user. Never raises: closed DMs, bots and missing users are silently ignored."""
    try:
        if user is None or getattr(user, "bot", False):
            return False
        await user.send(embed=knight_embed(title, description, color))
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- never fail silently
async def report_ui_error(interaction: discord.Interaction, error: Exception):
    """Print the real error to the console AND tell the user, so a broken button never shows
    Discord's 'The application did not respond' without any explanation."""
    traceback.print_exception(type(error), error, error.__traceback__)
    embed = knight_embed("Halt, Knight!", "Something went wrong on my side. Please try again. 🛡️", DARK)
    try:
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)
    except discord.HTTPException:
        pass  # the interaction already expired, nothing more we can do


def install_error_handlers():
    """Make every View and Modal in the bot report errors instead of failing silently."""
    async def view_on_error(self, interaction: discord.Interaction, error: Exception, item):
        await report_ui_error(interaction, error)

    async def modal_on_error(self, interaction: discord.Interaction, error: Exception):
        await report_ui_error(interaction, error)

    discord.ui.View.on_error = view_on_error
    discord.ui.Modal.on_error = modal_on_error
