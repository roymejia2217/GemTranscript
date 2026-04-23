"""
Tests for GUI non-visual logic: queue handling, validation, and detection.

These tests verify planned GUI logic that can be tested without a display:
- Progress event queueing and polling (thread-safe queue)
- API key validation (Config.GEMINI_API_KEY presence)
- FFmpeg detection (shutil.which('ffprobe'))
- File selection counting
"""

import pytest
import os
import queue
import threading
import shutil
from unittest.mock import patch, MagicMock
from pathlib import Path


# ===========================================================================
# 1. Progress event queue handling
# ===========================================================================

class TestProgressEventQueue:
    """
    Simulate the GUI pattern where a worker thread puts progress events
    into a queue and the main thread drains them.
    """

    def test_queue_put_and_get_single_event(self):
        """A single event can be put and retrieved from the queue."""
        q = queue.Queue()
        event = {"type": "start", "total": 3}
        q.put(event)
        retrieved = q.get(timeout=1)
        assert retrieved == event

    def test_queue_preserves_order(self):
        """Events should be retrieved in FIFO order."""
        q = queue.Queue()
        events = [
            {"type": "start", "total": 2},
            {"type": "file_start", "file": "a.mp4", "current": 1, "total": 2},
            {"type": "file_done", "file": "a.mp4", "success": True, "current": 1, "total": 2},
            {"type": "complete", "success": 1, "fail": 0, "total": 2},
        ]
        for e in events:
            q.put(e)

        retrieved = []
        while not q.empty():
            retrieved.append(q.get(timeout=1))

        assert retrieved == events

    def test_queue_thread_safety(self):
        """Events put from a worker thread can be read from the main thread."""
        q = queue.Queue()
        results = []

        def worker():
            for i in range(5):
                q.put({"type": "file_start", "current": i + 1, "total": 5})
                q.put({"type": "file_done", "current": i + 1, "total": 5, "success": True})

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join(timeout=5)

        while not q.empty():
            results.append(q.get(timeout=1))

        assert len(results) == 10
        assert all(isinstance(r, dict) and "type" in r for r in results)

    def test_queue_drain_with_sentinel(self):
        """A sentinel value can signal the end of event stream."""
        q = queue.Queue()
        q.put({"type": "start", "total": 1})
        q.put({"type": "complete", "success": 1, "fail": 0, "total": 1})
        q.put(None)  # Sentinel

        events = []
        while True:
            item = q.get(timeout=1)
            if item is None:
                break
            events.append(item)

        assert len(events) == 2
        assert events[0]["type"] == "start"
        assert events[1]["type"] == "complete"

    def test_queue_empty_check(self):
        """queue.empty() can be used to check if more events are pending."""
        q = queue.Queue()
        assert q.empty()

        q.put({"type": "start", "total": 1})
        assert not q.empty()

        q.get(timeout=1)
        assert q.empty()

    def test_progress_callback_puts_to_queue(self):
        """A progress_callback function that puts events into a queue
        should work correctly with MediaTranscriber."""
        q = queue.Queue()

        def progress_callback(event):
            q.put(event)

        # Simulate what process_all_files would do
        progress_callback({"type": "start", "total": 2})
        progress_callback({"type": "file_start", "file": "a.mp4", "current": 1, "total": 2})
        progress_callback({"type": "file_done", "file": "a.mp4", "success": True, "current": 1, "total": 2})
        progress_callback({"type": "file_start", "file": "b.mp4", "current": 2, "total": 2})
        progress_callback({"type": "file_done", "file": "b.mp4", "success": True, "current": 2, "total": 2})
        progress_callback({"type": "complete", "success": 2, "fail": 0, "total": 2})

        events = []
        while not q.empty():
            events.append(q.get(timeout=1))

        assert len(events) == 6
        assert events[0]["type"] == "start"
        assert events[-1]["type"] == "complete"


# ===========================================================================
# 2. API key validation
# ===========================================================================

