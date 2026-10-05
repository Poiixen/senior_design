import os
import tempfile
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile

from backend.database.connection import create_sqlite_engine, initialize_database
from backend.ingestion.csv_loader import CSVLoadError, load_csv
from backend.services import AnalysisService
from backend.models.schemas import NON_ISSUE_SEVERITIES


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = create_sqlite_engine()
    initialize_database(engine)
    app.state.analysis_service = AnalysisService(engine)
    try:
        yield
    finally:
        engine.dispose()


app = FastAPI(title="Team Science API", lifespan=lifespan)


def get_analysis_service(request: Request) -> AnalysisService:
    return request.app.state.analysis_service


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/analyze")
async def analyze(
    file: UploadFile = File(...),
    service: AnalysisService = Depends(get_analysis_service),
) -> dict:
    contents = await file.read()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
        tmp.write(contents)
        tmp_path = tmp.name

    parsing_options: dict = {}
    try:
        df = load_csv(tmp_path, **parsing_options)
    except (FileNotFoundError, PermissionError, CSVLoadError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        os.remove(tmp_path)

    file_name = file.filename or None
    dataset = service.register_dataset(
        df, name=file_name or "upload", source="upload", file_name=file_name
    )
    analysis = service.run_analysis(dataset.id, df, parsing_options)
    findings = [
        {
            "type": finding.diagnostic_type,
            "column": finding.column_name,
            "severity": finding.severity,
            "value": finding.value,
            "message": finding.message,
        }
        for finding in service.list_findings(analysis.id)
    ]

    errors = [
        finding["message"]
        for finding in findings
        if finding["type"] == "validation" and finding["severity"] == "error"
    ]
    if errors:
        raise HTTPException(
            status_code=422,
            detail={"analysis_id": analysis.id, "errors": errors},
        )

    diagnostics = [
        finding for finding in findings if finding["severity"] not in NON_ISSUE_SEVERITIES
    ]
    profile = [finding for finding in findings if finding["type"] == "profile"]

    report = service.get_report(analysis.id)

    return {
        "dataset_id": dataset.id,
        "analysis_id": analysis.id,
        "report": report.model_dump(mode="json") if report else None,
        "dataset": {"rows": dataset.row_count, "columns": dataset.column_count},
        "summary": {"issues_detected": len(diagnostics)},
        "profile": profile,
        "diagnostics": diagnostics,
    }


@app.get("/api/analyses/{analysis_id}/report")
def get_report(
    analysis_id: int,
    service: AnalysisService = Depends(get_analysis_service),
) -> dict:
    report = service.get_report(analysis_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return report.model_dump(mode="json")
