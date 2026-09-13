import os
import shutil
import subprocess
import time
import uuid

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename


# =========================================================
# FLASK APP
# =========================================================

app = Flask(__name__)

MAX_FILE_SIZE = 25 * 1024 * 1024
BASE_FOLDER = "/tmp/pdf_compressor"

app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE

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
        "X-Compression-Level"
    ]
)


# =========================================================
# SECURITY HEADERS
# =========================================================

@app.after_request
def add_security_headers(response):

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"

    return response


# =========================================================
# LEVEL COMPRESSION
#
# LOW:
# Better quality / lighter compression
#
# RECOMMENDED:
# Balanced quality / medium compression
#
# HIGH:
# Strong compression
# =========================================================

LEVEL_PROFILES = {

    "low": {
        "dpi": 170,
        "quality": 82
    },

    "recommended": {
        "dpi": 110,
        "quality": 55
    },

    "high": {
        "dpi": 72,
        "quality": 32
    }

}


# =========================================================
# NORMAL TARGET SIZE PROFILES
# =========================================================

TARGET_PROFILES = [

    (180, 82),
    (160, 76),
    (140, 70),
    (120, 62),
    (105, 55),
    (90, 47),
    (80, 40),
    (72, 34),
    (60, 27),
    (50, 21),
    (42, 17),
    (35, 13),
    (30, 10)

]


# =========================================================
# STRONG <= 100 KB COLOR PROFILES
# =========================================================

