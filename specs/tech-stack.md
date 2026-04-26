# Tech Stack: Subtitle Creator

The Subtitle Creator is built using a modern Python-based ecosystem, leveraging specialized libraries for media processing and industry-leading cloud services for machine learning tasks.

## Programming Language
- **Python 3.12+**: Utilizes modern Python features for type hinting and efficient asynchronous-like cloud operations.

## Core Libraries & Frameworks
- **MoviePy**: Used for robust video manipulation and high-fidelity audio extraction.
- **python-dotenv**: Manages environment-specific configurations and sensitive API credentials.
- **Ruff**: Employed for high-performance linting and code formatting to maintain project standards.

## Cloud Infrastructure (Google Cloud Platform)
The application relies on GCP for its heavy-lifting machine learning and storage requirements:
- **Google Cloud Speech-to-Text (v2)**: Provides the core transcription engine utilizing the **Chirp-3** model for high-accuracy multilingual transcription and word-level timing.
- **Google Cloud Translation (v2)**: Handles the contextual conversion of transcribed text into the target language.
- **Google Cloud Storage (GCS)**: Acts as a temporary staging area for audio files to facilitate long-running transcription tasks.

## Development & Dependency Management
- **uv / pyproject.toml**: Follows standard Python packaging conventions for reproducible environments and efficient dependency resolution.
