<p align="center">
  <img src="docs/banner.webp" alt="GemTranscript Banner" />
</p>

<h1 align="center">GemTranscript</h1>

<p align="center">
  <a href="https://www.python.org/">
    <img src="https://img.shields.io/badge/Built%20with-Python_3.10%2B-blue?style=flat&logo=python" alt="Python" />
  </a>
  <a href="https://pypi.org/project/google-genai/">
    <img src="https://img.shields.io/badge/SDK-google__genai-orange?style=flat" alt="google-genai" />
  </a>
  <a href="https://pypi.org/project/tenacity/">
    <img src="https://img.shields.io/badge/Retry-Tenacity-green?style=flat" alt="Tenacity" />
  </a>
  <a href="https://ai.google.dev/">
    <img src="https://img.shields.io/badge/Model-Gemini_Flash-blueviolet?style=flat" alt="Gemini Flash" />
  </a>
  <a href="https://ffmpeg.org/">
    <img src="https://img.shields.io/badge/Dependency-FFmpeg-green?style=flat" alt="FFmpeg" />
  </a>
  <a href="LICENSE">
    <img src="https://img.shields.io/badge/License-MIT-yellow.svg?style=flat" alt="License: MIT" />
  </a>
</p>

<p align="center">
  High-performance batch transcription tool for audio and video files using Google Gemini Flash,
  with both a GUI and CLI, optimized for low bandwidth consumption and deterministic output.
</p>

---

## Quick Start

