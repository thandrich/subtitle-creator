import html
import math
import os
from datetime import timedelta

from dotenv import load_dotenv
from google.cloud import speech, storage
from google.cloud import translate_v2 as translate
from moviepy import VideoFileClip

load_dotenv()

# --- Configuratoin ---
VIDEO_FILE_PATH = "test/test.mp4"
AUDIO_FILE_PATH = "temp_audio.wav"
SOURCE_LANGUAGE = "de-DE"
PROJECT_ID = os.environ.get("GCP_PROJECT_ID")
BUCKET_NAME = os.environ.get("GCP_BUCKET_NAME")

# Adjustable subtitle constraints
MAX_WORDS_PER_SUBTITLE = 16
MAX_CHARS_PER_LINE = 42
PUNCTUATION_SPLITS = (".", "?", "!", ":")


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
    Takes a fully translated English block, counts words, and uses the
    German total duration to divide it into evenly timed SRT sub-blocks.
    """
    words = translated_text.split()
    if not words:
        return []

    total_duration = (end_time_delta - start_time_delta).total_seconds()
    time_per_word = total_duration / len(words)

    chunks = []
    current_chunk_words = []

    for i, word in enumerate(words):
        current_chunk_words.append(word)
        word_text = word.strip()

        reached_max = len(current_chunk_words) >= MAX_WORDS_PER_SUBTITLE
        is_sentence_end = word_text.endswith(PUNCTUATION_SPLITS)

        if reached_max or is_sentence_end:
            # Determine timings based on word index
            chunk_start_idx = i - len(current_chunk_words) + 1
            chunk_end_idx = i

            chunk_start_time = start_time_delta + timedelta(
                seconds=chunk_start_idx * time_per_word
            )
            chunk_end_time = start_time_delta + timedelta(
                seconds=(chunk_end_idx + 1) * time_per_word
            )

            chunks.append(
                {
                    "text": " ".join(current_chunk_words),
                    "start": chunk_start_time,
                    "end": chunk_end_time,
                }
            )
            current_chunk_words = []

    if current_chunk_words:
        chunk_start_idx = len(words) - len(current_chunk_words)
        chunk_end_idx = len(words) - 1

        chunk_start_time = start_time_delta + timedelta(
            seconds=chunk_start_idx * time_per_word
        )
        chunk_end_time = end_time_delta  # Hard stop at the actual end of the audio

        chunks.append(
            {
                "text": " ".join(current_chunk_words),
                "start": chunk_start_time,
                "end": chunk_end_time,
            }
        )

    return chunks


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


def main():
    print("Starting sutitle pipeline...")

    # Initialise our GCP clients
    storage_client = storage.Client(project=PROJECT_ID)
    speech_client = speech.SpeechClient()
    translate_client = translate.Client()

    # Main logic wrapped in try block to enable cleanup even upon failure
    try:
        print("\n[1/5] Extracting audio form video...")

        video = VideoFileClip(VIDEO_FILE_PATH)
        video.audio.write_audiofile(
            AUDIO_FILE_PATH,
            fps=16000,
            nbytes=2,
            codec="pcm_s16le",
            logger=None,
        )

        print("[2/5] Uploading temporary audio to Google Cloud Storage ...")

        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(AUDIO_FILE_PATH)
        blob.upload_from_filename(AUDIO_FILE_PATH)
        gcs_uri = f"gs://{BUCKET_NAME}/{AUDIO_FILE_PATH}"

        print("[3/5] Transcribing audio with timestamps (this might take a while)...")

        audio = speech.RecognitionAudio(uri=gcs_uri)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=16000,
            language_code=SOURCE_LANGUAGE,
            enable_word_time_offsets=True,
            audio_channel_count=2,
        )
        operation = speech_client.long_running_recognize(config=config, audio=audio)
        response = operation.result(timeout=600)

        print("[4/5] Translating full context and interpolating subtitle timings...")

        srt_filename = VIDEO_FILE_PATH.replace(".mp4", ".srt")
        srt_content = ""
        counter = 1

        for result in response.results:
            alternative = result.alternatives[0]

            # 1. Grab the WHOLE German paragraph and actual audio limits
            full_german_text = alternative.transcript
            paragraph_start = alternative.words[0].start_time
            paragraph_end = alternative.words[-1].end_time

            # 2. Translate the WHOLE paragraph (preserving context!)
            translation = translate_client.translate(
                full_german_text, target_language="en"
            )
            full_english_text = html.unescape(translation["translatedText"])

            # 3. Use smart interpolation to split the English words across the German timeline
            english_chunks = chunk_translated_text_by_time(
                full_english_text, paragraph_start, paragraph_end
            )

            # 4. Write SRT
            for chunk in english_chunks:
                neat_text = wrap_text_to_lines(chunk["text"])

                srt_content += f"{counter}\n"
                srt_content += f"{format_srt_time(chunk['start'])} --> {format_srt_time(chunk['end'])}\n"
                srt_content += f"{neat_text}\n\n"

                counter += 1

        with open(srt_filename, "w", encoding="utf-8") as f:
            f.write(srt_content)
            print(f"[5/5] Success! Subtitles saved to {srt_filename}")

    finally:
        print("\n--- INITIALISING CLEANUP ---")
        if os.path.exists(AUDIO_FILE_PATH):
            os.remove(AUDIO_FILE_PATH)
            print(" -> Deleted local temporary audio file.")

            try:
                bucket = storage_client.bucket(BUCKET_NAME)
                blob = bucket.blob(AUDIO_FILE_PATH)
                if blob.exists():
                    blob.delete()
                    print(f" -> Deleted {AUDIO_FILE_PATH} from Cloud Storage bucket.")
            except Exception as e:
                print(
                    f" -> Could not delete GCS file. You may need to check manually. Error: {e}"
                )

        print("Cleanup complete. Pipeline finished.")


if __name__ == "__main__":
    main()
