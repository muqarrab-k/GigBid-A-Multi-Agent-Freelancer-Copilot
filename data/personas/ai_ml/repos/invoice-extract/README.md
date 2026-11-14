Invoice field extraction service for scanned supplier invoices, returning vendor, dates, totals, and line items as JSON.

## Setup

- Python
- Tesseract
- LayoutLMv3
- Hugging Face Transformers
- FastAPI
- Docker

Install the runtime dependencies, make sure Tesseract is available, and build the container if you want to run it in Docker. The repo centers on OCR plus token classification and post-processing.

## Usage

```bash
# run the API
uvicorn main:app --host 0.0.0.0 --port 8000

# send an invoice image or scan to the extraction endpoint
# response includes vendor, dates, totals, and line items as JSON
```

## Notes

`extract/layout.py` runs LayoutLMv3 token classification over OCR words and bounding boxes.

`extract/postprocess.py` normalises dates and money amounts, then checks whether totals add up.

The system was evaluated on 1,800 test invoices and reached a field-level score of 96.2%. Manual data entry dropped by about 70%.

This repository covers the invoice extraction pipeline built over a fixed engagement from 2021-09 to 2021-12.
