import asyncio
from contextlib import nullcontext

import pytest

import server.main as server


@pytest.mark.parametrize("error", [None, RuntimeError, asyncio.CancelledError])
def test_lifespan_always_stops_and_awaits_expiry_task(monkeypatch, error):
    async def scenario():
        started = asyncio.Event()
        stopped = asyncio.Event()
        expiry_task = None

        async def expiry():
            nonlocal expiry_task
            expiry_task = asyncio.current_task()
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                # Shutdown must await asynchronous cleanup, not just cancel.
                await asyncio.sleep(0)
                stopped.set()

        monkeypatch.setattr(server, "expire_sessions", expiry)
        try:
            with pytest.raises(error) if error else nullcontext():
                async with server.lifespan(server.app):
                    await asyncio.wait_for(started.wait(), 1)
                    if error:
                        raise error()
            assert stopped.is_set()
            assert expiry_task.done()
        finally:
            # Keep a failing regression from leaking its own background task.
            if expiry_task is not None:
                expiry_task.cancel()
                await asyncio.gather(expiry_task, return_exceptions=True)

    asyncio.run(scenario())
