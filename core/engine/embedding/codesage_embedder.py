"""CodeSage-Large-v2 embedder — best permissive open-source code embedding model.

Apache-2.0 license. 1.3B params, 1024-dim output.
First use downloads ~2.5GB to ace_model_dir via HuggingFace.
Inference is blocking; wrapped in run_in_executor for async compatibility.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "CodeSage/CodeSage-Large-v2"
_DIMENSIONS = 1024


class CodeSageEmbedder:
    """Embed code using CodeSage-Large-v2 via sentence-transformers."""

    def __init__(
        self,
        model_name: str = _DEFAULT_MODEL,
        model_dir: str = "~/.ace/models",
        device: str = "cpu",
    ) -> None:
        self._model_name = model_name
        self._cache_dir = str(Path(os.path.expanduser(model_dir)))
        self._device = device
        self._model = None

    @property
    def dimensions(self) -> int:
        return _DIMENSIONS

    def _load(self) -> None:
        if self._model is not None:
            return
        logger.info("Loading %s (first run downloads ~2.5GB)...", self._model_name)
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(
            self._model_name,
            # trust_remote_code required by CodeSage's custom pooling layer.
            # Changing _model_name to an untrusted source extends this trust — only
            # use HuggingFace repos you control or have audited.
            trust_remote_code=True,
            cache_folder=self._cache_dir,
            device=self._device,
        )
        logger.info("CodeSage ready on %s", self._device)

    def _encode(self, texts: list[str]) -> list[list[float]]:
        self._load()
        vectors = self._model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
            batch_size=16,
        )
        return vectors.tolist()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts. Returns normalized 1024-dim float vectors."""
        if not texts:
            return []
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._encode, texts)
