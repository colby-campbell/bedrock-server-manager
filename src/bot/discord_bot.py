from utils import BroadcastHandler, LineBroadcaster
import asyncio
import discord
import logging
from discord.ext import commands


## Command to check if the user has admin privileges
def is_admin(admin_ids):
    async def predicate(ctx):
        # Check if the user is an admin or the bot owner
        is_owner = await commands.is_owner().predicate(ctx)
        is_admin = ctx.author.id in admin_ids
        return is_admin or is_owner

    return commands.check(predicate)


class DiscordBot:
    """
    Discord bot for managing a Minecraft Bedrock server.
    """
    def __init__(self, config, server, automation):
        """
        Initialize the DiscordBot with configuration, server runner, and automation instances.
        Args:
            config (ServerConfig): The server configuration instance.
            server (ServerRunner): The server runner instance.
            automation (ServerAutomation): The server automation instance.
        """
        self.admin_list = config.admins
        self.token = config.bot_token
        self.server = server
        self.automation = automation
        self.broadcaster = LineBroadcaster()
        # Create a custom broadcast handler for logging
        self.broadcast_handler = BroadcastHandler(self.broadcaster, self.automation.logger)
        # Create a custom log formatter for logging
        self.log_formatter = logging.Formatter('[%(asctime)s %(levelname)s] %(message)s')
        intents = discord.Intents.default()
        intents.message_content = True
        self.bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

    def discord_bot_start(self):
        """Start the Discord bot and register commands."""
        # Create the help command
        @self.bot.command(name="help")
        async def discord_help(ctx):
            embed = discord.Embed(
                title="Help",
                description="Here's a list of all available commands.",
                color=discord.Color.red()
            )

            embed.add_field(
                name="Bot Owner Commands",
                value="\n".join([
                    "`!cmd` — Allows access to the command-line of the internal Minecraft Bedrock server."
                ])
            )

            embed.add_field(
                name="Admin Commands",
                value="\n".join([
                    "`!start` - Start the Minecraft Bedrock server.",
                    "`!stop` - Stop the server.",
                    "`!restart` - Restart the server.",
                    "`!backup` - Create a world backup.",
                    "`!list` - List existing backups.",
                    "`!mark <backup_name | latest | YYYY-MM-DD>` - Protect backup(s) from automatic deletion.",
                    "`!unmark <backup_name | latest | YYYY-MM-DD>` - Unprotect backup(s) from automatic deletion.",
                    "`!switch <backup_name> - Switch the world to the specified backup.",
                    "`!check` - Check for Bedrock server updates.",
                    "`!update` - Update the Bedrock server to the latest version.",
                ]),
                inline=False
            )

            embed.add_field(
                name="General Commands",
                value="\n".join([
                    "`!help` — Show this message.",
                    "`!online` — Show who is online."
                ]),
                inline=False
            )

            await ctx.send(embed=embed)

        # Bot owner command
        @commands.is_owner()
        @self.bot.command(name="cmd")
        async def discord_cmd(ctx):
            print("Command-line access invoked")

        # Admin commands
        @is_admin(self.admin_list)
        @self.bot.command(name="start")
        async def discord_start(ctx):
            print("Start command invoked")

        @is_admin(self.admin_list)
        @self.bot.command(name="stop")
        async def discord_stop(ctx):
            print("Stop command invoked")

        @is_admin(self.admin_list)
        @self.bot.command(name="restart")
        async def discord_restart(ctx):
            print("Restart command invoked")

        @is_admin(self.admin_list)
        @self.bot.command(name="backup")
        async def discord_backup(ctx):
            print("Backup command invoked")

        @is_admin(self.admin_list)
        @self.bot.command(name="list")
        async def discord_list(ctx):
            print("List command invoked")

        @is_admin(self.admin_list)
        @self.bot.command(name="mark")
        async def discord_mark(ctx):
            print("Mark command invoked")

        @is_admin(self.admin_list)
        @self.bot.command(name="unmark")
        async def discord_unmark(ctx):
            print("Unmark command invoked")

        @is_admin(self.admin_list)
        @self.bot.command(name="switch")
        async def discord_switch(ctx):
            print("Switch command invoked")

        @is_admin(self.admin_list)
        @self.bot.command(name="check")
        async def discord_check(ctx):
            print("Check command invoked")

        @is_admin(self.admin_list)
        @self.bot.command(name="update")
        async def discord_update(ctx):
            print("Update command invoked")

        # General commands that don't require admin privileges
        @self.bot.command(name="online")
        async def discord_online(ctx):
            print("Online command invoked")

        @self.bot.event
        async def on_command_error(ctx, error):
            if isinstance(error, commands.errors.CheckFailure):
                await ctx.send("You do not have the permissions to use this command.")

        # Start the discord bot with custom logging
        self.bot.run(self.token, log_handler=self.broadcast_handler, log_formatter=self.log_formatter)

    def discord_bot_stop(self):
        """Stop the Discord bot."""
        # To shut down properly, schedule the close coroutine on the event loop
        asyncio.run_coroutine_threadsafe(self.bot.close(), self.bot.loop)