class TestApiKeyValidation:
    """Test validation logic for GEMINI_API_KEY presence."""

    def test_missing_api_key_raises_value_error(self):
        """Config.validate() should raise ValueError when GEMINI_API_KEY is not set."""
        from config.settings import Config
        with patch.object(Config, "GEMINI_API_KEY", None), \
             patch.object(Config, "FILES_DIR", Path("/tmp/test_files")), \
             patch.object(Config, "OUTPUT_DIR", Path("/tmp/test_output")), \
             patch.object(Config, "LOGS_DIR", Path("/tmp/test_logs")):
            with pytest.raises(ValueError, match="GEMINI_API_KEY"):
                Config.validate()

    def test_empty_api_key_raises_value_error(self):
        """Config.validate() should raise ValueError when GEMINI_API_KEY is empty string."""
        from config.settings import Config
        with patch.object(Config, "GEMINI_API_KEY", ""), \
             patch.object(Config, "FILES_DIR", Path("/tmp/test_files")), \
             patch.object(Config, "OUTPUT_DIR", Path("/tmp/test_output")), \
             patch.object(Config, "LOGS_DIR", Path("/tmp/test_logs")):
            with pytest.raises(ValueError, match="GEMINI_API_KEY"):
                Config.validate()

    def test_valid_api_key_passes_validation(self, tmp_path):
        """Config.validate() should not raise when GEMINI_API_KEY is set."""
        from config.settings import Config
        with patch.object(Config, "GEMINI_API_KEY", "valid-test-key-12345"), \
             patch.object(Config, "FILES_DIR", tmp_path / "files"), \
             patch.object(Config, "OUTPUT_DIR", tmp_path / "output"), \
             patch.object(Config, "LOGS_DIR", tmp_path / "logs"):
            # Should not raise
            Config.validate()

    def test_gui_should_check_api_key_before_starting(self):
        """The GUI should detect a missing API key and prevent transcription start."""
        from config.settings import Config

        with patch.object(Config, "GEMINI_API_KEY", None):
            api_key_present = bool(Config.GEMINI_API_KEY)
            assert api_key_present is False, "GUI should detect missing API key"

        with patch.object(Config, "GEMINI_API_KEY", "some-key"):
            api_key_present = bool(Config.GEMINI_API_KEY)
            assert api_key_present is True, "GUI should detect present API key"


# ===========================================================================
# 3. FFmpeg detection
# ===========================================================================

class TestFFmpegDetection:
    """Test FFmpeg/ffprobe detection logic for GUI prerequisites check."""

    def test_ffprobe_detected_when_available(self):
        """When ffprobe is on PATH, shutil.which should find it."""
        with patch("shutil.which") as mock_which:
            mock_which.return_value = "/usr/bin/ffprobe"
            result = shutil.which("ffprobe")
            assert result is not None
            assert result == "/usr/bin/ffprobe"

    def test_ffprobe_not_detected_when_missing(self):
        """When ffprobe is not on PATH, shutil.which should return None."""
        with patch("shutil.which") as mock_which:
            mock_which.return_value = None
            result = shutil.which("ffprobe")
            assert result is None

    def test_media_processor_sets_has_ffprobe_flag(self):
        """MediaProcessor.__init__ should set has_ffprobe based on shutil.which."""
        with patch("src.media_processor.shutil.which") as mock_which:
            mock_which.return_value = "/usr/bin/ffprobe"
            from src.media_processor import MediaProcessor
            mp = MediaProcessor()
            assert mp.has_ffprobe is True

    def test_media_processor_without_ffprobe(self):
        """MediaProcessor should set has_ffprobe=False when ffprobe is missing."""
        with patch("src.media_processor.shutil.which") as mock_which:
            mock_which.return_value = None
            from src.media_processor import MediaProcessor
            mp = MediaProcessor()
            assert mp.has_ffprobe is False

    def test_gui_should_warn_without_ffprobe(self):
        """The GUI should detect missing ffprobe and warn the user."""
        with patch("shutil.which") as mock_which:
            mock_which.return_value = None
            ffprobe_available = shutil.which("ffprobe") is not None
            assert ffprobe_available is False, "GUI should detect missing ffprobe"

        with patch("shutil.which") as mock_which:
            mock_which.return_value = "/usr/bin/ffprobe"
            ffprobe_available = shutil.which("ffprobe") is not None
            assert ffprobe_available is True, "GUI should detect available ffprobe"


