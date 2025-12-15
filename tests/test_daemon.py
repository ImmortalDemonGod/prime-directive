import pytest
import time
from unittest.mock import patch, MagicMock, AsyncMock
from prime_directive.bin.pd_daemon import AutoFreezeHandler, main
from omegaconf import OmegaConf
from datetime import datetime, timedelta

@pytest.fixture
def mock_config(tmp_path):
    log_file = tmp_path / "pd.log"
    return OmegaConf.create(
        {
            "system": {
                "editor_cmd": "code",
                "ai_model": "gpt-4",
                "ollama_api_url": "http://localhost:11434/api/generate",
                "ollama_timeout_seconds": 5.0,
                "ollama_max_retries": 0,
                "ollama_backoff_seconds": 0.0,
                "db_path": ":memory:",
                "log_path": str(log_file),
                "mock_mode": False,
            },
            "repos": {
                "test-repo": {"id": "test-repo", "path": "/tmp/test-repo", "priority": 10, "active_branch": "main"}
            },
        }
    )

def test_handler_update():
    handler = AutoFreezeHandler("test-repo", None)
    initial_time = handler.last_modified
    handler.is_frozen = True  # Set to frozen to test reset
    
    # Simulate an event
    event = MagicMock()
    event.is_directory = False
    event.src_path = "/tmp/test-repo/file.py"
    
    time.sleep(0.01) # Ensure time advances
    handler.on_any_event(event)
    
    assert handler.last_modified > initial_time
    assert handler.is_frozen is False # Verify reset

@patch("prime_directive.bin.pd_daemon.load_config")
@patch("prime_directive.bin.pd_daemon.Observer")
@patch("prime_directive.bin.pd_daemon.time.sleep")
@patch("prime_directive.bin.pd_daemon.freeze_logic", new_callable=AsyncMock)
@patch("prime_directive.bin.pd_daemon.os.path.exists")
def test_daemon_loop(mock_exists, mock_freeze, mock_sleep, mock_observer, mock_load, mock_config):
    mock_load.return_value = mock_config
    mock_exists.return_value = True
    
    # mock_freeze is AsyncMock, so it returns an awaitable automatically
    
    # Mock Observer
    observer_instance = MagicMock()
    mock_observer.return_value = observer_instance
    
    # Control the infinite loop: run once then raise KeyboardInterrupt
    mock_sleep.side_effect = [None, KeyboardInterrupt]
    
    # Mock Handler state to trigger freeze
    with patch("prime_directive.bin.pd_daemon.AutoFreezeHandler") as MockHandlerClass:
        mock_handler = MagicMock()
        # Set last_modified to 1 hour ago
        mock_handler.last_modified = datetime.now() - timedelta(hours=1)
        # Explicitly set is_frozen to False so logic triggers
        mock_handler.is_frozen = False
        MockHandlerClass.return_value = mock_handler
        
        try:
            main(interval=1, inactivity_limit=1800) # 30 mins limit
        except KeyboardInterrupt:
            pass
        
        # Verify monitoring started
        observer_instance.schedule.assert_called_once()
        observer_instance.start.assert_called_once()
        
        # Verify freeze trigger
        mock_freeze.assert_called_with("test-repo", mock_config)
        
        # Verify handler state updated
        assert mock_handler.is_frozen is True
