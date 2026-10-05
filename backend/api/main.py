import json
import math
import os
import tempfile
import traceback
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from backend.database import repository
from backend.database.connection import (
    DEFAULT_DATABASE_PATH,
    create_sqlite_engine,
    initialize_database,
    session_scope,
)
from backend.diagnostics.generic_dataset_profiler import profile_dataset
from backend.diagnostics.iqr_outlier_detection import detect_numeric_outliers
from backend.diagnostics.validate_dataset import validate_dataset
from backend.ingestion.csv_loader import CSVLoadError, load_csv
from backend.services.analysis_service import AnalysisService

app = FastAPI(title="Team Science API")

allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://127.0.0.1:5173,http://localhost:5173",
    ).split(",")
    if origin.strip()
]
if allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

database_path = os.getenv("DATABASE_PATH", str(DEFAULT_DATABASE_PATH))
engine = create_sqlite_engine(database_path)
initialize_database(engine)
analysis_service = AnalysisService(engine)

# Configuration: Maximum upload size in bytes (100 MB default)
MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", 100 * 1024 * 1024))
CHUNK_SIZE = 64 * 1024  # Read in 64 KB chunks
SUPPORTED_DELIMITERS = {",", ";", "\t", "|"}
STANDARD_MISSING_VALUES = ["?"]


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

    contents = bytearray()
    while True:
        chunk = await file.read(CHUNK_SIZE)
        if not chunk:
            break
        contents.extend(chunk)
        if len(contents) > max_size:
            raise UploadError(
                f"File exceeds maximum size of {max_size // (1024 * 1024)} MB.",
                status_code=413,
            )

    if len(contents) == 0:
        raise UploadError("File is empty.")

    return bytes(contents)


def parse_missing_values(raw_value: str) -> list[str]:
    """Parse the JSON form field used for additional missing-value markers."""
    try:
        value = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise UploadError("Missing-value markers must be a JSON array of strings.") from exc

    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise UploadError("Missing-value markers must be a JSON array of strings.")
    return list(dict.fromkeys(item for item in value if item))


def json_measurement(value) -> Optional[float]:
    """Return a finite JSON number, or null for unavailable measurements."""
    numeric = float(value)
    return numeric if math.isfinite(numeric) else None


def utc_timestamp(value) -> Optional[str]:
    if value is None:
        return None
    return f"{value.isoformat()}Z"


@app.post("/api/analyze")
async def analyze(
    file: UploadFile = File(...),
    delimiter: str = Form(","),
    has_header: bool = Form(True),
    missing_values: str = Form("[]"),
) -> dict:
    tmp_path: Optional[str] = None

    try:
        # Read and validate upload
        contents = await read_upload_with_limit(file)

        if delimiter not in SUPPORTED_DELIMITERS:
            raise UploadError("Delimiter must be a comma, semicolon, tab, or pipe.")
        custom_missing_values = parse_missing_values(missing_values)
        effective_missing_values = list(
            dict.fromkeys([*STANDARD_MISSING_VALUES, *custom_missing_values])
        )

        # Write to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
            tmp.write(contents)
            tmp_path = tmp.name

        # Load and analyze
        try:
            df = load_csv(
                tmp_path,
                sep=delimiter,
                header=0 if has_header else None,
                na_values=effective_missing_values,
                keep_default_na=True,
                # Common CSV exports (including UCI Adult) put a space after
                # delimiters. Ignore that formatting whitespace so markers
                # such as "?" match values written as " ?".
                skipinitialspace=True,
            )
        except CSVLoadError as exc:
            raise UploadError(
                "The CSV file could not be parsed. Check its delimiter and formatting."
            ) from exc
        except UnicodeDecodeError:
            raise UploadError(
                "File encoding is not supported. Please use UTF-8 or ASCII."
            )

        # Headerless CSVs receive integer labels from pandas; report fields use strings.
        df.columns = [str(column) for column in df.columns]

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
            {"type": "validation", "severity": "warning", "message": warning}
            for warning in validation["warnings"]
        )
        diagnostics.extend(
            {"type": "validation", "severity": "error", "message": error}
            for error in validation["errors"]
        )

        filename = Path(file.filename or "dataset.csv").name
        dataset = analysis_service.register_dataset(
            df,
            name=Path(filename).stem or filename,
            source="upload",
            file_name=filename,
        )
        analysis = analysis_service.run_analysis(dataset.id, df)

        missing_results = [
            {
                "column_name": str(entry["column_name"]),
                "missing_count": int(entry["missing_count"]),
                "missing_percentage": json_measurement(entry["missing_percentage"]),
                "severity": str(entry["severity"]),
            }
            for entry in profile["missing_values"]
        ]
        outlier_results = [
            {
                "column_name": str(entry["column_name"]),
                "outlier_count": int(entry["outlier_count"]),
                "outlier_percentage": json_measurement(entry["outlier_percentage"]),
                "q1": json_measurement(entry["q1"]),
                "q3": json_measurement(entry["q3"]),
                "iqr": json_measurement(entry["iqr"]),
                "lower_bound": json_measurement(entry["lower_bound"]),
                "upper_bound": json_measurement(entry["upper_bound"]),
            }
            for entry in outliers
        ]

        report = {
            "analysis_id": analysis.id,
            "filename": filename,
            "status": analysis.status,
            "started_at": utc_timestamp(analysis.started_at),
            "completed_at": utc_timestamp(analysis.completed_at),
            "dataset": {"rows": profile["rows"], "columns": profile["columns"]},
            "summary": {
                "issues_detected": len(diagnostics),
                "numeric_columns": len(profile["numeric_columns"]),
                "categorical_columns": len(profile["categorical_columns"]),
                "duplicate_rows": int(profile["duplicates"]["duplicate_count"]),
                "missing_columns": len(missing_results),
                "outlier_columns": sum(
                    entry["outlier_count"] > 0 for entry in outlier_results
                ),
            },
            "parsing_options": {
                "delimiter": delimiter,
                "has_header": has_header,
                "missing_values": custom_missing_values,
            },
            "missing_values": missing_results,
            "outliers": outlier_results,
            "validation": validation,
            "diagnostics": diagnostics,
        }

        with session_scope(engine) as session:
            repository.save_analysis_report(session, analysis.id, report)

        return report

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


@app.get("/api/reports/{analysis_id}")
def get_report(analysis_id: int) -> dict:
    with session_scope(engine) as session:
        report = repository.get_analysis_report(session, analysis_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Analysis report not found.")
    return report


@app.get("/api/reports")
def list_reports() -> dict:
    with session_scope(engine) as session:
        reports = repository.list_analysis_reports(session)

    return {
        "reports": [
            {
                "analysis_id": report["analysis_id"],
                "filename": report["filename"],
                "status": report["status"],
                "started_at": report["started_at"],
                "completed_at": report["completed_at"],
                "dataset": report["dataset"],
                "summary": report["summary"],
            }
            for report in reports
        ]
    }