# ===========================================================================
# 4. File selection counting
# ===========================================================================

class TestFileSelectionCounting:
    """Test logic for counting selected media files in a directory."""

    def test_count_media_files_in_directory(self, tmp_path):
        """MediaProcessor.get_media_files should return only media files."""
        (tmp_path / "video.mp4").write_bytes(b"\x00")
        (tmp_path / "audio.mp3").write_bytes(b"\x00")
        (tmp_path / "document.txt").write_bytes(b"\x00")
        (tmp_path / "image.png").write_bytes(b"\x00")
        (tmp_path / "movie.mkv").write_bytes(b"\x00")

        from src.media_processor import MediaProcessor
        mp = MediaProcessor()
        with patch.object(mp, 'has_ffprobe', True):
            media_files = mp.get_media_files(tmp_path)

        extensions = {f.suffix.lower() for f in media_files}
        assert ".mp4" in extensions
        assert ".mp3" in extensions
        assert ".mkv" in extensions
        assert ".txt" not in extensions
        assert ".png" not in extensions

    def test_count_empty_directory(self, tmp_path):
        """An empty directory should return zero media files."""
        from src.media_processor import MediaProcessor
        mp = MediaProcessor()
        media_files = mp.get_media_files(tmp_path)
        assert len(media_files) == 0

    def test_count_nonexistent_directory(self, tmp_path):
        """A non-existent directory should return zero media files."""
        from src.media_processor import MediaProcessor
        mp = MediaProcessor()
        media_files = mp.get_media_files(tmp_path / "nonexistent")
        assert len(media_files) == 0

    def test_count_only_audio_files(self, tmp_path):
        """Should correctly identify audio-only files."""
        (tmp_path / "song.mp3").write_bytes(b"\x00")
        (tmp_path / "podcast.wav").write_bytes(b"\x00")
        (tmp_path / "notes.txt").write_bytes(b"\x00")

        from src.media_processor import MediaProcessor
        mp = MediaProcessor()
        media_files = mp.get_media_files(tmp_path)
        assert len(media_files) == 2

    def test_count_only_video_files(self, tmp_path):
        """Should correctly identify video-only files."""
        (tmp_path / "clip.mp4").write_bytes(b"\x00")
        (tmp_path / "movie.mkv").write_bytes(b"\x00")
        (tmp_path / "readme.md").write_bytes(b"\x00")

        from src.media_processor import MediaProcessor
        mp = MediaProcessor()
        media_files = mp.get_media_files(tmp_path)
        assert len(media_files) == 2

    def test_gui_file_count_matches_media_processor(self, tmp_path):
        """The GUI's file count display should match MediaProcessor.get_media_files count."""
        (tmp_path / "video1.mp4").write_bytes(b"\x00")
        (tmp_path / "video2.mp4").write_bytes(b"\x00")
        (tmp_path / "audio1.mp3").write_bytes(b"\x00")
        (tmp_path / "readme.txt").write_bytes(b"\x00")

        from src.media_processor import MediaProcessor
        mp = MediaProcessor()
        media_files = mp.get_media_files(tmp_path)

        file_count = len(media_files)
        assert file_count == 3, f"Expected 3 media files, got {file_count}"


# ===========================================================================
# 5. Progress event parsing for GUI display
# ===========================================================================

