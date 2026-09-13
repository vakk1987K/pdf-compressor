import os
import uuid
import shutil
import subprocess

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename


# =========================================================
# APPLICATION CONFIGURATION
# =========================================================

app = Flask(__name__)

# Allows Blogger/browser frontend requests.
# Later, this can be restricted to your Blogger domain only.
CORS(app)

# Maximum upload size: 25 MB
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024

BASE_FOLDER = "/tmp/pdf_compressor"
os.makedirs(BASE_FOLDER, exist_ok=True)


# =========================================================
# SECURITY HEADERS
# =========================================================

@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Cache-Control"] = "no-store"

    # Blogger frontend needs these headers to display
    # original/compressed file size information.
    response.headers["Access-Control-Expose-Headers"] = (
        "X-Original-Size, "
        "X-Compressed-Size, "
        "X-Reduction-Percent, "
        "X-Target-Reached, "
        "X-Target-KB, "
        "Content-Disposition"
    )

    return response


# =========================================================
# REQUEST LOGGING
# =========================================================

@app.before_request
def log_request():
    print(
        f"{request.method} {request.path} "
        f"from {request.remote_addr}"
    )


# =========================================================
# 413 - FILE TOO LARGE
# =========================================================

@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({
        "success": False,
        "error": "File is too large. Maximum allowed size is 25 MB."
    }), 413


# =========================================================
# HOME
# =========================================================

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "success": True,
        "name": "TeluguTech777 PDF Compressor API",
        "status": "online",
        "max_upload_mb": 25,
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
            capture_output=True,
            text=True,
            timeout=10
        )

        version = (
            result.stdout.strip()
            if result.stdout
            else result.stderr.strip()
        )

        return jsonify({
            "success": True,
            "status": "ok",
            "ghostscript": {
                "installed": result.returncode == 0,
                "version": version
            }
        })

    except Exception as exc:
        return jsonify({
            "success": False,
            "status": "error",
            "ghostscript": {
                "installed": False
            },
            "error": str(exc)
        }), 500


# =========================================================
# HELPERS
# =========================================================

def format_download_name(original_name):
    """
    Example:
    report.pdf -> report-compressed.pdf
    """

    safe_name = secure_filename(original_name)

    base_name = os.path.splitext(safe_name)[0]

    if not base_name:
        base_name = "document"

    return f"{base_name}-compressed.pdf"


def verify_pdf_signature(path):
    """
    Simple PDF signature validation.
    """

    with open(path, "rb") as pdf_file:
        signature = pdf_file.read(5)

    return signature == b"%PDF-"


def validate_pdf_with_ghostscript(path):
    """
    Ask Ghostscript to parse the PDF without producing output.
    This helps reject damaged/non-PDF files.
    """

    command = [
        "gs",
        "-q",
        "-dNOPAUSE",
        "-dBATCH",
        "-dSAFER",
        "-sDEVICE=nullpage",
        path
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=60
    )

    if result.returncode != 0:
        raise ValueError("The uploaded file is not a valid readable PDF.")


def compression_settings(level):
    """
    Returns (DPI, JPEG quality).

    low:
        Better quality, smaller reduction.

    recommended:
        Balanced quality and size.

    high:
        Stronger image compression.
    """

    settings = {
        "low": (170, 82),
        "recommended": (120, 65),
        "high": (85, 45)
    }

    return settings.get(
        level,
        settings["recommended"]
    )


def run_ghostscript(
    input_path,
    output_path,
    dpi,
    jpeg_quality
):
    """
    Compress PDF using Ghostscript.

    Important:
    PDF compression is content-dependent.
    Text-heavy PDFs may already be very small.
    Scanned/image PDFs usually compress much more.
    """

    command = [
        "gs",
        "-sDEVICE=pdfwrite",
        "-dCompatibilityLevel=1.4",
        "-dNOPAUSE",
        "-dBATCH",
        "-dQUIET",
        "-dSAFER",

        # General PDF optimization
        "-dDetectDuplicateImages=true",
        "-dCompressFonts=true",
        "-dSubsetFonts=true",

        # Color images
        "-dAutoFilterColorImages=false",
        "-dColorImageFilter=/DCTEncode",
        "-dDownsampleColorImages=true",
        "-dColorImageDownsampleType=/Bicubic",
        f"-dColorImageResolution={dpi}",

        # Grayscale images
        "-dAutoFilterGrayImages=false",
        "-dGrayImageFilter=/DCTEncode",
        "-dDownsampleGrayImages=true",
        "-dGrayImageDownsampleType=/Bicubic",
        f"-dGrayImageResolution={dpi}",

        # Monochrome images
        "-dDownsampleMonoImages=true",
        "-dMonoImageDownsampleType=/Subsample",
        "-dMonoImageResolution=300",

        # JPEG quality
        f"-dJPEGQ={jpeg_quality}",

        f"-sOutputFile={output_path}",
        input_path
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=180
    )

    if result.returncode != 0:
        print("Ghostscript stdout:", result.stdout)
        print("Ghostscript stderr:", result.stderr)

        raise RuntimeError(
            "Ghostscript could not compress the PDF."
        )

    if not os.path.exists(output_path):
        raise RuntimeError(
            "Compressed PDF was not created."
        )

    if os.path.getsize(output_path) <= 0:
        raise RuntimeError(
            "Compressed PDF is empty."
        )