```bash
git clone https://github.com/roymejia2217/GemTranscript.git
cd GemTranscript
python -m venv venv
source venv/bin/activate    # Linux/macOS
# .\venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```env
GEMINI_API_KEY=your_api_key_here
```

Run with CLI or GUI:

```bash
python main.py        # CLI mode
python gui.py         # GUI mode
```

---

## Features

| Feature | Description |
|---------|-------------|
| **Gemini Flash Engine** | Supports a massive context window to process multi-hour files in a single pass |
| **Graphical Interface (GUI)** | Tkinter app with file selection, progress bar, success/failure count, and direct output folder opening |
| **Dynamic Model Resolution** | Automatically discovers available Flash models via API with an intelligent fallback chain |
| **Bandwidth Optimization** | Extracts audio from video to mono MP3 at 32kbps before upload, reducing transfer size by ~95% |
| **Multi-Format Support** | Transparently handles MP4, MOV, MKV, MP3, WAV, M4A, FLAC, OGG, AVI, WEBM, FLV, and 3GP |
| **Parallel Processing** | Configurable thread pool (default 3 workers) for concurrent file transcription |
| **Idempotent Execution** | Skips files that already have a corresponding transcription, enabling safe re-runs |
| **Unicode Name Handling** | Sanitizes file paths and uses hardlinks to work around non-ASCII character restrictions in the Google API |
| **Deterministic Output** | Fixed temperature at 0 for verbatim transcription without hallucinations or conversational metadata |
| **Automatic Cleanup** | Deletes local temporary files and remote Google File API uploads after each transcription |
| **Retry with Backoff** | Exponential backoff for transient API failures, with configurable retry count and wait limits |
| **Progress Tracking** | Progress callback with events for start, current file, file completion, and finish |

---

## Prerequisites

| Dependency | Purpose | Installation |
|------------|---------|--------------|
| **Python** 3.10+ | Runtime environment | [python.org](https://www.python.org/) |
| **FFmpeg** | Audio extraction and media duration detection | `sudo apt install ffmpeg` (Linux), `brew install ffmpeg` (macOS), [ffmpeg.org](https://ffmpeg.org/) (Windows) |
| **FFprobe** | Media metadata retrieval | Included with FFmpeg |
| **Google Gemini API Key** | Authentication for the Gemini API | [aistudio.google.com](https://aistudio.google.com/) |
| **GEMINI_MODEL_NAME** (optional) | Override for the automatic Flash model | See Model Configuration section |

---

## Installation

### Basic Installation

```bash
pip install -r requirements.txt
```

### Installation with Entry Points (global access)

```bash
pip install -e .
```

This enables the commands:

```bash
gemtranscript       # CLI
gemtranscript-gui   # GUI
```

---

## Usage

### CLI Mode

1. Place audio or video files in the `files/` directory.
2. Run the application:

```bash
python main.py
```

3. Transcriptions are saved as `.txt` files in the `output/` directory, named `{original_name}_transcription.txt`.

Files that already have a corresponding transcription are automatically skipped.

### GUI Mode

1. Launch the graphical application:

```bash
python gui.py
# or if you installed with entry points:
gemtranscript-gui
```

2. Select files using the multi-select dialog.
3. Click "Transcribe" to start processing.
4. The progress bar shows the current status.
5. When complete, click "Open Output Folder" to view the results.

The GUI validates at startup:
- That `GEMINI_API_KEY` is configured.
- That `ffprobe` is available.
- That the Gemini model can be resolved.

---

## Configuration

The `.env` file in the project root controls configuration options:

| Variable | Required | Description |
|----------|----------|-------------|
| `GEMINI_API_KEY` | Yes | Google Gemini API key. Get yours at [aistudio.google.com](https://aistudio.google.com/) |
| `GEMINI_MODEL_NAME` | No | Model name override. If not specified, the model is discovered automatically |

Example `.env`:

```env
GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL_NAME=gemini-2.0-flash
```

---

## Model Configuration

GemTranscript automatically resolves the best available Gemini Flash model.

### How It Works

1. If `GEMINI_MODEL_NAME` is set in `.env`, it is validated and used.
2. If no override is provided, dynamic discovery is performed via `client.models.list()`.
3. If discovery fails, the fallback chain is used:

```
gemini-2.5-flash -> gemini-2.0-flash -> gemini-2.0-flash-001 -> gemini-1.5-flash
```

4. The result is cached in memory to avoid repeated API calls.

### Manual Override

To force a specific model, add to `.env`:

```env
GEMINI_MODEL_NAME=gemini-2.0-flash
```

### If No Model Is Found

If resolution fails completely, a clear error is displayed indicating:

- That a valid model could not be found
- Which models were attempted
- Recommendations to check: API key, network connection, or manual configuration via `.env`

---

## Building the Executable

To create standalone executables on Linux:

```bash
./build.sh
```

This will:

1. Create a clean virtual environment `build_venv`.
2. Install dependencies and PyInstaller.
3. Build two executables: `gemtranscript` (CLI) and `gemtranscript-gui` (GUI).
4. Output the executables to `dist/`.

Build requirements:

- Python 3.10+
- PyInstaller (installed automatically by the script)
- Linux (the script uses Bash commands)

---

## Testing

The project includes a comprehensive test suite using pytest:

```bash
pip install -r requirements-dev.txt
pytest
```

Test coverage includes:

- Transcriber callbacks (progress events)
- GUI logic
- Model resolution and error handling

---

## Project Structure

```
config/
└── settings.py             # Global configuration (model, paths, limits, concurrency)
src/
├── gemini_client.py        # Gemini API client (upload, poll, transcribe, delete, retry)
├── media_processor.py      # FFmpeg operations, media detection, segment calculation
├── model_resolver.py       # Dynamic Flash model resolution via API
├── transcriber.py          # Orchestrator (batch processing, thread pool, idempotency)
└── utils.py                # Filename sanitization for API compatibility
gui.py                      # GUI entry point (tkinter)
main.py                     # CLI entry point (validation, logging, execution)
pyproject.toml              # Package configuration with entry points
build.sh                    # Build script for Linux executables
requirements.txt            # Production dependencies
requirements-dev.txt        # Development dependencies (pytest)
tests/
├── __init__.py
├── test_transcriber_callbacks.py  # Progress callback tests
├── test_gui_logic.py             # GUI logic tests
└── test_model_resolver.py        # Model resolution tests
```

Runtime directories (created automatically):

```
files/          # Input media files
output/         # Transcription files (.txt)
logs/           # Execution logs and temporary audio extractions
temp_uploads/   # Temporary hardlinks for Unicode filenames
```

---

## Credits

| Project | Description | License |
|---------|-------------|---------|
| [google-genai](https://pypi.org/project/google-genai/) | Official Google SDK for Gemini | Apache 2.0 |
| [python-dotenv](https://pypi.org/project/python-dotenv/) | Environment variable loading | BSD |
| [tenacity](https://pypi.org/project/tenacity/) | Automatic retry with backoff | Apache 2.0 |
| [pytest](https://pypi.org/project/pytest/) | Testing framework | MIT |

---

## License

MIT License. See [LICENSE](LICENSE) for details.
