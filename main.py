import argparse
import html
import logging
import os
import signal
import sys
import time
from datetime import timedelta

from dotenv import load_dotenv
from google.api_core.client_options import ClientOptions
from google.cloud import speech_v2 as speech
from google.cloud import storage
from google.cloud import translate_v2 as translate
from google.cloud.speech_v2.types import cloud_speech
from moviepy import VideoFileClip
from tqdm import tqdm

load_dotenv()

# --- Configuration ---
AUDIO_FILE_PATH = "temp_audio.wav"
PROJECT_ID = os.environ.get("GCP_PROJECT_ID")
BUCKET_NAME = os.environ.get("GCP_BUCKET_NAME")
GCP_REGION = os.environ.get("GCP_REGION", "us-central1")

# Global variables for cleanup in signal handler
GLOBAL_STORAGE_CLIENT = None
CURRENT_GCS_BLOB_NAME = None


# Adjustable subtitle constraints
MAX_WORDS_PER_SUBTITLE = int(os.environ.get("MAX_WORDS_PER_SUBTITLE", 16))
MAX_CHARS_PER_LINE = int(os.environ.get("MAX_CHARS_PER_LINE", 42))
MIN_DURATION = float(os.environ.get("MIN_DURATION", 1.2))
PUNCTUATION_SPLITS = tuple(os.environ.get("PUNCTUATION_SPLITS", ".,?,!,:").split(","))


def cleanup():
    """Removes local and remote temporary files."""
    logging.info("\n--- INITIALISING CLEANUP ---")
    if os.path.exists(AUDIO_FILE_PATH):
        try:
            os.remove(AUDIO_FILE_PATH)
            logging.info(" -> Deleted local temporary audio file.")
        except Exception as e:
            logging.warning(f" -> Could not delete local file: {e}")

    if GLOBAL_STORAGE_CLIENT and CURRENT_GCS_BLOB_NAME:
        try:
            bucket = GLOBAL_STORAGE_CLIENT.bucket(BUCKET_NAME)
            blob = bucket.blob(CURRENT_GCS_BLOB_NAME)
            if blob.exists():
                blob.delete()
                logging.info(
                    f" -> Deleted {CURRENT_GCS_BLOB_NAME} from Cloud Storage bucket."
                )
        except Exception as e:
            logging.warning(
                f" -> Could not delete GCS file. You may need to check manually. Error: {e}"
            )
    logging.info("Cleanup complete.")


def signal_handler(sig, frame):
    """Handles interruption signals to ensure cleanup."""
    logging.info(f"\nProcess interrupted (signal {sig}).")
    cleanup()
    sys.exit(0)


