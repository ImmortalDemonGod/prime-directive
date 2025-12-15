import pytest
from unittest.mock import patch, Mock
import requests
from prime_directive.core.scribe import generate_sitrep

def test_generate_sitrep_success():
    mock_response = Mock()
    mock_response.json.return_value = {"response": "SITREP: All systems go. Next: Deploy."}
    mock_response.raise_for_status.return_value = None

    with patch("requests.post", return_value=mock_response) as mock_post:
        result = generate_sitrep(
            repo_id="test-repo",
            git_state="clean",
            terminal_logs="echo hello",
            active_task={"id": 1, "title": "Test Task", "description": "Testing"}
        )
        
        assert result == "SITREP: All systems go. Next: Deploy."
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert kwargs["json"]["model"] == "qwen2.5-coder"
        assert "Test Task" in kwargs["json"]["prompt"]

def test_generate_sitrep_timeout():
    with patch("requests.post", side_effect=requests.exceptions.Timeout("Timed out")):
        result = generate_sitrep(
            repo_id="test-repo",
            git_state="clean",
            terminal_logs="loading..."
        )
        assert "Error generating SITREP" in result
        assert "Timed out" in result

def test_generate_sitrep_connection_error():
    with patch("requests.post", side_effect=requests.exceptions.ConnectionError("Connection refused")):
        result = generate_sitrep(
            repo_id="test-repo",
            git_state="clean",
            terminal_logs="loading..."
        )
        assert "Error generating SITREP" in result
        assert "Connection refused" in result
