import pytest

from core.engine.canvas import canvas_engagement as ce


class _FakeLLM:
    def __init__(self, chunks):
        self._chunks = chunks

    async def stream(self, prompt, model=None, max_tokens=4096):
        for c in self._chunks:
            yield c


@pytest.mark.asyncio
async def test_stream_spin_emits_batched_deltas_and_returns_full_content(monkeypatch):
    # Avoid DB: stub prompt assembly to a fixed prompt + empty specialties.
    async def fake_assemble(task, perspective, classification, product_id):
        return ("PROMPT", [])

    monkeypatch.setattr(ce, "_assemble_canvas_prompt", fake_assemble)
    # 90 chars total. Pending accrues 25(a) → 50(a+b ≥40 → flush 50) → 25(c) →
    # 40(c+d ≥40 → flush 40). Exactly 2 deltas: 50 then 40.
    chunks = ["a" * 25, "b" * 25, "c" * 25, "d" * 15]
    monkeypatch.setattr(ce, "llm", _FakeLLM(chunks))

    deltas = []

    async def on_delta(text):
        deltas.append(text)

    spin = await ce._stream_spin_content(
        task="t",
        perspective="analyst",
        classification={},
        product_id="product:test",
        on_delta=on_delta,
        max_tokens=128,
    )

    assert spin.content == "a" * 25 + "b" * 25 + "c" * 25 + "d" * 15
    assert "".join(deltas) == spin.content  # no tokens lost
    assert all(len(d) > 0 for d in deltas)
    assert len(deltas) == 2  # exact batching: 50 then 40
    assert spin.perspective == "analyst"


@pytest.mark.asyncio
async def test_stream_spin_handles_empty_stream(monkeypatch):
    async def fake_assemble(task, perspective, classification, product_id):
        return ("PROMPT", [])

    monkeypatch.setattr(ce, "_assemble_canvas_prompt", fake_assemble)
    monkeypatch.setattr(ce, "llm", _FakeLLM([]))

    deltas = []
    spin = await ce._stream_spin_content(
        task="t",
        perspective="analyst",
        classification={},
        product_id="p",
        on_delta=lambda x: deltas.append(x) or _noop(),
        max_tokens=128,
    )
    assert spin.content == ""
    assert deltas == []


async def _noop():
    return None
