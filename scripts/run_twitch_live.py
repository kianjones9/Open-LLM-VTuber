import os
import sys
import asyncio
from loguru import logger

# Add project root to path to enable imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_root)

from src.open_llm_vtuber.live.twitch_live import TwitchLivePlatform
from src.open_llm_vtuber.config_manager.utils import read_yaml, validate_config


async def main():
    """
    Main function to run the Twitch Live platform client.
    Connects to Twitch IRC and forwards chat messages to the VTuber.
    """
    logger.info("Starting Twitch Live platform client")

    try:
        # Load configuration
        config_path = os.path.join(project_root, "conf.yaml")
        config_data = read_yaml(config_path)
        config = validate_config(config_data)

        # Extract Twitch Live configuration
        twitch_config = config.live_config.twitch_live

        # Check if channel is provided
        if not twitch_config.channel:
            logger.error(
                "No Twitch channel specified in configuration. Please add a channel name."
            )
            return

        logger.info(f"Connecting to Twitch channel: #{twitch_config.channel}")

        # Initialize and run the Twitch Live platform
        platform = TwitchLivePlatform(
            channel=twitch_config.channel,
            oauth_token=twitch_config.oauth_token,
            username=twitch_config.username
        )

        await platform.run()

    except ImportError as e:
        logger.error(f"Failed to import required modules: {e}")
        logger.error("Make sure you have installed websocket-client with: pip install websocket-client")
    except Exception as e:
        logger.error(f"Error starting Twitch Live client: {e}")
        import traceback

        logger.debug(traceback.format_exc())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down Twitch Live platform")

# Usage: uv run python scripts/run_twitch_live.py