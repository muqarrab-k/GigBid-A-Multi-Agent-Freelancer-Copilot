import re
from functools import lru_cache
from pathlib import Path

from agent.config import get_config

NODE_RE = re.compile(r"^[a-z_]+$")
FILE_RE = re.compile(r"^(?P<node>[a-z_]+)\.v(?P<version>\d+)\.md$")


def prompt_versions(node: str, prompts_dir: Path | None = None) -> list[int]:
    """Available versions for a node, sorted."""
    folder = prompts_dir or get_config().paths.prompts_dir
    versions = []
    for path in folder.glob(f"{node}.v*.md"):
        match = FILE_RE.match(path.name)
        if match and match["node"] == node:
            versions.append(int(match["version"]))
    return sorted(versions)


@lru_cache(maxsize=64)
def load_prompt(node: str, version: int | None = None, prompts_dir: Path | None = None) -> str:
    """Read <node>.v<N>.md, latest if no version."""
    if not NODE_RE.match(node):
        raise ValueError(f"bad node name: {node!r}")
    folder = prompts_dir or get_config().paths.prompts_dir

    if version is None:
        found = prompt_versions(node, folder)
        if not found:
            raise FileNotFoundError(f"no prompt for '{node}' in {folder}")
        version = found[-1]

    path = folder / f"{node}.v{version}.md"
    if not path.is_file():
        raise FileNotFoundError(f"missing prompt file {path}")
    return path.read_text(encoding="utf-8").strip()
