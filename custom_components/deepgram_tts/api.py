"""Sample API Client."""

from __future__ import annotations

import socket
from typing import AsyncIterator

import aiohttp
import async_timeout


class IntegrationBlueprintApiClientError(Exception):
    """Exception to indicate a general API error."""


class IntegrationBlueprintApiClientCommunicationError(
    IntegrationBlueprintApiClientError,
):
    """Exception to indicate a communication error."""


class IntegrationBlueprintApiClientAuthenticationError(
    IntegrationBlueprintApiClientError,
):
    """Exception to indicate an authentication error."""


def _verify_response_or_raise(response: aiohttp.ClientResponse) -> None:
    """Verify that the response is valid."""
    if response.status in (401, 403):
        msg = "Invalid credentials"
        raise IntegrationBlueprintApiClientAuthenticationError(
            msg,
        )
    response.raise_for_status()


class DeepgramTTSApiClientError(Exception):
    """Exception to indicate a general API error."""


class DeepgramTTSApiClientCommunicationError(DeepgramTTSApiClientError):
    """Exception to indicate a communication error."""


class DeepgramTTSApiClientAuthenticationError(DeepgramTTSApiClientError):
    """Exception to indicate an authentication error."""


def _verify_response_or_raise(response: aiohttp.ClientResponse) -> None:
    """Verify that the response is valid."""
    if response.status in (401, 403):
        msg = "Invalid API key"
        raise DeepgramTTSApiClientAuthenticationError(msg)
    response.raise_for_status()


class DeepgramTTSApiClient:
    """Deepgram TTS API Client."""

    def __init__(
        self,
        api_key: str,
        session: aiohttp.ClientSession,
    ) -> None:
        """Initialize Deepgram TTS API client."""
        self._api_key = api_key
        self._session = session
        self._base_url = "https://api.deepgram.com/v1/speak"

    async def async_test_api_key(self) -> None:
        """Test if the API key is valid by making a simple request."""
        test_payload = {
            "text": "test",
        }
        headers = {
            "Authorization": f"Token {self._api_key}",
            "Content-Type": "text/plain"
        }
        params = {
            "model": "aura-2-thalia-en"
        }
        try:
            async with async_timeout.timeout(10):
                response = await self._session.post(
                    self._base_url,
                    data="test".encode("utf-8"),
                    headers=headers,
                    params=params,
                )
                _verify_response_or_raise(response)
        except Exception as exc:
            raise

    async def async_synthesize_speech(
        self,
        text: str,
        model: str = "aura-2-thalia-en",
        encoding: str = "mp3",
    ) -> bytes:
        """Synthesize speech from text using Deepgram TTS API.

        Returns audio data bytes.
        """
        # Ensure model is not empty
        if not model or model.strip() == "":
            model = "aura-2-thalia-en"

        headers = {
            "Authorization": f"Token {self._api_key}",
            "Content-Type": "text/plain",
        }
        params = {
            "model": model,
            "encoding": encoding,
        }
        try:
            async with async_timeout.timeout(30):
                response = await self._session.post(
                    self._base_url,
                    data=text.encode("utf-8"),
                    headers=headers,
                    params=params,
                )
                _verify_response_or_raise(response)
                audio_bytes = await response.read()
                return audio_bytes
        except TimeoutError as exception:
            msg = f"Timeout error fetching information - {exception}"
            raise DeepgramTTSApiClientCommunicationError(
                msg,
            ) from exception
        except (aiohttp.ClientError, socket.gaierror) as exception:
            msg = f"Error fetching information - {exception}"
            raise DeepgramTTSApiClientCommunicationError(
                msg,
            ) from exception
        except Exception as exception:  # pylint: disable=broad-except
            msg = f"Something really wrong happened! - {exception}"
            raise DeepgramTTSApiClientError(
                msg,
            ) from exception

    async def async_stream_speech(
        self,
        text: str,
        model: str = "aura-2-thalia-en",
        encoding: str = "mp3",
    ) -> AsyncIterator[bytes]:
        """Synthesize speech and yield audio bytes as they arrive.

        Streams the HTTP response body so playback can begin after the first
        byte instead of waiting for the full synthesis, as recommended in
        https://developers.deepgram.com/docs/text-to-speech-latency
        """
        # Ensure model is not empty
        if not model or model.strip() == "":
            model = "aura-2-thalia-en"

        headers = {
            "Authorization": f"Token {self._api_key}",
            "Content-Type": "text/plain",
        }
        params = {
            "model": model,
            "encoding": encoding,
        }
        try:
            async with async_timeout.timeout(30):
                async with self._session.post(
                    self._base_url,
                    data=text.encode("utf-8"),
                    headers=headers,
                    params=params,
                ) as response:
                    _verify_response_or_raise(response)
                    # iter_any() yields each buffer as soon as it is received,
                    # minimising time-to-first-audio.
                    async for chunk in response.content.iter_any():
                        if chunk:
                            yield chunk
        except TimeoutError as exception:
            msg = f"Timeout error fetching information - {exception}"
            raise DeepgramTTSApiClientCommunicationError(
                msg,
            ) from exception
        except (aiohttp.ClientError, socket.gaierror) as exception:
            msg = f"Error fetching information - {exception}"
            raise DeepgramTTSApiClientCommunicationError(
                msg,
            ) from exception