COLOR_100KB_PROFILES = [

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


# =========================================================
# STRONG <= 100 KB GRAYSCALE PROFILES
# =========================================================

GRAYSCALE_100KB_PROFILES = [

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


# =========================================================
# HELPERS
# =========================================================

def get_file_size(path):

    try:
        return os.path.getsize(path)

    except Exception:
        return 0


def calculate_reduction(original_size, compressed_size):

    if original_size <= 0:
        return 0.0

    reduction = (
        1 -
        (compressed_size / original_size)
    ) * 100

    return max(
        0.0,
        round(reduction, 1)
    )


def is_pdf(filename):

    return bool(
        filename and
        filename.lower().endswith(".pdf")
    )


# =========================================================
# GHOSTSCRIPT
# =========================================================

def run_ghostscript(
    input_pdf,
    output_pdf,
    dpi,
    jpeg_quality,
    grayscale=False
):

    command = [

        "gs",

        "-q",

        "-dNOPAUSE",
        "-dBATCH",
        "-dSAFER",

        "-sDEVICE=pdfwrite",

        "-dCompatibilityLevel=1.4",

        "-dDetectDuplicateImages=true",

        # Force JPEG / JPX recompression
        "-dPassThroughJPEGImages=false",
        "-dPassThroughJPXImages=false",

        "-dEncodeColorImages=true",
        "-dEncodeGrayImages=true",

        # Fonts
        "-dCompressFonts=true",
        "-dSubsetFonts=true",
        "-dEmbedAllFonts=true",

        "-dAutoRotatePages=/None",

        # =================================================
        # COLOR IMAGE COMPRESSION
        # =================================================

        "-dDownsampleColorImages=true",

        "-dColorImageDownsampleType=/Bicubic",

        "-dColorImageDownsampleThreshold=1.0",

        f"-dColorImageResolution={dpi}",

        "-dAutoFilterColorImages=false",

        "-dColorImageFilter=/DCTEncode",

        # =================================================
        # GRAYSCALE IMAGE COMPRESSION
        # =================================================

        "-dDownsampleGrayImages=true",

        "-dGrayImageDownsampleType=/Bicubic",

        "-dGrayImageDownsampleThreshold=1.0",

        f"-dGrayImageResolution={dpi}",

        "-dAutoFilterGrayImages=false",

        "-dGrayImageFilter=/DCTEncode",

        # =================================================
        # MONO IMAGE COMPRESSION
        # =================================================

        "-dDownsampleMonoImages=true",

        "-dMonoImageDownsampleType=/Subsample",

        "-dMonoImageDownsampleThreshold=1.0",

        f"-dMonoImageResolution={max(dpi * 2, 50)}",

        # =================================================
        # JPEG QUALITY
        # =================================================

        f"-dJPEGQ={jpeg_quality}"

    ]


    if grayscale:

        command.extend([

            "-sColorConversionStrategy=Gray",

            "-dProcessColorModel=/DeviceGray"

        ])


    command.extend([

        f"-sOutputFile={output_pdf}",

        input_pdf

    ])


    process = subprocess.run(

        command,

        stdout=subprocess.PIPE,

        stderr=subprocess.PIPE,

        timeout=90

    )


    if process.returncode != 0:

        error_text = process.stderr.decode(
            "utf-8",
            errors="ignore"
        )

        raise RuntimeError(
            "Ghostscript failed: " +
            error_text
        )


    if not os.path.exists(output_pdf):

        raise RuntimeError(
            "Ghostscript output file was not created."
        )


    if os.path.getsize(output_pdf) <= 0:

        raise RuntimeError(
            "Ghostscript created an empty PDF."
        )


# =========================================================
# LEVEL COMPRESSION
# =========================================================

def compress_by_level(
    input_pdf,
    job_folder,
    level
):

    if level not in LEVEL_PROFILES:
        level = "recommended"


    settings = LEVEL_PROFILES[level]

    dpi = settings["dpi"]
    quality = settings["quality"]


    original_size = get_file_size(
        input_pdf
    )


    output_file = os.path.join(

        job_folder,

        f"compressed-{level}.pdf"

    )


    print(
        f"Compression mode: LEVEL",
        flush=True
    )

    print(
        f"Selected level: {level}",
        flush=True
    )

    print(
        f"DPI: {dpi}",
        flush=True
    )

    print(
        f"JPEG quality: {quality}",
        flush=True
    )


    run_ghostscript(

        input_pdf=input_pdf,

        output_pdf=output_file,

        dpi=dpi,

        jpeg_quality=quality,

        grayscale=False

    )


    compressed_size = get_file_size(
        output_file
    )


    print(
        f"Original bytes: {original_size}",
        flush=True
    )

    print(
        f"Compressed bytes: {compressed_size}",
        flush=True
    )


    # Never return a larger file than original
    if (
        compressed_size <= 0 or
        compressed_size >= original_size
    ):

        print(
            "Compressed file was not smaller. "
            "Returning original PDF.",
            flush=True
        )

        shutil.copy2(
            input_pdf,
            output_file
        )


    return output_file


# =========================================================
# TARGET SIZE COMPRESSION
# =========================================================

def compress_to_target(
    input_pdf,
    job_folder,
    target_kb
):

    original_size = get_file_size(
        input_pdf
    )


    target_bytes = (
        target_kb * 1024
    )


    # Already below selected target
    if original_size <= target_bytes:

        output_file = os.path.join(
            job_folder,
            "compressed-target.pdf"
        )

        shutil.copy2(
            input_pdf,
            output_file
        )

        return (
            output_file,
            True
        )


    best_file = None
    best_size = original_size

    start_time = time.time()


    # =====================================================
    # STRONG 100 KB MODE
    # =====================================================

    if target_kb <= 100:


        # =================================================
        # COLOR ATTEMPTS
        # =================================================

        for index, (
            dpi,
            quality
        ) in enumerate(
            COLOR_100KB_PROFILES,
            start=1
        ):


            if (
                time.time() -
                start_time >
                150
            ):
                break


            output_file = os.path.join(

                job_folder,

                f"target-color-{index}.pdf"

            )


            try:

                run_ghostscript(

                    input_pdf=input_pdf,

                    output_pdf=output_file,

                    dpi=dpi,

                    jpeg_quality=quality,

                    grayscale=False

                )


            except Exception as exc:

                print(
                    f"100KB color attempt failed: {exc}",
                    flush=True
                )

                continue


            current_size = get_file_size(
                output_file
            )


            if (
                current_size > 0 and
                current_size < best_size
            ):

                best_size = current_size
                best_file = output_file


            if (
                current_size > 0 and
                current_size <= target_bytes
            ):

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
                    True
                )


        # =================================================
        # GRAYSCALE FALLBACK
        # =================================================

        for index, (
            dpi,
            quality
        ) in enumerate(
            GRAYSCALE_100KB_PROFILES,
            start=1
        ):


            if (
                time.time() -
                start_time >
                175
            ):
                break


            output_file = os.path.join(

                job_folder,

                f"target-gray-{index}.pdf"

            )


            try:

                run_ghostscript(

                    input_pdf=input_pdf,

                    output_pdf=output_file,

                    dpi=dpi,

                    jpeg_quality=quality,

                    grayscale=True

                )


            except Exception as exc:

                print(
                    f"100KB grayscale attempt failed: {exc}",
                    flush=True
                )

                continue


            current_size = get_file_size(
                output_file
            )


            if (
                current_size > 0 and
                current_size < best_size
            ):

                best_size = current_size
                best_file = output_file


            if (
                current_size > 0 and
                current_size <= target_bytes
            ):

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
                    True
                )


    # =====================================================
    # 200 KB / 500 KB / 1 MB / CUSTOM
    # =====================================================

    else:


        for index, (
            dpi,
            quality
        ) in enumerate(
            TARGET_PROFILES,
            start=1
        ):


            if (
                time.time() -
                start_time >
                175
            ):
                break


            output_file = os.path.join(

                job_folder,

                f"target-{index}.pdf"

            )


            try:

                run_ghostscript(

                    input_pdf=input_pdf,

                    output_pdf=output_file,

                    dpi=dpi,

                    jpeg_quality=quality,

                    grayscale=False

                )


            except Exception as exc:

                print(
                    f"Target attempt failed: {exc}",
                    flush=True
                )

                continue


            current_size = get_file_size(
                output_file
            )


            if (
                current_size > 0 and
                current_size < best_size
            ):

                best_size = current_size
                best_file = output_file


            if (
                current_size > 0 and
                current_size <= target_bytes
            ):

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
                    True
                )


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


    final_size = get_file_size(
        final_file
    )


    reached = (
        final_size <= target_bytes
    )


    return (
        final_file,
        reached
    )


