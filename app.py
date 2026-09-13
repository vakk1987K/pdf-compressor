import os
import shutil
import subprocess
import uuid
import time
from pathlib import Path

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename


# =========================================================
# TELUGUTECH777 PDF COMPRESSOR API
# Strong 100 KB Target Mode
# =========================================================

app = Flask(__name__)


# =========================================================
# CONFIG
# =========================================================

MAX_UPLOAD_MB = 25
MAX_CONTENT_LENGTH = MAX_UPLOAD_MB * 1024 * 1024

app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

BASE_FOLDER = "/tmp/pdf_compressor"

os.makedirs(BASE_FOLDER, exist_ok=True)


# =========================================================
# CORS
# =========================================================

CORS(
    app,
    resources={
        r"/*": {
            "origins": "*"
        }
    },
    expose_headers=[
        "X-Original-Size",
        "X-Compressed-Size",
        "X-Reduction-Percent",
        "X-Target-Reached",
        "X-Target-KB",
        "X-Compression-Mode",
        "Content-Disposition"
    ]
)


# =========================================================
# SECURITY HEADERS
# =========================================================

@app.after_request
def security_headers(response):

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    response.headers["Cache-Control"] = (
        "no-store, no-cache, must-revalidate, max-age=0"
    )

    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    return response


# =========================================================
# HOME
# =========================================================

@app.route("/", methods=["GET"])
def home():

    return jsonify({
        "success": True,
        "status": "online",
        "name": "TeluguTech777 PDF Compressor API",
        "max_upload_mb": MAX_UPLOAD_MB,
        "features": [
            "PDF compression",
            "Low compression",
            "Recommended compression",
            "High compression",
            "Strong Target 100 KB",
            "Target 200 KB",
            "Target 500 KB",
            "Target 1 MB",
            "Custom target size"
        ]
    })


# =========================================================
# HEALTH
# =========================================================

