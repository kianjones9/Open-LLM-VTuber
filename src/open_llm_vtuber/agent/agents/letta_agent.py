from typing import AsyncIterator, List, Dict, Any
from .agent_interface import AgentInterface
from ..output_types import SentenceOutput
from ..transformers import (
    sentence_divider,
    actions_extractor,
    tts_filter,
    display_processor,
)
from ...config_manager import TTSPreprocessorConfig
from ..input_types import BatchInput, TextSource
from letta_client import Letta


class LettaAgent(AgentInterface):
    """
    Custom Letta class to interface with the Letta server.
    """

    def __init__(
        self,
        live2d_model,
        id,
        tts_preprocessor_config: TTSPreprocessorConfig = None,
        faster_first_response: bool = True,
        segment_method: str = "pysbd",
        host: str = "localhost",
        port: int = 8283,
        letta_cloud_api_key: str = None,
    ):
        super().__init__()
        self.id = id
        
        # Initialize Letta client based on whether cloud API key is provided
        if letta_cloud_api_key:
            # Use Letta Cloud with API key
            self.client = Letta(base_url="https://api.letta.com", token=letta_cloud_api_key)
        else:
            # Use local Letta server
            self.url = f"http://{host}:{port}"
            self.client = Letta(base_url=self.url)
        # Initialize decorator parameters
        self._tts_preprocessor_config = tts_preprocessor_config
        self._live2d_model = live2d_model
        self._faster_first_response = faster_first_response
        self._segment_method = segment_method

        # Delay decorator application
        self.chat = tts_filter(self._tts_preprocessor_config)(
            display_processor()(
                actions_extractor(self._live2d_model)(
                    sentence_divider(
                        faster_first_response=self._faster_first_response,
                        segment_method=self._segment_method,
                        valid_tags=["think"],
                    )(self.chat)
                )
            )
        )

    def set_memory_from_history(self, conf_uid: str, history_uid: str) -> None:
        # The Letta Server automatically stores historical messages, so this part is not needed
        pass

    def handle_interrupt(self, heard_response: str) -> None:
        pass

    async def generator_to_async(self, gen):
        for item in gen:
            yield item

    async def chat(self, input_data: BatchInput) -> AsyncIterator[SentenceOutput]:
        messages = self._to_messages(input_data)
        
        try:
            # Use Letta Cloud streaming (stream_tokens=False works for content streaming)
            stream = self.generator_to_async(
                self.client.agents.messages.create_stream(
                    agent_id=self.id,
                    messages=messages,
                    stream_tokens=False,
                )
            )

            complete_response = ""
            async for token in stream:
                # Handle different token types
                if hasattr(token, 'message_type'):
                    # Skip metadata tokens
                    if token.message_type in ["stop_reason", "usage_statistics", "reasoning_message"]:
                        continue
                    elif token.message_type == "assistant_message" and hasattr(token, 'content') and token.content:
                        yield token.content
                        complete_response += token.content
                elif isinstance(token, str):
                    # Direct string tokens from Letta streaming
                    yield token
                    complete_response += token
                    
        except Exception as e:
            from loguru import logger
            logger.error(f"Error in Letta streaming: {e}")
            # Fallback to non-streaming
            try:
                response = self.client.agents.messages.create(
                    agent_id=self.id,
                    messages=messages,
                )
                
                if hasattr(response, 'messages') and response.messages:
                    for msg in response.messages:
                        is_assistant = (
                            (hasattr(msg, 'role') and msg.role == 'assistant') or
                            (hasattr(msg, 'message_type') and msg.message_type == 'assistant_message')
                        )
                        
                        if is_assistant and hasattr(msg, 'content') and msg.content:
                            yield msg.content
                            
            except Exception as fallback_error:
                logger.error(f"Fallback non-streaming also failed: {fallback_error}")
                yield "I'm having trouble connecting to Letta. Please check the logs."

    def _to_text_prompt(self, input_data: BatchInput) -> str:
        """
        Format BatchInput into a prompt string for the LLM.

        Args:
            input_data: BatchInput - The input data containing texts

        Returns:
            str - Formatted message string
        """
        message_parts = []

        # Process text inputs in order
        for text_data in input_data.texts:
            if text_data.source == TextSource.INPUT:
                message_parts.append(text_data.content)
            elif text_data.source == TextSource.CLIPBOARD:
                message_parts.append(f"[Clipboard content: {text_data.content}]")

        return "\n".join(message_parts)

    def _to_messages(self, input_data: BatchInput) -> List[Dict[str, Any]]:
        """
        Prepare messages list without image support.
        """
        messages = []

        if input_data.images:
            content = []
            text_content = self._to_text_prompt(input_data)
            content.append({"type": "text", "text": text_content})
            user_message = {"role": "user", "content": content}
        else:
            user_message = {"role": "user", "content": self._to_text_prompt(input_data)}

        messages.append(user_message)

        return messages
