from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_processor_marks_observation_processed():
    """Processor must UPDATE observation status to 'processed' after synthesis."""
    obs = {
        "id": MagicMock(__str__=lambda s: "observation:abc123"),
        "content": "chose product over org as root field",
        "observation_type": "decision",
        "domain_path": "architecture",
        "confidence": 0.8,
        "product": MagicMock(__str__=lambda s: "product:platform"),
    }

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[[]])

    class FakeConn:
        async def __aenter__(self):
            return mock_db

        async def __aexit__(self, *a):
            pass

    with patch("core.engine.worker.processor.pool") as mock_pool:
        mock_pool.connection.return_value = FakeConn()
        with patch("core.engine.worker.processor.Synthesizer") as MockSynth:
            mock_synth = AsyncMock()
            mock_synth.add_observation = AsyncMock()
            mock_synth.flush = AsyncMock()
            MockSynth.return_value = mock_synth
            from core.engine.worker.processor import process_observation

            await process_observation(obs)

    call_args = mock_db.query.call_args_list
    update_calls = [c for c in call_args if "UPDATE" in str(c) and "processed" in str(c)]
    assert update_calls, "Must UPDATE observation to status=processed"


@pytest.mark.asyncio
async def test_processor_marks_failed_on_error_after_budget_exhausted():
    """Processor marks observation as failed only once the retry budget is exhausted."""
    from core.engine.worker.processor import MAX_RETRIES

    obs = {
        "id": MagicMock(__str__=lambda s: "observation:abc123"),
        "content": "test",
        "observation_type": "pattern",
        "domain_path": "testing",
        "confidence": 0.7,
        "product": MagicMock(__str__=lambda s: "product:platform"),
        "retry_count": MAX_RETRIES - 1,
    }

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[[]])

    class FakeConn:
        async def __aenter__(self):
            return mock_db

        async def __aexit__(self, *a):
            pass

    with patch("core.engine.worker.processor.pool") as mock_pool:
        mock_pool.connection.return_value = FakeConn()
        with patch("core.engine.worker.processor.Synthesizer") as MockSynth:
            mock_synth = AsyncMock()
            mock_synth.add_observation = AsyncMock()
            mock_synth.flush = AsyncMock(side_effect=RuntimeError("LLM error"))
            MockSynth.return_value = mock_synth
            from core.engine.worker.processor import process_observation

            await process_observation(obs)

    call_args = mock_db.query.call_args_list
    failed_calls = [c for c in call_args if "failed" in str(c)]
    assert failed_calls, "Must UPDATE observation to status=failed once budget exhausted"


@pytest.mark.asyncio
async def test_processor_wires_db_pool_to_synthesizer():
    """process_observation must set synth._db_pool = pool — without it _write_insight silently no-ops."""
    obs = {
        "id": MagicMock(__str__=lambda s: "observation:xyz"),
        "content": "test observation",
        "observation_type": "pattern",
        "domain_path": "architecture",
        "confidence": 0.7,
        "product": MagicMock(__str__=lambda s: "product:platform"),
    }

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[[]])

    class FakeConn:
        async def __aenter__(self):
            return mock_db

        async def __aexit__(self, *a):
            pass

    captured_synth = {}

    with patch("core.engine.worker.processor.pool") as mock_pool:
        mock_pool.connection.return_value = FakeConn()
        with patch("core.engine.worker.processor.Synthesizer") as MockSynth:
            mock_synth = AsyncMock()
            mock_synth.add_observation = AsyncMock()
            mock_synth.flush = AsyncMock()
            MockSynth.return_value = mock_synth
            from core.engine.worker.processor import process_observation

            await process_observation(obs)
            captured_synth["instance"] = mock_synth

    # The sentinel: _db_pool must be set before flush() is called
    assert captured_synth["instance"]._db_pool is mock_pool, (
        "_db_pool not wired — _write_insight would silently no-op on every synthesis"
    )


@pytest.mark.asyncio
async def test_dedup_insights_runs_without_error():
    """dedup_insights must not raise when DB returns no rows."""
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[[]])

    class FakeConn:
        async def __aenter__(self):
            return mock_db

        async def __aexit__(self, *a):
            pass

    with patch("core.engine.worker.processor.pool") as mock_pool:
        mock_pool.connection.return_value = FakeConn()
        from core.engine.worker.processor import dedup_insights

        result = await dedup_insights("product:platform", "architecture")
    assert isinstance(result, int)


@pytest.mark.asyncio
async def test_run_poll_cycle_calls_extract_and_emit_in_order():
    """run_poll_cycle must call extract_signals then emit_signals_to_bus after dedup/embed."""
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[[]])

    class FakeConn:
        async def __aenter__(self):
            return mock_db

        async def __aexit__(self, *a):
            pass

    call_order = []

    async def fake_extract(product_id):
        call_order.append("extract")
        return []

    async def fake_emit(signals):
        call_order.append("emit")

    with patch("core.engine.worker.processor.pool") as mock_pool:
        mock_pool.connection.return_value = FakeConn()
        with patch("core.engine.worker.processor.Synthesizer") as MockSynth:
            mock_synth = AsyncMock()
            mock_synth.add_observation = AsyncMock()
            mock_synth.flush = AsyncMock()
            MockSynth.return_value = mock_synth
            with patch("core.engine.worker.processor.get_embedder") as mock_embedder:
                mock_emb = MagicMock()
                mock_emb.dimensions = 0  # skip embedding
                mock_embedder.return_value = mock_emb
                with patch("core.engine.worker.signals.extract_signals", new=fake_extract):
                    with patch("core.engine.worker.bus_bridge.emit_signals_to_bus", new=fake_emit):
                        # Patch fetch_pending to return one obs so the cycle runs
                        with patch(
                            "core.engine.worker.processor.fetch_pending",
                            new=AsyncMock(
                                return_value=[
                                    {
                                        "id": MagicMock(__str__=lambda s: "observation:test1"),
                                        "content": "test",
                                        "domain_path": "architecture",
                                        "product": MagicMock(__str__=lambda s: "product:platform"),
                                    }
                                ]
                            ),
                        ):
                            from core.engine.worker.processor import run_poll_cycle

                            result = await run_poll_cycle("product:platform")

    assert isinstance(result, int), "run_poll_cycle must return int"
    assert "extract" in call_order, "extract_signals must be called"
    assert "emit" in call_order, "emit_signals_to_bus must be called"
    assert call_order.index("extract") < call_order.index("emit"), "extract must precede emit"
