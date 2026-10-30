import json
import os
import secrets
import tempfile
import traceback
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal, Optional, Union

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, StrictBool, StrictFloat, StrictInt, StrictStr
from sqlalchemy.engine import Engine
from starlette.middleware.sessions import SessionMiddleware

from backend.api.auth import SESSION_IDLE_SECONDS, get_current_user, router as auth_router
from backend.database import repository
from backend.database.connection import (
    DEFAULT_DATABASE_PATH,
    create_sqlite_engine,
    initialize_database,
    session_scope,
)
from backend.database.dataset_store import DatasetStore
from backend.diagnostics.comparison_common import ComparisonError
from backend.ingestion.dataset_loader import DatasetLoadError, SUPPORTED_FILE_EXTENSIONS, load_dataset
from backend.models import User
from backend.models.conversations import QuestionRequest
from backend.models.suggestions import SuggestionRequest
from backend.services import conversations
from backend.services.analysis_service import AnalysisService, DatasetRowsUnavailable
from backend.services.suggestions import InvalidComparisonSelection, generate_suggestions
from backend.services.suggestions.ai_wording import default_complete


def configure_database(
    app: FastAPI,
    database_path: Union[str, Path] = DEFAULT_DATABASE_PATH,
    dataset_directory: Optional[Union[str, Path]] = None,
) -> Engine:
    """Open the SQLite database at ``database_path`` and attach it to ``app``.

    Uploaded rows are stored in ``dataset_directory``, by default a
    ``datasets`` folder beside the database file. An in-memory database gets
    no dataset store unless a directory is given.

    Nothing touches a database at import time; the server calls this on
    startup and tests call it with a temporary path. Dispose the returned
    engine when finished.
    """
    engine = create_sqlite_engine(database_path)
    initialize_database(engine)
    if dataset_directory is None and str(database_path) != ":memory:":
        dataset_directory = Path(database_path).expanduser().resolve().parent / "datasets"
    store = DatasetStore(dataset_directory) if dataset_directory is not None else None
    app.state.engine = engine
    app.state.analysis_service = AnalysisService(engine, dataset_store=store)
    return engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Keep a database a caller already configured (tests do this).
    if getattr(app.state, "engine", None) is None:
        configure_database(
            app,
            os.getenv("DATABASE_PATH", str(DEFAULT_DATABASE_PATH)),
            os.getenv("DATASET_STORAGE_DIR") or None,
        )
    try:
        yield
    finally:
        app.state.engine.dispose()


app = FastAPI(title="Team Science API", lifespan=lifespan)

allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://127.0.0.1:5173,http://localhost:5173",
    ).split(",")
    if origin.strip()
]
# Signs the session cookie. Without SECRET_KEY a random key is used, so
# logins reset whenever the server restarts; set it for stable sessions.
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SECRET_KEY") or secrets.token_urlsafe(32),
    same_site="lax",
    https_only=os.getenv("SESSION_COOKIE_SECURE", "").lower() in ("1", "true"),
    max_age=SESSION_IDLE_SECONDS,
)

if allowed_origins:
    # Added last so it is outermost and answers preflight before the session.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
        allow_credentials=True,
    )

app.include_router(auth_router)

# Configuration: Maximum upload size in bytes (100 MB default)
MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", 100 * 1024 * 1024))
CHUNK_SIZE = 64 * 1024  # Read in 64 KB chunks
SUPPORTED_DELIMITERS = {",", ";", "\t", "|"}
STANDARD_MISSING_VALUES = ["?"]
REPORT_NOT_FOUND = "Analysis report not found."


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

    if Path(file.filename).suffix.lower() not in SUPPORTED_FILE_EXTENSIONS:
        raise UploadError("Unsupported file format. Choose a CSV, TSV, XLSX, or JSON file.")

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


def parse_has_header(raw_value: Optional[str]) -> bool:
    """Parse the form field used to indicate whether the first row is headers."""
    if raw_value is None:
        return True
    normalized = raw_value.strip().lower()
    if normalized in {"", "1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise UploadError("has_header must be true or false.")


@app.post("/api/analyze")
async def analyze(
    request: Request,
    file: UploadFile = File(...),
    delimiter: str = Form(","),
    has_header: Optional[str] = Form(None),
    missing_values: str = Form("[]"),
    user: User = Depends(get_current_user),
) -> dict:
    tmp_path: Optional[str] = None

    try:
        # Read and validate upload
        contents = await read_upload_with_limit(file)

        if delimiter not in SUPPORTED_DELIMITERS:
            raise UploadError("Delimiter must be a comma, semicolon, tab, or pipe.")
        has_header_value = parse_has_header(has_header)
        custom_missing_values = parse_missing_values(missing_values)
        effective_missing_values = list(
            dict.fromkeys([*STANDARD_MISSING_VALUES, *custom_missing_values])
        )

        filename = Path(file.filename or "dataset.csv").name
        extension = Path(filename).suffix.lower()
        # Preserve the source suffix because spreadsheet readers rely on it.
        with tempfile.NamedTemporaryFile(delete=False, suffix=extension) as tmp:
            tmp.write(contents)
            tmp_path = tmp.name

        # Load and analyze
        try:
            loader_options = {}
            if extension in {".csv", ".tsv"}:
                loader_options = {
                    "sep": delimiter,
                    "header": 0 if has_header_value else None,
                    "na_values": effective_missing_values,
                    "keep_default_na": True,
                    "skipinitialspace": True,
                }
            df = load_dataset(tmp_path, filename, **loader_options)
        except DatasetLoadError as exc:
            raise UploadError(str(exc)) from exc

        # Headerless files get stable identifiers; editable display names are
        # stored separately so analysis and comparison references never break.
        df.columns = (
            [f"column_{index + 1}" for index in range(len(df.columns))]
            if not has_header_value
            else [str(column) for column in df.columns]
        )

        analysis_service = request.app.state.analysis_service
        dataset = analysis_service.register_dataset(
            df,
            name=Path(filename).stem or filename,
            source="upload",
            file_name=filename,
            user_id=user.id,
        )
        analysis = analysis_service.run_analysis(
            dataset.id,
            df,
            parsing_options={
                "delimiter": delimiter,
                "has_header": has_header_value,
                "missing_values": custom_missing_values,
            },
        )
        return analysis_service.get_report(analysis.id)

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
def get_report(
    analysis_id: int, request: Request, user: User = Depends(get_current_user)
) -> dict:
    with session_scope(request.app.state.engine) as session:
        report = repository.get_analysis_report_for_user(session, analysis_id, user.id)
        analysis = (
            None
            if report
            else repository.get_analysis_for_user(session, analysis_id, user.id)
        )
    if report is not None:
        return report
    if analysis is not None and analysis.status == "failed":
        raise HTTPException(
            status_code=409,
            detail="This analysis failed, so no report is available.",
        )
    if analysis is not None and analysis.status == "running":
        raise HTTPException(
            status_code=409,
            detail="This analysis is still running. Try again shortly.",
        )
    raise HTTPException(status_code=404, detail=REPORT_NOT_FOUND)


@app.get("/api/reports")
def list_reports(request: Request, user: User = Depends(get_current_user)) -> dict:
    with session_scope(request.app.state.engine) as session:
        reports = repository.list_analysis_reports_for_user(session, user.id)

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


class ColumnDisplayNamesRequest(BaseModel):
    column_display_names: dict[str, str]


@app.patch("/api/reports/{analysis_id}/column-names")
def update_column_display_names(
    analysis_id: int,
    payload: ColumnDisplayNamesRequest,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict:
    """Save labels for a headerless report without renaming source columns."""
    with session_scope(request.app.state.engine) as session:
        report = repository.get_analysis_report_for_user(session, analysis_id, user.id)
        if report is None:
            raise HTTPException(status_code=404, detail=REPORT_NOT_FOUND)
        if report.get("parsing_options", {}).get("has_header", True):
            raise HTTPException(status_code=400, detail="Only headerless uploads support editable display names.")
        available = {str(profile["name"]) for profile in report.get("column_profiles") or []}
        if set(payload.column_display_names) != available:
            raise HTTPException(status_code=400, detail="Provide one display name for every report column.")
        cleaned = {key: value.strip() for key, value in payload.column_display_names.items()}
        if any(not value or len(value) > 100 for value in cleaned.values()):
            raise HTTPException(status_code=400, detail="Display names must contain 1 to 100 characters.")
        normalized = [value.casefold() for value in cleaned.values()]
        if len(normalized) != len(set(normalized)):
            raise HTTPException(status_code=400, detail="Display names must be unique.")
        return repository.update_report_column_display_names(session, analysis_id, cleaned)


Category = Union[StrictBool, StrictInt, StrictFloat, StrictStr]


class CategoryCombination(BaseModel):
    """Original ``categories`` to combine under one new ``label``.

    Categories keep their JSON type: 1, "1" and true are different categories.
    """

    label: str
    categories: list[Category]


class CategoricalComparisonRequest(BaseModel):
    """How ``outcome_column`` is distributed within each ``group_column`` group."""

    comparison_type: Literal["categorical_categorical"]
    group_column: str
    outcome_column: str
    # Column name -> combinations, applied to a copy before comparing.
    category_mappings: Optional[dict[str, list[CategoryCombination]]] = None
    # Flagged columns the user has confirmed are meaningful.
    confirm_columns: list[str] = Field(default_factory=list)


class NumericComparisonRequest(BaseModel):
    """How ``value_column`` differs across ``group_column``'s independent groups."""

    comparison_type: Literal["categorical_numeric"]
    group_column: str
    value_column: str
    category_mappings: Optional[dict[str, list[CategoryCombination]]] = None
    confirm_columns: list[str] = Field(default_factory=list)


ComparisonRequest = Annotated[
    Union[CategoricalComparisonRequest, NumericComparisonRequest],
    Field(discriminator="comparison_type"),
]


def require_owned_analysis(request: Request, analysis_id: int, user: User) -> None:
    """404, the same as for a missing report, unless the user owns it."""
    with session_scope(request.app.state.engine) as session:
        analysis = repository.get_analysis_for_user(session, analysis_id, user.id)
    if analysis is None:
        raise HTTPException(status_code=404, detail=REPORT_NOT_FOUND)


@app.post("/api/reports/{analysis_id}/comparisons", status_code=201)
def create_comparison(
    analysis_id: int,
    selection: ComparisonRequest,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict:
    """Compare two columns of the report's dataset and save the result.

    Columns that cannot be compared (unknown, wrong type, identical) give
    400. Data that cannot be tested still gives 201 with ``status`` or
    ``test.status`` "unavailable" and a ``reason``.
    """
    compared_column = (
        selection.outcome_column
        if isinstance(selection, CategoricalComparisonRequest)
        else selection.value_column
    )
    try:
        comparison = request.app.state.analysis_service.compare_columns(
            analysis_id,
            user.id,
            selection.comparison_type,
            selection.group_column,
            compared_column,
            category_mappings={
                column: [combination.model_dump() for combination in combinations]
                for column, combinations in (selection.category_mappings or {}).items()
            }
            or None,
            confirm_columns=selection.confirm_columns,
        )
    except ComparisonError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except DatasetRowsUnavailable as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if comparison is None:
        raise HTTPException(status_code=404, detail=REPORT_NOT_FOUND)
    return comparison


@app.get("/api/reports/{analysis_id}/comparisons")
def list_comparisons(
    analysis_id: int, request: Request, user: User = Depends(get_current_user)
) -> dict:
    require_owned_analysis(request, analysis_id, user)
    return {
        "comparisons": request.app.state.analysis_service.list_comparisons(
            analysis_id, user.id
        )
    }


@app.get("/api/reports/{analysis_id}/comparisons/{comparison_id}")
def get_comparison(
    analysis_id: int,
    comparison_id: int,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict:
    comparison = request.app.state.analysis_service.get_comparison(
        analysis_id, comparison_id, user.id
    )
    if comparison is None:
        raise HTTPException(status_code=404, detail="Comparison not found.")
    return comparison


@app.post("/api/reports/{analysis_id}/suggestions")
def create_suggestions(
    analysis_id: int,
    request: Request,
    selection: Optional[SuggestionRequest] = None,
    user: User = Depends(get_current_user),
) -> dict:
    """Ranked, evidence-linked findings and next steps for a saved report.

    Works without AI credentials: ``source`` is "fallback" unless optional
    rewording was applied and validated. The body is optional.
    """
    try:
        response = generate_suggestions(
            request.app.state.analysis_service,
            analysis_id,
            user.id,
            selection,
            getattr(request.app.state, "suggestion_complete", None) or default_complete(),
        )
    except InvalidComparisonSelection as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if response is None:
        raise HTTPException(status_code=404, detail=REPORT_NOT_FOUND)
    return response


CONVERSATION_NOT_FOUND = "Conversation not found."


@app.post("/api/reports/{analysis_id}/conversations", status_code=201)
def create_conversation(
    analysis_id: int, request: Request, user: User = Depends(get_current_user)
) -> dict:
    """Start an empty follow-up thread about a report."""
    conversation = conversations.create_conversation(
        request.app.state.analysis_service, analysis_id, user.id
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail=REPORT_NOT_FOUND)
    return conversation


@app.get("/api/reports/{analysis_id}/conversations")
def list_conversations(
    analysis_id: int, request: Request, user: User = Depends(get_current_user)
) -> dict:
    """The user's threads about one report, newest first."""
    listing = conversations.list_conversations(
        request.app.state.analysis_service, analysis_id, user.id
    )
    if listing is None:
        raise HTTPException(status_code=404, detail=REPORT_NOT_FOUND)
    return listing


@app.get("/api/reports/{analysis_id}/conversations/{conversation_id}")
def get_conversation(
    analysis_id: int,
    conversation_id: int,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict:
    """Every saved question and answer of one thread, oldest first."""
    history = conversations.get_history(
        request.app.state.analysis_service, analysis_id, conversation_id, user.id
    )
    if history is None:
        raise HTTPException(status_code=404, detail=CONVERSATION_NOT_FOUND)
    return history


@app.post("/api/reports/{analysis_id}/questions")
def ask_question(
    analysis_id: int,
    question: QuestionRequest,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict:
    """Answer a follow-up question from the report's saved results.

    ``status`` is "answered", "insufficient_evidence" or "unavailable". An
    unavailable answer is still a 200: the question is saved and retrying with
    the same ``request_id`` asks again without a second copy of it.
    """
    try:
        response = conversations.ask_question(
            request.app.state.analysis_service,
            analysis_id,
            user.id,
            question,
            getattr(request.app.state, "conversation_complete", None) or default_complete(),
        )
    except conversations.ConversationNotFound:
        raise HTTPException(status_code=404, detail=CONVERSATION_NOT_FOUND)
    except conversations.RequestIdReused as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if response is None:
        raise HTTPException(status_code=404, detail=REPORT_NOT_FOUND)
    return response
