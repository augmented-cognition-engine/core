"""ONNX Runtime embedder — runs CodeRankEmbed INT8 locally on CPU.

Downloads model on first use from HuggingFace. Cached at ace_model_dir.
No API key, no network after first download, zero per-query cost.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

_MODEL_SOURCES = {
    "CodeRankEmbed": {
        "repo": "lprevelige/coderankembed-onnx-q8",
        "model_file": "onnx/model.onnx",
        "tokenizer_file": "tokenizer.json",
        "dimensions": 768,
    },
}


class OnnxEmbedder:
    """Embed code using ONNX Runtime with a bundled model."""

    def __init__(self, model_name: str = "CodeRankEmbed", model_dir: str = "~/.ace/models"):
        self._model_name = model_name
        self._model_dir = Path(os.path.expanduser(model_dir)) / model_name
        self._config = _MODEL_SOURCES.get(model_name, _MODEL_SOURCES["CodeRankEmbed"])
        self._session = None
        self._tokenizer = None

    @property
    def dimensions(self) -> int:
        return self._config["dimensions"]

    def _ensure_model(self) -> None:
        """Download model + tokenizer if not cached."""
        model_path = self._model_dir / "model.onnx"
        tokenizer_path = self._model_dir / "tokenizer.json"

        if model_path.exists() and tokenizer_path.exists():
            return

        self._model_dir.mkdir(parents=True, exist_ok=True)
        repo = self._config["repo"]
        logger.info("Downloading %s model from %s...", self._model_name, repo)

        try:
            from huggingface_hub import hf_hub_download

            # Download model file
            downloaded_model = hf_hub_download(
                repo_id=repo,
                filename=self._config["model_file"],
            )
            # Download tokenizer file
            downloaded_tokenizer = hf_hub_download(
                repo_id=repo,
                filename=self._config["tokenizer_file"],
            )

            # Copy to our cache dir
            import shutil

            shutil.copy2(downloaded_model, str(model_path))
            shutil.copy2(downloaded_tokenizer, str(tokenizer_path))

            logger.info("Model cached at %s", self._model_dir)
        except ImportError:
            raise RuntimeError("huggingface_hub is required for model download. Install: pip install huggingface_hub")

    def _load(self) -> None:
        """Load ONNX session + tokenizer into memory."""
        if self._session is not None:
            return

        self._ensure_model()

        import onnxruntime as ort
        from tokenizers import Tokenizer

        model_path = self._model_dir / "model.onnx"
        tokenizer_path = self._model_dir / "tokenizer.json"

        self._session = ort.InferenceSession(
            str(model_path),
            providers=["CPUExecutionProvider"],
        )
        self._tokenizer = Tokenizer.from_file(str(tokenizer_path))

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts. Returns normalized 768-dim vectors."""
        if not texts:
            return []

        self._load()

        # Tokenize with truncation and padding
        self._tokenizer.enable_truncation(max_length=8192)
        self._tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")
        encoded = self._tokenizer.encode_batch(texts)

        input_ids = np.array([e.ids for e in encoded], dtype=np.int64)
        attention_mask = np.array([e.attention_mask for e in encoded], dtype=np.int64)

        # Run inference
        outputs = self._session.run(
            None,
            {"input_ids": input_ids, "attention_mask": attention_mask},
        )

        # Mean pooling over token embeddings (masked)
        token_embeddings = outputs[0]  # (batch, seq_len, hidden_dim)
        mask_expanded = attention_mask[:, :, np.newaxis].astype(np.float32)
        sum_embeddings = np.sum(token_embeddings * mask_expanded, axis=1)
        sum_mask = np.sum(mask_expanded, axis=1)
        sum_mask = np.clip(sum_mask, a_min=1e-9, a_max=None)
        mean_embeddings = sum_embeddings / sum_mask

        # L2 normalize
        norms = np.linalg.norm(mean_embeddings, axis=1, keepdims=True)
        norms = np.clip(norms, a_min=1e-9, a_max=None)
        normalized = mean_embeddings / norms

        return [vec.tolist() for vec in normalized]
