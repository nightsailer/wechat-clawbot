"""Tests for EndpointManager.health_check_loop (Phase 6.2)."""

from __future__ import annotations

import anyio
import pytest

from wechat_clawbot.gateway.endpoint_manager import EndpointManager
from wechat_clawbot.gateway.types import ChannelType, EndpointConfig, EndpointStatus


def _ep(ep_id: str, name: str = "") -> EndpointConfig:
    return EndpointConfig(id=ep_id, name=name or ep_id, type=ChannelType.MCP)


class _FakeChannel:
    """Minimal stub implementing is_endpoint_connected."""

    def __init__(self, connected: set[str] | None = None) -> None:
        self._connected = connected or set()

    def is_endpoint_connected(self, endpoint_id: str) -> bool:
        return endpoint_id in self._connected

    def get_connected_endpoints(self) -> list[str]:
        return sorted(self._connected)

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def deliver_message(
        self, endpoint_id: str, sender_id: str, text: str, **kwargs: object
    ) -> bool:
        return endpoint_id in self._connected

    async def send_reply(
        self, endpoint_id: str, sender_id: str, text: str, **kwargs: object
    ) -> None:
        pass


class TestHealthCheckLoop:
    @pytest.mark.asyncio
    async def test_marks_offline_when_not_connected(self) -> None:
        """An ONLINE endpoint should be set to OFFLINE if no channel reports it connected."""
        mgr = EndpointManager()
        mgr.register(_ep("ep-1"))
        mgr.set_connected("ep-1", True)
        assert mgr.is_online("ep-1") is True

        # Channel reports ep-1 as NOT connected
        fake = _FakeChannel(connected=set())
        stop_event = anyio.Event()

        async def run_one_cycle() -> None:
            """Run the loop, then signal stop after a tiny delay."""
            await anyio.sleep(0.05)
            stop_event.set()

        async with anyio.create_task_group() as tg:
            tg.start_soon(mgr.health_check_loop, [fake], 0.01, stop_event)
            tg.start_soon(run_one_cycle)

        info = mgr.get_endpoint("ep-1")
        assert info is not None
        assert info.status == EndpointStatus.OFFLINE

    @pytest.mark.asyncio
    async def test_stays_online_when_connected(self) -> None:
        """An ONLINE endpoint should remain ONLINE if a channel reports it connected."""
        mgr = EndpointManager()
        mgr.register(_ep("ep-1"))
        mgr.set_connected("ep-1", True)

        # Channel reports ep-1 as connected
        fake = _FakeChannel(connected={"ep-1"})
        stop_event = anyio.Event()

        async def run_one_cycle() -> None:
            await anyio.sleep(0.05)
            stop_event.set()

        async with anyio.create_task_group() as tg:
            tg.start_soon(mgr.health_check_loop, [fake], 0.01, stop_event)
            tg.start_soon(run_one_cycle)

        info = mgr.get_endpoint("ep-1")
        assert info is not None
        assert info.status == EndpointStatus.ONLINE

    @pytest.mark.asyncio
    async def test_skips_offline_endpoints(self) -> None:
        """OFFLINE endpoints should not be changed by the health check."""
        mgr = EndpointManager()
        mgr.register(_ep("ep-1"))
        # ep-1 starts OFFLINE (default)
        assert mgr.is_online("ep-1") is False

        fake = _FakeChannel(connected=set())
        stop_event = anyio.Event()

        async def run_one_cycle() -> None:
            await anyio.sleep(0.05)
            stop_event.set()

        async with anyio.create_task_group() as tg:
            tg.start_soon(mgr.health_check_loop, [fake], 0.01, stop_event)
            tg.start_soon(run_one_cycle)

        info = mgr.get_endpoint("ep-1")
        assert info is not None
        assert info.status == EndpointStatus.OFFLINE

    @pytest.mark.asyncio
    async def test_multiple_channels(self) -> None:
        """Endpoint stays ONLINE if ANY channel reports it connected."""
        mgr = EndpointManager()
        mgr.register(_ep("ep-1"))
        mgr.set_connected("ep-1", True)

        ch1 = _FakeChannel(connected=set())
        ch2 = _FakeChannel(connected={"ep-1"})
        stop_event = anyio.Event()

        async def run_one_cycle() -> None:
            await anyio.sleep(0.05)
            stop_event.set()

        async with anyio.create_task_group() as tg:
            tg.start_soon(mgr.health_check_loop, [ch1, ch2], 0.01, stop_event)
            tg.start_soon(run_one_cycle)

        info = mgr.get_endpoint("ep-1")
        assert info is not None
        assert info.status == EndpointStatus.ONLINE

    @pytest.mark.asyncio
    async def test_no_channels_marks_offline(self) -> None:
        """With no channels provided, all ONLINE endpoints go OFFLINE."""
        mgr = EndpointManager()
        mgr.register(_ep("ep-1"))
        mgr.set_connected("ep-1", True)

        stop_event = anyio.Event()

        async def run_one_cycle() -> None:
            await anyio.sleep(0.05)
            stop_event.set()

        async with anyio.create_task_group() as tg:
            tg.start_soon(mgr.health_check_loop, [], 0.01, stop_event)
            tg.start_soon(run_one_cycle)

        info = mgr.get_endpoint("ep-1")
        assert info is not None
        assert info.status == EndpointStatus.OFFLINE

    @pytest.mark.asyncio
    async def test_stop_event_terminates_loop(self) -> None:
        """Setting the stop_event should terminate the loop."""
        mgr = EndpointManager()
        stop_event = anyio.Event()
        stop_event.set()  # Already set before starting

        # Should return immediately since stop_event is already set
        await mgr.health_check_loop(channels=[], interval=60.0, stop_event=stop_event)
