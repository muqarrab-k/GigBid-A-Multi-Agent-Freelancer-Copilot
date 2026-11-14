# Invoice field extraction for Ledgerline Accounting

Ledgerline Accounting needed a faster way to turn scanned supplier invoices into usable accounting data. Their team was spending too much time on manual entry, especially when invoices arrived as mixed-quality scans with varied layouts and line-item tables. I built a service that reads those invoices and returns the key fields the team needs in JSON: vendor, dates, totals, and line items.

I designed the workflow around a practical production setup. First, Tesseract handled text extraction from scanned pages. Then I used LayoutLMv3 with Hugging Face Transformers to identify and structure invoice fields from both the text and page layout. I wrapped the model pipeline in FastAPI so Ledgerline Accounting could send invoice files to a simple endpoint and receive normalized output immediately. The service was packaged with Docker so it could be run consistently in their environment.

A small example of the service shape is below:

```python
from fastapi import FastAPI, UploadFile

app = FastAPI()

@app.post("/extract")
async def extract_invoice(file: UploadFile):
    image_bytes = await file.read()
    # OCR + layout-aware parsing
    return {
        "vendor": "...",
        "dates": [],
        "totals": {},
        "line_items": []
    }
```

The main goal was to fit into how the accounting team already works. Instead of retyping invoice details by hand, they could now pass scanned files through the service and review structured results. That changed their process from repetitive data entry to validation and exception handling, which made the team’s day-to-day work much more efficient.

The final system reached 96.2% field-level accuracy on 1,800 test invoices and cut manual data entry by about 70%. For Ledgerline Accounting, that meant fewer keystrokes, faster invoice processing, and a cleaner handoff from incoming scan to accounting-ready data.