def format_srt_time(time_delta):
    """Converts a timedelta onject into the standard SRT timestamp format."""
    total_seconds = time_delta.total_seconds()
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = int(total_seconds % 60)
    miliseconds = int((total_seconds - int(total_seconds)) * 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{miliseconds:03}"


def chunk_translated_text_by_time(translated_text, start_time_delta, end_time_delta):
    """
    Groups English words into bite-sized SRT sub-blocks based on timeline interpolation,
    and intelligently merges micro-blocks (less than 1.2s) to prevent unreadable single-word flicker.
    """
    words = translated_text.split()
    if not words:
        return []

    total_duration = (end_time_delta - start_time_delta).total_seconds()
    time_per_word = total_duration / len(words)

    raw_chunks = []
    current_chunk_words = []

    # --- Phase 1: Build Raw Chunks (Your existing logic) ---
    for i, word in enumerate(words):
        current_chunk_words.append(word)
        word_text = word.strip()

        reached_max = len(current_chunk_words) >= MAX_WORDS_PER_SUBTITLE
        is_sentence_end = word_text.endswith(PUNCTUATION_SPLITS)

        if reached_max or is_sentence_end:
            chunk_start_idx = i - len(current_chunk_words) + 1
            chunk_end_idx = i

            chunk_start_time = start_time_delta + timedelta(
                seconds=chunk_start_idx * time_per_word
            )
            chunk_end_time = start_time_delta + timedelta(
                seconds=(chunk_end_idx + 1) * time_per_word
            )

            raw_chunks.append(
                {
                    "text": " ".join(current_chunk_words),
                    "start": chunk_start_time,
                    "end": chunk_end_time,
                }
            )
            current_chunk_words = []

    if current_chunk_words:
        chunk_start_idx = len(words) - len(current_chunk_words)
        chunk_start_time = start_time_delta + timedelta(
            seconds=chunk_start_idx * time_per_word
        )
        raw_chunks.append(
            {
                "text": " ".join(current_chunk_words),
                "start": chunk_start_time,
                "end": end_time_delta,
            }
        )

    if not raw_chunks:
        return []

    merged_chunks = []
    i = 0

    while i < len(raw_chunks):
        current = raw_chunks[i]
        duration = (current["end"] - current["start"]).total_seconds()

        # If it's too short, let's see if we can merge it
        if duration < MIN_DURATION:
            if i == len(raw_chunks) - 1 and len(merged_chunks) > 0:
                merged_chunks[-1]["text"] += " " + current["text"]
                merged_chunks[-1]["end"] = current["end"]
                i += 1
                continue

            elif i + 1 < len(raw_chunks):
                next_chunk = raw_chunks[i + 1]
                next_chunk["text"] = current["text"] + " " + next_chunk["text"]
                next_chunk["start"] = current["start"]  # Absorb the time
                # We do not push current to merged_chunks; it gets absorbed by next loop
                i += 1
                continue

            else:
                current["end"] = current["start"] + timedelta(seconds=MIN_DURATION)

        merged_chunks.append(current)
        i += 1

    return merged_chunks


def wrap_text_to_lines(text, max_chars=MAX_CHARS_PER_LINE):
    """
    Intelligently splits a string into two lines (max 2 lines for SRT readability)
    without breaking words in half.
    """
    words = text.split()
    lines = []
    current_line = []
    current_length = 0

    for word in words:
        if current_length + len(word) + 1 > max_chars and current_line:
            lines.append(" ".join(current_line))
            current_line = [word]
            current_length = len(word)
        else:
            current_line.append(word)
            current_length += len(word) + 1

    if current_line:
        lines.append(" ".join(current_line))

    # Join the lines using standard newline characters
    return "\n".join(lines)


def process_video(
    video_file_path,
    source_lang,
    target_lang,
    storage_client,
    speech_client,
    translate_client,
):
    """Processes a single video file through the subtitle pipeline."""
    global CURRENT_GCS_BLOB_NAME
    # Main logic wrapped in try block to enable cleanup even upon failure
    try:
        logging.info(f"\nProcessing: {video_file_path}")
        logging.info("[1/5] Extracting audio form video...")

        video = VideoFileClip(video_file_path)
        video.audio.write_audiofile(
            AUDIO_FILE_PATH,
            fps=16000,
            nbytes=2,
            codec="pcm_s16le",
            logger=None,
        )

        logging.info("[2/5] Uploading temporary audio to Google Cloud Storage ...")

        CURRENT_GCS_BLOB_NAME = (
            os.path.basename(video_file_path) + "_" + AUDIO_FILE_PATH
        )
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(CURRENT_GCS_BLOB_NAME)
        blob.upload_from_filename(AUDIO_FILE_PATH)
        gcs_uri = f"gs://{BUCKET_NAME}/{CURRENT_GCS_BLOB_NAME}"

        logging.info(
            "[3/5] Transcribing audio with timestamps (this might take a while)..."
        )

        config = cloud_speech.RecognitionConfig(
            explicit_decoding_config=cloud_speech.ExplicitDecodingConfig(
                encoding=cloud_speech.ExplicitDecodingConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=16000,
                audio_channel_count=2,
            ),
            model="chirp_3",
            language_codes=[source_lang],
            features=cloud_speech.RecognitionFeatures(
                enable_word_time_offsets=True,
                enable_automatic_punctuation=True,
                diarization_config=cloud_speech.SpeakerDiarizationConfig(
                    min_speaker_count=1,
                    max_speaker_count=6,
                ),
            ),
        )

        request = cloud_speech.BatchRecognizeRequest(
            recognizer=f"projects/{PROJECT_ID}/locations/{GCP_REGION}/recognizers/_",
            config=config,
            files=[cloud_speech.BatchRecognizeFileMetadata(uri=gcs_uri)],
            recognition_output_config=cloud_speech.RecognitionOutputConfig(
                inline_output_config=cloud_speech.InlineOutputConfig(),
            ),
        )

        operation = speech_client.batch_recognize(request=request)

        # Progress tracking for the LRO
        with tqdm(desc="Transcribing", unit="s", total=None) as pbar:
            while not operation.done():
                time.sleep(1)
                pbar.update(1)

        response = operation.result(timeout=3600)

        logging.info(
            "[4/5] Translating full context and interpolating subtitle timings..."
        )

        file_result = response.results[gcs_uri]
        if file_result.error.code:
            raise Exception(f"STT Error: {file_result.error.message}")

        srt_filename = video_file_path.rsplit(".", 1)[0] + ".srt"
        srt_content = ""
        counter = 1

        for result in file_result.inline_result.transcript.results:
            if not result.alternatives:
                continue

            alternative = result.alternatives[0]
            if not alternative.words:
                continue

            # 1. Grab the WHOLE transcript and actual audio limits
            full_text = alternative.transcript
            paragraph_start = alternative.words[0].start_offset
            paragraph_end = alternative.words[-1].end_offset

            # 2. Translate the WHOLE paragraph (preserving context!)
            translation = translate_client.translate(
                full_text, target_language=target_lang
            )
            full_translated_text = html.unescape(translation["translatedText"])

            # 3. Use smart interpolation to split the words across the timeline
            chunks = chunk_translated_text_by_time(
                full_translated_text, paragraph_start, paragraph_end
            )

            # 4. Write SRT
            for chunk in chunks:
                neat_text = wrap_text_to_lines(chunk["text"])

                srt_content += f"{counter}\n"
                srt_content += f"{format_srt_time(chunk['start'])} --> {format_srt_time(chunk['end'])}\n"
                srt_content += f"{neat_text}\n\n"

                counter += 1

        with open(srt_filename, "w", encoding="utf-8") as f:
            f.write(srt_content)
            logging.info(f"[5/5] Success! Subtitles saved to {srt_filename}")

    finally:
        cleanup()
        CURRENT_GCS_BLOB_NAME = None


def pre_flight_checks(storage_client):
    """Validates GCP configuration and bucket access before starting."""
    logging.info("[0/5] Running pre-flight checks...")
    if not PROJECT_ID:
        raise ValueError("GCP_PROJECT_ID not set in environment.")
    if not BUCKET_NAME:
        raise ValueError("GCP_BUCKET_NAME not set in environment.")

    try:
        storage_client.get_bucket(BUCKET_NAME)
        logging.info(f" -> Access to bucket '{BUCKET_NAME}' verified.")
    except Exception as e:
        raise RuntimeError(f"Could not access GCS bucket '{BUCKET_NAME}': {e}")


def main():
    global MAX_WORDS_PER_SUBTITLE, MAX_CHARS_PER_LINE, MIN_DURATION, PUNCTUATION_SPLITS
    global GLOBAL_STORAGE_CLIENT

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler("pipeline.log"),
            logging.StreamHandler(sys.stdout),
        ],
    )

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    parser = argparse.ArgumentParser(description="Subtitle Creator Pipeline")

    parser.add_argument(
        "input_path",
        help="Path to an MP4 video file or a directory containing MP4 files",
    )
    parser.add_argument(
        "--source-lang",
        default="ja-JP",
        help="Source language code (default: ja-JP)",
    )
    parser.add_argument(
        "--target-lang",
        default="en",
        help="Target language code (default: en)",
    )
    parser.add_argument(
        "--max-words",
        type=int,
        default=MAX_WORDS_PER_SUBTITLE,
        help=f"Max words per subtitle block (default: {MAX_WORDS_PER_SUBTITLE})",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=MAX_CHARS_PER_LINE,
        help=f"Max characters per line (default: {MAX_CHARS_PER_LINE})",
    )
    parser.add_argument(
        "--min-duration",
        type=float,
        default=MIN_DURATION,
        help=f"Min duration for a subtitle block in seconds (default: {MIN_DURATION})",
    )
    parser.add_argument(
        "--punctuation-splits",
        default=".,?,!,:",
        help="Comma-separated punctuation marks to split on (default: .,?,!,:)",
    )
    args = parser.parse_args()

    input_path = args.input_path
    source_lang = args.source_lang
    target_lang = args.target_lang

    # Override globals with CLI arguments for this run
    MAX_WORDS_PER_SUBTITLE = args.max_words
    MAX_CHARS_PER_LINE = args.max_chars
    MIN_DURATION = args.min_duration
    PUNCTUATION_SPLITS = tuple(args.punctuation_splits.split(","))

    logging.info("Starting sutitle pipeline...")

    # Initialise our GCP clients
    storage_client = storage.Client(project=PROJECT_ID)
    GLOBAL_STORAGE_CLIENT = storage_client
    speech_client = speech.SpeechClient(
        client_options=ClientOptions(
            api_endpoint=f"{GCP_REGION}-speech.googleapis.com",
        )
    )
    translate_client = translate.Client()

    # Run pre-flight checks
    try:
        pre_flight_checks(storage_client)
    except Exception as e:
        logging.error(f"Pre-flight check failed: {e}")
        return

    # Determine input files
    if os.path.isdir(input_path):
        video_files = [
            os.path.join(input_path, f)
            for f in os.listdir(input_path)
            if f.lower().endswith(".mp4")
        ]
        video_files.sort()
        logging.info(f"Found {len(video_files)} MP4 files in directory: {input_path}")
    elif os.path.isfile(input_path):
        video_files = [input_path]
    else:
        logging.error(f"Error: {input_path} is not a valid file or directory.")
        return

    for video_file in video_files:
        try:
            process_video(
                video_file,
                source_lang,
                target_lang,
                storage_client,
                speech_client,
                translate_client,
            )
        except Exception as e:
            logging.exception(f"Failed to process {video_file}: {e}")

    logging.info("\nAll tasks completed.")


if __name__ == "__main__":
    main()
