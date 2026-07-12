"""Launch n8n instance MCP via mcp-remote (stdio bridge for Cursor)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def load_env_local(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def _node_dirs() -> list[Path]:
    dirs: list[Path] = []
    for name in ("node", "node.exe"):
        found = shutil.which(name)
        if found:
            dirs.append(Path(found).resolve().parent)

    for candidate in (
        Path("C:/nvm4w/nodejs"),
        Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "nodejs",
        Path(os.environ.get("APPDATA", "")) / "npm",
    ):
        if (candidate / "node.exe").is_file() or (candidate / "npx.cmd").is_file():
            dirs.append(candidate.resolve())

    unique: list[Path] = []
    for d in dirs:
        if d not in unique:
            unique.append(d)
    return unique


def find_npx() -> str:
    for node_dir in _node_dirs():
        for name in ("npx.cmd", "npx"):
            candidate = node_dir / name
            if candidate.is_file():
                return str(candidate)

    for name in ("npx", "npx.cmd"):
        found = shutil.which(name)
        if found:
            return found

    print("npx not found (Cursor MCP may have a minimal PATH)", file=sys.stderr)
    sys.exit(1)


def subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    extra = os.pathsep.join(str(d) for d in _node_dirs())
    if extra:
        env["PATH"] = extra + os.pathsep + env.get("PATH", "")
    return env


def mcp_url_from_env() -> str:
    base_url = os.environ.get("N8N_MCP_URL", "").rstrip("/")
    if not base_url:
        print("N8N_MCP_URL is not set (.env.local)", file=sys.stderr)
        sys.exit(1)
    if base_url.endswith("/mcp-server/http"):
        return base_url
    return f"{base_url}/mcp-server/http"


def main() -> None:
    repo = Path(__file__).resolve().parents[1]
    load_env_local(repo / ".env.local")

    token = os.environ.get("N8N_MCP_TOKEN", "")
    if not token:
        print("N8N_MCP_TOKEN is not set (.env.local)", file=sys.stderr)
        sys.exit(1)

    npx = find_npx()
    cmd = [
        npx,
        "-y",
        "@trayio/mcp-remote",
        mcp_url_from_env(),
        "--transport",
        "http-only",
        "--header",
        f"Authorization: Bearer {token}",
    ]
    sys.exit(subprocess.call(cmd, env=subprocess_env()))


if __name__ == "__main__":
    main()
