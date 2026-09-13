import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename


# =========================================================
# TELUGUTECH777 PDF COMPRESSOR API
# =========================================================

app = Flask(__name__)


# =========================================================
# CONFIGURATION
# =========================================================

MAX_UPLOAD_MB = 25

MAX_CONTENT_LENGTH = MAX_UPLOAD_MB * 1024 * 1024

app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH


BASE_FOLDER = "/tmp/pdf_compressor"

os.makedirs(
    BASE_FOLDER,
    exist_ok=True
)


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
        "Content-Disposition"
    ]
)


# =========================================================
# SECURITY HEADERS
# =========================================================

@app.after_request
def add_security_headers(response):

    response.headers["X-Content-Type-Options"] = "nosniff"

    response.headers["X-Frame-Options"] = "SAMEORIGIN"

    response.headers["Referrer-Policy"] = (
        "strict-origin-when-cross-origin"
    )

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
            "Target 100 KB",
            "Target 200 KB",
            "Target 500 KB",
            "Target 1 MB",
            "Custom target size"
        ]
    })


# =========================================================
# HEALTH CHECK
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

            version = result.stdout.strip()

            return jsonify({
                "success": True,
                "status": "ok",
                "ghostscript": {
                    "installed": True,
                    "version": version
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
        "error": (
            "File is too large. "
            f"Maximum allowed size is {MAX_UPLOAD_MB} MB."
        )
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
# PDF VALIDATION
# =========================================================

def is_pdf_file(file_path):

    try:

        with open(file_path, "rb") as pdf_file:

            header = pdf_file.read(5)

            return header == b"%PDF-"

    except Exception:

        return False


def validate_pdf_with_ghostscript(file_path):

    """
    Ask Ghostscript to parse the PDF.

    This helps reject badly corrupted or invalid PDF files.
    """

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
# FILE SIZE
# =========================================================

def get_file_size(file_path):

    try:

        return os.path.getsize(file_path)

    except Exception:

        return 0


# =========================================================
# GHOSTSCRIPT COMPRESSION
# =========================================================

def run_ghostscript(
    input_pdf,
    output_pdf,
    dpi,
    jpeg_quality
):

    """
    Compress PDF using Ghostscript.

    dpi:
        Controls image resolution.

    jpeg_quality:
        Controls JPEG image quality.
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

        # -------------------------------------------------
        # COLOR IMAGES
        # -------------------------------------------------

        "-dDownsampleColorImages=true",

        "-dColorImageDownsampleType=/Bicubic",

        f"-dColorImageResolution={dpi}",

        "-dAutoFilterColorImages=false",

        "-dColorImageFilter=/DCTEncode",

        f"-dJPEGQ={jpeg_quality}",

        # -------------------------------------------------
        # GRAYSCALE IMAGES
        # -------------------------------------------------

        "-dDownsampleGrayImages=true",

        "-dGrayImageDownsampleType=/Bicubic",

        f"-dGrayImageResolution={dpi}",

        "-dAutoFilterGrayImages=false",

        "-dGrayImageFilter=/DCTEncode",

        # -------------------------------------------------
        # MONOCHROME IMAGES
        # -------------------------------------------------

        "-dDownsampleMonoImages=true",

        "-dMonoImageDownsampleType=/Subsample",

        f"-dMonoImageResolution={max(dpi * 2, 72)}",

        # -------------------------------------------------
        # OUTPUT
        # -------------------------------------------------

        f"-sOutputFile={output_pdf}",

        input_pdf
    ]


    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=180
    )


    if result.returncode != 0:

        raise RuntimeError(
            "Ghostscript compression failed."
        )


    if not os.path.exists(output_pdf):

        raise RuntimeError(
            "Compressed PDF was not created."
        )


    if get_file_size(output_pdf) <= 0:

        raise RuntimeError(
            "Compressed PDF is empty."
        )


# =========================================================
# NORMAL COMPRESSION LEVELS
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
# TARGET PROFILES
# =========================================================

def get_target_profiles(target_kb):

    """
    Smaller requested targets receive more aggressive profiles.

    The 100 KB target intentionally has additional steps.
    """


    # =====================================================
    # 100 KB
    # =====================================================

    if target_kb <= 100:

        return [

            (160, 78),
            (140, 72),
            (125, 66),
            (110, 60),
            (100, 54),
            (90, 48),
            (82, 43),
            (75, 38),
            (68, 34),
            (62, 30),
            (56, 27),
            (50, 24),
            (46, 21),
            (42, 18),
            (38, 16),
            (34, 14),
            (30, 12),
            (28, 10),
            (26, 8),
            (24, 7)
        ]


    # =====================================================
    # 200 KB
    # =====================================================

    if target_kb <= 200:

        return [

            (170, 82),
            (150, 76),
            (135, 70),
            (120, 64),
            (108, 58),
            (96, 52),
            (86, 46),
            (78, 40),
            (70, 35),
            (62, 30),
            (56, 27),
            (50, 24),
            (46, 21),
            (42, 18),
            (38, 16)
        ]


    # =====================================================
    # 500 KB
    # =====================================================

    if target_kb <= 500:

        return [

            (180, 84),
            (160, 80),
            (145, 74),
            (130, 68),
            (115, 62),
            (105, 57),
            (95, 52),
            (85, 47),
            (75, 41),
            (68, 36),
            (60, 31),
            (54, 27)
        ]


    # =====================================================
    # 1 MB OR CUSTOM LARGE TARGET
    # =====================================================

    return [

        (200, 88),
        (180, 84),
        (160, 80),
        (145, 75),
        (130, 70),
        (115, 64),
        (100, 58),
        (90, 52),
        (80, 46),
        (70, 40),
        (60, 34),
        (52, 28)
    ]


# =========================================================
# LEVEL COMPRESSION
# =========================================================

def compress_by_level(
    input_pdf,
    job_folder,
    level
):

    settings = LEVEL_SETTINGS.get(level)

    if settings is None:

        raise ValueError(
            "Invalid compression level."
        )


    output_pdf = os.path.join(
        job_folder,
        f"compressed-{level}.pdf"
    )


    run_ghostscript(
        input_pdf=input_pdf,
        output_pdf=output_pdf,
        dpi=settings["dpi"],
        jpeg_quality=settings["quality"]
    )


    original_size = get_file_size(
        input_pdf
    )

    compressed_size = get_file_size(
        output_pdf
    )


    # Do not return a larger file
    if compressed_size >= original_size:

        shutil.copy2(
            input_pdf,
            output_pdf
        )

        compressed_size = original_size


    return output_pdf


# =========================================================
# TARGET SIZE COMPRESSION
# =========================================================

def compress_to_target(
    input_pdf,
    job_folder,
    target_kb
):

    """
    Try progressively stronger compression until the target
    is reached.

    Returns:
        output_path
        target_reached
    """


    target_bytes = (
        int(target_kb) * 1024
    )


    original_size = get_file_size(
        input_pdf
    )


    # -----------------------------------------------------
    # Original already meets target
    # -----------------------------------------------------

    if original_size <= target_bytes:

        output_pdf = os.path.join(
            job_folder,
            "compressed-target.pdf"
        )

        shutil.copy2(
            input_pdf,
            output_pdf
        )

        return output_pdf, True


    profiles = get_target_profiles(
        target_kb
    )


    best_file = None

    best_size = original_size


    # =====================================================
    # TRY EACH PROFILE
    # =====================================================

    for attempt_number, profile in enumerate(
        profiles,
        start=1
    ):

        dpi, quality = profile


        attempt_file = os.path.join(
            job_folder,
            f"attempt-{attempt_number}.pdf"
        )


        try:

            run_ghostscript(
                input_pdf=input_pdf,
                output_pdf=attempt_file,
                dpi=dpi,
                jpeg_quality=quality
            )

        except Exception:

            continue


        attempt_size = get_file_size(
            attempt_file
        )


        if attempt_size <= 0:

            continue


        # -------------------------------------------------
        # Remember smallest result
        # -------------------------------------------------

        if attempt_size < best_size:

            best_size = attempt_size

            best_file = attempt_file


        # -------------------------------------------------
        # TARGET REACHED
        # -------------------------------------------------

        if attempt_size <= target_bytes:

            final_file = os.path.join(
                job_folder,
                "compressed-target.pdf"
            )


            shutil.copy2(
                attempt_file,
                final_file
            )


            return final_file, True


    # =====================================================
    # TARGET NOT REACHED
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


    return final_file, False


# =========================================================
# COMPRESS PDF ENDPOINT
# =========================================================

@app.route(
    "/compress-pdf",
    methods=["POST"]
)
def compress_pdf():

    job_id = str(
        uuid.uuid4()
    )


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
        # FILE CHECK
        # =================================================

        if "file" not in request.files:

            shutil.rmtree(
                job_folder,
                ignore_errors=True
            )

            return jsonify({
                "success": False,
                "error": "No PDF file was uploaded."
            }), 400


        uploaded_file = request.files["file"]


        if (
            uploaded_file is None or
            uploaded_file.filename is None or
            uploaded_file.filename.strip() == ""
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
        # SAVE UPLOAD
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
        # FILE SIGNATURE
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
                "error": "The uploaded file is not a valid PDF."
            }), 400


        # =================================================
        # GHOSTSCRIPT VALIDATION
        # =================================================

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
                    "The PDF appears to be corrupted "
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
                        "Maximum target size is 20480 KB."
                    )
                }), 400


            output_pdf, target_reached = (
                compress_to_target(
                    input_pdf=input_pdf,
                    job_folder=job_folder,
                    target_kb=target_kb
                )
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
                        "Compression level must be "
                        "low, recommended or high."
                    )
                }), 400


            output_pdf = compress_by_level(
                input_pdf=input_pdf,
                job_folder=job_folder,
                level=level
            )


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
        # FINAL FILE CHECK
        # =================================================

        if not os.path.exists(
            output_pdf
        ):

            raise RuntimeError(
                "Compressed PDF was not created."
            )


        compressed_size = get_file_size(
            output_pdf
        )


        if compressed_size <= 0:

            raise RuntimeError(
                "Compressed PDF is empty."
            )


        # =================================================
        # NEVER RETURN A FILE BIGGER THAN ORIGINAL
        # =================================================

        if compressed_size > original_size:

            shutil.copy2(
                input_pdf,
                output_pdf
            )

            compressed_size = original_size


            if (
                mode == "target" and
                original_size <= target_kb * 1024
            ):

                target_reached = True


        # =================================================
        # CALCULATE REDUCTION
        # =================================================

        if original_size > 0:

            reduction_percent = (
                (
                    original_size -
                    compressed_size
                )
                /
                original_size
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
        # SEND FILE
        # =================================================

        response = send_file(
            output_pdf,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=download_filename
        )


        # =================================================
        # CUSTOM HEADERS
        # =================================================

        response.headers[
            "X-Original-Size"
        ] = str(
            original_size
        )


        response.headers[
            "X-Compressed-Size"
        ] = str(
            compressed_size
        )


        response.headers[
            "X-Reduction-Percent"
        ] = (
            f"{reduction_percent:.1f}"
        )


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
            ] = str(
                target_kb
            )


        # =================================================
        # CLEAN TEMP FILES AFTER RESPONSE
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
                "PDF compression took too long. "
                "Please try a smaller PDF."
            )
        }), 504


    # =====================================================
    # OTHER ERROR
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
# RUN LOCALLY
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
