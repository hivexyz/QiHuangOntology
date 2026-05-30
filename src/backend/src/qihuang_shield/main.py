from __future__ import annotations

import uvicorn


def run() -> None:
    uvicorn.run(
        "qihuang_shield.app:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        factory=False,
    )


if __name__ == "__main__":
    run()
