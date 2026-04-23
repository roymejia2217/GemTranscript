import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import queue
import shutil
import webbrowser
from pathlib import Path

from config.settings import Config
from src.transcriber import MediaTranscriber
from src.model_resolver import resolve_model, ModelResolutionError


class GemTranscriptGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("GemTranscript")
        self.root.geometry("600x400")

        self.selected_files = []
        self.event_queue = queue.Queue()
        self.resolved_model = None

        self._build_ui()
        self._check_prerequisites()
        self._poll_queue()

    def _build_ui(self):
        self.btn_select = tk.Button(self.root, text="Select Files", command=self._select_files)
        self.btn_select.pack(pady=5)

        self.lbl_files = tk.Label(self.root, text="No files selected")
        self.lbl_files.pack(pady=5)

        self.btn_transcribe = tk.Button(self.root, text="Transcribe", command=self._start_transcription)
        self.btn_transcribe.pack(pady=5)

        self.btn_open = tk.Button(self.root, text="Open Output Folder", command=self._open_output_folder)
        self.btn_open.pack(pady=5)

        self.progress = ttk.Progressbar(self.root, orient="horizontal", length=400, mode="determinate")
        self.progress.pack(pady=10)

        self.lbl_status = tk.Label(self.root, text="Ready")
        self.lbl_status.pack(pady=5)

        self.lbl_detail = tk.Label(self.root, text="")
        self.lbl_detail.pack(pady=5)

    def _check_prerequisites(self):
        warnings = []
        if not Config.GEMINI_API_KEY:
            warnings.append("GEMINI_API_KEY not configured")
        if not shutil.which("ffprobe"):
            warnings.append("ffprobe not found")

        if warnings:
            self.lbl_status.config(text="Warning: " + "; ".join(warnings))
            self.btn_transcribe.config(state="disabled")
            return

        # Resolve model
        try:
            self.resolved_model = resolve_model(Config.GEMINI_API_KEY, Config.GEMINI_MODEL_NAME)
            self.lbl_status.config(text=f"Ready (model: {self.resolved_model})")
        except ModelResolutionError as e:
            messagebox.showerror("Model Error", str(e))
            self.lbl_status.config(text="Error: No valid model found")
            self.btn_transcribe.config(state="disabled")
            return

    def _select_files(self):
        files = filedialog.askopenfilenames(
            title="Select Media Files",
            filetypes=[
                ("Media Files", "*.mp4 *.mkv *.avi *.mp3 *.wav *.m4a *.flac *.ogg"),
                ("All Files", "*.*"),
            ],
        )
        if files:
            self.selected_files = list(files)
            count = len(self.selected_files)
            self.lbl_files.config(text=f"{count} file(s) selected")

    def _start_transcription(self):
        if not self.selected_files:
            messagebox.showwarning("No Files", "Please select files first.")
            return

        self.btn_transcribe.config(state="disabled")
        self.btn_select.config(state="disabled")
        self.progress["value"] = 0
        self.lbl_status.config(text="Transcribing...")

        thread = threading.Thread(target=self._transcribe_worker, daemon=True)
        thread.start()

    def _transcribe_worker(self):
        def callback(event):
            self.event_queue.put(event)

        transcriber = MediaTranscriber(self.resolved_model)
        file_paths = [Path(f) for f in self.selected_files]
        transcriber.process_all_files(file_list=file_paths, progress_callback=callback)
        self.event_queue.put(None)  # Sentinel

    def _poll_queue(self):
        try:
            while True:
                event = self.event_queue.get_nowait()
                if event is None:
                    self.btn_transcribe.config(state="normal")
                    self.btn_select.config(state="normal")
                    self.lbl_status.config(text="Completed")
                    self.progress["value"] = 100
                    break

                if event["type"] == "start":
                    self.progress["maximum"] = event["total"]
                elif event["type"] == "file_start":
                    self.lbl_detail.config(text=f"Processing: {Path(event['file']).name}")
                elif event["type"] == "file_done":
                    self.progress["value"] = event["current"]
                elif event["type"] == "complete":
                    self.lbl_status.config(
                        text=f"Done: {event['success']} success, {event['fail']} failed"
                    )
                    self.progress["value"] = event["total"]
        except queue.Empty:
            pass

        self.root.after(100, self._poll_queue)

    def _open_output_folder(self):
        output_dir = Config.OUTPUT_DIR
        if not output_dir.exists():
            output_dir.mkdir(parents=True, exist_ok=True)
        webbrowser.open(f"file://{output_dir.resolve()}")


def main():
    root = tk.Tk()
    app = GemTranscriptGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
