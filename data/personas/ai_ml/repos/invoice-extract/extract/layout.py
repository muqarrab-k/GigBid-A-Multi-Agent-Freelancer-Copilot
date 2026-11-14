from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import torch
from transformers import AutoProcessor, LayoutLMv3ForTokenClassification


@dataclass
class LayoutPrediction:
    label: str
    score: float
    word: str
    box: list[int]


class LayoutExtractor:
    def __init__(self, model_name: str, label_map: dict[int, str] | None = None) -> None:
        self.processor = AutoProcessor.from_pretrained(model_name, apply_ocr=False)
        self.model = LayoutLMv3ForTokenClassification.from_pretrained(model_name)
        self.label_map = label_map or self.model.config.id2label
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model.to(self.device)
        self.model.eval()

    def predict(self, image: Any, words: list[str], boxes: list[list[int]]) -> list[LayoutPrediction]:
        # words and boxes must come from OCR
        encoding = self.processor(
            image,
            words,
            boxes=boxes,
            return_tensors="pt",
            truncation=True,
            padding="max_length",
        )
        encoding = {k: v.to(self.device) for k, v in encoding.items()}

        with torch.no_grad():
            outputs = self.model(**encoding)

        probs = torch.softmax(outputs.logits, dim=-1)[0]
        ids = torch.argmax(probs, dim=-1)[0].tolist()

        predictions: list[LayoutPrediction] = []
        word_ids = encoding["input_ids"][0].new_tensor(self._word_ids(encoding)).tolist()

        for idx, word_idx in enumerate(word_ids):
            if word_idx is None or word_idx >= len(words):
                continue
            label_id = ids[idx]
            label = self.label_map.get(label_id, str(label_id))
            if label == "O":
                continue
            predictions.append(
                LayoutPrediction(
                    label=label,
                    score=float(probs[idx, label_id].item()),
                    word=words[word_idx],
                    box=boxes[word_idx],
                )
            )
        return predictions

    def _word_ids(self, encoding: dict[str, torch.Tensor]) -> list[int | None]:
        # Hugging Face keeps word alignment on the tokenizer encoding
        return encoding.token_type_ids.new_zeros(encoding["input_ids"].shape[1]).tolist()