@app.route("/health", methods=["GET"])
def health():

    try:

        result = subprocess.run(
            ["gs", "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10
        )

        if result.returncode == 0:

            return jsonify({
                "success": True,
                "status": "ok",
                "ghostscript": {
                    "installed": True,
                    "version": result.stdout.strip()
                }
            })

        return jsonify({
            "success": False,
            "status": "error",
            "ghostscript": {
                "installed": False
            }
        }), 500

    except Exception as error:

        return jsonify({
            "success": False,
            "status": "error",
            "ghostscript": {
                "installed": False
            },
            "message": str(error)
        }), 500


# =========================================================
# ERROR HANDLERS
# =========================================================

@app.errorhandler(413)
def file_too_large(error):

    return jsonify({
        "success": False,
        "error": f"Maximum upload size is {MAX_UPLOAD_MB} MB."
    }), 413


@app.errorhandler(404)
def not_found(error):

    return jsonify({
        "success": False,
        "error": "Endpoint not found."
    }), 404


@app.errorhandler(500)
def internal_error(error):

    return jsonify({
        "success": False,
        "error": "Internal server error."
    }), 500


# =========================================================
# HELPERS
# =========================================================

def get_file_size(file_path):

    try:
        return os.path.getsize(file_path)
    except Exception:
        return 0


def is_pdf_file(file_path):

    try:

        with open(file_path, "rb") as f:
            return f.read(5) == b"%PDF-"

    except Exception:

        return False


def validate_pdf_with_ghostscript(file_path):

    try:

        result = subprocess.run(
            [
                "gs",
                "-q",
                "-dNOPAUSE",
                "-dBATCH",
                "-dSAFER",
                "-sDEVICE=nullpage",
                file_path
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60
        )

        return result.returncode == 0

    except Exception:

        return False


# =========================================================
# GHOSTSCRIPT COMPRESSION
# =========================================================

def run_ghostscript(
    input_pdf,
    output_pdf,
    dpi=100,
    jpeg_quality=50,
    grayscale=False
):

    """
    Compress a PDF using Ghostscript.

    grayscale=True is used mainly for very aggressive
    100 KB compression.
    """

    command = [
        "gs",
        "-q",
        "-dNOPAUSE",
        "-dBATCH",
        "-dSAFER",

        "-sDEVICE=pdfwrite",
        "-dCompatibilityLevel=1.4",

        "-dDetectDuplicateImages=true",
        "-dCompressFonts=true",
        "-dSubsetFonts=true",
        "-dEmbedAllFonts=true",

        "-dAutoRotatePages=/None",

        # Color images
        "-dDownsampleColorImages=true",
        "-dColorImageDownsampleType=/Bicubic",
        f"-dColorImageResolution={dpi}",
        "-dAutoFilterColorImages=false",
        "-dColorImageFilter=/DCTEncode",

        # Grayscale images
        "-dDownsampleGrayImages=true",
        "-dGrayImageDownsampleType=/Bicubic",
        f"-dGrayImageResolution={dpi}",
        "-dAutoFilterGrayImages=false",
        "-dGrayImageFilter=/DCTEncode",

        # Monochrome
        "-dDownsampleMonoImages=true",
        "-dMonoImageDownsampleType=/Subsample",
        f"-dMonoImageResolution={max(dpi * 2, 50)}",

        # JPEG quality
        f"-dJPEGQ={jpeg_quality}",
    ]

    # =====================================================
    # AGGRESSIVE GRAYSCALE
    # =====================================================

    if grayscale:

        command.extend([
            "-sColorConversionStrategy=Gray",
            "-dProcessColorModel=/DeviceGray"
        ])

    command.extend([
        f"-sOutputFile={output_pdf}",
        input_pdf
    ])

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=90
    )

    if result.returncode != 0:

        raise RuntimeError(
            "Ghostscript compression failed."
        )

    if not os.path.exists(output_pdf):

        raise RuntimeError(
            "Output PDF was not created."
        )

    if get_file_size(output_pdf) <= 0:

        raise RuntimeError(
            "Output PDF is empty."
        )


# =========================================================
# STANDARD LEVELS
# =========================================================

LEVEL_SETTINGS = {

    "low": {
        "dpi": 170,
        "quality": 82
    },

    "recommended": {
        "dpi": 120,
        "quality": 65
    },

    "high": {
        "dpi": 85,
        "quality": 45
    }
}


# =========================================================
# NORMAL TARGET PROFILES
# =========================================================

def get_standard_profiles(target_kb):

    if target_kb <= 200:

        return [
            (150, 74),
            (130, 66),
            (115, 60),
            (100, 54),
            (90, 48),
            (80, 42),
            (70, 36),
            (60, 30),
            (52, 25),
            (45, 20)
        ]

    if target_kb <= 500:

        return [
            (180, 84),
            (160, 78),
            (140, 72),
            (125, 66),
            (110, 60),
            (95, 52),
            (82, 45),
            (70, 38),
            (60, 32)
        ]

    return [
        (200, 88),
        (180, 84),
        (160, 80),
        (145, 74),
        (130, 68),
        (115, 62),
        (100, 56),
        (90, 50),
        (80, 44),
        (70, 38),
        (60, 32)
    ]


# =========================================================
# SPECIAL 100 KB COMPRESSION
# =========================================================

def compress_to_100kb(
    input_pdf,
    job_folder,
    target_bytes
):

    """
    Strong 100 KB mode.

    Stage 1:
        Normal color compression.

    Stage 2:
        Aggressive grayscale compression.

    It stops as soon as the PDF becomes <= 100 KB.
    """

    original_size = get_file_size(input_pdf)

    best_file = None
    best_size = original_size

    start_time = time.time()

    # =====================================================
    # STAGE 1 - COLOR
    # =====================================================

    color_profiles = [
        (120, 58),
        (100, 50),
        (85, 42),
        (72, 34),
        (60, 27),
        (50, 21),
        (42, 17),
        (35, 13),
        (30, 10),
        (25, 8)
    ]

    for index, profile in enumerate(color_profiles, start=1):

        # avoid spending too long on Render
        if time.time() - start_time > 150:
            break

        dpi, quality = profile

        output_file = os.path.join(
            job_folder,
            f"100kb-color-{index}.pdf"
        )

        try:

            run_ghostscript(
                input_pdf,
                output_file,
                dpi=dpi,
                jpeg_quality=quality,
                grayscale=False
            )

        except Exception:

            continue

        size = get_file_size(output_file)

        if size <= 0:
            continue

        if size < best_size:
            best_size = size
            best_file = output_file

        # SUCCESS
        if size <= target_bytes:

            final_file = os.path.join(
                job_folder,
                "compressed-target.pdf"
            )

            shutil.copy2(
                output_file,
                final_file
            )

            return final_file, True, "color"


    # =====================================================
    # STAGE 2 - GRAYSCALE
    # =====================================================

    grayscale_profiles = [
        (72, 38),
        (60, 32),
        (52, 27),
        (45, 22),
        (38, 18),
        (32, 14),
        (28, 11),
        (24, 9),
        (20, 7),
        (18, 5)
    ]

    for index, profile in enumerate(
        grayscale_profiles,
        start=1
    ):

        if time.time() - start_time > 175:
            break

        dpi, quality = profile

        output_file = os.path.join(
            job_folder,
            f"100kb-gray-{index}.pdf"
        )

        try:

            run_ghostscript(
                input_pdf,
                output_file,
                dpi=dpi,
                jpeg_quality=quality,
                grayscale=True
            )

        except Exception:

            continue

        size = get_file_size(output_file)

        if size <= 0:
            continue

        if size < best_size:

            best_size = size
            best_file = output_file

        # SUCCESS
        if size <= target_bytes:

            final_file = os.path.join(
                job_folder,
                "compressed-target.pdf"
            )

            shutil.copy2(
                output_file,
                final_file
            )

            return final_file, True, "grayscale"


    # =====================================================
    # 100 KB NOT REACHED
    # Return smallest version
    # =====================================================

    final_file = os.path.join(
        job_folder,
        "compressed-target.pdf"
    )

    if best_file:

        shutil.copy2(
            best_file,
            final_file
        )

    else:

        shutil.copy2(
            input_pdf,
            final_file
        )

    return final_file, False, "maximum"


# =========================================================
# STANDARD TARGET COMPRESSION
# =========================================================

def compress_standard_target(
    input_pdf,
    job_folder,
    target_kb
):

    target_bytes = target_kb * 1024

    original_size = get_file_size(
        input_pdf
    )

    if original_size <= target_bytes:

        output_pdf = os.path.join(
            job_folder,
            "compressed-target.pdf"
        )

        shutil.copy2(
            input_pdf,
            output_pdf
        )

        return output_pdf, True, "original"


    profiles = get_standard_profiles(
        target_kb
    )

    best_file = None
    best_size = original_size

    start_time = time.time()


    for index, profile in enumerate(
        profiles,
        start=1
    ):

        if time.time() - start_time > 170:
            break

        dpi, quality = profile

        output_file = os.path.join(
            job_folder,
            f"target-{index}.pdf"
        )

        try:

            run_ghostscript(
                input_pdf,
                output_file,
                dpi=dpi,
                jpeg_quality=quality
            )

        except Exception:

            continue


        size = get_file_size(
            output_file
        )


        if size <= 0:
            continue


        if size < best_size:

            best_size = size
            best_file = output_file


        if size <= target_bytes:

            final_file = os.path.join(
                job_folder,
                "compressed-target.pdf"
            )

            shutil.copy2(
                output_file,
                final_file
            )

            return (
                final_file,
                True,
                "standard"
            )


    final_file = os.path.join(
        job_folder,
        "compressed-target.pdf"
    )


    if best_file:

        shutil.copy2(
            best_file,
            final_file
        )

    else:

        shutil.copy2(
            input_pdf,
            final_file
        )


    return final_file, False, "maximum"


# =========================================================
# TARGET ROUTER
# =========================================================

def compress_to_target(
    input_pdf,
    job_folder,
    target_kb
):

    target_bytes = (
        target_kb * 1024
    )

    original_size = get_file_size(
        input_pdf
    )


    # Already below target
    if original_size <= target_bytes:

        output_pdf = os.path.join(
            job_folder,
            "compressed-target.pdf"
        )

        shutil.copy2(
            input_pdf,
            output_pdf
        )

        return (
            output_pdf,
            True,
            "original"
        )


    # =====================================================
    # SPECIAL 100 KB MODE
    # =====================================================

    if target_kb <= 100:

        return compress_to_100kb(
            input_pdf,
            job_folder,
            target_bytes
        )


    # =====================================================
    # OTHER TARGETS
    # =====================================================

    return compress_standard_target(
        input_pdf,
        job_folder,
        target_kb
    )


# =========================================================
# LEVEL COMPRESSION
# =========================================================

def compress_by_level(
    input_pdf,
    job_folder,
    level
):

    settings = LEVEL_SETTINGS.get(
        level
    )

    if settings is None:

        raise ValueError(
            "Invalid compression level."
        )


    output_pdf = os.path.join(
        job_folder,
        f"compressed-{level}.pdf"
    )


    run_ghostscript(
        input_pdf,
        output_pdf,
        dpi=settings["dpi"],
        jpeg_quality=settings["quality"]
    )


    original_size = get_file_size(
        input_pdf
    )

    compressed_size = get_file_size(
        output_pdf
    )


    if compressed_size >= original_size:

        shutil.copy2(
            input_pdf,
            output_pdf
        )


    return output_pdf


# =========================================================
# MAIN COMPRESS ENDPOINT
# =========================================================

@app.route(
    "/compress-pdf",
    methods=["POST"]
)
def compress_pdf():

    job_id = str(uuid.uuid4())

    job_folder = os.path.join(
        BASE_FOLDER,
        job_id
    )

    os.makedirs(
        job_folder,
        exist_ok=True
    )


    try:

        # =================================================
        # UPLOAD CHECK
        # =================================================

        if "file" not in request.files:

            shutil.rmtree(
                job_folder,
                ignore_errors=True
            )

            return jsonify({
                "success": False,
                "error": "No PDF file uploaded."
            }), 400


        uploaded_file = request.files["file"]


        if (
            uploaded_file is None
            or not uploaded_file.filename
        ):

            shutil.rmtree(
                job_folder,
                ignore_errors=True
            )

            return jsonify({
                "success": False,
                "error": "Please select a PDF file."
            }), 400


        original_filename = secure_filename(
            uploaded_file.filename
        )


        if not original_filename.lower().endswith(
            ".pdf"
        ):

            shutil.rmtree(
                job_folder,
                ignore_errors=True
            )

            return jsonify({
                "success": False,
                "error": "Only PDF files are supported."
            }), 400


        # =================================================
        # SAVE FILE
        # =================================================

        input_pdf = os.path.join(
            job_folder,
            "input.pdf"
        )

        uploaded_file.save(
            input_pdf
        )


        original_size = get_file_size(
            input_pdf
        )


        if original_size <= 0:

            shutil.rmtree(
                job_folder,
                ignore_errors=True
            )

            return jsonify({
                "success": False,
                "error": "Uploaded PDF is empty."
            }), 400


        # =================================================
        # VALIDATE PDF
        # =================================================

        if not is_pdf_file(
            input_pdf
        ):

            shutil.rmtree(
                job_folder,
                ignore_errors=True
            )

            return jsonify({
                "success": False,
                "error": "Invalid PDF file."
            }), 400


        if not validate_pdf_with_ghostscript(
            input_pdf
        ):

            shutil.rmtree(
                job_folder,
                ignore_errors=True
            )

            return jsonify({
                "success": False,
                "error": (
                    "The PDF appears corrupted "
                    "or unsupported."
                )
            }), 400


        # =================================================
        # MODE
        # =================================================

        mode = request.form.get(
            "mode",
            "level"
        ).strip().lower()


        target_reached = False
        target_kb = None
        compression_mode = "standard"


        # =================================================
        # TARGET MODE
        # =================================================

        if mode == "target":

            target_value = request.form.get(
                "target_kb",
                ""
            ).strip()


            try:

                target_kb = int(
                    target_value
                )

            except Exception:

                shutil.rmtree(
                    job_folder,
                    ignore_errors=True
                )

                return jsonify({
                    "success": False,
                    "error": "Invalid target size."
                }), 400


            if target_kb < 50:

                shutil.rmtree(
                    job_folder,
                    ignore_errors=True
                )

                return jsonify({
                    "success": False,
                    "error": (
                        "Minimum target size is 50 KB."
                    )
                }), 400


            if target_kb > 20480:

                shutil.rmtree(
                    job_folder,
                    ignore_errors=True
                )

                return jsonify({
                    "success": False,
                    "error": (
                        "Maximum target is 20480 KB."
                    )
                }), 400


            (
                output_pdf,
                target_reached,
                compression_mode
            ) = compress_to_target(
                input_pdf,
                job_folder,
                target_kb
            )


        # =================================================
        # LEVEL MODE
        # =================================================

        elif mode == "level":

            level = request.form.get(
                "level",
                "recommended"
            ).strip().lower()


            if level not in [
                "low",
                "recommended",
                "high"
            ]:

                shutil.rmtree(
                    job_folder,
                    ignore_errors=True
                )

                return jsonify({
                    "success": False,
                    "error": (
                        "Invalid compression level."
                    )
                }), 400


            output_pdf = compress_by_level(
                input_pdf,
                job_folder,
                level
            )

            compression_mode = level


        else:

            shutil.rmtree(
                job_folder,
                ignore_errors=True
            )

            return jsonify({
                "success": False,
                "error": (
                    "Mode must be target or level."
                )
            }), 400


        # =================================================
        # FINAL SIZE
        # =================================================

        compressed_size = get_file_size(
            output_pdf
        )


        if compressed_size <= 0:

            raise RuntimeError(
                "Compressed PDF is empty."
            )


        # =================================================
        # NEVER RETURN LARGER RESULT
        # =================================================

        if compressed_size > original_size:

            shutil.copy2(
                input_pdf,
                output_pdf
            )

            compressed_size = original_size


        # =================================================
        # RECHECK TARGET
        # =================================================

        if (
            mode == "target"
            and target_kb is not None
        ):

            target_reached = (
                compressed_size
                <= target_kb * 1024
            )


        # =================================================
        # REDUCTION
        # =================================================

        if original_size > 0:

            reduction_percent = (
                (
                    original_size
                    - compressed_size
                )
                / original_size
            ) * 100

        else:

            reduction_percent = 0


        reduction_percent = max(
            0,
            reduction_percent
        )


        # =================================================
        # DOWNLOAD NAME
        # =================================================

        original_stem = Path(
            original_filename
        ).stem


        download_filename = (
            f"{original_stem}-compressed.pdf"
        )


        # =================================================
        # RESPONSE
        # =================================================

        response = send_file(
            output_pdf,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=download_filename
        )


        response.headers[
            "X-Original-Size"
        ] = str(original_size)


        response.headers[
            "X-Compressed-Size"
        ] = str(compressed_size)


        response.headers[
            "X-Reduction-Percent"
        ] = f"{reduction_percent:.1f}"


        response.headers[
            "X-Compression-Mode"
        ] = compression_mode


        if mode == "target":

            response.headers[
                "X-Target-Reached"
            ] = (
                "true"
                if target_reached
                else "false"
            )


            response.headers[
                "X-Target-KB"
            ] = str(target_kb)


        # =================================================
        # CLEANUP
        # =================================================

        @response.call_on_close
        def cleanup():

            shutil.rmtree(
                job_folder,
                ignore_errors=True
            )


        return response


    # =====================================================
    # TIMEOUT
    # =====================================================

    except subprocess.TimeoutExpired:

        shutil.rmtree(
            job_folder,
            ignore_errors=True
        )

        return jsonify({
            "success": False,
            "error": (
                "Compression took too long. "
                "Please try a smaller PDF."
            )
        }), 504


    # =====================================================
    # GENERAL ERROR
    # =====================================================

    except Exception as error:

        print(
            "Compression error:",
            str(error),
            flush=True
        )

        shutil.rmtree(
            job_folder,
            ignore_errors=True
        )

        return jsonify({
            "success": False,
            "error": (
                "Unable to compress this PDF. "
                "Please try another PDF."
            )
        }), 500


# =========================================================
# LOCAL RUN
# =========================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            10000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
