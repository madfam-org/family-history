"""`python -m family_history.worker [healthcheck]`.

`healthcheck` exits 0 when `/tmp/worker-heartbeat` was touched within the last 120 seconds (the
pod's exec liveness probe); it imports nothing heavy, so the probe stays cheap.
"""

from __future__ import annotations

import os
import sys
import time

HEARTBEAT = "/tmp/worker-heartbeat"  # noqa: S108 - an emptyDir in the pod
MAX_AGE_SECONDS = 120.0


def healthcheck(path: str = HEARTBEAT, max_age: float = MAX_AGE_SECONDS) -> int:
    try:
        age = time.time() - os.path.getmtime(path)
    except OSError:
        print("worker heartbeat missing", file=sys.stderr)
        return 1
    if age > max_age:
        print(f"worker heartbeat is {age:.0f}s old", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args[:1] == ["healthcheck"]:
        return healthcheck()
    if args:
        print("usage: python -m family_history.worker [healthcheck]", file=sys.stderr)
        return 2
    from family_history.worker.main import serve

    return serve()


if __name__ == "__main__":
    sys.exit(main())
