import ctypes
import datetime
import os
import re
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

__version__ = "1.5.0"

# Determine directory (handles development mode and PyInstaller extracted _MEIPASS bundle)
BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
DLL_PATH = os.path.join(BASE_DIR, "fastfilter.dll")

# Native C progress callback type: void cb(long long scanned, long long kept, long long bytes_read)
PROGRESS_CB_TYPE = ctypes.CFUNCTYPE(None, ctypes.c_longlong, ctypes.c_longlong, ctypes.c_longlong)

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
                PROGRESS_CB_TYPE,  # progress_cb
                ctypes.POINTER(ctypes.c_longlong), # out_scanned
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
                PROGRESS_CB_TYPE,
                ctypes.POINTER(ctypes.c_longlong),
            ]
            C_FILTER_FUNC.restype = ctypes.c_longlong
            C_FILTER_IS_WIDE = False
except Exception:
    C_FILTER_FUNC = None


class LengthFilterApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Wordlist-Edit-Tool v{__version__}")
        self.root.geometry("700x620")
        self.root.minsize(640, 560)
        self.root.resizable(True, True)

        # Style configuration
        self.style = ttk.Style()
        self.style.theme_use("clam")

        # State variables
        self.file_path_var = tk.StringVar()
        self.dest_folder_var = tk.StringVar()
        self.dest_filename_var = tk.StringVar()
        self.naming_style_var = tk.StringVar(value="Rule Prefix (Recommended)")
        self.user_custom_filename = False
        self._updating_naming = False

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
        self.log_visible = False

        self._build_ui()

        # Variable traces for live dynamic preview updates
        self.dest_folder_var.trace_add("write", lambda *args: self._update_destination_preview())
        self.min_len_var.trace_add("write", lambda *args: self._on_rule_change_event())
        self.max_len_var.trace_add("write", lambda *args: self._on_rule_change_event())
        self.charset_var.trace_add("write", lambda *args: self._on_rule_change_event())

        # Initialize naming preview
        self._update_destination_preview()

        # Keyboard shortcut: Enter key triggers filtering
        self.root.bind("<Return>", lambda event: self._process_file())

    def _build_ui(self):
        # 1. PERMANENT STICKY BOTTOM CONTAINER (Packed first with side=BOTTOM so it's NEVER hidden)
        self.bottom_container = ttk.Frame(self.root)
        self.bottom_container.pack(side=tk.BOTTOM, fill=tk.X)

        # Determinate visual progression bar row
        progress_frame = ttk.Frame(self.bottom_container, padding="10 6 10 2")
        progress_frame.pack(fill=tk.X)

        self.progress_bar = ttk.Progressbar(
            progress_frame, orient="horizontal", mode="determinate", maximum=100.0
        )
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

        self.progress_pct_label = ttk.Label(
            progress_frame, text="0%", font=("Segoe UI", 9, "bold"), width=5, anchor="e"
        )
        self.progress_pct_label.pack(side=tk.RIGHT)

        # Bottom action bar with Start button, Log toggle button, and live status label
        action_bar = ttk.Frame(self.bottom_container, padding="10 4 10 8", relief="groove")
        action_bar.pack(fill=tk.X)

        self.run_btn = ttk.Button(
            action_bar,
            text="▶  Start Filtering",
            command=self._process_file,
            width=18,
        )
        self.run_btn.pack(side=tk.LEFT, padx=(2, 6), ipady=4)

        self.toggle_log_btn = ttk.Button(
            action_bar,
            text="📋  Show Log",
            command=self._toggle_log_view,
            width=13,
        )
        self.toggle_log_btn.pack(side=tk.LEFT, padx=(0, 8), ipady=4)

        engine_info = "Native C Engine" if C_FILTER_FUNC else "Standard Python Engine"
        self.status_label = ttk.Label(
            action_bar,
            text=f"Ready ({engine_info}). Select a source file and click Start Filtering.",
            foreground="#333333",
        )
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # 2. COLLAPSIBLE REAL-TIME STATUS & PROGRESS LOG FRAME (Unpacked by default)
        self.log_container = ttk.LabelFrame(self.root, text="Real-Time Status & Progress Log", padding="6")

        log_toolbar = ttk.Frame(self.log_container)
        log_toolbar.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(log_toolbar, text="Live Telemetry Stream:", font=("Segoe UI", 8, "italic")).pack(side=tk.LEFT)
        ttk.Button(log_toolbar, text="Clear Log", width=10, command=self._clear_log).pack(side=tk.RIGHT)

        log_box_frame = ttk.Frame(self.log_container)
        log_box_frame.pack(fill=tk.BOTH, expand=True)

        self.log_text = tk.Text(
            log_box_frame,
            height=7,
            font=("Consolas", 9),
            bg="#1e1e1e",
            fg="#dcdcdc",
            insertbackground="white",
            wrap="none",
        )
        log_scroll_y = ttk.Scrollbar(log_box_frame, orient="vertical", command=self.log_text.yview)
        log_scroll_x = ttk.Scrollbar(log_box_frame, orient="horizontal", command=self.log_text.xview)
        self.log_text.configure(yscrollcommand=log_scroll_y.set, xscrollcommand=log_scroll_x.set)

        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        log_scroll_x.pack(side=tk.BOTTOM, fill=tk.X)

        self.log_text.tag_config("info", foreground="#80d8ff")
        self.log_text.tag_config("success", foreground="#69f0ae")
        self.log_text.tag_config("warn", foreground="#ffd740")
        self.log_text.tag_config("error", foreground="#ff5252")
        self.log_text.tag_config("stat", foreground="#ffff8d")
        self.log_text.tag_config("subtle", foreground="#9e9e9e")
        self.log_text.config(state="disabled")

        # 3. MAIN CONFIGURATION CONTAINER
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

        # Section 2: Destination Folder & Custom Output Filename
        dest_frame = ttk.LabelFrame(main_container, text="2. Destination Folder & Output Filename", padding="6")
        dest_frame.pack(fill=tk.X, pady=(0, 6))

        # Row 1: Destination folder
        folder_row = ttk.Frame(dest_frame)
        folder_row.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(folder_row, text="Folder:", width=10).pack(side=tk.LEFT)
        self.dest_folder_entry = ttk.Entry(folder_row, textvariable=self.dest_folder_var)
        self.dest_folder_entry.pack(side=tk.LEFT, padx=(0, 6), fill=tk.X, expand=True)
        ttk.Button(folder_row, text="Browse...", command=self._browse_dest_folder).pack(side=tk.RIGHT)

        # Row 2: Custom filename & Rule-based options
        fname_row = ttk.Frame(dest_frame)
        fname_row.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(fname_row, text="Filename:", width=10).pack(side=tk.LEFT)
        self.dest_fname_entry = ttk.Entry(fname_row, textvariable=self.dest_filename_var)
        self.dest_fname_entry.pack(side=tk.LEFT, padx=(0, 6), fill=tk.X, expand=True)
        self.dest_fname_entry.bind("<KeyRelease>", self._on_manual_filename_edit)

        # Naming style / options combobox
        self.naming_combo = ttk.Combobox(
            fname_row,
            textvariable=self.naming_style_var,
            state="readonly",
            width=30,
        )
        self.naming_combo.pack(side=tk.LEFT, padx=(0, 4))
        self.naming_combo.bind("<<ComboboxSelected>>", self._on_naming_style_selected)

        self.reset_name_btn = ttk.Button(
            fname_row, text="↺ Auto", width=7, command=self._reset_filename_to_auto
        )
        self.reset_name_btn.pack(side=tk.RIGHT)

        # Row 3: Live Output Path Preview
        preview_row = ttk.Frame(dest_frame)
        preview_row.pack(fill=tk.X, pady=(2, 0))
        ttk.Label(preview_row, text="Preview:", width=10, font=("Segoe UI", 8, "bold")).pack(side=tk.LEFT)
        self.preview_label = ttk.Label(
            preview_row,
            text="Select a source file to preview destination path",
            font=("Consolas", 8),
            foreground="#0055d4",
            anchor="w",
        )
        self.preview_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

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
        self._update_destination_preview()

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
        self._update_destination_preview()

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
        self._update_destination_preview()

    def _toggle_custom_regex(self):
        if self.charset_var.get() == "custom":
            self.regex_entry.config(state="normal")
        else:
            self.regex_entry.config(state="disabled")

    def _toggle_log_view(self):
        if not self.log_visible:
            self.log_container.pack(
                side=tk.BOTTOM, fill=tk.BOTH, expand=False, before=self.bottom_container, padx=12, pady=(0, 6)
            )
            self.toggle_log_btn.config(text="📋  Hide Log")
            self.log_visible = True
            cur_w = self.root.winfo_width()
            cur_h = self.root.winfo_height()
            if cur_h < 740:
                self.root.geometry(f"{max(cur_w, 700)}x780")
        else:
            self.log_container.pack_forget()
            self.toggle_log_btn.config(text="📋  Show Log")
            self.log_visible = False
            cur_w = self.root.winfo_width()
            cur_h = self.root.winfo_height()
            if cur_h > 640:
                self.root.geometry(f"{max(cur_w, 700)}x620")

    def _log(self, message, tag="info"):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        formatted = f"[{timestamp}] {message}\n"
        self.log_text.config(state="normal")
        self.log_text.insert(tk.END, formatted, tag)
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")

    def _clear_log(self):
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state="disabled")

    def _update_progress_ui(self, scanned, kept, bytes_read, total_file_size):
        if not self.is_processing:
            return
        pct = min(100.0, (bytes_read / total_file_size * 100.0)) if total_file_size > 0 else 0.0
        self.progress_bar["value"] = pct
        self.progress_pct_label.config(text=f"{pct:.0f}%")
        mb_read = bytes_read / (1024 * 1024)
        mb_tot = total_file_size / (1024 * 1024)
        self.status_label.config(
            text=f"Filtering: {pct:.1f}% ({mb_read:.1f} MB / {mb_tot:.1f} MB) | Scanned: {scanned:,} | Kept: {kept:,}",
            foreground="#0055d4",
        )

    def _compute_rule_tag(self):
        min_v = self.min_len_var.get().strip()
        max_v = self.max_len_var.get().strip()
        if not min_v.isdigit():
            min_v = "3"
        if not max_v.isdigit():
            max_v = "12"

        charset = self.charset_var.get()
        preset = self.preset_var.get()

        if preset.startswith("WPA2 Length"):
            return f"ASCII{min_v}to{max_v}char"
        elif preset.startswith("WPA2 Typical"):
            return f"ASCII{min_v}to{max_v}char"
        elif charset == "ascii_printable":
            return f"ASCII{min_v}to{max_v}char"
        elif charset == "letters":
            return f"Letters{min_v}to{max_v}char"
        elif charset == "alnum":
            return f"Alnum{min_v}to{max_v}char"
        elif charset == "custom":
            return f"Regex{min_v}to{max_v}char"
        else:
            return f"{min_v}to{max_v}_anychar"

    def _compute_naming_options(self, orig_name):
        if not orig_name:
            orig_name = "filename.txt"
        base, ext = os.path.splitext(orig_name)
        if not ext:
            ext = ".txt"

        rule_tag = self._compute_rule_tag()

        rule_prefix = f"{rule_tag}_{base}{ext}"
        rule_suffix = f"{base}_{rule_tag}{ext}"
        tool_prefix = f"WordlistEdit_{base}{ext}"
        filtered_prefix = f"Filtered_{base}{ext}"
        classic_prefix = f"lengthfilter_{base}{ext}"

        return {
            "rule_prefix": rule_prefix,
            "rule_suffix": rule_suffix,
            "tool_prefix": tool_prefix,
            "filtered": filtered_prefix,
            "classic": classic_prefix,
        }

    def _refresh_naming_combo_values(self):
        source_path = self.file_path_var.get().strip()
        orig_name = os.path.basename(source_path) if source_path else "filename.txt"
        opts = self._compute_naming_options(orig_name)

        combo_values = [
            f"Rule Prefix: {opts['rule_prefix']}",
            f"Rule Suffix: {opts['rule_suffix']}",
            f"WordlistEdit: {opts['tool_prefix']}",
            f"Filtered: {opts['filtered']}",
            f"Classic: {opts['classic']}",
            "Custom / Manual",
        ]
        self.naming_combo["values"] = combo_values
        return opts

    def _on_naming_style_selected(self, event=None):
        val = self.naming_style_var.get()
        source_path = self.file_path_var.get().strip()
        orig_name = os.path.basename(source_path) if source_path else "filename.txt"
        opts = self._compute_naming_options(orig_name)

        if val.startswith("Rule Prefix"):
            self.user_custom_filename = False
            self.dest_filename_var.set(opts["rule_prefix"])
        elif val.startswith("Rule Suffix"):
            self.user_custom_filename = False
            self.dest_filename_var.set(opts["rule_suffix"])
        elif val.startswith("WordlistEdit"):
            self.user_custom_filename = False
            self.dest_filename_var.set(opts["tool_prefix"])
        elif val.startswith("Filtered"):
            self.user_custom_filename = False
            self.dest_filename_var.set(opts["filtered"])
        elif val.startswith("Classic"):
            self.user_custom_filename = False
            self.dest_filename_var.set(opts["classic"])
        elif val == "Custom / Manual":
            self.user_custom_filename = True

        self._update_destination_preview()

    def _on_manual_filename_edit(self, event=None):
        self.user_custom_filename = True
        self.naming_style_var.set("Custom / Manual")
        self._update_destination_preview()

    def _reset_filename_to_auto(self):
        self.user_custom_filename = False
        source_path = self.file_path_var.get().strip()
        orig_name = os.path.basename(source_path) if source_path else "filename.txt"
        opts = self._compute_naming_options(orig_name)
        self.naming_style_var.set(f"Rule Prefix: {opts['rule_prefix']}")
        self.dest_filename_var.set(opts["rule_prefix"])
        self._refresh_naming_combo_values()
        self._update_destination_preview()

    def _on_rule_change_event(self):
        self._update_destination_preview()

    def _update_destination_preview(self):
        if getattr(self, "_updating_naming", False):
            return
        self._updating_naming = True
        try:
            source_path = self.file_path_var.get().strip()
            orig_name = os.path.basename(source_path) if source_path else "filename.txt"

            opts = self._refresh_naming_combo_values()

            if not getattr(self, "user_custom_filename", False):
                current_style = self.naming_style_var.get()
                if current_style.startswith("Rule Suffix"):
                    self.dest_filename_var.set(opts["rule_suffix"])
                    self.naming_style_var.set(f"Rule Suffix: {opts['rule_suffix']}")
                elif current_style.startswith("WordlistEdit"):
                    self.dest_filename_var.set(opts["tool_prefix"])
                    self.naming_style_var.set(f"WordlistEdit: {opts['tool_prefix']}")
                elif current_style.startswith("Filtered"):
                    self.dest_filename_var.set(opts["filtered"])
                    self.naming_style_var.set(f"Filtered: {opts['filtered']}")
                elif current_style.startswith("Classic"):
                    self.dest_filename_var.set(opts["classic"])
                    self.naming_style_var.set(f"Classic: {opts['classic']}")
                else:
                    self.dest_filename_var.set(opts["rule_prefix"])
                    self.naming_style_var.set(f"Rule Prefix: {opts['rule_prefix']}")

            dest_dir = self.dest_folder_var.get().strip()
            if not dest_dir and source_path:
                dest_dir = os.path.dirname(source_path)
            if not dest_dir:
                dest_dir = "[Source Folder]"

            filename = self.dest_filename_var.get().strip()
            if not filename:
                filename = opts["rule_prefix"]

            if self.split_enabled_var.get():
                base, ext = os.path.splitext(filename)
                preview_fname = f"{base}_part1{ext} (+ _part2{ext}...)"
            else:
                preview_fname = filename

            if not source_path:
                self.preview_label.config(
                    text=f"Select source file to preview destination path (e.g. {preview_fname})",
                    foreground="#666666",
                )
            else:
                full_path = os.path.join(dest_dir, preview_fname)
                self.preview_label.config(text=full_path, foreground="#0055d4")
        finally:
            self._updating_naming = False

    def _browse_source_file(self):
        chosen_path = filedialog.askopenfilename(
            title="Select Text / Wordlist File",
            filetypes=[("All Files", "*.*"), ("Text Files", "*.txt"), ("Wordlists", "*.dict;*.lst")],
        )
        if chosen_path:
            self.file_path_var.set(chosen_path)
            if not self.dest_folder_var.get().strip():
                self.dest_folder_var.set(os.path.dirname(chosen_path))
            sz_mb = os.path.getsize(chosen_path) / (1024 * 1024)
            self.status_label.config(
                text=f"Selected: {os.path.basename(chosen_path)} ({sz_mb:.1f} MB) — Click 'Start Filtering' to run.",
                foreground="#000000",
            )
            self._log(f"Selected source: {chosen_path} ({sz_mb:.2f} MB)", tag="info")
            self._update_destination_preview()

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
            self._log(f"Selected destination directory: {chosen_dir}", tag="subtle")
            self._update_destination_preview()

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

    def _run_python_filter(
        self, source_path, output_path, min_len, max_len, charset_mode, mode, dedup, split_lines, split_bytes, progress_cb=None
    ):
        char_validator = self._get_validator()
        if charset_mode == "ascii_printable":
            word_token_pattern = re.compile(r"\s+")
        else:
            word_token_pattern = re.compile(r"[^\w'-]+")

        total_scanned = 0
        total_kept = 0
        bytes_read = 0
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
                        bytes_read += len(line.encode("utf-8"))
                        tokens = word_token_pattern.split(line.strip())
                        for token in tokens:
                            if not token:
                                continue
                            total_scanned += 1
                            if progress_cb and (total_scanned % 50000) == 0:
                                progress_cb(total_scanned, total_kept, bytes_read)

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
                        bytes_read += len(line.encode("utf-8"))
                        words = word_token_pattern.split(line.strip())
                        kept_in_line = []
                        for token in words:
                            if not token:
                                continue
                            total_scanned += 1
                            if progress_cb and (total_scanned % 50000) == 0:
                                progress_cb(total_scanned, total_kept, bytes_read)

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

        if progress_cb:
            progress_cb(total_scanned, total_kept, bytes_read)

        return total_kept, total_scanned

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

        # Destination folder & custom output filename setup
        source_dir, original_name = os.path.split(source_path)
        dest_dir = self.dest_folder_var.get().strip()
        if not dest_dir or not os.path.isdir(dest_dir):
            dest_dir = source_dir

        output_filename = self.dest_filename_var.get().strip()
        if not output_filename:
            opts = self._compute_naming_options(original_name)
            output_filename = opts["rule_prefix"]

        # Ensure filename has an extension if omitted
        base_f, ext_f = os.path.splitext(output_filename)
        if not ext_f:
            _, src_ext = os.path.splitext(original_name)
            output_filename = f"{output_filename}{src_ext or '.txt'}"

        output_path = os.path.join(dest_dir, output_filename)
        mode = self.mode_var.get()
        dedup = bool(self.unique_var.get())

        total_file_size = os.path.getsize(source_path)
        start_time = time.time()

        # Set UI to busy state
        self.is_processing = True
        self.run_btn.config(state="disabled", text="⏳  Filtering... Please wait")
        self.progress_bar["value"] = 0.0
        self.progress_pct_label.config(text="0%")
        self.status_label.config(text="Initializing filtering engine...", foreground="#0055d4")

        engine_name = "Native C Acceleration (fastfilter.dll)" if (C_FILTER_FUNC and charset_mode in ("all", "letters", "alnum", "ascii_printable")) else "Python Streaming Engine"

        self._log(f"======================================================", tag="info")
        self._log(f"Starting filter task: '{original_name}' -> '{output_filename}' ({total_file_size / (1024*1024):.2f} MB)", tag="info")
        self._log(f"  • Output destination: {output_path}", tag="subtle")
        self._log(f"  • Rules: length {min_len}-{max_len} | charset='{charset_mode}' | unique={dedup}", tag="subtle")
        if split_lines > 0 or split_bytes > 0:
            split_info = f"{split_lines:,} words/part" if split_lines > 0 else f"{split_bytes/(1024*1024):.0f} MB/part"
            self._log(f"  • Split output: Enabled ({split_info})", tag="subtle")
        self._log(f"  • Engine: {engine_name}", tag="subtle")

        last_update_time = [0.0]
        last_log_time = [0.0]

        def on_progress(scanned, kept, bytes_read):
            now = time.time()
            if now - last_update_time[0] >= 0.05:
                last_update_time[0] = now
                self.root.after_idle(self._update_progress_ui, scanned, kept, bytes_read, total_file_size)

            if now - last_log_time[0] >= 1.0:
                last_log_time[0] = now
                pct = min(100.0, (bytes_read / total_file_size * 100.0)) if total_file_size > 0 else 0.0
                mb_read = bytes_read / (1024 * 1024)
                self.root.after_idle(
                    self._log,
                    f"Progress: {pct:.1f}% | Scanned: {scanned:,} | Kept: {kept:,} | Read: {mb_read:.1f} MB",
                    "subtle",
                )

        # Worker thread for smooth non-blocking UI
        def worker():
            err = None
            total_kept = 0
            total_scanned = 0
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

                    c_cb = PROGRESS_CB_TYPE(on_progress)
                    c_scanned = ctypes.c_longlong(0)

                    if C_FILTER_IS_WIDE:
                        res = C_FILTER_FUNC(
                            source_path,
                            output_path,
                            min_len,
                            max_len,
                            c_charset,
                            c_mode,
                            c_dedup,
                            split_lines,
                            split_bytes,
                            c_cb,
                            ctypes.byref(c_scanned),
                        )
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
                            c_cb,
                            ctypes.byref(c_scanned),
                        )

                    if res < 0:
                        raise RuntimeError(f"Native engine failed with error code {res}")
                    total_kept = res
                    total_scanned = c_scanned.value
                else:
                    total_kept, total_scanned = self._run_python_filter(
                        source_path, output_path, min_len, max_len, charset_mode, mode, dedup, split_lines, split_bytes, progress_cb=on_progress
                    )
            except Exception as e:
                err = str(e)

            elapsed_time = time.time() - start_time
            self.root.after(0, lambda: self._on_complete(
                err, total_kept, total_scanned, output_filename, dest_dir, split_lines > 0 or split_bytes > 0, elapsed_time, total_file_size
            ))

        threading.Thread(target=worker, daemon=True).start()

    def _on_complete(self, err, total_kept, total_scanned, output_filename, directory, was_split, elapsed_time, total_file_size):
        self.is_processing = False
        self.run_btn.config(state="normal", text="▶  Start Filtering")
        self.progress_bar["value"] = 100.0 if not err else 0.0
        self.progress_pct_label.config(text="100%" if not err else "0%")

        if err:
            self.status_label.config(text=f"Error: {err}", foreground="#cc0000")
            self._log(f"Processing error: {err}", tag="error")
            messagebox.showerror("Processing Error", f"An error occurred while processing:\n{err}")
        else:
            removed = max(0, total_scanned - total_kept)
            pct_kept = (total_kept / total_scanned * 100.0) if total_scanned > 0 else 0.0
            pct_removed = (removed / total_scanned * 100.0) if total_scanned > 0 else 0.0
            mb_tot = total_file_size / (1024 * 1024)
            speed_mb = mb_tot / elapsed_time if elapsed_time > 0 else 0.0

            if was_split:
                status_txt = f"Done in {elapsed_time:.2f}s! Kept: {total_kept:,} ({pct_kept:.1f}%) | Removed: {removed:,} ({pct_removed:.1f}%) across parts"
                msg_body = (
                    f"Wordlist filtering completed successfully across split parts!\n\n"
                    f"Processing Time: {elapsed_time:.2f} seconds ({speed_mb:.1f} MB/s)\n\n"
                    f"Word Count Statistics:\n"
                    f"  • Original Words:  {total_scanned:,} (100.0%)\n"
                    f"  • Retained Words:  {total_kept:,} ({pct_kept:.1f}%)\n"
                    f"  • Removed Words:   {removed:,} ({pct_removed:.1f}%)\n\n"
                    f"Destination:\n"
                    f"  • Output Parts: {output_filename.replace('.', '_partN.')}\n"
                    f"  • Folder: {directory}"
                )
            else:
                status_txt = f"Done in {elapsed_time:.2f}s! Kept: {total_kept:,} ({pct_kept:.1f}%) | Removed: {removed:,} ({pct_removed:.1f}%)"
                msg_body = (
                    f"Wordlist filtering completed successfully!\n\n"
                    f"Processing Time: {elapsed_time:.2f} seconds ({speed_mb:.1f} MB/s)\n\n"
                    f"Word Count Statistics:\n"
                    f"  • Original Words:  {total_scanned:,} (100.0%)\n"
                    f"  • Retained Words:  {total_kept:,} ({pct_kept:.1f}%)\n"
                    f"  • Removed Words:   {removed:,} ({pct_removed:.1f}%)\n\n"
                    f"Destination:\n"
                    f"  • Output File: {output_filename}\n"
                    f"  • Folder: {directory}"
                )

            self.status_label.config(text=status_txt, foreground="#008000")
            self._log(f"======================================================", tag="success")
            self._log(f"PROCESSING COMPLETED in {elapsed_time:.2f}s ({speed_mb:.1f} MB/s)", tag="success")
            self._log(f"  • Original words:  {total_scanned:,} (100.0%)", tag="stat")
            self._log(f"  • Retained words:  {total_kept:,} ({pct_kept:.1f}%)", tag="stat")
            self._log(f"  • Removed words:   {removed:,} ({pct_removed:.1f}%)", tag="stat")
            self._log(f"  • Destination:     {os.path.join(directory, output_filename)}", tag="info")
            self._log(f"======================================================", tag="success")
            messagebox.showinfo("Processing Complete", msg_body)


if __name__ == "__main__":
    app_window = tk.Tk()
    app = LengthFilterApp(app_window)
    app_window.mainloop()