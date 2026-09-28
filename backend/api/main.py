import os
import tempfile

from fastapi import FastAPI, File, HTTPException, UploadFile

from backend.diagnostics.generic_dataset_profiler import profile_dataset
from backend.diagnostics.iqr_outlier_detection import detect_numeric_outliers
from backend.diagnostics.validate_dataset import validate_dataset
from backend.ingestion.csv_loader import CSVLoadError, load_csv

app = FastAPI(title="Team Science API")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/analyze")
async def analyze(file: UploadFile = File(...)) -> dict:
    contents = await file.read()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
        tmp.write(contents)
        tmp_path = tmp.name

    try:
        df = load_csv(tmp_path)
    except (FileNotFoundError, PermissionError, CSVLoadError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        os.remove(tmp_path)

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
