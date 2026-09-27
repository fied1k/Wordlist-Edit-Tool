import ctypes
import os
import re
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

__version__ = "1.1.0"

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
            ]
            C_FILTER_FUNC.restype = ctypes.c_longlong
            C_FILTER_IS_WIDE = False
except Exception:
    C_FILTER_FUNC = None


class LengthFilterApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Word Length & Character Filter v{__version__}")
        self.root.geometry("580x650")
        self.root.minsize(540, 600)
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
        self.is_processing = False

        self._build_ui()

    def _build_ui(self):
        container = ttk.Frame(self.root, padding="14")
        container.pack(fill=tk.BOTH, expand=True)

        # 1. Source File Selection
        src_frame = ttk.LabelFrame(container, text="1. Source Wordlist File", padding="8")
        src_frame.pack(fill=tk.X, pady=(0, 8))

        ttk.Entry(src_frame, textvariable=self.file_path_var).pack(
            side=tk.LEFT, padx=(0, 8), fill=tk.X, expand=True
        )
        ttk.Button(src_frame, text="Browse...", command=self._browse_source_file).pack(
            side=tk.RIGHT
        )

        # 2. Destination Folder Selection
        dest_frame = ttk.LabelFrame(container, text="2. Destination Folder (Optional)", padding="8")
        dest_frame.pack(fill=tk.X, pady=(0, 8))

        ttk.Entry(dest_frame, textvariable=self.dest_folder_var).pack(
            side=tk.LEFT, padx=(0, 8), fill=tk.X, expand=True
        )
        ttk.Button(dest_frame, text="Browse...", command=self._browse_dest_folder).pack(
            side=tk.RIGHT
        )

        # 3. Rule Presets
        preset_frame = ttk.LabelFrame(container, text="3. Quick Presets", padding="8")
        preset_frame.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(preset_frame, text="Select Preset:").pack(side=tk.LEFT, padx=(4, 8))
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
            width=45,
        )
        self.preset_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        self.preset_combo.bind("<<ComboboxSelected>>", self._on_preset_change)

        # 4. Length Range Controls
        len_frame = ttk.LabelFrame(container, text="4. Character Length Range", padding="8")
        len_frame.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(len_frame, text="Minimum:").grid(row=0, column=0, sticky=tk.W, padx=4)
        ttk.Spinbox(
            len_frame, from_=1, to=999, textvariable=self.min_len_var, width=6
        ).grid(row=0, column=1, sticky=tk.W, padx=(0, 24))

        ttk.Label(len_frame, text="Maximum:").grid(row=0, column=2, sticky=tk.W, padx=4)
        ttk.Spinbox(
            len_frame, from_=1, to=999, textvariable=self.max_len_var, width=6
        ).grid(row=0, column=3, sticky=tk.W, padx=4)

        # 5. Character Filter Rules
        char_frame = ttk.LabelFrame(container, text="5. Character Rules", padding="8")
        char_frame.pack(fill=tk.X, pady=(0, 8))

        ttk.Radiobutton(
            char_frame,
            text="Any characters (Standard words with hyphens/apostrophes)",
            variable=self.charset_var,
            value="all",
            command=self._on_rule_manual_change,
        ).grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=1)

        ttk.Radiobutton(
            char_frame,
            text="Letters only (Exclude numbers, punctuation, and symbols)",
            variable=self.charset_var,
            value="letters",
            command=self._on_rule_manual_change,
        ).grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=1)

        ttk.Radiobutton(
            char_frame,
            text="Alphanumeric only (Letters and digits, no punctuation)",
            variable=self.charset_var,
            value="alnum",
            command=self._on_rule_manual_change,
        ).grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=1)

        ttk.Radiobutton(
            char_frame,
            text="ASCII printable only (32-126, WPA2 / Wi-Fi keys, preserved symbols)",
            variable=self.charset_var,
            value="ascii_printable",
            command=self._on_rule_manual_change,
        ).grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=1)

        ttk.Radiobutton(
            char_frame,
            text="Custom Regex match:",
            variable=self.charset_var,
            value="custom",
            command=self._on_rule_manual_change,
        ).grid(row=4, column=0, sticky=tk.W, pady=1)

        self.regex_entry = ttk.Entry(
            char_frame, textvariable=self.custom_regex_var, width=28, state="disabled"
        )
        self.regex_entry.grid(row=4, column=1, sticky=tk.W, padx=(8, 0), pady=1)

        # 6. Output Options
        opts_frame = ttk.LabelFrame(container, text="6. Output Options", padding="8")
        opts_frame.pack(fill=tk.X, pady=(0, 8))

        ttk.Radiobutton(
            opts_frame,
            text="One word per line (wordlist format)",
            variable=self.mode_var,
            value="list",
        ).pack(anchor=tk.W)

        ttk.Radiobutton(
            opts_frame,
            text="Preserve line structure (filter words within each line)",
            variable=self.mode_var,
            value="preserve",
        ).pack(anchor=tk.W)

        ttk.Checkbutton(
            opts_frame,
            text="Remove duplicate words (deduplication)",
            variable=self.unique_var,
        ).pack(anchor=tk.W, pady=(3, 0))

        # 7. Action Button & Status
        self.run_btn = ttk.Button(
            container, text="Filter and Save", command=self._process_file
        )
        self.run_btn.pack(fill=tk.X, pady=(2, 6))

        engine_info = "Native C Acceleration" if C_FILTER_FUNC else "Standard Engine"
        self.status_label = ttk.Label(
            container, text=f"Ready ({engine_info}). Select a source file to begin.", foreground="#555555"
        )
        self.status_label.pack(anchor=tk.W)

    def _on_preset_change(self, event=None):
        choice = self.preset_var.get()
        if choice.startswith("WPA2 Length (8-63"):
            self.min_len_var.set("8")
            self.max_len_var.set("63")
            self.charset_var.set("ascii_printable")
            self._toggle_custom_regex()
            self.status_label.config(
                text="Preset: WPA2 Length (8-63 chars, ASCII printable)",
                foreground="#0055d4",
            )
        elif choice.startswith("WPA2 Typical (8-16"):
            self.min_len_var.set("8")
            self.max_len_var.set("16")
            self.charset_var.set("ascii_printable")
            self._toggle_custom_regex()
            self.status_label.config(
                text="Preset: WPA2 Typical (8-16 chars, ASCII printable)",
                foreground="#0055d4",
            )
        elif choice.startswith("Alphanumeric (8-16"):
            self.min_len_var.set("8")
            self.max_len_var.set("16")
            self.charset_var.set("alnum")
            self._toggle_custom_regex()
            self.status_label.config(
                text="Preset: Alphanumeric (8-16 chars)",
                foreground="#0055d4",
            )
        elif choice.startswith("Letters Only (4-12"):
            self.min_len_var.set("4")
            self.max_len_var.set("12")
            self.charset_var.set("letters")
            self._toggle_custom_regex()
            self.status_label.config(
                text="Preset: Letters Only (4-12 chars)",
                foreground="#0055d4",
            )

    def _on_rule_manual_change(self):
        self._toggle_custom_regex()
        # Reflect manual customization in preset dropdown
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
            # Default destination folder to source file directory if not already set
            if not self.dest_folder_var.get().strip():
                self.dest_folder_var.set(os.path.dirname(chosen_path))
            self.status_label.config(
                text=f"Selected: {os.path.basename(chosen_path)}",
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
            # All ASCII characters between 32 (space) and 126 (tilde)
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

    def _run_python_filter(self, source_path, output_path, min_len, max_len, charset_mode, mode, dedup):
        char_validator = self._get_validator()
        if charset_mode == "ascii_printable":
            word_token_pattern = re.compile(r"\s+")
        else:
            word_token_pattern = re.compile(r"[^\w'-]+")

        total_kept = 0
        seen_words = set()

        with open(source_path, "r", encoding="utf-8", errors="replace") as in_f, \
             open(output_path, "w", encoding="utf-8", errors="replace") as out_f:
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
                            out_f.write(clean_token + "\n")
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
                        out_f.write(" ".join(kept_in_line) + "\n")

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
        self.run_btn.config(state="disabled", text="Filtering... Please wait")
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
                        res = C_FILTER_FUNC(source_path, output_path, min_len, max_len, c_charset, c_mode, c_dedup)
                    else:
                        res = C_FILTER_FUNC(
                            source_path.encode("utf-8"),
                            output_path.encode("utf-8"),
                            min_len,
                            max_len,
                            c_charset,
                            c_mode,
                            c_dedup,
                        )

                    if res < 0:
                        raise RuntimeError(f"Native engine failed with error code {res}")
                    total_kept = res
                else:
                    total_kept = self._run_python_filter(
                        source_path, output_path, min_len, max_len, charset_mode, mode, dedup
                    )
            except Exception as e:
                err = str(e)

            self.root.after(0, lambda: self._on_complete(err, total_kept, output_filename, dest_dir))

        threading.Thread(target=worker, daemon=True).start()

    def _on_complete(self, err, total_kept, output_filename, directory):
        self.is_processing = False
        self.run_btn.config(state="normal", text="Filter and Save")

        if err:
            self.status_label.config(text=f"Error: {err}", foreground="#cc0000")
            messagebox.showerror("Processing Error", f"An error occurred while processing:\n{err}")
        else:
            self.status_label.config(
                text=f"Done! {total_kept:,} words saved to {output_filename}",
                foreground="#008000",
            )
            messagebox.showinfo(
                "Success",
                f"Filtered list saved successfully!\n\n"
                f"Retained words: {total_kept:,}\n"
                f"Output file: {output_filename}\n"
                f"Destination folder: {directory}",
            )


if __name__ == "__main__":
    app_window = tk.Tk()
    app = LengthFilterApp(app_window)
    app_window.mainloop()