def copy_if_smaller(source_path, candidate_path, best_path):
    """
    Replace best_path only when candidate is smaller.
    """

    candidate_size = os.path.getsize(candidate_path)

    if os.path.exists(best_path):
        best_size = os.path.getsize(best_path)
    else:
        best_size = None

    if best_size is None or candidate_size < best_size:
        shutil.copy2(candidate_path, best_path)


# =========================================================
# PDF COMPRESSOR
#
# POST /compress-pdf
#
# Multipart fields:
#
# file
#
# mode = level
# level = low | recommended | high
#
# OR
#
# mode = target
# target_kb = 100 | 200 | 500 | 1024 | custom number
# =========================================================

@app.route("/compress-pdf", methods=["POST"])
def compress_pdf():

    job_id = uuid.uuid4().hex

    job_folder = os.path.join(
        BASE_FOLDER,
        job_id
    )

    os.makedirs(
        job_folder,
        exist_ok=True
    )

    try:

        # -------------------------------------------------
        # FILE UPLOAD CHECK
        # -------------------------------------------------

        if "file" not in request.files:
            return jsonify({
                "success": False,
                "error": "Please upload a PDF file."
            }), 400

        uploaded_file = request.files["file"]

        if (
            not uploaded_file
            or not uploaded_file.filename
        ):
            return jsonify({
                "success": False,
                "error": "No PDF file selected."
            }), 400

        original_filename = uploaded_file.filename

        safe_filename = secure_filename(
            original_filename
        )

        if not safe_filename:
            return jsonify({
                "success": False,
                "error": "Invalid filename."
            }), 400

        extension = os.path.splitext(
            safe_filename
        )[1].lower()

        if extension != ".pdf":
            return jsonify({
                "success": False,
                "error": "Only PDF files are supported."
            }), 400

        # -------------------------------------------------
        # SAVE INPUT
        # -------------------------------------------------

        input_path = os.path.join(
            job_folder,
            "input.pdf"
        )

        uploaded_file.save(
            input_path
        )

        original_size = os.path.getsize(
            input_path
        )

        if original_size <= 0:
            return jsonify({
                "success": False,
                "error": "The uploaded PDF is empty."
            }), 400

        # -------------------------------------------------
        # PDF VALIDATION
        # -------------------------------------------------

        if not verify_pdf_signature(
            input_path
        ):
            return jsonify({
                "success": False,
                "error": "The uploaded file is not a valid PDF."
            }), 400

        try:
            validate_pdf_with_ghostscript(
                input_path
            )

        except ValueError:
            return jsonify({
                "success": False,
                "error": "The PDF is damaged or cannot be read."
            }), 400

        # -------------------------------------------------
        # REQUEST MODE
        # -------------------------------------------------

        mode = request.form.get(
            "mode",
            "level"
        ).strip().lower()

        final_output = os.path.join(
            job_folder,
            "compressed.pdf"
        )

        target_reached = True
        target_kb = None

        # =================================================
        # COMPRESSION LEVEL
        # =================================================

        if mode == "level":

            level = request.form.get(
                "level",
                "recommended"
            ).strip().lower()

            if level not in {
                "low",
                "recommended",
                "high"
            }:
                return jsonify({
                    "success": False,
                    "error": (
                        "Invalid compression level. "
                        "Use low, recommended or high."
                    )
                }), 400

            dpi, jpeg_quality = compression_settings(
                level
            )

            candidate_path = os.path.join(
                job_folder,
                "candidate.pdf"
            )

            run_ghostscript(
                input_path,
                candidate_path,
                dpi,
                jpeg_quality
            )

            candidate_size = os.path.getsize(
                candidate_path
            )

            # Never return a file larger than the original.
            if candidate_size < original_size:
                shutil.copy2(
                    candidate_path,
                    final_output
                )
            else:
                shutil.copy2(
                    input_path,
                    final_output
                )

        # =================================================
        # TARGET FILE SIZE
        # =================================================

        elif mode == "target":

            raw_target = request.form.get(
                "target_kb",
                "200"
            )

            try:
                target_kb = int(
                    raw_target
                )

            except (TypeError, ValueError):
                return jsonify({
                    "success": False,
                    "error": "Target size must be a number in KB."
                }), 400

            # Practical limits
            if target_kb < 50:
                return jsonify({
                    "success": False,
                    "error": "Minimum target size is 50 KB."
                }), 400

            if target_kb > 20480:
                return jsonify({
                    "success": False,
                    "error": "Maximum custom target size is 20480 KB (20 MB)."
                }), 400

            target_bytes = (
                target_kb * 1024
            )

            # Already below target.
            if original_size <= target_bytes:
                shutil.copy2(
                    input_path,
                    final_output
                )

            else:

                # Start with better quality and progressively
                # compress more strongly.
                attempts = [
                    (170, 82),
                    (150, 76),
                    (130, 70),
                    (115, 64),
                    (100, 57),
                    (90, 50),
                    (80, 44),
                    (72, 38),
                    (64, 33),
                    (56, 28),
                    (50, 24)
                ]

                best_output = os.path.join(
                    job_folder,
                    "best.pdf"
                )

                for attempt_index, (
                    dpi,
                    jpeg_quality
                ) in enumerate(attempts):

                    attempt_path = os.path.join(
                        job_folder,
                        f"attempt-{attempt_index}.pdf"
                    )

                    run_ghostscript(
                        input_path,
                        attempt_path,
                        dpi,
                        jpeg_quality
                    )

                    copy_if_smaller(
                        input_path,
                        attempt_path,
                        best_output
                    )

                    attempt_size = os.path.getsize(
                        attempt_path
                    )

                    if attempt_size <= target_bytes:
                        break

                if not os.path.exists(
                    best_output
                ):
                    raise RuntimeError(
                        "No compressed PDF was produced."
                    )

                best_size = os.path.getsize(
                    best_output
                )

                # Never return a larger result.
                if best_size < original_size:
                    shutil.copy2(
                        best_output,
                        final_output
                    )
                else:
                    shutil.copy2(
                        input_path,
                        final_output
                    )

                final_size_for_target = os.path.getsize(
                    final_output
                )

                target_reached = (
                    final_size_for_target <= target_bytes
                )

        else:
            return jsonify({
                "success": False,
                "error": (
                    "Invalid mode. "
                    "Use level or target."
                )
            }), 400

        # -------------------------------------------------
        # FINAL RESULT
        # -------------------------------------------------

        compressed_size = os.path.getsize(
            final_output
        )

        if compressed_size <= 0:
            raise RuntimeError(
                "Compressed PDF is empty."
            )

        reduction = 0.0

        if original_size > 0:
            reduction = round(
                (
                    (
                        original_size
                        - compressed_size
                    )
                    / original_size
                )
                * 100,
                2
            )

        download_name = format_download_name(
            original_filename
        )

        response = send_file(
            final_output,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=download_name
        )

        response.headers["X-Original-Size"] = str(
            original_size
        )

        response.headers["X-Compressed-Size"] = str(
            compressed_size
        )

        response.headers["X-Reduction-Percent"] = str(
            reduction
        )

        response.headers["X-Target-Reached"] = (
            "true"
            if target_reached
            else "false"
        )

        if target_kb is not None:
            response.headers["X-Target-KB"] = str(
                target_kb
            )

        # Remove uploaded and generated files
        # after Flask finishes sending the response.
        @response.call_on_close
        def cleanup():
            shutil.rmtree(
                job_folder,
                ignore_errors=True
            )

        return response

    except subprocess.TimeoutExpired:

        print(
            "PDF compression timeout:",
            job_id
        )

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

    except Exception as exc:

        print(
            "PDF compression error:",
            str(exc)
        )

        shutil.rmtree(
            job_folder,
            ignore_errors=True
        )

        return jsonify({
            "success": False,
            "error": (
                "Unable to compress the PDF. "
                "Please try another file."
            )
        }), 500


# =========================================================
# 404
# =========================================================

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "success": False,
        "error": "Endpoint not found."
    }), 404


# =========================================================
# 500
# =========================================================

@app.errorhandler(500)
def internal_server_error(error):
    return jsonify({
        "success": False,
        "error": "An internal server error occurred."
    }), 500


# =========================================================
# LOCAL DEVELOPMENT
# Render uses Gunicorn in production
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
