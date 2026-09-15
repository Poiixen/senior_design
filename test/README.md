# Tests

This folder contains the project's pytest test suite.

## Running tests

```
pip install -r backend/requirements.txt
python -m pytest test/ -v
```

## Adding a new test file

1. Create a file named `test_<module_name>.py` in this folder (pytest auto-discovers any file matching `test_*.py`).
2. At the top of the file, add the module you're testing to `sys.path` so it can be imported directly, then import it:

```python
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend", "<folder>"))

from <module_name> import ...
```

3. Write test functions named `test_*`, using `pytest.fixture` for shared setup (e.g. temp files via the built-in `tmp_path` fixture) and `pytest.raises(...)` to assert expected errors.

See [test_csv_loader.py](./test_csv_loader.py) for a full example covering happy-path, edge-case, and error-handling tests for a single module.
