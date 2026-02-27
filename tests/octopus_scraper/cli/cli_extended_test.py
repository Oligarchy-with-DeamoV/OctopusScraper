import argparse
import os
import tempfile
from unittest.mock import Mock, mock_open, patch

import pytest
import yaml

from octopus_scraper.cli import (
    create_args,
    create_service_args,
    load_yml_config,
    run_octopus_go,
    run_octopus_service,
)


class TestCLI:
    def test_load_yml_config_valid_file(self):
        """测试加载有效的YAML配置文件"""
        config_data = {"test": "value", "number": 42}
        yaml_content = yaml.dump(config_data)

        with patch("builtins.open", mock_open(read_data=yaml_content)):
            result = load_yml_config("test.yml")
            assert result == config_data

    def test_load_yml_config_file_not_found(self):
        """测试文件不存在的情况"""
        with pytest.raises(FileNotFoundError):
            load_yml_config("nonexistent.yml")

    def test_load_yml_config_invalid_yaml(self):
        """测试无效YAML格式"""
        invalid_yaml = "invalid: yaml: content:"

        with patch("builtins.open", mock_open(read_data=invalid_yaml)):
            with pytest.raises(yaml.YAMLError):
                load_yml_config("invalid.yml")

    @patch("sys.argv", ["script", "--config", "test.yml"])
    def test_create_args_required_config(self):
        """测试必须提供config参数"""
        args = create_args()
        assert args.config == "test.yml"
        assert args.notion_upload is False

    @patch("sys.argv", ["script", "--config", "test.yml", "--notion_upload"])
    def test_create_args_with_notion_upload(self):
        """测试带notion_upload参数"""
        args = create_args()
        assert args.config == "test.yml"
        assert args.notion_upload is True

    @patch("sys.argv", ["script"])
    def test_create_args_missing_config(self):
        """测试缺少必须的config参数"""
        with pytest.raises(SystemExit):
            create_args()

    @patch("sys.argv", ["service", "--host", "127.0.0.1", "--port", "9000", "--debug"])
    def test_create_service_args_custom_values(self):
        """测试自定义服务参数"""
        args = create_service_args()
        assert args.host == "127.0.0.1"
        assert args.port == 9000
        assert args.debug is True

    @patch("sys.argv", ["service", "--log-level", "WARNING"])
    def test_create_service_args_log_level_choices(self):
        """测试日志级别选择"""
        args = create_service_args()
        assert args.log_level == "WARNING"

    @patch("sys.argv", ["service", "--log-format", "json"])
    def test_create_service_args_log_format_choices(self):
        """测试日志格式选择"""
        args = create_service_args()
        assert args.log_format == "json"

    @patch("octopus_scraper.cli.create_args")
    @patch("octopus_scraper.cli.load_yml_config")
    @patch("octopus_scraper.cli.Octopus")
    def test_run_octopus_go_without_notion_upload(
        self, mock_octopus, mock_load_config, mock_create_args
    ):
        """测试运行octopus不上传notion"""
        # Setup mocks
        mock_args = Mock()
        mock_args.config = "test.yml"
        mock_args.notion_upload = False
        mock_create_args.return_value = mock_args

        mock_config = {
            "scrapers_config_with_fetch_params": [],
            "notion_api_config": {"api_key": "test", "database_id": "test"},
        }
        mock_load_config.return_value = mock_config

        mock_instance = Mock()
        mock_octopus.return_value = mock_instance

        # Run function
        run_octopus_go()

        # Verify calls
        mock_load_config.assert_called_once_with("test.yml")
        mock_octopus.assert_called_once_with(mock_config)
        mock_instance.trigger_scraper.assert_called_once()
        mock_instance.trigger_upload.assert_not_called()

    @patch("octopus_scraper.cli.create_args")
    @patch("octopus_scraper.cli.load_yml_config")
    @patch("octopus_scraper.cli.Octopus")
    def test_run_octopus_go_with_notion_upload(
        self, mock_octopus, mock_load_config, mock_create_args
    ):
        """测试运行octopus并上传notion"""
        # Setup mocks
        mock_args = Mock()
        mock_args.config = "test.yml"
        mock_args.notion_upload = True
        mock_create_args.return_value = mock_args

        mock_config = {
            "scrapers_config_with_fetch_params": [],
            "notion_api_config": {"api_key": "test", "database_id": "test"},
        }
        mock_load_config.return_value = mock_config

        mock_instance = Mock()
        mock_octopus.return_value = mock_instance

        # Run function
        run_octopus_go()

        # Verify calls
        mock_load_config.assert_called_once_with("test.yml")
        mock_octopus.assert_called_once_with(mock_config)
        mock_instance.trigger_scraper.assert_called_once()
        mock_instance.trigger_upload.assert_called_once()

    @patch("octopus_scraper.cli.create_service_args")
    @patch("octopus_scraper.octopus_service.app")
    @patch("structlog.configure")
    @patch("structlog.getLogger")
    @patch("logging.getLogger")
    def test_run_octopus_service_single_process(
        self,
        mock_get_logger,
        mock_structlog_logger,
        mock_structlog,
        mock_app,
        mock_create_args,
    ):
        """测试单进程模式运行服务"""
        # Setup mocks
        mock_args = Mock()
        mock_args.host = "127.0.0.1"
        mock_args.port = 8000
        mock_args.debug = False
        mock_args.log_level = "INFO"
        mock_args.log_format = "plain"
        mock_args.single_process = True
        mock_args.workers = 1
        mock_create_args.return_value = mock_args

        # Mock logger
        mock_logger = Mock()
        mock_logger.name = "test_logger"
        mock_get_logger.return_value = mock_logger
        mock_structlog_logger.return_value = mock_logger

        # Run function
        run_octopus_service()

        # Verify service configuration
        expected_config = {
            "host": "127.0.0.1",
            "port": 8000,
            "debug": False,
            "single_process": True,
        }
        mock_app.run.assert_called_once_with(**expected_config)

    @patch("octopus_scraper.cli.create_service_args")
    @patch("octopus_scraper.octopus_service.app")
    @patch("structlog.configure")
    @patch("structlog.getLogger")
    @patch("logging.getLogger")
    def test_run_octopus_service_keyboard_interrupt(
        self,
        mock_get_logger,
        mock_structlog_logger,
        mock_structlog,
        mock_app,
        mock_create_args,
    ):
        """测试服务被用户中断"""
        # Setup mocks
        mock_args = Mock()
        mock_args.host = "127.0.0.1"
        mock_args.port = 8000
        mock_args.debug = False
        mock_args.log_level = "INFO"
        mock_args.log_format = "plain"
        mock_args.single_process = True
        mock_args.workers = 1
        mock_create_args.return_value = mock_args

        # Mock logger
        mock_logger = Mock()
        mock_logger.name = "test_logger"
        mock_get_logger.return_value = mock_logger
        mock_structlog_logger.return_value = mock_logger

        # Make app.run raise KeyboardInterrupt
        mock_app.run.side_effect = KeyboardInterrupt()

        # Run function - should not raise exception
        run_octopus_service()

    @patch("octopus_scraper.cli.create_service_args")
    @patch("octopus_scraper.octopus_service.app")
    @patch("structlog.configure")
    @patch("structlog.getLogger")
    @patch("logging.getLogger")
    def test_run_octopus_service_exception(
        self,
        mock_get_logger,
        mock_structlog_logger,
        mock_structlog,
        mock_app,
        mock_create_args,
    ):
        """测试服务启动异常"""
        # Setup mocks
        mock_args = Mock()
        mock_args.host = "127.0.0.1"
        mock_args.port = 8000
        mock_args.debug = False
        mock_args.log_level = "INFO"
        mock_args.log_format = "plain"
        mock_args.single_process = True
        mock_args.workers = 1
        mock_create_args.return_value = mock_args

        # Mock logger
        mock_logger = Mock()
        mock_logger.name = "test_logger"
        mock_get_logger.return_value = mock_logger
        mock_structlog_logger.return_value = mock_logger

        # Make app.run raise Exception
        mock_app.run.side_effect = Exception("Service failed")

        # Run function - should re-raise exception
        with pytest.raises(Exception, match="Service failed"):
            run_octopus_service()
