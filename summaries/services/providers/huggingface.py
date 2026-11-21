import threading

from ..errors import SummaryProviderError
from .base import BaseSummaryProvider

_LOCK = threading.Lock()
_LOADED = {}  # nom du modèle -> (tokenizer, model) : chargé une seule fois


class HuggingFaceProvider(BaseSummaryProvider):
    """Résumé abstractif avec un modèle T5/BART de Hugging Face."""

    name = "huggingface"
    is_slow = True

    def __init__(self, model_name):
        self.model_name = model_name

    def _load(self):
        with _LOCK:
            if self.model_name not in _LOADED:
                try:
                    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
                except ImportError as exc:
                    raise SummaryProviderError(
                        "Les bibliothèques transformers/torch ne sont pas installées."
                    ) from exc
                try:
                    tokenizer = AutoTokenizer.from_pretrained(self.model_name)
                    model = AutoModelForSeq2SeqLM.from_pretrained(self.model_name)
                except Exception as exc:
                    raise SummaryProviderError(
                        f"Impossible de charger le modèle « {self.model_name} »."
                    ) from exc
                model.eval()
                _LOADED[self.model_name] = (tokenizer, model)
            return _LOADED[self.model_name]

    def summarize(self, text, max_words, level="medium"):
        text = text.strip()
        if not text:
            return ""
        tokenizer, model = self._load()

        import torch

        inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
        with torch.inference_mode():
            output_ids = model.generate(
                **inputs,
                max_new_tokens=max(16, int(max_words * 1.6)),
                num_beams=4,
                no_repeat_ngram_size=3,
                early_stopping=True,
            )
        return tokenizer.decode(output_ids[0], skip_special_tokens=True).strip()