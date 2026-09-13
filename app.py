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
# Fixed Custom Size Compression
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
    grayscale=True is used for aggressive compression.
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
        raise RuntimeError("Ghostscript compression failed.")

    if not os.path.exists(output_pdf):
        raise RuntimeError("Output PDF was not created.")

    if get_file_size(output_pdf) <= 0:
        raise RuntimeError("Output PDF is empty.")

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
# FIX: DYNAMIC TARGET PROFILES
# Works correctly for ANY custom size input
# =========================================================

def get_standard_profiles(target_kb):
    """
    Dynamically generate compression profiles based on
    target KB. Covers all custom sizes correctly.
    """

    # Very small targets: 101 KB - 150 KB (aggressive)
    if target_kb <= 150:
        return [
            (130, 68), (115, 62), (100, 55),
            (88,  48), (75,  40), (65,  34),
            (55,  28), (45,  22), (38,  17),
            (30,  12)
        ]

    # Small targets: 151 KB - 300 KB
    if target_kb <= 300:
        return [
            (160, 76), (145, 70), (130, 64),
            (115, 58), (100, 52), (88,  46),
            (75,  40), (65,  34), (55,  28),
            (45,  22)
        ]

    # Medium targets: 301 KB - 600 KB
    if target_kb <= 600:
        return [
            (185, 86), (170, 80), (155, 74),
            (140, 68), (125, 62), (110, 56),
            (95,  50), (82,  44), (70,  38),
            (58,  32)
        ]

    # Large targets: 601 KB - 2000 KB (2 MB)
    if target_kb <= 2000:
        return [
            (200, 90), (190, 86), (178, 82),
            (165, 78), (150, 74), (135, 68),
            (120, 62), (105, 56), (90,  50),
            (75,  44)
        ]

    # Very large targets: > 2 MB (light compression)
    return [
        (200, 92), (195, 90), (188, 88),
        (180, 86), (170, 84), (160, 80),
        (150, 76), (140, 72), (130, 68),
        (120, 64)
    ]

# =========================================================
# SPECIAL 100 KB / 150 KB COMPRESSION
# Two-stage: color first, then grayscale
# =========================================================

