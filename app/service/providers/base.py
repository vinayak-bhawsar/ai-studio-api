from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class LLMProvider(ABC):
    """
    Common interface for all LLM providers.

    Application services depend on this interface instead
    of depending on a specific provider such as Groq or OpenAI.
    """

    @abstractmethod
    async def generate(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.7,
    ) -> str:
        """
        Generate a normal text response.
        """
        raise NotImplementedError

    @abstractmethod
    async def stream(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        """
        Stream a normal text response.
        """
        raise NotImplementedError

    @abstractmethod
    async def generate_structured(
        self,
        messages: list[dict[str, str]],
        *,
        schema: dict,
        schema_name: str,
        temperature: float = 0.4,
    ) -> dict:
        """
        Generate a structured JSON response.
        """
        raise NotImplementedError

    @abstractmethod
    async def stream_structured(
        self,
        messages: list[dict[str, str]],
        *,
        schema: dict,
        schema_name: str,
        temperature: float = 0.4,
    ) -> AsyncIterator[str]:
        """
        Stream a structured JSON response.
        """
        raise NotImplementedError