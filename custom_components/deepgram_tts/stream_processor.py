from __future__ import annotations

import asyncio
import re
import logging
from typing import AsyncIterable, AsyncGenerator

_LOGGER = logging.getLogger(__name__)

SENTENCE_SEPARATORS = "\n。.，,；;！!？?、"

def remove_incompatible_characters(text: str) -> str:
    # Deepgram accepts UTF-8, but you can customize if needed
    return text.replace('*', '')

class DeepgramStreamProcessor:
    def __init__(self, client: object) -> None:
        self._client = client

    async def _preprocess_stream(self, text_stream: AsyncIterable[str]) -> AsyncIterable[str]:
        """Clean text by removing incompatible characters and custom markers."""
        async for chunk in text_stream:
            cleaned = remove_incompatible_characters(chunk)
            yield cleaned

    def _find_sentence(self, buffer_text: str) -> tuple[str, str]:
        """
        Extract the first complete sentence from the buffer using a language-agnostic
        approach for decimal points.
        """
        if not buffer_text:
            return "", ""

        DECIMAL_PLACEHOLDER = "##DEC##"
        safe_text = re.sub(r'(\d)\.(\d)', fr'\1{DECIMAL_PLACEHOLDER}\2', buffer_text)

        # Only split if the dot is not part of a list number (e.g., "1.", "2.", etc.)
        match = re.search(r"(?<!\d)[.!?]", safe_text)
        if match:
            end_index = match.start() + 1
            sentence_part = safe_text[:end_index]
            rest_part = safe_text[end_index:]
            final_sentence = sentence_part.replace(DECIMAL_PLACEHOLDER, '.')
            final_rest = rest_part.replace(DECIMAL_PLACEHOLDER, '.')
            return final_sentence.strip(), final_rest.strip()

        max_chars = 200
        if len(safe_text) > max_chars:
            search_area = safe_text[:max_chars + 20]
            last_space_index = search_area.rfind(" ")
            if last_space_index > 0:
                sentence_part = safe_text[:last_space_index]
                rest_part = safe_text[last_space_index:]
            else:
                sentence_part = safe_text[:max_chars]
                rest_part = safe_text[max_chars:]
            final_sentence = sentence_part.replace(DECIMAL_PLACEHOLDER, '.')
            final_rest = rest_part.replace(DECIMAL_PLACEHOLDER, '.')
            return final_sentence.strip(), final_rest.strip()

        return "", buffer_text

    async def _sentence_generator(self, text_stream: AsyncIterable[str]) -> AsyncGenerator[str, None]:
        """Yield complete, speakable sentences from a text stream using smart buffering."""
        buffer = ""
        generated_sentences = 0
        count = 0
        async for chunk in text_stream:
            _LOGGER.debug("Streaming tts sentence: %s", chunk)
            count += 1
            min_len = 2 ** count * 10  # Exponential buffer growth for optimal streaming
            buffer += chunk

            # Try to find complete sentences first
            while True:
                sentence, rest = self._find_sentence(buffer)
                if sentence:
                    if re.search(r'\w', sentence):
                        generated_sentences += 1
                        yield sentence
                    buffer = rest
                else:
                    break

            # If buffer is long enough and ends with separator, yield it
            msg = buffer.strip()
            if len(msg) >= min_len:
                # Check if buffer ends with a sentence separator
                if msg and msg[-1] in SENTENCE_SEPARATORS:
                    generated_sentences += 1
                    yield msg
                    buffer = ""

        # Yield any remaining content in buffer
        if msg := buffer.strip():
            if re.search(r'\w', msg):
                generated_sentences += 1
                yield msg

        if generated_sentences == 0:
            _LOGGER.warning("No sentence was generated for synthesis from the received text.")

    async def async_process_stream(
        self, text_stream: AsyncIterable[str], model: str
    ) -> AsyncIterable[bytes]:
        """
        Split the incoming text into sentences and synthesize them sequentially,
        forwarding each audio chunk to the caller as soon as it arrives.

        A small look-ahead queue lets the next sentence be synthesized while the
        current one is still being streamed, keeping the audio pipeline full
        without buffering whole fragments in memory.
        """
        output_queue: asyncio.Queue = asyncio.Queue(maxsize=10)
        processing_task = asyncio.create_task(
            self._process_all_text(text_stream, output_queue, model)
        )

        try:
            while True:
                item = await output_queue.get()
                if item is None:
                    break
                if isinstance(item, Exception):
                    raise item
                yield item
        finally:
            if not processing_task.done():
                processing_task.cancel()
            # Drain any buffered chunks so a producer blocked on a full queue
            # (e.g. when the consumer stops early) can unwind instead of hanging.
            while not output_queue.empty():
                try:
                    output_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
            await asyncio.gather(processing_task, return_exceptions=True)

    async def _process_all_text(
        self, text_stream: AsyncIterable[str], output_queue: asyncio.Queue, model: str
    ):
        try:
            sentences_generator = self._sentence_generator(self._preprocess_stream(text_stream))
            async for sentence in sentences_generator:
                try:
                    got_audio = False
                    async for audio_chunk in self._client.async_stream_speech(
                        text=sentence,
                        model=model,
                        encoding="mp3",
                    ):
                        got_audio = True
                        await output_queue.put(audio_chunk)
                    if not got_audio:
                        _LOGGER.error("Deepgram returned empty audio for sentence: '%s'", sentence)
                except Exception as e:
                    _LOGGER.error("Error processing sentence '%s': %s", sentence[:30], e, exc_info=True)
        finally:
            await output_queue.put(None)
