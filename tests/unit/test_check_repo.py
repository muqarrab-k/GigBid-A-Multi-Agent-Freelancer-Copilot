from pathlib import Path

import pytest

from scripts import check_repo


def test_flags_inline_prompt_and_secret(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(check_repo, "ROOT", tmp_path)
    prompt = "You are an assistant that writes proposals. " * 5
    (tmp_path / "node.py").write_text(f'PROMPT = "{prompt}"\n')
    (tmp_path / "ok.py").write_text('"""You are an assistant docstring is fine."""\nX = "short"\n')
    (tmp_path / "leak.txt").write_text("key = gsk_" + "a" * 30)
    assert check_repo.inline_prompts(["node.py", "ok.py"]) == [
        "node.py:1: prompt-like string; move it to agent/prompts/"]
    assert check_repo.secrets(["leak.txt"]) == ["leak.txt: looks like a groq key"]
