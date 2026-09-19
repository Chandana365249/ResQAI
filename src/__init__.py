"""
The `src` package.

Phase 1 modules (data_loader.py, data_preparation.py,
feature_engineering.py, train_model.py, evaluate_model.py) were written
to be run directly (e.g. `python src/train_model.py`, as documented in
docs/ML_PIPELINE.md) and import each other with bare, absolute imports
(e.g. `from data_preparation import ...`). That only resolves when the
`src/` directory itself is on `sys.path` -- true when a script inside
it is run directly, but not when this package is imported normally
(e.g. `import src.ml_adapter`, or `python -m src.report_parser`).

Rather than rewriting Phase 1's working, documented import style, this
bootstrap ensures `src/`'s own directory is always on `sys.path` the
moment anything under the `src` package is imported, so Phase 3 code
can import Phase 1 modules (e.g. feature_engineering.py's feature
lists) without changing a single Phase 1 file or breaking Phase 1's
existing `python src/<script>.py` commands.
"""

import sys
from pathlib import Path

_SRC_DIR = str(Path(__file__).resolve().parent)
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)
