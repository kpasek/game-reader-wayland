import queue
import threading
import time
import pytest
from unittest.mock import MagicMock, patch
from app.player import PlayerThread

@pytest.fixture
def player_resources():
    stop_event = threading.Event()
    audio_queue = queue.Queue()
    pt = PlayerThread(stop_event, audio_queue)
    return pt, stop_event, audio_queue

@patch("subprocess.Popen")
@patch("os.path.exists", return_value=True)
def test_player_consumes_queue(mock_exists, mock_popen, player_resources):
    pt, stop_event, audio_queue = player_resources
    
    # Mock process behavior
    process_mock = MagicMock()
    process_mock.poll.side_effect = [None, 0] # Run once then finish
    mock_popen.return_value = process_mock
    
    # Add item to queue
    audio_file = "/tmp/test.mp3"
    audio_queue.put(audio_file)
    
    # Run in a separate thread so we can join it or just call run() if we mock specific loop break?
    # Player runs "while not stop_event.is_set()"
    # We can start it, let it process, then set stop event.
    
    t = threading.Thread(target=pt.run)
    t.start()
    
    time.sleep(0.1) # Give it time to pick up item
    stop_event.set()
    t.join(timeout=1)
    
    mock_popen.assert_called()
    args, _ = mock_popen.call_args
    cmd = args[0]
    # Check if command has ffplay and correct file
    assert "ffplay" in cmd[0] or cmd[0].endswith("ffplay")
    assert cmd[-1] == audio_file

@patch("subprocess.Popen")
@patch("os.path.exists", return_value=True)
def test_player_speed_calculation(mock_exists, mock_popen, player_resources):
    pt, stop_event, audio_queue = player_resources
    
    # Mock callbacks
    pt.base_speed_callback = MagicMock(return_value=1.5)
    pt.volume_callback = MagicMock(return_value=0.8)
    
    process_mock = MagicMock()
    process_mock.poll.return_value = 0
    mock_popen.return_value = process_mock
    
    # Pass tuple with dynamic multiplier
    audio_queue.put(("/tmp/speedy.mp3", 1.2))
    
    # Run one iteration logic manually to avoid threading complexity if possible? 
    # Or just loop thread shortly.
    t = threading.Thread(target=pt.run)
    t.start()
    time.sleep(0.1)
    stop_event.set()
    t.join(timeout=1)
    
    mock_popen.assert_called()
    args, _ = mock_popen.call_args
    cmd = args[0]
    
    # Expected speed = 1.5 * 1.2 = 1.8
    # Filter complex should contain atempo=1.80
    # Command structure: [ffplay, -nodisp, -autoexit, -af, FILTER_STRING, file]
    # So we check cmd[4]
    filter_arg = cmd[4] 
    assert "atempo=1.80" in filter_arg
    assert "volume=0.80" in filter_arg