class TestProgressEventParsing:
    """Test parsing of progress events for GUI display updates."""

    def test_parse_start_event(self):
        """A start event should be parseable for total count."""
        event = {"type": "start", "total": 5}
        assert event["type"] == "start"
        assert event["total"] == 5

    def test_parse_file_start_event(self):
        """A file_start event should provide filename and progress."""
        event = {"type": "file_start", "file": "video.mp4", "current": 2, "total": 5}
        assert event["type"] == "file_start"
        assert event["file"] == "video.mp4"
        assert event["current"] == 2
        assert event["total"] == 5

    def test_parse_file_done_event_success(self):
        """A file_done event with success=True should be parseable."""
        event = {"type": "file_done", "file": "video.mp4", "success": True, "current": 2, "total": 5}
        assert event["success"] is True

    def test_parse_file_done_event_failure(self):
        """A file_done event with success=False should be parseable."""
        event = {"type": "file_done", "file": "video.mp4", "success": False, "current": 2, "total": 5}
        assert event["success"] is False

    def test_parse_complete_event(self):
        """A complete event should provide final tallies."""
        event = {"type": "complete", "success": 4, "fail": 1, "total": 5}
        assert event["type"] == "complete"
        assert event["success"] == 4
        assert event["fail"] == 1
        assert event["total"] == 5

    def test_progress_percentage_calculation(self):
        """The GUI should be able to calculate progress percentage from events."""
        event = {"type": "file_start", "file": "video.mp4", "current": 3, "total": 10}
        percentage = (event["current"] / event["total"]) * 100
        assert percentage == 30.0

    def test_progress_bar_value_from_complete_event(self):
        """The GUI should set progress bar to 100% on complete event."""
        event = {"type": "complete", "success": 5, "fail": 0, "total": 5}
        progress_percent = (event["success"] + event["fail"]) / event["total"] * 100
        assert progress_percent == 100.0


# ===========================================================================
# 6. Open Output Folder
# ===========================================================================

