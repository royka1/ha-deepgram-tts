"""Deepgram TTS platform for Home Assistant."""

from __future__ import annotations

import logging
from typing import Any
import re
from typing import AsyncGenerator

# (chunk_text eliminado, usar solo el chunking de stream_processor.py)

from homeassistant.components.tts import (
    ATTR_VOICE,
    TextToSpeechEntity,
    Voice,
    TTSAudioRequest,
    TTSAudioResponse,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import DeepgramTTSApiClient
from .const import DOMAIN
from .stream_processor import DeepgramStreamProcessor

from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Deepgram TTS platform."""
    client = hass.data[DOMAIN][config_entry.entry_id]["client"]
    processor = hass.data[DOMAIN][config_entry.entry_id]["processor"]
    async_add_entities([DeepgramTtsEntity(config_entry, client, processor)])

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Deepgram TTS platform."""
    return True

class DeepgramTtsEntity(TextToSpeechEntity):
    """Representation of a Deepgram TTS entity."""

    def __init__(self, config_entry: ConfigEntry, client: DeepgramTTSApiClient, processor: DeepgramStreamProcessor) -> None:
        """Initialize the Deepgram TTS entity."""
        self._config_entry = config_entry
        self._client = client
        self._processor = processor
        self._attr_name = "Deepgram TTS"
        self._attr_unique_id = config_entry.entry_id

        # Leer valores por defecto desde options o data
        self._default_voice = config_entry.options.get("voice", config_entry.data.get("voice", "aura-2-thalia-en"))
        if not self._default_voice or self._default_voice.strip() == "":
            self._default_voice = "aura-2-thalia-en"
        self._default_language = config_entry.options.get("language", config_entry.data.get("language", "en"))

    @property
    def default_language(self) -> str:
        """Return the default language."""
        return self._config_entry.options.get("language", self._config_entry.data.get("language", "en"))

    @property
    def supported_languages(self) -> list[str]:
        """Return list of supported languages (idiomas base únicos de los modelos)."""
        models = getattr(self._client, "_models_cache", [])
        languages = set()
        for model in models:
            for lang in model.get("languages", []):
                base = lang.split("_")[0]
                languages.add(base)
        return sorted(languages) if languages else [self.default_language]

    @property
    def supported_options(self) -> list[str]:
        """Return a list of supported options."""
        return [ATTR_VOICE]

    @property
    def default_options(self) -> dict[str, Any]:
        """Return a dict including default options."""
        voice = self._config_entry.options.get("voice", self._config_entry.data.get("voice", "aura-2-thalia-en"))
        # Ensure voice is not empty
        if not voice or voice.strip() == "":
            voice = "aura-2-thalia-en"
        return {
            ATTR_VOICE: voice
        }

    @callback
    def async_get_supported_voices(self, language: str) -> list[Voice] | None:
        """Return a list of supported voices for a language base."""
        models = getattr(self._client, "_models_cache", [])
        voices = []
        _LOGGER.debug(f"async_get_supported_voices: received language={language}")
        for model in models:
            if any(lang.split("_")[0] == language for lang in model.get("languages", [])):
                voices.append(Voice(model["canonical_name"], model["name"]))
        _LOGGER.debug(f"async_get_supported_voices: returning {len(voices)} voices for {language}: {[v.name for v in voices]}")
        return voices if voices else None

    async def async_get_tts_audio(
        self,
        message: str,
        language: str,
        options: dict[str, Any] | None = None,
    ) -> tuple[str, bytes] | None:
        """Load TTS from Deepgram."""
        # Usar la voz e idioma configurados si no se pasan opciones
        voice = (
            options.get(ATTR_VOICE)
            if options and ATTR_VOICE in options
            else self._config_entry.options.get("voice", self._config_entry.data.get("voice", "aura-2-thalia-en"))
        )
        # Ensure voice is not empty
        if not voice or voice.strip() == "":
            voice = "aura-2-thalia-en"
        language_opt = (
            options.get("language")
            if options and "language" in options
            else self._config_entry.options.get("language", self._config_entry.data.get("language", "en"))
        )
        # If voice is not set, try to find a voice matching the language
        if not voice and language_opt:
            for model in self._processor._client._models_cache or []:
                if language_opt in model.get("languages", []):
                    voice = model.get("canonical_name")
                    break
        if not voice:
            raise ServiceValidationError("No valid voice found for the requested language or configuration.")

        try:
            audio_bytes = await self._client.async_synthesize_speech(
                text=message,
                model=voice,
            )
            return "mp3", audio_bytes
        except Exception as exc:
            _LOGGER.error("Error in Deepgram TTS synthesis: %s", exc)
            raise HomeAssistantError(f"Failed to synthesize speech with Deepgram: {exc}") from exc

    async def async_stream_tts_audio(self, request: TTSAudioRequest) -> TTSAudioResponse:
        """Stream TTS audio for a message."""
        # Use the same voice selection logic as non-streaming TTS
        _LOGGER.debug(f"Streaming TTS request options: {request.options}")
        _LOGGER.debug(f"Config entry options: {self._config_entry.options}")
        _LOGGER.debug(f"Config entry data: {self._config_entry.data}")

        voice = (
            request.options.get(ATTR_VOICE)
            if request.options and ATTR_VOICE in request.options
            else self._config_entry.options.get("voice", self._config_entry.data.get("voice", "aura-2-thalia-en"))
        )
        _LOGGER.debug(f"Selected voice for streaming: {voice}")

        # Ensure voice is not empty
        if not voice or voice.strip() == "":
            voice = "aura-2-thalia-en"
            _LOGGER.debug(f"Voice was empty, using default: {voice}")

        async def message_gen() -> AsyncGenerator[str, None]:
            # Forward text chunks as the LLM produces them so the first sentence
            # can be synthesized while later sentences are still being written,
            # instead of waiting for the full message.
            if hasattr(request, "message_gen") and request.message_gen is not None:
                async for chunk in request.message_gen:
                    if chunk:
                        yield chunk

        audio_generator = self._processor.async_process_stream(message_gen(), model=voice)
        return TTSAudioResponse(extension="mp3", data_gen=audio_generator)
