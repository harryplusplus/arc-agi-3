from __future__ import annotations

import sys

from arc_benchmark_faithful.constants import REPO_ROOT


if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from arc_agi_3.ls20_observable import ObservableState, observe_state  # noqa: E402

__all__ = ["ObservableState", "observe_state"]
