# Mission: Subtitle Creator

The Subtitle Creator is an automated pipeline designed to transform video content into professionally formatted, translated subtitle files (SRT). It bridges the gap between raw audio and readable subtitles by combining speech recognition, machine translation, and intelligent text segmenting.

## Core Functionality

- **Audio Extraction**: Automatically extracts high-quality audio from MP4 video files to prepare for transcription.
- **Speech-to-Text Transcription**: Utilizes advanced speech recognition to generate transcripts with precise word-level timestamps.
- **Contextual Translation**: Translates transcribed text while preserving the original context of complete paragraphs or segments.
- **Intelligent Subtitle Segmenting**:
    - **Time-Based Interpolation**: Maps translated words back to the original audio timeline.
    - **Micro-Block Merging**: Prevents "flicker" by ensuring subtitle blocks meet a minimum duration (1.2 seconds) for readability.
    - **Punctuation-Aware Splitting**: Prefers splitting subtitle blocks at natural sentence boundaries (e.g., periods, question marks).
- **SRT Formatting**:
    - Generates standard `.srt` files with sequential numbering and precise timestamps.
    - **Visual Constraints**: Enforces maximum character counts per line and maximum word counts per subtitle block to ensure compatibility with standard video players and human reading speeds.
- **Cloud Integration**: Manages temporary storage and processing using cloud-based storage and compute resources.

## Operational Constraints

- **Input Format**: Currently configured to process `.mp4` video files.
- **Output Format**: Produces SubRip Subtitle (`.srt`) files.
- **Source Language**: Fixed to a specific source language (currently Japanese `ja-JP` by default).
- **Target Language**: Fixed to a specific target language (currently English `en`).
- **Subtitle Layout**: 
    - Maximum 2 lines per subtitle block.
    - Maximum 42 characters per line.
    - Maximum 16 words per subtitle block.
- **Resource Management**: Requires access to Google Cloud Platform (Speech-to-Text, Translation, and Cloud Storage) and utilizes local temporary files for intermediate processing steps.
