import ctypes
import os
import re
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

__version__ = "1.2.1"

# Determine directory (handles development mode and PyInstaller extracted _MEIPASS bundle)
BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
DLL_PATH = os.path.join(BASE_DIR, "fastfilter.dll")

# Attempt to load the native C acceleration engine
C_FILTER_FUNC = None
C_FILTER_IS_WIDE = False

try:
    if os.path.exists(DLL_PATH):
        _clib = ctypes.CDLL(DLL_PATH)
        if hasattr(_clib, "process_file_fast_w"):
            C_FILTER_FUNC = _clib.process_file_fast_w
            C_FILTER_FUNC.argtypes = [
                ctypes.c_wchar_p,  # src_path
                ctypes.c_wchar_p,  # dst_path
                ctypes.c_int,      # min_len
                ctypes.c_int,      # max_len
                ctypes.c_int,      # charset_mode (0=all, 1=letters, 2=alnum, 3=ascii_printable)
                ctypes.c_int,      # output_mode  (0=list, 1=preserve)
                ctypes.c_int,      # dedup (0 or 1)
                ctypes.c_longlong, # split_lines (0=disabled)
                ctypes.c_longlong, # split_bytes (0=disabled)
            ]
            C_FILTER_FUNC.restype = ctypes.c_longlong
            C_FILTER_IS_WIDE = True
        elif hasattr(_clib, "process_file_fast"):
            C_FILTER_FUNC = _clib.process_file_fast
            C_FILTER_FUNC.argtypes = [
                ctypes.c_char_p,
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_longlong,
                ctypes.c_longlong,
            ]
            C_FILTER_FUNC.restype = ctypes.c_longlong
            C_FILTER_IS_WIDE = False
except Exception:
    C_FILTER_FUNC = None


class LengthFilterApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Word Length & Character Filter v{__version__}")
        self.root.geometry("690x560")
        self.root.minsize(620, 500)
        self.root.resizable(True, True)

        # Style configuration
        self.style = ttk.Style()
        self.style.theme_use("clam")

        # State variables
        self.file_path_var = tk.StringVar()
        self.dest_folder_var = tk.StringVar()
        self.preset_var = tk.StringVar(value="Custom / Manual")
        self.min_len_var = tk.StringVar(value="3")
        self.max_len_var = tk.StringVar(value="12")
        self.mode_var = tk.StringVar(value="list")
        self.unique_var = tk.BooleanVar(value=False)
        self.charset_var = tk.StringVar(value="all")
        self.custom_regex_var = tk.StringVar(value=r"^[a-zA-Z0-9_-]+$")

        # Output splitting state variables
        self.split_enabled_var = tk.BooleanVar(value=False)
        self.split_mode_var = tk.StringVar(value="lines")  # "lines" or "mb"
        self.split_lines_var = tk.StringVar(value="5000000")
        self.split_mb_var = tk.StringVar(value="1024")

        self.is_processing = False

        self._build_ui()

        # Keyboard shortcut: Enter key triggers filtering
        self.root.bind("<Return>", lambda event: self._process_file())

    def _build_ui(self):
        # 1. PERMANENT STICKY BOTTOM ACTION BAR (Packed first with side=BOTTOM so it's NEVER hidden)
        bottom_bar = ttk.Frame(self.root, padding="10 8 10 10", relief="groove")
        bottom_bar.pack(side=tk.BOTTOM, fill=tk.X)

        self.run_btn = ttk.Button(
            bottom_bar,
            text="▶  Start Filtering",
            command=self._process_file,
            width=22,
        )
        self.run_btn.pack(side=tk.LEFT, padx=(4, 12), ipady=5)

        engine_info = "Native C Engine (Ultra-Fast)" if C_FILTER_FUNC else "Standard Engine"
        self.status_label = ttk.Label(
            bottom_bar,
            text=f"Ready ({engine_info}). Select a source file and click Start Filtering.",
            foreground="#333333",
        )
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # 2. MAIN CONFIGURATION CONTAINER
        main_container = ttk.Frame(self.root, padding="12 10 12 4")
        main_container.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Section 1: Source File Selection
        src_frame = ttk.LabelFrame(main_container, text="1. Source Wordlist File", padding="6")
        src_frame.pack(fill=tk.X, pady=(0, 5))

        ttk.Entry(src_frame, textvariable=self.file_path_var).pack(
            side=tk.LEFT, padx=(0, 6), fill=tk.X, expand=True
        )
        ttk.Button(src_frame, text="Browse...", command=self._browse_source_file).pack(
            side=tk.RIGHT
        )

        # Section 2: Destination Folder Selection
        dest_frame = ttk.LabelFrame(main_container, text="2. Destination Folder (Optional - defaults to source dir)", padding="6")
        dest_frame.pack(fill=tk.X, pady=(0, 6))

        ttk.Entry(dest_frame, textvariable=self.dest_folder_var).pack(
            side=tk.LEFT, padx=(0, 6), fill=tk.X, expand=True
        )
        ttk.Button(dest_frame, text="Browse...", command=self._browse_dest_folder).pack(
            side=tk.RIGHT
        )

        # Responsive 2-Column Grid Layout for Settings
        cols_frame = ttk.Frame(main_container)
        cols_frame.pack(fill=tk.BOTH, expand=True)
        cols_frame.columnconfigure(0, weight=1)
        cols_frame.columnconfigure(1, weight=1)

        # ================= LEFT COLUMN =================
        left_col = ttk.Frame(cols_frame)
        left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        # Section 3: Presets
        preset_frame = ttk.LabelFrame(left_col, text="3. Quick Presets", padding="6")
        preset_frame.pack(fill=tk.X, pady=(0, 6))

        self.preset_combo = ttk.Combobox(
            preset_frame,
            textvariable=self.preset_var,
            state="readonly",
            values=[
                "Custom / Manual",
                "WPA2 Length (8-63 chars, ASCII Printable only)",
                "WPA2 Typical (8-16 chars, ASCII Printable only)",
                "Alphanumeric (8-16 chars)",
                "Letters Only (4-12 chars)",
            ],
        )
        self.preset_combo.pack(fill=tk.X, padx=2, pady=1)
        self.preset_combo.bind("<<ComboboxSelected>>", self._on_preset_change)

        # Section 4: Character Filter Rules
        char_frame = ttk.LabelFrame(left_col, text="4. Character Rules", padding="6")
        char_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Radiobutton(
            char_frame,
            text="Any characters (Standard words)",
            variable=self.charset_var,
            value="all",
            command=self._on_rule_manual_change,
        ).pack(anchor=tk.W, pady=1)

        ttk.Radiobutton(
            char_frame,
            text="Letters only (Exclude numbers/symbols)",
            variable=self.charset_var,
            value="letters",
            command=self._on_rule_manual_change,
        ).pack(anchor=tk.W, pady=1)

        ttk.Radiobutton(
            char_frame,
            text="Alphanumeric only (Letters and digits)",
            variable=self.charset_var,
            value="alnum",
            command=self._on_rule_manual_change,
        ).pack(anchor=tk.W, pady=1)

        ttk.Radiobutton(
            char_frame,
            text="ASCII printable only (32-126, WPA2/Wi-Fi)",
            variable=self.charset_var,
            value="ascii_printable",
            command=self._on_rule_manual_change,
        ).pack(anchor=tk.W, pady=1)

        custom_row = ttk.Frame(char_frame)
        custom_row.pack(fill=tk.X, pady=(2, 0))
        ttk.Radiobutton(
            custom_row,
            text="Custom Regex:",
            variable=self.charset_var,
            value="custom",
            command=self._on_rule_manual_change,
        ).pack(side=tk.LEFT)

        self.regex_entry = ttk.Entry(
            custom_row, textvariable=self.custom_regex_var, width=20, state="disabled"
        )
        self.regex_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))

        # ================= RIGHT COLUMN =================
        right_col = ttk.Frame(cols_frame)
        right_col.grid(row=0, column=1, sticky="nsew", padx=(5, 0))

        # Section 5: Length Controls
        len_frame = ttk.LabelFrame(right_col, text="5. Character Length Range", padding="6")
        len_frame.pack(fill=tk.X, pady=(0, 6))

        len_sub = ttk.Frame(len_frame)
        len_sub.pack(fill=tk.X)
        ttk.Label(len_sub, text="Minimum:").pack(side=tk.LEFT, padx=(2, 4))
        ttk.Spinbox(
            len_sub, from_=1, to=999, textvariable=self.min_len_var, width=6
        ).pack(side=tk.LEFT, padx=(0, 16))

        ttk.Label(len_sub, text="Maximum:").pack(side=tk.LEFT, padx=(2, 4))
        ttk.Spinbox(
            len_sub, from_=1, to=999, textvariable=self.max_len_var, width=6
        ).pack(side=tk.LEFT)

        # Section 6: Output & Deduplication
        opts_frame = ttk.LabelFrame(right_col, text="6. Output & Deduplication", padding="6")
        opts_frame.pack(fill=tk.X, pady=(0, 6))

        ttk.Radiobutton(
            opts_frame,
            text="One word per line (standard wordlist)",
            variable=self.mode_var,
            value="list",
        ).pack(anchor=tk.W, pady=1)

        ttk.Radiobutton(
            opts_frame,
            text="Preserve line structure",
            variable=self.mode_var,
            value="preserve",
        ).pack(anchor=tk.W, pady=1)

        ttk.Checkbutton(
            opts_frame,
            text="Remove duplicate words (deduplication)",
            variable=self.unique_var,
        ).pack(anchor=tk.W, pady=(2, 0))

        # Section 7: Output Splitting
        split_frame = ttk.LabelFrame(right_col, text="7. Output Splitting (Large Files)", padding="6")
        split_frame.pack(fill=tk.X)

        ttk.Checkbutton(
            split_frame,
            text="Split output into parts (_part1, _part2...)",
            variable=self.split_enabled_var,
            command=self._toggle_split_controls,
        ).pack(anchor=tk.W, pady=(0, 2))

        split_opts_frame = ttk.Frame(split_frame)
        split_opts_frame.pack(fill=tk.X, padx=4)

        split_line_row = ttk.Frame(split_opts_frame)
        split_line_row.pack(fill=tk.X, pady=1)
        ttk.Radiobutton(
            split_line_row,
            text="By count:",
            variable=self.split_mode_var,
            value="lines",
            command=self._toggle_split_controls,
        ).pack(side=tk.LEFT)
        self.split_lines_entry = ttk.Spinbox(
            split_line_row,
            from_=1000,
            to=1000000000,
            textvariable=self.split_lines_var,
            width=10,
            state="disabled",
        )
        self.split_lines_entry.pack(side=tk.LEFT, padx=(4, 4))
        ttk.Label(split_line_row, text="words/part").pack(side=tk.LEFT)

        split_mb_row = ttk.Frame(split_opts_frame)
        split_mb_row.pack(fill=tk.X, pady=1)
        ttk.Radiobutton(
            split_mb_row,
            text="By size:",
            variable=self.split_mode_var,
            value="mb",
            command=self._toggle_split_controls,
        ).pack(side=tk.LEFT)
        self.split_mb_entry = ttk.Spinbox(
            split_mb_row,
            from_=10,
            to=1000000,
            textvariable=self.split_mb_var,
            width=10,
            state="disabled",
        )
        self.split_mb_entry.pack(side=tk.LEFT, padx=(13, 4))
        ttk.Label(split_mb_row, text="MB/part").pack(side=tk.LEFT)

    def _toggle_split_controls(self):
        if self.split_enabled_var.get():
            if self.split_mode_var.get() == "lines":
                self.split_lines_entry.config(state="normal")
                self.split_mb_entry.config(state="disabled")
            else:
                self.split_lines_entry.config(state="disabled")
                self.split_mb_entry.config(state="normal")
        else:
            self.split_lines_entry.config(state="disabled")
            self.split_mb_entry.config(state="disabled")

    def _on_preset_change(self, event=None):
        choice = self.preset_var.get()
        if choice.startswith("WPA2 Length (8-63"):
            self.min_len_var.set("8")
            self.max_len_var.set("63")
            self.charset_var.set("ascii_printable")
            self._toggle_custom_regex()
            self.status_label.config(
                text="Preset applied: WPA2 Length (8-63 chars, ASCII printable). Press Enter to Start.",
                foreground="#0055d4",
            )
        elif choice.startswith("WPA2 Typical (8-16"):
            self.min_len_var.set("8")
            self.max_len_var.set("16")
            self.charset_var.set("ascii_printable")
            self._toggle_custom_regex()
            self.status_label.config(
                text="Preset applied: WPA2 Typical (8-16 chars, ASCII printable). Press Enter to Start.",
                foreground="#0055d4",
            )
        elif choice.startswith("Alphanumeric (8-16"):
            self.min_len_var.set("8")
            self.max_len_var.set("16")
            self.charset_var.set("alnum")
            self._toggle_custom_regex()
            self.status_label.config(
                text="Preset applied: Alphanumeric (8-16 chars). Press Enter to Start.",
                foreground="#0055d4",
            )
        elif choice.startswith("Letters Only (4-12"):
            self.min_len_var.set("4")
            self.max_len_var.set("12")
            self.charset_var.set("letters")
            self._toggle_custom_regex()
            self.status_label.config(
                text="Preset applied: Letters Only (4-12 chars). Press Enter to Start.",
                foreground="#0055d4",
            )

    def _on_rule_manual_change(self):
        self._toggle_custom_regex()
        current_rule = self.charset_var.get()
        min_v = self.min_len_var.get()
        max_v = self.max_len_var.get()

        if current_rule == "ascii_printable" and min_v == "8" and max_v == "63":
            self.preset_var.set("WPA2 Length (8-63 chars, ASCII Printable only)")
        elif current_rule == "ascii_printable" and min_v == "8" and max_v == "16":
            self.preset_var.set("WPA2 Typical (8-16 chars, ASCII Printable only)")
        elif current_rule == "alnum" and min_v == "8" and max_v == "16":
            self.preset_var.set("Alphanumeric (8-16 chars)")
        elif current_rule == "letters" and min_v == "4" and max_v == "12":
            self.preset_var.set("Letters Only (4-12 chars)")
        else:
            self.preset_var.set("Custom / Manual")

    def _toggle_custom_regex(self):
        if self.charset_var.get() == "custom":
            self.regex_entry.config(state="normal")
        else:
            self.regex_entry.config(state="disabled")

    def _browse_source_file(self):
        chosen_path = filedialog.askopenfilename(
            title="Select Text / Wordlist File",
            filetypes=[("All Files", "*.*"), ("Text Files", "*.txt"), ("Wordlists", "*.dict;*.lst")],
        )
        if chosen_path:
            self.file_path_var.set(chosen_path)
            if not self.dest_folder_var.get().strip():
                self.dest_folder_var.set(os.path.dirname(chosen_path))
            self.status_label.config(
                text=f"Selected: {os.path.basename(chosen_path)} — Click 'Start Filtering' to run.",
                foreground="#000000",
            )

    def _browse_dest_folder(self):
        current_dir = self.dest_folder_var.get().strip()
        if not current_dir and self.file_path_var.get().strip():
            current_dir = os.path.dirname(self.file_path_var.get().strip())
        if not current_dir or not os.path.isdir(current_dir):
            current_dir = os.getcwd()

        chosen_dir = filedialog.askdirectory(
            title="Select Destination Folder",
            initialdir=current_dir,
        )
        if chosen_dir:
            self.dest_folder_var.set(chosen_dir)

    def _get_validator(self):
        mode = self.charset_var.get()
        if mode == "letters":
            pattern = re.compile(r"^[a-zA-Z]+$")
            return lambda word: bool(pattern.match(word))
        elif mode == "alnum":
            pattern = re.compile(r"^[a-zA-Z0-9]+$")
            return lambda word: bool(pattern.match(word))
        elif mode == "ascii_printable":
            pattern = re.compile(r"^[\x20-\x7E]+$")
            return lambda word: bool(pattern.match(word))
        elif mode == "custom":
            raw_pattern = self.custom_regex_var.get().strip()
            try:
                pattern = re.compile(raw_pattern)
                return lambda word: bool(pattern.match(word))
            except re.error as e:
                raise ValueError(f"Invalid custom regular expression:\n{e}")
        return lambda word: True

    def _run_python_filter(self, source_path, output_path, min_len, max_len, charset_mode, mode, dedup, split_lines, split_bytes):
        char_validator = self._get_validator()
        if charset_mode == "ascii_printable":
            word_token_pattern = re.compile(r"\s+")
        else:
            word_token_pattern = re.compile(r"[^\w'-]+")

        total_kept = 0
        seen_words = set()

        base, ext = os.path.splitext(output_path)
        is_split = split_lines > 0 or split_bytes > 0
        part_num = 1
        curr_lines = 0
        curr_bytes = 0

        def get_current_out_path(p_idx):
            return f"{base}_part{p_idx}{ext}" if is_split else output_path

        out_f = open(get_current_out_path(part_num), "w", encoding="utf-8", errors="replace")

        def check_rollover():
            nonlocal out_f, part_num, curr_lines, curr_bytes
            if is_split:
                if (split_lines > 0 and curr_lines >= split_lines) or (split_bytes > 0 and curr_bytes >= split_bytes):
                    out_f.close()
                    part_num += 1
                    curr_lines = 0
                    curr_bytes = 0
                    out_f = open(get_current_out_path(part_num), "w", encoding="utf-8", errors="replace")

        try:
            with open(source_path, "r", encoding="utf-8", errors="replace") as in_f:
                if mode == "list":
                    for line in in_f:
                        tokens = word_token_pattern.split(line.strip())
                        for token in tokens:
                            clean_token = token if charset_mode == "ascii_printable" else token.strip("'-_")
                            if min_len <= len(clean_token) <= max_len and char_validator(clean_token):
                                if dedup:
                                    normalized = clean_token if charset_mode == "ascii_printable" else clean_token.lower()
                                    if normalized in seen_words:
                                        continue
                                    seen_words.add(normalized)
                                check_rollover()
                                out_f.write(clean_token + "\n")
                                curr_lines += 1
                                curr_bytes += len(clean_token.encode("utf-8")) + 1
                                total_kept += 1
                else:
                    for line in in_f:
                        words = word_token_pattern.split(line.strip())
                        kept_in_line = []
                        for token in words:
                            clean_token = token if charset_mode == "ascii_printable" else token.strip("'-_")
                            if min_len <= len(clean_token) <= max_len and char_validator(clean_token):
                                if dedup:
                                    normalized = clean_token if charset_mode == "ascii_printable" else clean_token.lower()
                                    if normalized in seen_words:
                                        continue
                                    seen_words.add(normalized)
                                kept_in_line.append(clean_token)
                                total_kept += 1
                        if kept_in_line:
                            check_rollover()
                            line_str = " ".join(kept_in_line) + "\n"
                            out_f.write(line_str)
                            curr_lines += 1
                            curr_bytes += len(line_str.encode("utf-8"))
        finally:
            out_f.close()

        return total_kept

    def _process_file(self):
        if self.is_processing:
            return

        source_path = self.file_path_var.get().strip()
        if not source_path or not os.path.isfile(source_path):
            messagebox.showerror("Error", "Please select a valid source file first.")
            return

        # Validate range values
        try:
            min_len = int(self.min_len_var.get())
            max_len = int(self.max_len_var.get())
        except ValueError:
            messagebox.showerror(
                "Error", "Minimum and Maximum lengths must be integers."
            )
            return

        if min_len < 1:
            messagebox.showerror("Error", "Minimum length must be at least 1.")
            return

        if min_len > max_len:
            messagebox.showerror(
                "Error", "Minimum length cannot be greater than Maximum length."
            )
            return

        # Validate regex if custom mode selected
        charset_mode = self.charset_var.get()
        if charset_mode == "custom":
            try:
                self._get_validator()
            except ValueError as err:
                messagebox.showerror("Regex Error", str(err))
                return

        # Validate splitting thresholds
        split_lines = 0
        split_bytes = 0
        if self.split_enabled_var.get():
            if self.split_mode_var.get() == "lines":
                try:
                    split_lines = int(self.split_lines_var.get())
                    if split_lines < 1:
                        raise ValueError()
                except ValueError:
                    messagebox.showerror("Error", "Split word count must be a positive integer.")
                    return
            else:
                try:
                    split_mb = int(self.split_mb_var.get())
                    if split_mb < 1:
                        raise ValueError()
                    split_bytes = split_mb * 1024 * 1024
                except ValueError:
                    messagebox.showerror("Error", "Split file size must be a positive integer in MB.")
                    return

        # Destination folder setup
        source_dir, original_name = os.path.split(source_path)
        dest_dir = self.dest_folder_var.get().strip()
        if not dest_dir or not os.path.isdir(dest_dir):
            dest_dir = source_dir

        output_filename = f"lengthfilter_{original_name}"
        output_path = os.path.join(dest_dir, output_filename)
        mode = self.mode_var.get()
        dedup = bool(self.unique_var.get())

        # Set UI to busy state
        self.is_processing = True
        self.run_btn.config(state="disabled", text="⏳  Filtering... Please wait")
        self.status_label.config(text="Processing file in background...", foreground="#0055d4")

        # Worker thread for smooth non-blocking UI
        def worker():
            err = None
            total_kept = 0
            try:
                if C_FILTER_FUNC and charset_mode in ("all", "letters", "alnum", "ascii_printable"):
                    c_mode = 0 if mode == "list" else 1
                    if charset_mode == "letters":
                        c_charset = 1
                    elif charset_mode == "alnum":
                        c_charset = 2
                    elif charset_mode == "ascii_printable":
                        c_charset = 3
                    else:
                        c_charset = 0
                    c_dedup = 1 if dedup else 0

                    if C_FILTER_IS_WIDE:
                        res = C_FILTER_FUNC(source_path, output_path, min_len, max_len, c_charset, c_mode, c_dedup, split_lines, split_bytes)
                    else:
                        res = C_FILTER_FUNC(
                            source_path.encode("utf-8"),
                            output_path.encode("utf-8"),
                            min_len,
                            max_len,
                            c_charset,
                            c_mode,
                            c_dedup,
                            split_lines,
                            split_bytes,
                        )

                    if res < 0:
                        raise RuntimeError(f"Native engine failed with error code {res}")
                    total_kept = res
                else:
                    total_kept = self._run_python_filter(
                        source_path, output_path, min_len, max_len, charset_mode, mode, dedup, split_lines, split_bytes
                    )
            except Exception as e:
                err = str(e)

            self.root.after(0, lambda: self._on_complete(err, total_kept, output_filename, dest_dir, split_lines > 0 or split_bytes > 0))

        threading.Thread(target=worker, daemon=True).start()

    def _on_complete(self, err, total_kept, output_filename, directory, was_split):
        self.is_processing = False
        self.run_btn.config(state="normal", text="▶  Start Filtering")

        if err:
            self.status_label.config(text=f"Error: {err}", foreground="#cc0000")
            messagebox.showerror("Processing Error", f"An error occurred while processing:\n{err}")
        else:
            if was_split:
                status_txt = f"Done! {total_kept:,} words saved across split parts (_part1, _part2...)"
                msg_body = (
                    f"Filtered list saved successfully across multiple parts!\n\n"
                    f"Total retained words: {total_kept:,}\n"
                    f"Output parts pattern: {output_filename.replace('.', '_partN.')}\n"
                    f"Destination folder: {directory}"
                )
            else:
                status_txt = f"Done! {total_kept:,} words saved to {output_filename}"
                msg_body = (
                    f"Filtered list saved successfully!\n\n"
                    f"Retained words: {total_kept:,}\n"
                    f"Output file: {output_filename}\n"
                    f"Destination folder: {directory}"
                )

            self.status_label.config(text=status_txt, foreground="#008000")
            messagebox.showinfo("Success", msg_body)


if __name__ == "__main__":
    app_window = tk.Tk()
    app = LengthFilterApp(app_window)
    app_window.mainloop()