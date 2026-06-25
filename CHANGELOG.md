# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.3] - 2026-06-25

### Changed (latency optimizations)

Aligned the streaming path with Deepgram's [text-to-speech latency guidance](https://developers.deepgram.com/docs/text-to-speech-latency):

- **Stream after first byte**: audio is now forwarded from the HTTP response body as it arrives (`response.content.iter_any()`) instead of waiting for each sentence to be fully synthesized (`response.read()`). New `DeepgramTTSApiClient.async_stream_speech()` generator.
- **Incremental text pass-through**: LLM text chunks are forwarded to the sentence splitter as they are produced, so the first sentence is synthesized while later sentences are still being written, instead of buffering the entire message first.
- **Removed artificial synthesis delay**: dropped the 150 ms `asyncio.sleep` that preceded every sentence request.
- **Removed pydub decode/re-encode round-trip**: audio fragments are forwarded directly, which also removes the undeclared `pydub`/`ffmpeg` runtime dependency that could break streaming.

### Fixed

- Streaming no longer hangs when the consumer stops early (e.g. voice barge-in): the look-ahead queue is drained on cleanup.

## [1.0.2] - 2026-08-01

### Fixed

- **Streaming Audio Quality**: Eliminated clicks and micro-cuts in streaming TTS by completely removing audio trimming
- **Audio Transitions**: Preserved natural audio transitions between sentences for smoother playback
- **Buffer Management**: Implemented smart buffering with exponential growth for optimal streaming performance

### Added

- **Smart Sentence Detection**: Added multi-language sentence separators for better text segmentation
- **Performance Optimization**: Skip unnecessary audio processing when trimming is disabled
- **Enhanced Buffering**: Exponential buffer growth algorithm for adaptive streaming

### Changed

- **Audio Processing**: `TRIM_MS_FROM_END` reduced from 100ms to 0ms for natural audio preservation
- **Synthesis Delay**: Increased from 100ms to 150ms for better buffer synchronization
- **Text Processing**: Improved sentence generation with smart buffering and separator detection

### Technical Details

- **Stream Processor**: Completely rewrote sentence buffering algorithm in `stream_processor.py`
- **Audio Quality**: Removed all audio trimming while maintaining processing optimization
- **Multi-language Support**: Added comprehensive sentence separators for global language support
- **Performance**: Reduced unnecessary processing by conditional trimming logic

## [1.0.1] - 2025-01-10

### Fixed

- **Critical Bug Fix**: Resolved 400 Bad Request errors when using streaming TTS by adding validation to ensure model parameters are never empty
- **Voice Configuration**: Fixed streaming TTS to use the same voice selection logic as regular TTS, ensuring configured voices are respected in both modes
- **Integration Setup**: Fixed platform setup issues that were preventing proper integration loading
- **Import Error**: Removed incorrect Platform import that was causing integration configuration failures

### Added

- **Debug Logging**: Added comprehensive debug logging in streaming TTS to help troubleshoot voice selection issues
- **Input Validation**: Added multiple layers of validation to prevent empty voice/model parameters from reaching the API

### Technical Details

- **API Layer**: Enhanced `async_synthesize_speech()` with model parameter validation
- **TTS Entity**: Updated both `async_get_tts_audio()` and `async_stream_tts_audio()` methods with consistent voice selection logic
- **Integration Setup**: Fixed platform forwarding in `__init__.py` to use proper async/await pattern
- **Error Prevention**: Added fallback mechanisms to ensure TTS requests always have valid voice parameters

## [1.0.0] - 2025-08-04

### Added

- Initial release of Deepgram TTS integration
- Support for Deepgram Aura-2 text-to-speech models
- Streaming TTS support for Home Assistant 2025.7+
- Voice and language selection
- HACS compatibility
- UI-based configuration (config flow)