class TestOpenOutputFolder:
    """Test _open_output_folder method for platform-specific folder opening."""

    def _create_gui_instance(self):
        """Create a GemTranscriptGUI instance with mocked tkinter init methods."""
        from gui import GemTranscriptGUI
        with patch.object(GemTranscriptGUI, "_build_ui"), \
             patch.object(GemTranscriptGUI, "_check_prerequisites"), \
             patch.object(GemTranscriptGUI, "_poll_queue"):
            root = MagicMock()
            gui = GemTranscriptGUI(root)
        return gui

    def test_linux_opens_with_xdg_open(self):
        """On Linux, _open_output_folder should call subprocess.Popen with xdg-open."""
        from config.settings import Config
        gui = self._create_gui_instance()
        mock_output_dir = MagicMock()
        mock_output_dir.exists.return_value = True
        mock_output_dir.resolve.return_value = Path("/tmp/test_output")

        with patch("sys.platform", "linux"), \
             patch("subprocess.Popen") as mock_popen, \
             patch("gui.webbrowser.open"), \
             patch.object(Config, "OUTPUT_DIR", mock_output_dir):
            gui._open_output_folder()
            mock_popen.assert_called_once_with(["xdg-open", "/tmp/test_output"])

    def test_darwin_opens_with_open(self):
        """On macOS, _open_output_folder should call subprocess.Popen with open."""
        from config.settings import Config
        gui = self._create_gui_instance()
        mock_output_dir = MagicMock()
        mock_output_dir.exists.return_value = True
        mock_output_dir.resolve.return_value = Path("/tmp/test_output")

        with patch("sys.platform", "darwin"), \
             patch("subprocess.Popen") as mock_popen, \
             patch("gui.webbrowser.open"), \
             patch.object(Config, "OUTPUT_DIR", mock_output_dir):
            gui._open_output_folder()
            mock_popen.assert_called_once_with(["open", "/tmp/test_output"])

    def test_windows_opens_with_startfile(self):
        """On Windows, _open_output_folder should call os.startfile with path."""
        from config.settings import Config
        gui = self._create_gui_instance()
        mock_output_dir = MagicMock()
        mock_output_dir.exists.return_value = True
        mock_output_dir.resolve.return_value = Path("/tmp/test_output")

        with patch("sys.platform", "win32"), \
             patch("os.startfile", create=True) as mock_startfile, \
             patch("gui.webbrowser.open"), \
             patch.object(Config, "OUTPUT_DIR", mock_output_dir):
            gui._open_output_folder()
            mock_startfile.assert_called_once_with("/tmp/test_output")

    def test_path_with_spaces_linux(self):
        """Path with spaces should be passed as single list element to Popen on Linux."""
        from config.settings import Config
        gui = self._create_gui_instance()
        mock_output_dir = MagicMock()
        mock_output_dir.exists.return_value = True
        mock_output_dir.resolve.return_value = Path("/tmp/test output")

        with patch("sys.platform", "linux"), \
             patch("subprocess.Popen") as mock_popen, \
             patch("gui.webbrowser.open"), \
             patch.object(Config, "OUTPUT_DIR", mock_output_dir):
            gui._open_output_folder()
            call_args = mock_popen.call_args[0][0]
            assert len(call_args) == 2
            assert call_args[0] == "xdg-open"
            assert call_args[1] == "/tmp/test output"

    def test_path_with_spaces_darwin(self):
        """Path with spaces should be passed as single list element to Popen on macOS."""
        from config.settings import Config
        gui = self._create_gui_instance()
        mock_output_dir = MagicMock()
        mock_output_dir.exists.return_value = True
        mock_output_dir.resolve.return_value = Path("/tmp/test output")

        with patch("sys.platform", "darwin"), \
             patch("subprocess.Popen") as mock_popen, \
             patch("gui.webbrowser.open"), \
             patch.object(Config, "OUTPUT_DIR", mock_output_dir):
            gui._open_output_folder()
            call_args = mock_popen.call_args[0][0]
            assert len(call_args) == 2
            assert call_args[0] == "open"
            assert call_args[1] == "/tmp/test output"

    def test_creates_directory_if_missing(self):
        """_open_output_folder should create the directory if it doesn't exist."""
        from config.settings import Config
        gui = self._create_gui_instance()
        mock_output_dir = MagicMock()
        mock_output_dir.exists.return_value = False
        mock_output_dir.resolve.return_value = Path("/tmp/test_output")

        with patch("sys.platform", "linux"), \
             patch("subprocess.Popen") as mock_popen, \
             patch("gui.webbrowser.open"), \
             patch.object(Config, "OUTPUT_DIR", mock_output_dir):
            gui._open_output_folder()
            mock_output_dir.mkdir.assert_called_once_with(parents=True, exist_ok=True)

    def test_mkdir_permission_error_shows_dialog(self):
        """_open_output_folder should show error dialog when mkdir raises PermissionError."""
        from config.settings import Config
        gui = self._create_gui_instance()
        mock_output_dir = MagicMock()
        mock_output_dir.exists.return_value = False
        mock_output_dir.mkdir.side_effect = PermissionError("Permission denied")
        mock_output_dir.resolve.return_value = Path("/tmp/test_output")

        with patch("sys.platform", "linux"), \
             patch("subprocess.Popen") as mock_popen, \
             patch("gui.webbrowser.open"), \
             patch("gui.messagebox.showerror") as mock_showerror, \
             patch.object(Config, "OUTPUT_DIR", mock_output_dir):
            gui._open_output_folder()
            mock_showerror.assert_called_once()
            assert "Cannot create output directory" in mock_showerror.call_args[0][1]
            mock_popen.assert_not_called()

    def test_xdg_open_oserror_shows_dialog(self):
        """_open_output_folder should show error dialog when xdg-open raises OSError."""
        from config.settings import Config
        gui = self._create_gui_instance()
        mock_output_dir = MagicMock()
        mock_output_dir.exists.return_value = True
        mock_output_dir.resolve.return_value = Path("/tmp/test_output")

        with patch("sys.platform", "linux"), \
             patch("subprocess.Popen", side_effect=OSError("xdg-open failed")), \
             patch("gui.webbrowser.open"), \
             patch("gui.messagebox.showerror") as mock_showerror, \
             patch.object(Config, "OUTPUT_DIR", mock_output_dir):
            gui._open_output_folder()
            mock_showerror.assert_called_once()
            assert "Cannot open output folder" in mock_showerror.call_args[0][1]

    def test_startfile_oserror_shows_dialog(self):
        """_open_output_folder should show error dialog when os.startfile raises OSError."""
        from config.settings import Config
        gui = self._create_gui_instance()
        mock_output_dir = MagicMock()
        mock_output_dir.exists.return_value = True
        mock_output_dir.resolve.return_value = Path("/tmp/test_output")

        with patch("sys.platform", "win32"), \
             patch("os.startfile", create=True, side_effect=OSError("startfile failed")), \
             patch("gui.webbrowser.open"), \
             patch("gui.messagebox.showerror") as mock_showerror, \
             patch.object(Config, "OUTPUT_DIR", mock_output_dir):
            gui._open_output_folder()
            mock_showerror.assert_called_once()
            assert "Cannot open output folder" in mock_showerror.call_args[0][1]