# =========================================================
# HOME
# =========================================================

@app.route("/", methods=["GET"])
def home():

    return jsonify({

        "success": True,

        "status": "online",

        "service":
            "TeluguTech777 PDF Compressor",

        "features": [

            "Compress PDF",

            "100 KB target",

            "200 KB target",

            "500 KB target",

            "1 MB target",

            "Custom target",

            "Low compression",

            "Recommended compression",

            "High compression"

        ]

    })


# =========================================================
# HEALTH
# =========================================================

@app.route("/health", methods=["GET"])
def health():

    try:

        process = subprocess.run(

            [
                "gs",
                "--version"
            ],

            stdout=subprocess.PIPE,

            stderr=subprocess.PIPE,

            text=True,

            timeout=10

        )


        installed = (
            process.returncode == 0
        )


        version = (

            process.stdout.strip()

            if installed

            else None

        )


    except Exception:

        installed = False
        version = None


    return jsonify({

        "success": True,

        "status": "ok",

        "ghostscript": {

            "installed": installed,

            "version": version

        }

    })


# =========================================================
# COMPRESS ENDPOINT
# =========================================================

@app.route(
    "/compress-pdf",
    methods=["POST"]
)
def compress_pdf():

    job_folder = None


    try:

        # =================================================
        # FILE VALIDATION
        # =================================================

        if "file" not in request.files:

            return jsonify({

                "success": False,

                "error":
                    "No PDF uploaded."

            }), 400


        uploaded_file = request.files[
            "file"
        ]


        if (
            not uploaded_file or
            not uploaded_file.filename
        ):

            return jsonify({

                "success": False,

                "error":
                    "No PDF selected."

            }), 400


        filename = secure_filename(
            uploaded_file.filename
        )


        if not is_pdf(filename):

            return jsonify({

                "success": False,

                "error":
                    "Only PDF files are allowed."

            }), 400


        # =================================================
        # CREATE JOB FOLDER
        # =================================================

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

            raise RuntimeError(
                "Uploaded PDF is empty."
            )


        if original_size > MAX_FILE_SIZE:

            return jsonify({

                "success": False,

                "error":
                    "Maximum upload size is 25 MB."

            }), 413


        # =================================================
        # MODE
        # =================================================

        mode = request.form.get(
            "mode",
            "target"
        )


        mode = (
            mode.strip().lower()
        )


        print(
            f"Requested mode: {mode}",
            flush=True
        )


        if mode not in [
            "target",
            "level"
        ]:

            return jsonify({

                "success": False,

                "error":
                    "Invalid compression mode."

            }), 400


        target_reached = None
        target_kb = None
        level = None


        # =================================================
        # TARGET SIZE MODE
        # =================================================

        if mode == "target":


            target_value = request.form.get(
                "target_kb",
                "200"
            )


            try:

                target_kb = int(
                    target_value
                )


            except Exception:

                return jsonify({

                    "success": False,

                    "error":
                        "Invalid target size."

                }), 400


            if (
                target_kb < 50 or
                target_kb > 20480
            ):

                return jsonify({

                    "success": False,

                    "error":
                        "Target size must be "
                        "between 50 KB and 20480 KB."

                }), 400


            print(
                f"Target selected: {target_kb} KB",
                flush=True
            )


            (
                output_pdf,
                target_reached

            ) = compress_to_target(

                input_pdf,

                job_folder,

                target_kb

            )


        # =================================================
        # LEVEL MODE
        # =================================================

        else:


            level = request.form.get(
                "level",
                "recommended"
            )


            level = (
                level.strip().lower()
            )


            print(
                f"Compression level received: {level}",
                flush=True
            )


            if level not in [

                "low",

                "recommended",

                "high"

            ]:

                return jsonify({

                    "success": False,

                    "error":
                        "Invalid compression level."

                }), 400


            output_pdf = compress_by_level(

                input_pdf,

                job_folder,

                level

            )


        # =================================================
        # RESULT
        # =================================================

        compressed_size = get_file_size(
            output_pdf
        )


        if compressed_size <= 0:

            raise RuntimeError(
                "Compressed PDF not created."
            )


        # Never return larger than original
        if compressed_size > original_size:

            shutil.copy2(
                input_pdf,
                output_pdf
            )

            compressed_size = original_size


        reduction_percent = (
            calculate_reduction(

                original_size,

                compressed_size

            )
        )


        print(
            f"Original size: {original_size}",
            flush=True
        )


        print(
            f"Final size: {compressed_size}",
            flush=True
        )


        print(
            f"Reduction: {reduction_percent}%",
            flush=True
        )


        # =================================================
        # DOWNLOAD
        # =================================================

        base_name = os.path.splitext(
            filename
        )[0]


        download_name = (
            base_name +
            "-compressed.pdf"
        )


        response = send_file(

            output_pdf,

            mimetype="application/pdf",

            as_attachment=True,

            download_name=download_name,

            conditional=False

        )


        # =================================================
        # HEADERS
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
        ] = str(
            reduction_percent
        )


        response.headers[
            "X-Compression-Mode"
        ] = mode


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


        if mode == "level":

            response.headers[
                "X-Compression-Level"
            ] = level


        # =================================================
        # TEMP CLEANUP
        # =================================================

        @response.call_on_close
        def cleanup():

            try:

                shutil.rmtree(
                    job_folder,
                    ignore_errors=True
                )

            except Exception as exc:

                print(
                    f"Cleanup error: {exc}",
                    flush=True
                )


        return response


    # =====================================================
    # TIMEOUT
    # =====================================================

    except subprocess.TimeoutExpired:


        if job_folder:

            shutil.rmtree(
                job_folder,
                ignore_errors=True
            )


        return jsonify({

            "success": False,

            "error":
                "PDF compression timed out."

        }), 504


    # =====================================================
    # GENERAL ERROR
    # =====================================================

    except Exception as exc:


        print(
            f"Compression error: {exc}",
            flush=True
        )


        if job_folder:

            shutil.rmtree(
                job_folder,
                ignore_errors=True
            )


        return jsonify({

            "success": False,

            "error":
                "Unable to compress PDF."

        }), 500


# =========================================================
# 413
# =========================================================

@app.errorhandler(413)
def file_too_large(error):

    return jsonify({

        "success": False,

        "error":
            "PDF is too large. Maximum size is 25 MB."

    }), 413


# =========================================================
# 404
# =========================================================

@app.errorhandler(404)
def not_found(error):

    return jsonify({

        "success": False,

        "error":
            "Endpoint not found."

    }), 404


# =========================================================
# 500
# =========================================================

@app.errorhandler(500)
def internal_error(error):

    return jsonify({

        "success": False,

        "error":
            "Internal server error."

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

        port=port

    )
