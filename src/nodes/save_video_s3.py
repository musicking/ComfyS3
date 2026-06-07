import os
from urllib.parse import quote

import folder_paths
from comfy.cli_args import args
from comfy_api.latest import Types

from ..client_s3 import get_s3_instance, normalize_s3_key

S3_INSTANCE = get_s3_instance()


def _video_container_options():
    try:
        return Types.VideoContainer.as_input()
    except Exception:
        return ["auto", "mp4", "webm", "mkv", "gif"]


def _video_codec_options():
    try:
        return Types.VideoCodec.as_input()
    except Exception:
        return ["auto", "h264", "h265", "vp9", "av1", "prores"]


def _video_extension(format_name):
    try:
        return Types.VideoContainer.get_extension(format_name)
    except Exception:
        return "mp4" if format_name == "auto" else format_name


def _build_http_url(endpoint_url, bucket_name, s3_key):
    if not endpoint_url:
        return ""
    quoted_key = quote(s3_key.replace("\\", "/"), safe="/")
    return f"{endpoint_url.rstrip('/')}/{bucket_name}/{quoted_key}"


class SaveVideoS3:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("VIDEO",),
                "filename_prefix": ("STRING", {"default": "video/ComfyUI"}),
                "format": (_video_container_options(), {"default": "auto"}),
                "codec": (_video_codec_options(), {"default": "auto"}),
                "s3_folder": ("STRING", {"default": os.getenv("S3_OUTPUT_DIR", "output")}),
                "delete_local": (["false", "true"],),
            },
            "hidden": {
                "prompt": "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO",
            },
        }

    CATEGORY = "ComfyS3"
    OUTPUT_NODE = True
    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("s3_path", "http_url", "local_path")
    FUNCTION = "save_video_to_s3"

    def save_video_to_s3(
        self,
        video,
        filename_prefix="video/ComfyUI",
        format="auto",
        codec="auto",
        s3_folder="output",
        delete_local="false",
        prompt=None,
        extra_pnginfo=None,
    ):
        width, height = video.get_dimensions()
        full_output_folder, filename, counter, subfolder, _ = folder_paths.get_save_image_path(
            filename_prefix,
            folder_paths.get_output_directory(),
            width,
            height,
        )

        file = f"{filename}_{counter:05}_.{_video_extension(format)}"
        local_path = os.path.join(full_output_folder, file)

        saved_metadata = None
        if not args.disable_metadata:
            metadata = {}
            if extra_pnginfo is not None:
                metadata.update(extra_pnginfo)
            if prompt is not None:
                metadata["prompt"] = prompt
            if metadata:
                saved_metadata = metadata

        video.save_to(
            local_path,
            format=Types.VideoContainer(format),
            codec=codec,
            metadata=saved_metadata,
        )

        s3_key = normalize_s3_key(s3_folder, subfolder, file)
        uploaded_key = S3_INSTANCE.upload_file(local_path, s3_key)
        result_key = uploaded_key or s3_key
        http_url = _build_http_url(S3_INSTANCE.endpoint_url, S3_INSTANCE.bucket_name, result_key)

        if delete_local == "true" and os.path.exists(local_path):
            os.remove(local_path)

        return {
            "ui": {
                "s3_paths": [result_key],
                "http_urls": [http_url],
                "local_paths": [local_path],
            },
            "result": (result_key, http_url, local_path),
        }
