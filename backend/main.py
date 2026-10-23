"""Development entrypoint.

Run with::

    uv run uvicorn main:app --reload

or::

    uv run python main.py
"""

from __future__ import annotations

import uvicorn

from app.main import create_app

app = create_app()


def main() -> None:
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