def compress_to_100kb(
    input_pdf,
    job_folder,
    target_bytes
):
    """
    Strong aggressive mode for targets <= 150 KB.
    Stage 1: Color compression.
    Stage 2: Grayscale compression.
    Returns smallest possible file if target not reached.
    """

    original_size = get_file_size(input_pdf)
    best_file = None
    best_size = original_size
    start_time = time.time()

    # =================================================
    # STAGE 1 - COLOR
    # =================================================

    color_profiles = [
        (120, 58),
        (100, 50),
        (85,  42),
        (72,  34),
        (60,  27),
        (50,  21),
        (42,  17),
        (35,  13),
        (30,  10),
        (25,   8)
    ]

    for index, profile in enumerate(color_profiles, start=1):
        if time.time() - start_time > 150:
            break

        dpi, quality = profile
        output_file = os.path.join(
            job_folder,
            f"agr-color-{index}.pdf"
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

        if size <= target_bytes:
            final_file = os.path.join(
                job_folder,
                "compressed-target.pdf"
            )
            shutil.copy2(output_file, final_file)
            return final_file, True, "color"

    # =================================================
    # STAGE 2 - GRAYSCALE
    # =================================================

    grayscale_profiles = [
        (72, 38),
        (60, 32),
        (52, 27),
        (45, 22),
        (38, 18),
        (32, 14),
        (28, 11),
        (24,  9),
        (20,  7),
        (18,  5)
    ]

    for index, profile in enumerate(grayscale_profiles, start=1):
        if time.time() - start_time > 175:
            break

        dpi, quality = profile
        output_file = os.path.join(
            job_folder,
            f"agr-gray-{index}.pdf"
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

        if size <= target_bytes:
            final_file = os.path.join(
                job_folder,
                "compressed-target.pdf"
            )
            shutil.copy2(output_file, final_file)
            return final_file, True, "grayscale"

    # =================================================
    # Target not reached — return smallest found
    # =================================================

    final_file = os.path.join(
        job_folder,
        "compressed-target.pdf"
    )

    if best_file:
        shutil.copy2(best_file, final_file)
    else:
        shutil.copy2(input_pdf, final_file)

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
    original_size = get_file_size(input_pdf)

    if original_size <= target_bytes:
        output_pdf = os.path.join(
            job_folder,
            "compressed-target.pdf"
        )
        shutil.copy2(input_pdf, output_pdf)
        return output_pdf, True, "original"

    profiles = get_standard_profiles(target_kb)

    best_file = None
    best_size = original_size
    start_time = time.time()

    for index, profile in enumerate(profiles, start=1):
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

        size = get_file_size(output_file)
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
            shutil.copy2(output_file, final_file)
            return final_file, True, "standard"

    # Target not reached — return smallest found
    final_file = os.path.join(
        job_folder,
        "compressed-target.pdf"
    )

    if best_file:
        shutil.copy2(best_file, final_file)
    else:
        shutil.copy2(input_pdf, final_file)

    return final_file, False, "maximum"

# =========================================================
# FIX: TARGET ROUTER
# Extended aggressive mode to cover <= 150 KB
# =========================================================

def compress_to_target(
    input_pdf,
    job_folder,
    target_kb
):
    target_bytes = target_kb * 1024
    original_size = get_file_size(input_pdf)

    # Already below target — return as-is
    if original_size <= target_bytes:
        output_pdf = os.path.join(
            job_folder,
            "compressed-target.pdf"
        )
        shutil.copy2(input_pdf, output_pdf)
        return output_pdf, True, "original"

    # Use strong aggressive mode for any target <= 150 KB
    # (was only <= 100 KB before — this is the key fix)
    if target_kb <= 150:
        return compress_to_100kb(
            input_pdf,
            job_folder,
            target_bytes
        )

    # Standard mode for all other targets (151 KB and above)
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
    settings = LEVEL_SETTINGS.get(level)

    if settings is None:
        raise ValueError("Invalid compression level.")

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

    original_size = get_file_size(input_pdf)
    compressed_size = get_file_size(output_pdf)

    if compressed_size >= original_size:
        shutil.copy2(input_pdf, output_pdf)

    return output_pdf

# =========================================================
# MAIN COMPRESS ENDPOINT
# =========================================================

@app.route("/compress-pdf", methods=["POST"])
def compress_pdf():
    job_id = str(uuid.uuid4())
    job_folder = os.path.join(BASE_FOLDER, job_id)
    os.makedirs(job_folder, exist_ok=True)

    try:

        # =============================================
        # UPLOAD CHECK
        # =============================================

        if "file" not in request.files:
            shutil.rmtree(job_folder, ignore_errors=True)
            return jsonify({
                "success": False,
                "error": "No PDF file uploaded."
            }), 400

        uploaded_file = request.files["file"]

        if uploaded_file is None or not uploaded_file.filename:
            shutil.rmtree(job_folder, ignore_errors=True)
            return jsonify({
                "success": False,
                "error": "Please select a PDF file."
            }), 400

        original_filename = secure_filename(uploaded_file.filename)

        if not original_filename.lower().endswith(".pdf"):
            shutil.rmtree(job_folder, ignore_errors=True)
            return jsonify({
                "success": False,
                "error": "Only PDF files are supported."
            }), 400

        # =============================================
        # SAVE FILE
        # =============================================

        input_pdf = os.path.join(job_folder, "input.pdf")
        uploaded_file.save(input_pdf)

        original_size = get_file_size(input_pdf)

        if original_size <= 0:
            shutil.rmtree(job_folder, ignore_errors=True)
            return jsonify({
                "success": False,
                "error": "Uploaded PDF is empty."
            }), 400

        # =============================================
        # VALIDATE PDF
        # =============================================

        if not is_pdf_file(input_pdf):
            shutil.rmtree(job_folder, ignore_errors=True)
            return jsonify({
                "success": False,
                "error": "Invalid PDF file."
            }), 400

        if not validate_pdf_with_ghostscript(input_pdf):
            shutil.rmtree(job_folder, ignore_errors=True)
            return jsonify({
                "success": False,
                "error": (
                    "The PDF appears corrupted or unsupported."
                )
            }), 400

        # =============================================
        # READ PARAMETERS
        # =============================================

        mode = request.form.get("mode", "level").strip().lower()
        level = request.form.get("level", "recommended").strip().lower()
        target_kb_raw = request.form.get("target_kb", "").strip()

        # =============================================
        # VALIDATE TARGET KB FOR TARGET MODE
        # =============================================

        target_kb = None

        if mode == "target":
            if not target_kb_raw:
                shutil.rmtree(job_folder, ignore_errors=True)
                return jsonify({
                    "success": False,
                    "error": "target_kb is required for target mode."
                }), 400

            try:
                target_kb = float(target_kb_raw)
            except ValueError:
                shutil.rmtree(job_folder, ignore_errors=True)
                return jsonify({
                    "success": False,
                    "error": "target_kb must be a number."
                }), 400

            if target_kb < 50:
                shutil.rmtree(job_folder, ignore_errors=True)
                return jsonify({
                    "success": False,
                    "error": "Minimum target size is 50 KB."
                }), 400

            if target_kb > 25600:
                shutil.rmtree(job_folder, ignore_errors=True)
                return jsonify({
                    "success": False,
                    "error": "Maximum target size is 25600 KB (25 MB)."
                }), 400

            target_kb = int(target_kb)

        # =============================================
        # COMPRESS
        # =============================================

        output_pdf = None
        target_reached = None
        compression_mode_used = None

        if mode == "target":
            output_pdf, target_reached, compression_mode_used = (
                compress_to_target(
                    input_pdf,
                    job_folder,
                    target_kb
                )
            )
        else:
            if level not in LEVEL_SETTINGS:
                shutil.rmtree(job_folder, ignore_errors=True)
                return jsonify({
                    "success": False,
                    "error": (
                        "Invalid level. Use: low, recommended, high."
                    )
                }), 400

            output_pdf = compress_by_level(
                input_pdf,
                job_folder,
                level
            )
            target_reached = None
            compression_mode_used = level

        # =============================================
        # VERIFY OUTPUT
        # =============================================

        if not output_pdf or not os.path.exists(output_pdf):
            shutil.rmtree(job_folder, ignore_errors=True)
            return jsonify({
                "success": False,
                "error": "Compression failed. Output not created."
            }), 500

        compressed_size = get_file_size(output_pdf)

        if compressed_size <= 0:
            shutil.rmtree(job_folder, ignore_errors=True)
            return jsonify({
                "success": False,
                "error": "Compressed PDF is empty."
            }), 500

        # =============================================
        # CALCULATE STATS
        # =============================================

        if original_size > 0:
            reduction_percent = round(
                ((original_size - compressed_size) / original_size) * 100,
                1
            )
        else:
            reduction_percent = 0.0

        original_kb = round(original_size / 1024, 1)
        compressed_kb = round(compressed_size / 1024, 1)

        # =============================================
        # BUILD DOWNLOAD FILENAME
        # =============================================

        base_name = os.path.splitext(original_filename)[0]
        download_name = f"{base_name}_compressed.pdf"

        # =============================================
        # SEND FILE WITH STATS IN HEADERS
        # =============================================

        response = send_file(
            output_pdf,
            as_attachment=True,
            download_name=download_name,
            mimetype="application/pdf"
        )

        response.headers["X-Original-Size"] = str(original_size)
        response.headers["X-Compressed-Size"] = str(compressed_size)
        response.headers["X-Reduction-Percent"] = str(reduction_percent)
        response.headers["X-Compression-Mode"] = str(compression_mode_used)

        if mode == "target" and target_kb is not None:
            response.headers["X-Target-KB"] = str(target_kb)
            response.headers["X-Target-Reached"] = (
                "true" if target_reached else "false"
            )

        # =============================================
        # CLEANUP JOB FOLDER AFTER SEND
        # =============================================

        @response.call_on_close
        def cleanup():
            shutil.rmtree(job_folder, ignore_errors=True)

        return response

    except Exception as error:
        shutil.rmtree(job_folder, ignore_errors=True)
        return jsonify({
            "success": False,
            "error": f"Unexpected error: {str(error)}"
        }), 500

# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
