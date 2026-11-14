# LLM Evaluation Harness for Tutor-Bot Releases

I worked with **Quillstack**, an edtech company, from **2025-08 to 2025-10** on an hourly engagement to make their tutor-bot release process safer and more repeatable.

Quillstack needed a way to catch quality issues before they reached learners. Their product was improving quickly, but each new prompt, model change, or backend adjustment could shift the tone, accuracy, or usefulness of tutor responses. Manual review alone was not enough to keep pace with releases, and they needed a practical way to evaluate answers against a consistent standard every time they shipped.

I built an **LLM evaluation harness** in **Python** using **pytest**, the **OpenAI API**, and **vLLM**. The core of the system was a regression suite that graded tutor-bot answers against a **400-item rubric** before each release. Instead of relying on ad hoc spot checks, the team could run the suite and compare current outputs against the expected behavior for a broad set of tutoring scenarios.

A small example of the test structure looked like this:

```python
import pytest

@pytest.mark.parametrize("case_id", ["rubric_001", "rubric_002"])
def test_tutor_answer(case_id, judge_client):
    prompt = load_prompt(case_id)
    answer = generate_answer(prompt)
    score = judge_client.grade(answer, rubric_for(case_id))
    assert score.passes
```

The main business value was release confidence. The harness gave Quillstack a clear gate before shipping changes, so quality issues were less likely to reach production unnoticed. It also made failures easier to investigate because each regression was tied back to a rubric item and a reproducible test case.

The results were strong: the judge and human reviewers reached a **0.71 kappa** agreement, and the suite **caught 2 regressions before release**. For Quillstack, that meant fewer risky launches, faster review cycles, and a more dependable tutoring experience for users.
