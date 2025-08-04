"""
Tests for scheduler endpoints in octopus_service.py module.
"""
import json
from unittest.mock import Mock, patch

import pytest


class TestSchedulerEndpoints:
    """Test scheduler management endpoints."""

    @pytest.fixture
    def mock_octopus_with_scheduler(self):
        """Create mock octopus with scheduler enabled."""
        mock_octopus = Mock()

        # Mock scheduler status
        mock_octopus.get_scheduler_status.return_value = {
            "enabled": True,
            "status": "running",
            "total_schedules": 2,
            "enabled_schedules": 1,
            "running_scheduled_tasks": 0,
            "next_run": "2025-08-04T10:00:00",
            "schedules_by_status": {},
        }

        # Mock scheduler operations
        mock_octopus.start_scheduler.return_value = True
        mock_octopus.stop_scheduler.return_value = True
        mock_octopus.add_scraper_schedule.return_value = "test_schedule_123"
        mock_octopus.remove_schedule.return_value = True
        mock_octopus.enable_schedule.return_value = True
        mock_octopus.disable_schedule.return_value = True
        mock_octopus.trigger_schedule_now.return_value = "task_456"

        # Mock schedule data
        mock_octopus.list_schedules.return_value = [
            {
                "schedule_id": "daily_scraper",
                "scraper_name": "sspai_scraper",
                "cron_expression": "0 9 * * *",
                "enabled": True,
                "next_run": "2025-08-04T09:00:00",
                "last_run": None,
                "max_concurrent_runs": 1,
                "timeout_seconds": 1800,
                "metadata": {},
            }
        ]

        mock_octopus.get_schedule.return_value = {
            "schedule_id": "daily_scraper",
            "scraper_name": "sspai_scraper",
            "cron_expression": "0 9 * * *",
            "enabled": True,
            "next_run": "2025-08-04T09:00:00",
            "last_run": None,
            "max_concurrent_runs": 1,
            "timeout_seconds": 1800,
            "metadata": {},
            "fetch_params": {"limit": 20},
        }

        return mock_octopus

    @pytest.fixture
    def mock_app_with_scheduler(self, mock_octopus_with_scheduler):
        """Create mock app with scheduler-enabled octopus."""
        mock_app = Mock()
        mock_app.ctx = Mock()
        mock_app.ctx.octopus = mock_octopus_with_scheduler
        return mock_app

    @pytest.mark.asyncio
    async def test_get_scheduler_status(self, mock_app_with_scheduler):
        """Test getting scheduler status."""
        from octopus_scraper.octopus_service import get_scheduler_status

        mock_request = Mock()

        with patch("octopus_scraper.octopus_service.app", mock_app_with_scheduler):
            response = await get_scheduler_status(mock_request)

        assert response.status == 200
        response_data = json.loads(response.body.decode('utf-8'))
        assert response_data["status"] == "success"
        assert response_data["data"]["enabled"] is True
        assert response_data["data"]["status"] == "running"

    @pytest.mark.asyncio
    async def test_start_scheduler(self, mock_app_with_scheduler):
        """Test starting scheduler."""
        from octopus_scraper.octopus_service import start_scheduler

        mock_request = Mock()

        with patch("octopus_scraper.octopus_service.app", mock_app_with_scheduler):
            response = await start_scheduler(mock_request)

        assert response.status == 200
        response_data = json.loads(response.body.decode('utf-8'))
        assert response_data["status"] == "success"
        assert "started successfully" in response_data["message"]

    @pytest.mark.asyncio
    async def test_stop_scheduler(self, mock_app_with_scheduler):
        """Test stopping scheduler."""
        from octopus_scraper.octopus_service import stop_scheduler

        mock_request = Mock()

        with patch("octopus_scraper.octopus_service.app", mock_app_with_scheduler):
            response = await stop_scheduler(mock_request)

        assert response.status == 200
        response_data = json.loads(response.body.decode('utf-8'))
        assert response_data["status"] == "success"
        assert "stopped successfully" in response_data["message"]

    @pytest.mark.asyncio
    async def test_list_schedules(self, mock_app_with_scheduler):
        """Test listing schedules."""
        from octopus_scraper.octopus_service import list_schedules

        mock_request = Mock()
        mock_request.args.get.return_value = "false"

        with patch("octopus_scraper.octopus_service.app", mock_app_with_scheduler):
            response = await list_schedules(mock_request)

        assert response.status == 200
        response_data = json.loads(response.body.decode('utf-8'))
        assert response_data["status"] == "success"
        assert "schedules" in response_data["data"]
        assert response_data["data"]["count"] == 1

    @pytest.mark.asyncio
    async def test_add_schedule_success(self, mock_app_with_scheduler):
        """Test adding a schedule successfully."""
        from octopus_scraper.octopus_service import add_schedule

        mock_request = Mock()
        mock_request.json = {
            "schedule_id": "test_schedule",
            "scraper_name": "sspai_scraper",
            "cron_expression": "0 12 * * *",
            "fetch_params": {"limit": 15},
            "max_concurrent_runs": 1,
            "timeout_seconds": 1800,
            "enabled": True,
        }

        with patch("octopus_scraper.octopus_service.app", mock_app_with_scheduler):
            response = await add_schedule(mock_request)

        assert response.status == 200
        response_data = json.loads(response.body.decode('utf-8'))
        assert response_data["status"] == "success"
        assert response_data["schedule_id"] == "test_schedule_123"

    @pytest.mark.asyncio
    async def test_add_schedule_missing_fields(self, mock_app_with_scheduler):
        """Test adding schedule with missing required fields."""
        from octopus_scraper.octopus_service import add_schedule

        mock_request = Mock()
        mock_request.json = {
            "schedule_id": "test_schedule",
            # Missing scraper_name and cron_expression
        }

        with patch("octopus_scraper.octopus_service.app", mock_app_with_scheduler):
            response = await add_schedule(mock_request)

        assert response.status == 400
        response_data = json.loads(response.body.decode('utf-8'))
        assert response_data["status"] == "error"
        assert "Missing required field" in response_data["message"]

    @pytest.mark.asyncio
    async def test_get_schedule_success(self, mock_app_with_scheduler):
        """Test getting a specific schedule."""
        from octopus_scraper.octopus_service import get_schedule

        mock_request = Mock()

        with patch("octopus_scraper.octopus_service.app", mock_app_with_scheduler):
            response = await get_schedule(mock_request, "daily_scraper")

        assert response.status == 200
        response_data = json.loads(response.body.decode('utf-8'))
        assert response_data["status"] == "success"
        assert response_data["data"]["schedule_id"] == "daily_scraper"

    @pytest.mark.asyncio
    async def test_remove_schedule_success(self, mock_app_with_scheduler):
        """Test removing a schedule successfully."""
        from octopus_scraper.octopus_service import remove_schedule

        mock_request = Mock()

        with patch("octopus_scraper.octopus_service.app", mock_app_with_scheduler):
            response = await remove_schedule(mock_request, "daily_scraper")

        assert response.status == 200
        response_data = json.loads(response.body.decode('utf-8'))
        assert response_data["status"] == "success"
        assert "removed successfully" in response_data["message"]

    @pytest.mark.asyncio
    async def test_enable_schedule_success(self, mock_app_with_scheduler):
        """Test enabling a schedule successfully."""
        from octopus_scraper.octopus_service import enable_schedule

        mock_request = Mock()

        with patch("octopus_scraper.octopus_service.app", mock_app_with_scheduler):
            response = await enable_schedule(mock_request, "daily_scraper")

        assert response.status == 200
        response_data = json.loads(response.body.decode('utf-8'))
        assert response_data["status"] == "success"
        assert "enabled successfully" in response_data["message"]

    @pytest.mark.asyncio
    async def test_disable_schedule_success(self, mock_app_with_scheduler):
        """Test disabling a schedule successfully."""
        from octopus_scraper.octopus_service import disable_schedule

        mock_request = Mock()

        with patch("octopus_scraper.octopus_service.app", mock_app_with_scheduler):
            response = await disable_schedule(mock_request, "daily_scraper")

        assert response.status == 200
        response_data = json.loads(response.body.decode('utf-8'))
        assert response_data["status"] == "success"
        assert "disabled successfully" in response_data["message"]

    @pytest.mark.asyncio
    async def test_trigger_schedule_now_success(self, mock_app_with_scheduler):
        """Test manually triggering a schedule successfully."""
        from octopus_scraper.octopus_service import trigger_schedule_now

        mock_request = Mock()

        with patch("octopus_scraper.octopus_service.app", mock_app_with_scheduler):
            response = await trigger_schedule_now(mock_request, "daily_scraper")

        assert response.status == 200
        response_data = json.loads(response.body.decode('utf-8'))
        assert response_data["status"] == "success"
        assert response_data["task_id"] == "task_456"
        assert "triggered successfully" in response_data["message"]

    @pytest.mark.asyncio
    async def test_scheduler_operations_scheduler_disabled(self):
        """Test scheduler operations when scheduler is disabled."""
        from octopus_scraper.octopus_service import get_scheduler_status

        # Mock octopus without scheduler
        mock_octopus = Mock()
        mock_octopus.get_scheduler_status.return_value = {
            "enabled": False,
            "status": "disabled",
            "message": "TaskScheduler not enabled in configuration",
        }

        mock_app = Mock()
        mock_app.ctx = Mock()
        mock_app.ctx.octopus = mock_octopus

        mock_request = Mock()

        with patch("octopus_scraper.octopus_service.app", mock_app):
            response = await get_scheduler_status(mock_request)

        assert response.status == 200
        response_data = json.loads(response.body.decode('utf-8'))
        assert response_data["data"]["enabled"] is False
        assert response_data["data"]["status"] == "disabled"

    @pytest.mark.asyncio
    async def test_scheduler_endpoints_exception_handling(
        self, mock_app_with_scheduler
    ):
        """Test exception handling in scheduler endpoints."""
        from octopus_scraper.octopus_service import get_scheduler_status

        mock_request = Mock()

        # Mock octopus to raise exception
        mock_app_with_scheduler.ctx.octopus.get_scheduler_status.side_effect = (
            Exception("Test error")
        )

        with patch("octopus_scraper.octopus_service.app", mock_app_with_scheduler):
            response = await get_scheduler_status(mock_request)

        assert response.status == 500
        response_data = json.loads(response.body.decode('utf-8'))
        assert response_data["status"] == "error"
        assert "Failed to get scheduler status" in response_data["message"]
