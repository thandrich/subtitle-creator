# Roadmap: Subtitle Creator

This roadmap outlines the evolution of the Subtitle Creator from a hardcoded script to a robust, user-friendly tool. Each step is designed to be a small, incremental change suitable for a single commit.

## Phase 1: Configuration & CLI (Adjustability)
*Goal: Remove hardcoded values and allow user-defined parameters.*

- [x] **Commit 1**: Integrate `argparse` to allow passing the input video path as a command-line argument.
- [x] **Commit 2**: Add CLI arguments for `--source-lang` and `--target-lang` (defaulting to `ja-JP` and `en`).
- [x] **Commit 3**: Implement a `config.yaml` or `.env` expansion to manage subtitle constraints (max chars, max words, min duration).
- [x] **Commit 4**: Add CLI flags for all subtitle layout parameters to allow per-run overrides.
- [x] **Commit 5**: Support directory-based processing to batch-generate subtitles for multiple videos.

## Phase 2: Reliability & Resource Management
*Goal: Ensure GCP resources are managed safely and provide better feedback.*

- [x] **Commit 6**: Migrate to Speech-to-Text V2 API and optimize configuration using the `chirp_3` model for enhanced accuracy and language support.
- [x] **Commit 7**: Add "Pre-flight" checks to validate GCP credentials and bucket access before starting audio extraction.
- [x] **Commit 8**: Implement progress tracking for the GCP Long Running Recognize operation (using `tqdm` or simple polling).
- [x] **Commit 9**: Enhance cleanup logic with signal handling (e.g., `SIGINT`) to ensure GCS blobs are deleted even if the process is aborted.
- [x] **Commit 10**: Add structured logging to a file (`pipeline.log`) to track errors and timing for each stage.

## Phase 3: Minimal User Interface
*Goal: Provide an intuitive way to set parameters without complex CLI flags.*

**Technical Recommendation: TUI (Text User Interface)**
We recommend using **Typer** (for CLI structure) and **Rich** (for the UI components). This keeps the repository "minimal" (no web server overhead) while providing an interactive, visually appealing interface with progress bars, tables, and formatted prompts.

- [ ] **Commit 11**: Refactor CLI to use `Typer` for a more interactive command structure.
- [ ] **Commit 12**: Implement `Rich` progress bars for audio extraction and upload stages.
- [ ] **Commit 13**: Add an "Interactive Mode" that prompts the user for languages and files if no arguments are provided.
- [ ] **Commit 14**: Create a status dashboard showing active GCP jobs and estimated costs/time.

## Phase 4: UX Rounding & Polish (Additional Suggestions)
*Goal: Enhance the user experience without adding significant bloat.*

- [ ] **Commit 15**: **Dry-Run Mode**: A flag to simulate the pipeline, showing how text will be chunked without calling paid APIs.
- [ ] **Commit 16**: **Multi-Format Export**: Support for `.vtt` (WebVTT) export alongside `.srt`.
- [ ] **Commit 17**: **Audio Pre-processing**: Integration of basic noise reduction or volume normalization to improve transcription accuracy.
- [ ] **Commit 18**: **Summary Report**: Output a brief summary after completion (total duration, estimated cost, word count).
