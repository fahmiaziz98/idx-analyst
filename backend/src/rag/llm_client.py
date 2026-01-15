import base64
import io
from typing import Any

from loguru import logger
from openai import APIConnectionError, AsyncOpenAI
from PIL import Image

from src.core.config import settings
from src.core.exception import ParsingError, ValidationError


class VLMClient:
    """
    Client for interacting with Vision-Language Models (VLM).

    Designed to work with OpenAI-compatible APIs hosting VLMs like Qwen3-VL.
    Handles image-to-base64 conversion and structured prompt generation.

    Attributes:
        base_url (str): The API endpoint URL.
        model_name (str): The name of the model to query.
        max_tokens (int): Maximum tokens for the generated response.
        temperature (float): Sampling temperature for generation.
        min_p (float): Minimum probability for nucleus sampling.
    """

    def __init__(
        self,
        base_url: str | None = None,
        model_name: str = "Qwen3-VL",
        max_tokens: int = 8192,
        temperature: float = 1.5,
        min_p: float = 0.1,
        timeout: int = 600,
    ) -> None:
        """
        Initialize the VLM Client.

        Args:
            base_url: API endpoint URL. Defaults to settings.VLLM_ENDPOINT.
            model_name: Name of the model to use. Defaults to "Qwen3-VL".
            max_tokens: Max output tokens. Defaults to 8192.
            temperature: Sampling temperature. Defaults to 1.5.
            min_p: Min-p sampling parameter. Defaults to 0.1.
            timeout: Request timeout in seconds. Defaults to 600.

        Raises:
            ValidationError: If base_url is not configured or initialization fails.
        """
        self.base_url = base_url or settings.VLLM_ENDPOINT
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.min_p = min_p

        if not self.base_url:
            raise ValidationError("VLLM_ENDPOINT is not configured.")

        try:
            self.client = AsyncOpenAI(
                base_url=self.base_url,
                api_key="EMPTY",
                timeout=timeout,
                max_retries=3,
            )
            logger.info(f"VLM Client initialized: {self.model_name} @ {self.base_url}")
        except Exception as e:
            raise ValidationError(f"Failed to initialize VLM Client: {e}") from e

    def _image_to_base64(self, image: Image.Image) -> str:
        """
        Convert a PIL Image to a base64 encoded string.

        Args:
            image: The PIL Image object to convert.

        Returns:
            str: Base64 encoded string of the image (PNG format).
        """
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG")
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    async def generate(
        self,
        messages: list[dict[str, Any]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """
        Generate text response from a list of messages.

        Args:
            messages: List of message dictionaries (OpenAI chat format).
            temperature: Override default temperature.
            max_tokens: Override default max_tokens.

        Returns:
            str: The generated text response.

        Raises:
            ParsingError: If API connection or generation fails.
        """
        try:
            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                max_tokens=max_tokens or self.max_tokens,
                temperature=temperature or self.temperature,
                extra_body={"min_p": self.min_p},
            )
            return response.choices[0].message.content or ""
        except APIConnectionError as e:
            raise ParsingError(f"VLM API connection failed: {e}") from e
        except Exception as e:
            raise ParsingError(f"VLM generation failed: {e}") from e

    async def generate_with_image(
        self,
        image: Image.Image,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """
        Generate text response from an image and prompts.

        Constructs a multimodal message with the image and prompts.

        Args:
            image: The PIL Image to analyze.
            system_prompt: System instruction for the model.
            user_prompt: User query or instruction related to the image.
            temperature: Override default temperature.
            max_tokens: Override default max_tokens.

        Returns:
            str: The generated text response.
        """
        image_base64 = self._image_to_base64(image)

        messages = [
            # {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": system_prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
                    },
                ],
            },
        ]

        return await self.generate(messages, temperature, max_tokens)

    def get_metadata(self) -> dict[str, Any]:
        """
        Retrieve client configuration metadata.

        Returns:
            Dict[str, Any]: Configuration details (model, parameters).
        """
        return {
            "model_name": self.model_name,
            "base_url": self.base_url,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "min_p": self.min_p,
        }
