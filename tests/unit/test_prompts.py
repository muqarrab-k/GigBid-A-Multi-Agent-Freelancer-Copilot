from pathlib import Path

import pytest

from agent.prompts.loader import load_prompt, prompt_versions


@pytest.fixture
def prompts(tmp_path: Path) -> Path:
    (tmp_path / "writer.v1.md").write_text("old writer\n")
    (tmp_path / "writer.v2.md").write_text("new writer\n")
    (tmp_path / "writer_extra.v9.md").write_text("other node\n")
    return tmp_path


def test_latest_version_by_default(prompts: Path) -> None:
    assert prompt_versions("writer", prompts) == [1, 2]
    assert load_prompt("writer", prompts_dir=prompts) == "new writer"


def test_pinned_version(prompts: Path) -> None:
    assert load_prompt("writer", 1, prompts) == "old writer"


def test_missing_prompt(prompts: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_prompt("critic", prompts_dir=prompts)
    with pytest.raises(FileNotFoundError):
        load_prompt("writer", 7, prompts)


def test_rejects_path_tricks(prompts: Path) -> None:
    with pytest.raises(ValueError):
        load_prompt("../secrets", prompts_dir=prompts)
