# Clinical note summarisation for Brightwell Clinics

When Brightwell Clinics brought me in, their clinical team was spending too much time turning raw visit notes into usable summaries. The notes were accurate, but they were also inconsistent in structure and contained sensitive patient details that could not be passed through a drafting workflow as-is. The team needed a way to speed up documentation without adding risk or forcing clinicians into a completely new process.

I worked with them on an hourly engagement from 2023-07 to 2023-10 to build a summarisation pipeline around a model they could actually use in day-to-day operations. The core of the solution was a LoRA-tuned Flan-T5 model built with Python, Hugging Face Transformers, and AWS. Before a note reached the model, names, dates, and IDs were masked so the system could draft summaries from de-identified text. The output was designed to produce a clean first draft that clinicians could review and edit rather than write from scratch.

A simplified version of the setup looked like this:

```python
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

model_id = "google/flan-t5-base"
tokenizer = AutoTokenizer.from_pretrained(model_id)
model = AutoModelForSeq2SeqLM.from_pretrained(model_id)

prompt = "Draft a concise visit summary from masked clinical notes."
inputs = tokenizer(prompt, return_tensors="pt")
summary_ids = model.generate(**inputs, max_new_tokens=180)
print(tokenizer.decode(summary_ids[0], skip_special_tokens=True))
```

The result was a workflow that fit into how Brightwell Clinics already worked. Clinicians no longer had to start every summary from a blank page; instead, they reviewed a model draft, corrected details, and moved on. That shift mattered more than any single model output, because it made the summarisation step part of the existing clinical review process rather than an extra task.

In evaluation, the model reached a ROUGE-L score of 0.41. More importantly for the team, a 6-week trial showed clinician editing time down 38%. Brightwell Clinics ended up with a practical drafting tool that reduced repetitive writing while keeping clinicians in control of the final note.
