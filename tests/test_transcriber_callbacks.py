"""
Tests for MediaTranscriber progress_callback and file_list support.

These tests verify the planned additions to src/transcriber.py:
- process_all_files(file_list=None, progress_callback=None)
- _process_single_file(..., progress_callback=None, current_index=0, total=0)

When progress_callback is provided, it must receive dict events in order:
  {"type": "start", "total": int}
  {"type": "file_start", "file": str, "current": int, "total": int}
  {"type": "file_done", "file": str, "success": bool, "current": int, "total": int}
  {"type": "complete", "success": int, "fail": int, "total": int}

When progress_callback is None, CLI behavior must remain unchanged.
"""

import pytest
import os
from pathlib import Path
from unittest.mock import patch, MagicMock, call
import queue
import threading


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_media_dir(tmp_path):
    """Create a temporary media directory with dummy media files."""
    media_dir = tmp_path / "files"
    media_dir.mkdir()
    (media_dir / "video1.mp4").write_bytes(b"\x00" * 100)
    (media_dir / "audio1.mp3").write_bytes(b"\x00" * 100)
    (media_dir / "video2.mkv").write_bytes(b"\x00" * 100)
    return media_dir


@pytest.fixture
def tmp_output_dir(tmp_path):
    """Create a temporary output directory."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    return output_dir


@pytest.fixture
def tmp_logs_dir(tmp_path):
    """Create a temporary logs directory."""
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    return logs_dir


@pytest.fixture
def patched_config(tmp_path, tmp_media_dir, tmp_output_dir, tmp_logs_dir):
    """Patch Config to use temporary directories and a fake API key."""
    from config.settings import Config
    with patch.object(Config, "FILES_DIR", tmp_media_dir), \
         patch.object(Config, "OUTPUT_DIR", tmp_output_dir), \
         patch.object(Config, "LOGS_DIR", tmp_logs_dir), \
         patch.object(Config, "GEMINI_API_KEY", "fake-test-key"), \
         patch.object(Config, "MAX_WORKERS", 1):
        yield


@pytest.fixture
def mock_transcriber(patched_config):
    """
    Create a MediaTranscriber with mocked GeminiTranscriptionClient
    and MediaProcessor to avoid real API/FFmpeg calls.
    """
    with patch("src.transcriber.GeminiTranscriptionClient") as MockClient, \
         patch("src.transcriber.MediaProcessor") as MockProcessor:
        # Configure MediaProcessor mock
        mock_mp = MockProcessor.return_value
        mock_mp.get_media_duration.return_value = 60
        mock_mp.calculate_segments.return_value = [(None, None)]
        mock_mp.prepare_audio_for_upload.return_value = False

        # Configure GeminiTranscriptionClient mock
        mock_gc = MockClient.return_value
        mock_gc.transcribe_video_segment.return_value = "Test transcription text"

        from src.transcriber import MediaTranscriber
        transcriber = MediaTranscriber("test-model")

        # Replace with mocks
        transcriber.gemini_client = mock_gc
        transcriber.media_processor = mock_mp

        yield transcriber


# ===========================================================================
# 1. process_all_files accepts file_list and processes only those files
# ===========================================================================

class TestProcessAllFilesFileList:
    """Verify that process_all_files(file_list=...) processes only the given files."""

    def test_file_list_processes_only_specified_files(self, mock_transcriber, tmp_media_dir):
        """When file_list is provided, only those files should be processed."""
        all_files = list(tmp_media_dir.iterdir())
        single_file = [all_files[0]]

        # This will fail until file_list parameter is added
        mock_transcriber.process_all_files(file_list=single_file)

        mock_transcriber.gemini_client.transcribe_video_segment.assert_called()
        assert mock_transcriber.gemini_client.transcribe_video_segment.call_count == 1

    def test_file_list_empty_processes_nothing(self, mock_transcriber, tmp_media_dir):
        """An empty file_list should result in zero processing."""
        mock_transcriber.process_all_files(file_list=[])

        mock_transcriber.gemini_client.transcribe_video_segment.assert_not_called()

    def test_file_list_with_multiple_files(self, mock_transcriber, tmp_media_dir):
        """Multiple files in file_list should all be processed."""
        all_files = list(tmp_media_dir.iterdir())

        mock_transcriber.process_all_files(file_list=all_files)

        assert mock_transcriber.gemini_client.transcribe_video_segment.call_count == len(all_files)

    def test_file_list_overrides_directory_scan(self, mock_transcriber, tmp_media_dir):
        """When file_list is given, Config.FILES_DIR should NOT be scanned."""
        single_file = [list(tmp_media_dir.iterdir())[0]]

        mock_transcriber.process_all_files(file_list=single_file)

        # get_media_files should NOT be called when file_list is provided
        mock_transcriber.media_processor.get_media_files.assert_not_called()

    def test_no_file_list_scans_directory(self, mock_transcriber, tmp_media_dir):
        """When file_list is None (default), Config.FILES_DIR should be scanned."""
        mock_transcriber.process_all_files()

        mock_transcriber.media_processor.get_media_files.assert_called_once()


# ===========================================================================
# 2. progress_callback receives correct event sequence
# ===========================================================================

class TestProgressCallbackEvents:
    """Verify that progress_callback receives the correct dict events in order."""

    def test_callback_receives_start_event(self, mock_transcriber, tmp_media_dir):
        """First event should be {"type": "start", "total": N}."""
        events = []
        all_files = list(tmp_media_dir.iterdir())

        def capture_callback(event):
            events.append(event)

        mock_transcriber.process_all_files(
            file_list=all_files,
            progress_callback=capture_callback
        )

        start_events = [e for e in events if e["type"] == "start"]
        assert len(start_events) == 1
        assert start_events[0]["total"] == len(all_files)

    def test_callback_receives_file_start_events(self, mock_transcriber, tmp_media_dir):
        """Each file should produce a file_start event before processing."""
        events = []
        all_files = list(tmp_media_dir.iterdir())

        def capture_callback(event):
            events.append(event)

        mock_transcriber.process_all_files(
            file_list=all_files,
            progress_callback=capture_callback
        )

        file_start_events = [e for e in events if e["type"] == "file_start"]
        assert len(file_start_events) == len(all_files)

        for evt in file_start_events:
            assert "file" in evt
            assert "current" in evt
            assert "total" in evt
            assert evt["total"] == len(all_files)

    def test_callback_receives_file_done_events(self, mock_transcriber, tmp_media_dir):
        """Each file should produce a file_done event after processing."""
        events = []
        all_files = list(tmp_media_dir.iterdir())

        def capture_callback(event):
            events.append(event)

        mock_transcriber.process_all_files(
            file_list=all_files,
            progress_callback=capture_callback
        )

        file_done_events = [e for e in events if e["type"] == "file_done"]
        assert len(file_done_events) == len(all_files)

        for evt in file_done_events:
            assert "file" in evt
            assert "success" in evt
            assert "current" in evt
            assert "total" in evt

    def test_callback_receives_complete_event(self, mock_transcriber, tmp_media_dir):
        """Last event should be {"type": "complete", "success": N, "fail": M, "total": T}."""
        events = []
        all_files = list(tmp_media_dir.iterdir())

        def capture_callback(event):
            events.append(event)

        mock_transcriber.process_all_files(
            file_list=all_files,
            progress_callback=capture_callback
        )

        complete_events = [e for e in events if e["type"] == "complete"]
        assert len(complete_events) == 1
        complete = complete_events[0]
        assert "success" in complete
        assert "fail" in complete
        assert "total" in complete
        assert complete["total"] == len(all_files)
        assert complete["success"] + complete["fail"] == complete["total"]

    def test_callback_event_ordering(self, mock_transcriber, tmp_media_dir):
        """Events must arrive in order: start -> (file_start, file_done)* -> complete."""
        events = []
        all_files = list(tmp_media_dir.iterdir())

        def capture_callback(event):
            events.append(event)

        mock_transcriber.process_all_files(
            file_list=all_files,
            progress_callback=capture_callback
        )

        event_types = [e["type"] for e in events]

        # First event must be "start"
        assert event_types[0] == "start"

        # Last event must be "complete"
        assert event_types[-1] == "complete"

        # Between start and complete, events must alternate file_start/file_done
        middle_events = event_types[1:-1]
        for i in range(0, len(middle_events), 2):
            assert middle_events[i] == "file_start", \
                f"Expected file_start at position {i}, got {middle_events[i]}"
            if i + 1 < len(middle_events):
                assert middle_events[i + 1] == "file_done", \
                    f"Expected file_done at position {i+1}, got {middle_events[i+1]}"

    def test_callback_file_start_before_file_done_for_same_file(self, mock_transcriber, tmp_media_dir):
        """For each file, file_start must come before file_done."""
        events = []
        all_files = list(tmp_media_dir.iterdir())

        def capture_callback(event):
            events.append(event)

        mock_transcriber.process_all_files(
            file_list=all_files,
            progress_callback=capture_callback
        )

        started_files = {}
        for evt in events:
            if evt["type"] == "file_start":
                started_files[evt["file"]] = evt["current"]
            elif evt["type"] == "file_done":
                assert evt["file"] in started_files, \
                    f"file_done for {evt['file']} without file_start"

    def test_callback_current_indices_are_sequential(self, mock_transcriber, tmp_media_dir):
        """The 'current' field should increment from 1 to total."""
        events = []
        all_files = list(tmp_media_dir.iterdir())

        def capture_callback(event):
            events.append(event)

        mock_transcriber.process_all_files(
            file_list=all_files,
            progress_callback=capture_callback
        )

        file_start_events = [e for e in events if e["type"] == "file_start"]
        currents = [e["current"] for e in file_start_events]
        # Current should be 1-based indices
        assert sorted(currents) == list(range(1, len(all_files) + 1))


# ===========================================================================
# 3. progress_callback=None preserves existing CLI behavior
# ===========================================================================

class TestCallbackNoneBehavior:
    """Verify that progress_callback=None (default) preserves existing behavior."""

    def test_no_callback_no_error(self, mock_transcriber, tmp_media_dir):
        """process_all_files() without callback should work without errors."""
        result = mock_transcriber.process_all_files()
        # No exception means success

    def test_no_callback_processes_all_files(self, mock_transcriber, tmp_media_dir):
        """Without callback, all files in FILES_DIR should still be processed."""
        mock_transcriber.process_all_files()

        mock_transcriber.media_processor.get_media_files.assert_called_once()

    def test_no_callback_with_file_list(self, mock_transcriber, tmp_media_dir):
        """file_list works even when progress_callback is None."""
        all_files = list(tmp_media_dir.iterdir())

        mock_transcriber.process_all_files(file_list=all_files, progress_callback=None)

        assert mock_transcriber.gemini_client.transcribe_video_segment.call_count == len(all_files)


# ===========================================================================
# 4. Idempotency with callbacks
# ===========================================================================

class TestIdempotencyWithCallbacks:
    """Verify that skipping already-transcribed files still works with callbacks."""

    def test_skipped_file_still_emits_file_done_with_success_true(
        self, mock_transcriber, tmp_media_dir, tmp_output_dir
    ):
        """When a file is already transcribed (idempotent skip), it should still
        emit file_done with success=True."""
        all_files = list(tmp_media_dir.iterdir())
        first_file = all_files[0]

        # Create the output file to simulate already-transcribed
        output_filename = f"{first_file.stem}_transcription.txt"
        output_path = tmp_output_dir / output_filename
        output_path.write_text("Existing transcription", encoding="utf-8")

        events = []

        def capture_callback(event):
            events.append(event)

        mock_transcriber.process_all_files(
            file_list=[first_file],
            progress_callback=capture_callback
        )

        start_events = [e for e in events if e["type"] == "start"]
        complete_events = [e for e in events if e["type"] == "complete"]
        assert len(start_events) == 1
        assert len(complete_events) == 1

        # The skipped file should be counted as success
        assert complete_events[0]["success"] == 1
        assert complete_events[0]["fail"] == 0

    def test_skipped_file_emits_file_start_and_file_done(
        self, mock_transcriber, tmp_media_dir, tmp_output_dir
    ):
        """Even skipped files should emit file_start and file_done events."""
        all_files = list(tmp_media_dir.iterdir())
        first_file = all_files[0]

        output_filename = f"{first_file.stem}_transcription.txt"
        output_path = tmp_output_dir / output_filename
        output_path.write_text("Existing transcription", encoding="utf-8")

        events = []

        def capture_callback(event):
            events.append(event)

        mock_transcriber.process_all_files(
            file_list=[first_file],
            progress_callback=capture_callback
        )

        file_start_events = [e for e in events if e["type"] == "file_start"]
        file_done_events = [e for e in events if e["type"] == "file_done"]

        assert len(file_start_events) == 1
        assert len(file_done_events) == 1
        assert file_done_events[0]["success"] is True

    def test_mixed_skipped_and_new_files(
        self, mock_transcriber, tmp_media_dir, tmp_output_dir
    ):
        """When some files are already transcribed and some are new,
        both should emit events correctly."""
        all_files = list(tmp_media_dir.iterdir())

        # Mark the first file as already transcribed
        first_file = all_files[0]
        output_filename = f"{first_file.stem}_transcription.txt"
        output_path = tmp_output_dir / output_filename
        output_path.write_text("Existing transcription", encoding="utf-8")

        events = []

        def capture_callback(event):
            events.append(event)

        mock_transcriber.process_all_files(
            file_list=all_files,
            progress_callback=capture_callback
        )

        file_start_events = [e for e in events if e["type"] == "file_start"]
        file_done_events = [e for e in events if e["type"] == "file_done"]
        assert len(file_start_events) == len(all_files)
        assert len(file_done_events) == len(all_files)

        complete_events = [e for e in events if e["type"] == "complete"]
        assert complete_events[0]["total"] == len(all_files)


# ===========================================================================
# 5. _process_single_file with progress_callback
# ===========================================================================

class TestProcessSingleFileCallback:
    """Verify _process_single_file accepts and uses progress_callback."""

    def test_process_single_file_with_callback(self, mock_transcriber, tmp_media_dir, tmp_output_dir):
        """_process_single_file should accept progress_callback, current_index, and total."""
        all_files = list(tmp_media_dir.iterdir())
        first_file = all_files[0]

        events = []

        def capture_callback(event):
            events.append(event)

        # This will fail until _process_single_file signature is updated
        result = mock_transcriber._process_single_file(
            first_file,
            progress_callback=capture_callback,
            current_index=1,
            total=len(all_files)
        )

        file_start_events = [e for e in events if e["type"] == "file_start"]
        file_done_events = [e for e in events if e["type"] == "file_done"]

        assert len(file_start_events) == 1
        assert len(file_done_events) == 1
        assert file_start_events[0]["current"] == 1
        assert file_start_events[0]["total"] == len(all_files)

    def test_process_single_file_without_callback(self, mock_transcriber, tmp_media_dir, tmp_output_dir):
        """_process_single_file without callback should work as before."""
        all_files = list(tmp_media_dir.iterdir())
        first_file = all_files[0]

        # Should not raise any errors
        result = mock_transcriber._process_single_file(first_file)
        assert result is True

    def test_process_single_file_failure_emits_file_done(self, mock_transcriber, tmp_media_dir, tmp_output_dir):
        """When _process_single_file fails, it should emit file_done with success=False."""
        all_files = list(tmp_media_dir.iterdir())
        first_file = all_files[0]

        # Make transcription return empty string to simulate failure
        mock_transcriber.gemini_client.transcribe_video_segment.return_value = ""

        events = []

        def capture_callback(event):
            events.append(event)

        result = mock_transcriber._process_single_file(
            first_file,
            progress_callback=capture_callback,
            current_index=1,
            total=1
        )

        file_done_events = [e for e in events if e["type"] == "file_done"]
        assert len(file_done_events) == 1
        assert file_done_events[0]["success"] is False