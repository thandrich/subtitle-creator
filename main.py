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


def format_srt_time(time_delta):
    """Converts a timedelta onject into the standard SRT timestamp format."""
    total_seconds = time_delta.total_seconds()
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = int(total_seconds % 60)
    miliseconds = int((total_seconds - int(total_seconds)) * 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{miliseconds:03}"


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

        print("[4/5] Translating text and generating SRT file...")

        srt_filename = VIDEO_FILE_PATH.replace(".mp4", ".srt")
        srt_content = ""
        counter = 1

        for result in response.results:
            alternative = result.alternatives[0]
            original_text = alternative.transcript
            translation = translate_client.translate(
                original_text, target_language="en"
            )
            english_text = translation["translatedText"]
            start_time = alternative.words[0].start_time
            end_time = alternative.words[-1].end_time

            srt_content += f"{counter}\n"
            srt_content += (
                f"{format_srt_time(start_time)} --> {format_srt_time(end_time)}\n"
            )
            srt_content += f"{english_text}\n\n"

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
