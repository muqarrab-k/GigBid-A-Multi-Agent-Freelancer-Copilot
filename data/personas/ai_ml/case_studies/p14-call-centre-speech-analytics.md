# Call centre speech analytics for Vantor Call Centers

At Vantor Call Centers, the challenge was turning a large volume of recorded customer service calls into something the QA team could actually use every day. The raw audio existed, but reviewing it manually meant only a small fraction of calls ever got checked. I was brought in on a fixed engagement from 2024-10 to 2025-01 to build an automated pipeline that could transcribe each call, separate the agent and customer tracks, and generate a concise QA summary for every conversation.

I designed the system in Python around a transcription-and-enrichment flow. Whisper handled speech-to-text, while pyannote was used to split the call into distinct participant segments so the transcript could be attributed correctly. From there, I used the OpenAI API to produce structured QA summaries from the cleaned, role-aware transcript. The processed outputs were stored in PostgreSQL, which gave the team a durable way to query call-level results and integrate them into their review workflow.

A key part of the work was making the pipeline reliable at scale and accurate enough for QA use. I tuned the processing steps to keep transcription quality stable across varied call audio, and I validated the outputs against sample calls to keep the word error rate at 11.8%. The final system processed 2,300 hours of call audio and expanded QA coverage from 3% to 100% of calls.

```python
from openai import OpenAI

client = OpenAI()

summary = client.responses.create(
    model="gpt-4.1-mini",
    input=[
        {"role": "system", "content": "Write a concise QA summary from a call transcript."},
        {"role": "user", "content": transcript_text},
    ],
)
```

What I’m most proud of is that the solution didn’t just transcribe calls; it turned them into a consistent operational asset. Vantor Call Centers could move from selective manual review to full-call coverage, with every call carrying both a readable transcript and a QA summary ready for analysis.
