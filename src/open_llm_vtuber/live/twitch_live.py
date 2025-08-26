import asyncio
import json
import re
import traceback
from typing import Callable, Dict, Any, List, Optional
from loguru import logger
import websockets

from .live_interface import LivePlatformInterface

try:
    import websocket
    WEBSOCKET_CLIENT_AVAILABLE = True
except ImportError:
    logger.warning("websocket-client library required for Twitch integration")
    WEBSOCKET_CLIENT_AVAILABLE = False


class TwitchLivePlatform(LivePlatformInterface):
    """
    Implementation of LivePlatformInterface for Twitch.
    Connects to Twitch IRC chat and forwards messages to the VTuber.
    """

    def __init__(self, channel: str, oauth_token: str = "", username: str = ""):
        """
        Initialize the Twitch Live platform client.

        Args:
            channel: Twitch channel name to monitor (without #)
            oauth_token: OAuth token for authentication (optional for read-only)
            username: Username for the bot (optional for read-only)
        """
        if not WEBSOCKET_CLIENT_AVAILABLE:
            raise ImportError("websocket-client library is required for Twitch functionality")

        self._channel = channel.lower().lstrip('#')
        self._oauth_token = oauth_token
        self._username = username.lower() if username else "justinfan12345"
        self._websocket: Optional[websockets.WebSocketClientProtocol] = None
        self._irc_socket: Optional[websocket.WebSocket] = None
        self._connected = False
        self._running = False
        self._message_handlers: List[Callable[[Dict[str, Any]], None]] = []

    @property
    def is_connected(self) -> bool:
        """Check if connected to the proxy server."""
        try:
            if hasattr(self._websocket, "closed"):
                return (
                    self._connected and self._websocket and not self._websocket.closed
                )
            elif hasattr(self._websocket, "open"):
                return self._connected and self._websocket and self._websocket.open
            else:
                return self._connected and self._websocket is not None
        except Exception:
            return False

    async def connect(self, proxy_url: str) -> bool:
        """
        Connect to the proxy WebSocket server.

        Args:
            proxy_url: The WebSocket URL of the proxy

        Returns:
            bool: True if connection successful
        """
        try:
            self._websocket = await websockets.connect(
                proxy_url, ping_interval=20, ping_timeout=10, close_timeout=5
            )
            self._connected = True
            logger.info(f"Connected to proxy at {proxy_url}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to proxy: {e}")
            return False

    async def disconnect(self) -> None:
        """
        Disconnect from the proxy server and stop the Twitch client.
        """
        self._running = False

        # Close Twitch IRC connection
        if self._irc_socket:
            try:
                self._irc_socket.close()
                self._irc_socket = None
            except Exception as e:
                logger.warning(f"Error while closing Twitch IRC socket: {e}")

        # Close WebSocket connection
        if self._websocket:
            try:
                await self._websocket.close()
            except Exception as e:
                logger.warning(f"Error while closing WebSocket: {e}")

        self._connected = False
        logger.info("Disconnected from Twitch and proxy server")

    async def send_message(self, text: str) -> bool:
        """
        Send a text message to the Twitch chat through IRC.
        
        Args:
            text: The message text

        Returns:
            bool: True if sent successfully
        """
        if not self._irc_socket or not self._oauth_token:
            logger.warning("Cannot send message: No IRC connection or OAuth token")
            return False

        try:
            message = f"PRIVMSG #{self._channel} :{text}\r\n"
            self._irc_socket.send(message)
            logger.info(f"Sent message to Twitch chat: {text}")
            return True
        except Exception as e:
            logger.error(f"Error sending message to Twitch chat: {e}")
            return False

    async def register_message_handler(
        self, handler: Callable[[Dict[str, Any]], None]
    ) -> None:
        """
        Register a callback for handling incoming messages.

        Args:
            handler: Function to call when a message is received
        """
        self._message_handlers.append(handler)
        logger.debug("Registered new message handler")

    def _connect_to_twitch_irc(self) -> bool:
        """
        Connect to Twitch IRC server.

        Returns:
            bool: True if connection successful
        """
        try:
            self._irc_socket = websocket.create_connection("wss://irc-ws.chat.twitch.tv:443")
            
            # Send authentication if token provided
            if self._oauth_token and not self._oauth_token.startswith("oauth:"):
                oauth_token = f"oauth:{self._oauth_token}"
            else:
                oauth_token = self._oauth_token

            if oauth_token:
                self._irc_socket.send(f"PASS {oauth_token}\r\n")
            else:
                self._irc_socket.send(f"PASS oauth:anonymous\r\n")
            
            self._irc_socket.send(f"NICK {self._username}\r\n")
            self._irc_socket.send(f"JOIN #{self._channel}\r\n")
            
            logger.info(f"Connected to Twitch IRC for channel #{self._channel}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Twitch IRC: {e}")
            return False

    def _parse_irc_message(self, message: str) -> Optional[str]:
        """
        Parse IRC message to extract chat text.

        Args:
            message: Raw IRC message

        Returns:
            Optional[str]: Chat message text or None
        """
        try:
            # Parse PRIVMSG format: :user!user@user.tmi.twitch.tv PRIVMSG #channel :message
            if "PRIVMSG" in message:
                # Extract username and message using regex
                match = re.match(r":(\w+)!.*PRIVMSG #\w+ :(.+)", message)
                if match:
                    username, chat_message = match.groups()
                    return f"{username}: {chat_message.strip()}"
            return None
        except Exception as e:
            logger.error(f"Error parsing IRC message: {e}")
            return None

    async def _handle_chat_message(self, chat_text: str):
        """
        Process received chat message and forward it to VTuber.

        Args:
            chat_text: The chat text received from Twitch
        """
        try:
            await self._send_to_proxy(chat_text)
        except Exception as e:
            logger.error(f"Error forwarding chat message to proxy: {e}")

    async def _send_to_proxy(self, text: str) -> bool:
        """
        Send chat text to the proxy.

        Args:
            text: The chat text to send

        Returns:
            bool: True if sent successfully
        """
        if not self.is_connected:
            logger.error("Cannot send message: Not connected to proxy")
            return False

        try:
            message = {"type": "text-input", "text": text}
            await self._websocket.send(json.dumps(message))
            logger.info(f"Sent chat message to VTuber: {text}")
            return True
        except Exception as e:
            logger.error(f"Error sending message to proxy: {e}")
            self._connected = False
            return False

    async def start_receiving(self) -> None:
        """
        Start receiving messages from the proxy WebSocket.
        This runs in the background to receive messages from the VTuber.
        """
        if not self.is_connected:
            logger.error("Cannot start receiving: Not connected to proxy")
            return

        try:
            logger.info("Started receiving messages from proxy")
            while self._running and self.is_connected:
                try:
                    message = await self._websocket.recv()
                    data = json.loads(message)

                    # Log received message (truncate audio data for readability)
                    if "audio" in data:
                        log_data = data.copy()
                        log_data["audio"] = f"[Audio data, length: {len(data['audio'])}]"
                        logger.debug(f"Received message from VTuber: {log_data}")
                    else:
                        logger.debug(f"Received message from VTuber: {data}")

                    # Process the message
                    await self.handle_incoming_messages(data)

                except websockets.exceptions.ConnectionClosed:
                    logger.warning("WebSocket connection closed by server")
                    self._connected = False
                    break
                except Exception as e:
                    logger.error(f"Error receiving message from proxy: {e}")
                    await asyncio.sleep(1)

            logger.info("Stopped receiving messages from proxy")
        except Exception as e:
            logger.error(f"Error in message receiving loop: {e}")

    async def handle_incoming_messages(self, message: Dict[str, Any]) -> None:
        """
        Process messages received from the VTuber.

        Args:
            message: The message received from the VTuber
        """
        # Process the message with all registered handlers
        for handler in self._message_handlers:
            try:
                await asyncio.to_thread(handler, message)
            except Exception as e:
                logger.error(f"Error in message handler: {e}")

    async def _monitor_twitch_chat(self):
        """
        Monitor Twitch IRC chat for incoming messages.
        """
        try:
            logger.info(f"Started monitoring Twitch chat for #{self._channel}")
            while self._running and self._irc_socket:
                try:
                    # Receive IRC message
                    response = self._irc_socket.recv()
                    
                    # Handle multiple messages in one response
                    for line in response.strip().split('\r\n'):
                        if not line:
                            continue
                            
                        # Handle PING/PONG to keep connection alive
                        if line.startswith("PING"):
                            pong_message = line.replace("PING", "PONG")
                            self._irc_socket.send(f"{pong_message}\r\n")
                            continue

                        # Parse chat message
                        chat_message = self._parse_irc_message(line)
                        if chat_message:
                            logger.debug(f"Received chat: {chat_message}")
                            await self._handle_chat_message(chat_message)

                except Exception as e:
                    if self._running:
                        logger.error(f"Error monitoring Twitch chat: {e}")
                        await asyncio.sleep(1)
                    else:
                        break

            logger.info("Stopped monitoring Twitch chat")
        except Exception as e:
            logger.error(f"Error in Twitch chat monitoring loop: {e}")

    async def run(self) -> None:
        """
        Main entry point for running the Twitch Live platform client.
        Connects to Twitch IRC and the proxy, and starts monitoring chat.
        """
        proxy_url = "ws://localhost:12393/proxy-ws"

        try:
            self._running = True

            # Connect to the proxy
            if not await self.connect(proxy_url):
                logger.error("Failed to connect to proxy, exiting")
                return

            # Connect to Twitch IRC
            if not self._connect_to_twitch_irc():
                logger.error("Failed to connect to Twitch IRC, exiting")
                await self.disconnect()
                return

            # Start background task for receiving messages from the proxy
            receive_task = asyncio.create_task(self.start_receiving())
            
            # Start monitoring Twitch chat
            chat_task = asyncio.create_task(self._monitor_twitch_chat())

            logger.info(f"Connected to Twitch channel #{self._channel}")

            # Wait for tasks to complete
            try:
                await asyncio.gather(receive_task, chat_task)
            except asyncio.CancelledError:
                logger.info("Tasks cancelled")

        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt, shutting down")
        except Exception as e:
            logger.error(f"Error in Twitch Live run loop: {e}")
            logger.debug(traceback.format_exc())
        finally:
            # Ensure clean disconnect
            await self.disconnect()