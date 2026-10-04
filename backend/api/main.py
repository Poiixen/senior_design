import os
import tempfile
import traceback
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile

from backend.diagnostics.generic_dataset_profiler import profile_dataset
from backend.diagnostics.iqr_outlier_detection import detect_numeric_outliers
from backend.diagnostics.validate_dataset import validate_dataset
from backend.ingestion.csv_loader import CSVLoadError, load_csv

app = FastAPI(title="Team Science API")

# Configuration: Maximum upload size in bytes (100 MB default)
MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", 100 * 1024 * 1024))
CHUNK_SIZE = 64 * 1024  # Read in 64 KB chunks


class UploadError(Exception):
    """Upload validation error with user-friendly message."""
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


async def read_upload_with_limit(
    file: UploadFile, max_size: int = MAX_UPLOAD_SIZE
) -> bytes:
    """Read upload in chunks, enforcing size limit. Raises UploadError on violation."""
    if not file.filename:
        raise UploadError("No filename provided.")

    if not file.filename.lower().endswith(".csv"):
        raise UploadError("File must be a CSV (.csv extension required).")

    contents = b""
    while True:
        chunk = await file.read(CHUNK_SIZE)
        if not chunk:
            break
        contents += chunk
        if len(contents) > max_size:
            raise UploadError(
                f"File exceeds maximum size of {max_size // (1024 * 1024)} MB.",
                status_code=413,
            )

    if len(contents) == 0:
        raise UploadError("File is empty.")

    return contents


@app.post("/api/analyze")
async def analyze(file: UploadFile = File(...)) -> dict:
    tmp_path: Optional[str] = None

    try:
        # Read and validate upload
        try:
            contents = await read_upload_with_limit(file)
        except UploadError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.message)

        # Write to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
            tmp.write(contents)
            tmp_path = tmp.name

        # Load and analyze
        try:
            df = load_csv(tmp_path)
        except CSVLoadError as exc:
            raise UploadError(str(exc))
        except UnicodeDecodeError:
            raise UploadError(
                "File encoding is not supported. Please use UTF-8 or ASCII."
            )

        validation = validate_dataset(df)
        profile = profile_dataset(df)
        outliers = detect_numeric_outliers(df)

        diagnostics = []
        diagnostics.extend(
            {"type": "missing_values", **entry} for entry in profile["missing_values"]
        )
        if profile["duplicates"]["duplicate_count"] > 0:
            diagnostics.append({"type": "duplicates", **profile["duplicates"]})
        diagnostics.extend(
            {"type": "outlier", **entry} for entry in outliers if entry["outlier_count"] > 0
        )
        diagnostics.extend(
            {"type": "validation", "message": warning} for warning in validation["warnings"]
        )

        return {
            "dataset": {"rows": profile["rows"], "columns": profile["columns"]},
            "summary": {"issues_detected": len(diagnostics)},
            "diagnostics": diagnostics,
        }

    except UploadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    except Exception as exc:
        # Log the actual error for debugging
        error_msg = f"{type(exc).__name__}: {str(exc)}"
        print(f"API Error: {error_msg}")
        traceback.print_exc()
        # Generic error without exposing internals to client
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while processing your upload.",
        )
    finally:
        # Clean up temporary file in all cases
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
