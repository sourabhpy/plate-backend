import os
import shutil
import subprocess
import tempfile

MAX_MEDIA_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5MB
MAX_AUDIO_ANALYSIS_DURATION_SECONDS = 60.0  # 1 minute (60 seconds)


VIDEO_EXTENSIONS = {
    ".mp4",
    ".m4v",
    ".mov",
    ".avi",
    ".mkv",
    ".wmv",
    ".flv",
    ".3gp",
    ".3g2",
    ".ogv",
    ".ts",
    ".mts",
    ".m2ts",
    ".vob",
    ".divx",
    ".mpg",
    ".mpeg",
    ".asf",
    ".rm",
    ".rmvb",
}


def is_video_file(file_obj):
    """
    Detects if a file or UploadedFile is a video by extension, MIME type,
    or video stream inspection for containers like webm.
    """
    if not file_obj:
        return False

    name = getattr(file_obj, "name", "") or ""
    ext = os.path.splitext(name)[1].lower()
    content_type = (getattr(file_obj, "content_type", "") or "").lower()

    if content_type.startswith("video/"):
        return True

    if ext in VIDEO_EXTENSIONS:
        return True

    # For .webm, check if declared as video or inspect video stream
    if ext == ".webm":
        if "video" in content_type:
            return True
        if "audio" in content_type:
            return False
        return _has_video_stream(file_obj)

    return False


def _has_video_stream(file_obj):
    """
    Checks with ffprobe if the file contains a video stream.
    """
    cleanup = False
    path = None
    if isinstance(file_obj, str):
        path = file_obj
    elif hasattr(file_obj, "temporary_file_path"):
        try:
            path = file_obj.temporary_file_path()
        except Exception:
            path = None

    if not path:
        suffix = os.path.splitext(getattr(file_obj, "name", "") or "")[1] or ".webm"
        tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        pos = file_obj.tell() if hasattr(file_obj, "tell") else 0
        try:
            file_obj.seek(0)
            chunks = file_obj.chunks() if hasattr(file_obj, "chunks") else [file_obj.read()]
            for chunk in chunks:
                tmp.write(chunk)
            tmp.close()
            path = tmp.name
            cleanup = True
        finally:
            try:
                file_obj.seek(pos)
            except Exception:
                pass

    try:
        candidate_bins = [
            shutil.which("ffprobe"),
            "/opt/homebrew/bin/ffprobe",
            "/usr/local/bin/ffprobe",
            "/usr/bin/ffprobe",
        ]
        for ffprobe_bin in candidate_bins:
            if not ffprobe_bin or not os.path.exists(ffprobe_bin):
                continue
            try:
                res = subprocess.run(
                    [
                        ffprobe_bin,
                        "-v",
                        "error",
                        "-select_streams",
                        "v:0",
                        "-show_entries",
                        "stream=codec_type",
                        "-of",
                        "default=noprint_wrappers=1:nokey=1",
                        path,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if res.returncode == 0 and res.stdout.strip():
                    return True
                return False
            except Exception:
                pass
        return False
    finally:
        if cleanup and path and os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass


def validate_not_video(file_obj):
    """
    Validates that file_obj is not a video file.
    Returns (True, None) if valid, or (False, error_message) if invalid.
    """
    if not file_obj:
        return True, None
    if is_video_file(file_obj):
        return False, "Video files are not allowed for upload."
    return True, None


def validate_max_file_size(file_obj, max_size=MAX_MEDIA_FILE_SIZE_BYTES, label="File"):
    """
    Validates that file_obj.size does not exceed max_size.
    Returns (True, None) if valid, or (False, error_message) if invalid.
    """
    if not file_obj:
        return True, None
    if getattr(file_obj, "size", 0) > max_size:
        max_mb = int(max_size / (1024 * 1024))
        return False, f"{label} size exceeds the {max_mb}MB limit. Please upload a smaller file."
    return True, None


def get_audio_duration_seconds(file_obj):
    """
    Calculates duration in seconds of an audio file path or UploadedFile.
    Uses mutagen and ffprobe. Returns float or None.
    """
    if not file_obj:
        return None

    cleanup = False
    path = None
    if isinstance(file_obj, str):
        path = file_obj
    elif hasattr(file_obj, "temporary_file_path"):
        try:
            path = file_obj.temporary_file_path()
        except Exception:
            path = None

    if not path:
        suffix = os.path.splitext(getattr(file_obj, "name", "") or "")[1] or ".webm"
        tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        pos = file_obj.tell() if hasattr(file_obj, "tell") else 0
        try:
            file_obj.seek(0)
            chunks = file_obj.chunks() if hasattr(file_obj, "chunks") else [file_obj.read()]
            for chunk in chunks:
                tmp.write(chunk)
            tmp.close()
            path = tmp.name
            cleanup = True
        finally:
            try:
                file_obj.seek(pos)
            except Exception:
                pass

    try:
        # 1. Try mutagen
        try:
            import mutagen

            audio = mutagen.File(path)
            if audio is not None and getattr(audio, "info", None) is not None:
                length = getattr(audio.info, "length", None)
                if length is not None and length > 0:
                    return float(length)
        except Exception:
            pass

        # 2. Try ffprobe
        candidate_bins = [
            shutil.which("ffprobe"),
            "/opt/homebrew/bin/ffprobe",
            "/usr/local/bin/ffprobe",
            "/usr/bin/ffprobe",
        ]
        for ffprobe_bin in candidate_bins:
            if not ffprobe_bin or not os.path.exists(ffprobe_bin):
                continue
            try:
                res = subprocess.run(
                    [
                        ffprobe_bin,
                        "-v",
                        "error",
                        "-show_entries",
                        "format=duration",
                        "-of",
                        "default=noprint_wrappers=1:nokey=1",
                        path,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if res.returncode == 0 and res.stdout.strip():
                    return float(res.stdout.strip())
            except Exception:
                pass

        return None
    finally:
        if cleanup and path and os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass
