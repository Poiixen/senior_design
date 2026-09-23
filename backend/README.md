## Backend Setup

**Use this command to get all the needed dependencies:**

```
pip install -r backend/requirements.txt
```

## Running the API

From the repo root:

```
uvicorn backend.api.main:app --reload
```

Then check that it's up at http://127.0.0.1:8000/health, which should return `{"status": "ok"}`. Interactive docs are at http://127.0.0.1:8000/docs.
