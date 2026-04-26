# 🎬 Subtitle Creator

An automated pipeline that transforms video files into professionally formatted, translated subtitles (SRT). Using Google Cloud's advanced Speech-to-Text and Translation engines, it handles everything from audio extraction to intelligent subtitle segmenting.

## ✨ Features

- **High-Accuracy Transcription**: Leverages GCP Speech-to-Text V2 (**Chirp-3** model) for precise word-level timestamps.
- **Contextual Translation**: Translates text in paragraph-sized chunks to preserve original meaning.
- **Smart Segmenting**: 
  - Prevents "flicker" by merging short subtitle blocks (min 1.2s).
  - Prefers splitting at natural punctuation boundaries.
  - Enforces professional layout constraints (max 42 chars/line, 2 lines max).
- **Modern TUI**: Interactive terminal interface with progress bars, cost estimations, and summary dashboards using `Typer` and `Rich`.

## 🛠️ Tech Stack

- **Core**: Python 3.12+
- **Media**: MoviePy
- **Cloud**: Google Cloud Platform (STT v2, Translate v2, GCS)
- **UI**: Typer & Rich
- **Dev**: uv

## 🚀 Getting Started

### 1. Prerequisites
- [uv](https://github.com/astral-sh/uv) installed.
- A Google Cloud Project with the following APIs enabled:
  - Speech-to-Text API
  - Cloud Translation API
  - Cloud Storage
- A GCS Bucket for temporary audio storage.
- Local GCP credentials configured (e.g., `gcloud auth application-default login`).

### 2. Installation
Clone the repository and install dependencies:
```bash
git clone https://github.com/your-repo/subtitle-creator.git
cd subtitle-creator
uv sync
```

### 3. Configuration
Create a `.env` file in the root directory:
```env
GCP_PROJECT_ID=your-project-id
GCP_BUCKET_NAME=your-bucket-name
GCP_REGION=us-central1
```

## 📖 Usage

### Interactive Mode (Recommended)
Simply run the script without arguments to be prompted for files and languages:
```bash
uv run python main.py
```

### CLI Mode
Process a specific file or a whole directory with custom languages:
```bash
uv run python main.py /path/to/video.mp4 --source-lang ja-JP --target-lang en
```

### Options
- `--max-words`: Max words per subtitle block.
- `--max-chars`: Max characters per line.
- `--min-duration`: Minimum visibility time for a subtitle block.
- `--punctuation-splits`: Custom punctuation marks to trigger a split.

## 🗺️ Roadmap
Check out [specs/roadmap.md](specs/roadmap.md) for planned features, including dry-run modes, multi-format exports, and audio pre-processing.

## 📄 License
MIT
