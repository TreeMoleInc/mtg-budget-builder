# ui/app.py — Main application window

import os
import sys
import customtkinter as ctk
from core.parser import parse_decklist
from core import finder


def _resource(relative_path: str) -> str:
    """Resolve a resource path that works both in development and in a PyInstaller bundle."""
    if hasattr(sys, "_MEIPASS"):
        # Running from a PyInstaller bundle — resources are in the temp extraction dir
        return os.path.join(sys._MEIPASS, relative_path)
    # Development — resources live at the project root (one level above ui/)
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), relative_path)

# ---------------------------------------------------------------------------
# Theme / colour constants
# ---------------------------------------------------------------------------
BG_COLOR = "#1e1e1e"
PANEL_BG = "#2b2b2b"
BORDER_COLOR = "#3a3a3a"
BTN_GREEN = "#4caf50"
BTN_HOVER = "#388e3c"
TEXT_COLOR = "#ffffff"
MUTED_COLOR = "#888888"
ERROR_COLOR = "#ef5350"
PRICE_COLOR = "#81c784"
PRICE_BG = "#232323"
BASIC_BLUE = "#64b5f6"

INPUT_PLACEHOLDER = (
    "Paste your card list here...\n\n"
    "Supported formats:\n"
    "  4 Lightning Bolt\n"
    "  2x Counterspell\n"
    "  1 Sheoldred, the Apocalypse\n\n"
    "One card per line."
)

OUTPUT_PLACEHOLDER = "Results will appear here..."
PRICE_PLACEHOLDER = "Price"

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")


class BudgetBuilderApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("MTG Budget Builder v1.0.0")
        self.minsize(900, 600)
        self.configure(fg_color=BG_COLOR)

        # Set window icon (title bar + taskbar)
        ico = _resource("icon.ico")
        if os.path.exists(ico):
            self.iconbitmap(ico)

        # Placeholder state
        self._input_has_placeholder = True
        self._output_has_placeholder = True

        # Track whether a search is running
        self._searching = False

        # Basics discount toggle
        self.discount_basics_var = ctk.BooleanVar(value=False)

        self._build_layout()
        self._apply_input_placeholder()
        self._apply_output_placeholder()

    # -----------------------------------------------------------------------
    # Layout
    # -----------------------------------------------------------------------
    def _build_layout(self):
        # Root grid: 3 rows — main content, progress bar, status label
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)
        self.grid_rowconfigure(2, weight=0)

        # ---- Left column ----
        left_frame = ctk.CTkFrame(self, fg_color=PANEL_BG, corner_radius=8)
        left_frame.grid(row=0, column=0, padx=(12, 6), pady=12, sticky="nsew")
        left_frame.grid_rowconfigure(1, weight=1)
        left_frame.grid_columnconfigure(0, weight=1)

        input_label = ctk.CTkLabel(
            left_frame, text="Input", text_color=TEXT_COLOR,
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        input_label.grid(row=0, column=0, padx=10, pady=(10, 4), sticky="w")

        self.input_box = ctk.CTkTextbox(
            left_frame,
            fg_color=BG_COLOR,
            text_color=MUTED_COLOR,
            border_color=BORDER_COLOR,
            border_width=1,
            font=ctk.CTkFont(size=13),
            wrap="word",
        )
        self.input_box.grid(row=1, column=0, padx=10, pady=(0, 8), sticky="nsew")
        self.input_box.bind("<FocusIn>", self._on_input_focus_in)
        self.input_box.bind("<FocusOut>", self._on_input_focus_out)

        self.search_btn = ctk.CTkButton(
            left_frame,
            text="Find Cheapest Versions",
            fg_color=BTN_GREEN,
            hover_color=BTN_HOVER,
            text_color=TEXT_COLOR,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._on_search_clicked,
        )
        self.search_btn.grid(row=2, column=0, padx=10, pady=(0, 6), sticky="ew")

        self.discount_basics_check = ctk.CTkCheckBox(
            left_frame,
            text="Discount basics for price",
            variable=self.discount_basics_var,
            fg_color=BTN_GREEN,
            hover_color=BTN_HOVER,
            checkmark_color=BG_COLOR,
            border_color=BORDER_COLOR,
            text_color=TEXT_COLOR,
            font=ctk.CTkFont(size=12),
        )
        self.discount_basics_check.grid(row=3, column=0, padx=14, pady=(0, 10), sticky="w")

        # ---- Right column ----
        right_frame = ctk.CTkFrame(self, fg_color=PANEL_BG, corner_radius=8)
        right_frame.grid(row=0, column=1, padx=(6, 12), pady=12, sticky="nsew")
        right_frame.grid_rowconfigure(1, weight=1)
        right_frame.grid_columnconfigure(0, weight=1)

        output_label = ctk.CTkLabel(
            right_frame, text="Output", text_color=TEXT_COLOR,
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        output_label.grid(row=0, column=0, padx=10, pady=(10, 4), sticky="w")

        # Output area: card list + price column side by side
        output_area = ctk.CTkFrame(right_frame, fg_color=BG_COLOR, corner_radius=6)
        output_area.grid(row=1, column=0, padx=10, pady=(0, 8), sticky="nsew")
        output_area.grid_rowconfigure(0, weight=1)
        output_area.grid_columnconfigure(0, weight=1)
        output_area.grid_columnconfigure(1, weight=0)

        self.output_box = ctk.CTkTextbox(
            output_area,
            fg_color=BG_COLOR,
            text_color=TEXT_COLOR,
            border_width=0,
            font=ctk.CTkFont(family="Courier New", size=12),
            wrap="none",
            state="normal",
        )
        self.output_box.grid(row=0, column=0, padx=(4, 0), pady=4, sticky="nsew")

        # Text tags for coloured output lines
        self.output_box._textbox.tag_configure("error", foreground=ERROR_COLOR)
        self.output_box._textbox.tag_configure("basic", foreground=BASIC_BLUE)
        # Placeholder tag — muted color, no special meaning
        self.output_box._textbox.tag_configure("placeholder", foreground=MUTED_COLOR)

        self.price_box = ctk.CTkTextbox(
            output_area,
            fg_color=PRICE_BG,
            text_color=PRICE_COLOR,
            border_color=BORDER_COLOR,
            border_width=1,
            font=ctk.CTkFont(family="Courier New", size=12),
            wrap="none",
            width=100,
            state="disabled",
        )
        self.price_box.grid(row=0, column=1, padx=(2, 4), pady=4, sticky="ns")

        # Sync scroll: yscrollcommand fires for ALL scroll mechanisms (drag, wheel, keyboard).
        # Re-entrancy guard (_syncing) prevents the two handlers calling each other indefinitely.
        _out_tb = self.output_box._textbox
        _price_tb = self.price_box._textbox
        _syncing = [False]

        def _output_yscroll(first, last):
            self.output_box._y_scrollbar.set(first, last)
            if not _syncing[0]:
                _syncing[0] = True
                _price_tb.yview_moveto(first)
                _syncing[0] = False

        def _price_yscroll(first, last):
            self.price_box._y_scrollbar.set(first, last)
            if not _syncing[0]:
                _syncing[0] = True
                _out_tb.yview_moveto(first)
                _syncing[0] = False

        _out_tb.configure(yscrollcommand=_output_yscroll)
        _price_tb.configure(yscrollcommand=_price_yscroll)

        self.output_box.bind("<MouseWheel>", self._on_scroll)
        self.price_box.bind("<MouseWheel>", self._on_scroll)

        # Bottom bar — 2-row layout: copy button left, price info stacked right
        right_bottom = ctk.CTkFrame(right_frame, fg_color="transparent")
        right_bottom.grid(row=2, column=0, padx=10, pady=(0, 10), sticky="ew")
        right_bottom.grid_columnconfigure(0, weight=1)
        right_bottom.grid_columnconfigure(1, weight=0)

        self.copy_btn = ctk.CTkButton(
            right_bottom,
            text="Copy List",
            fg_color=BORDER_COLOR,
            hover_color="#4a4a4a",
            text_color=TEXT_COLOR,
            font=ctk.CTkFont(size=13),
            width=110,
            command=self._on_copy_clicked,
        )
        self.copy_btn.grid(row=0, column=0, rowspan=2, sticky="w")

        self.total_label = ctk.CTkLabel(
            right_bottom,
            text="Total: $0.00",
            text_color=PRICE_COLOR,
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.total_label.grid(row=0, column=1, sticky="e")

        self.count_label = ctk.CTkLabel(
            right_bottom,
            text="0 cards  \u00b7  0 unique",
            text_color=MUTED_COLOR,
            font=ctk.CTkFont(size=12),
        )
        self.count_label.grid(row=1, column=1, sticky="e")

        # ---- Progress bar (spans both columns) ----
        self.progress_bar = ctk.CTkProgressBar(
            self,
            fg_color=BORDER_COLOR,
            progress_color=BTN_GREEN,
        )
        self.progress_bar.grid(row=1, column=0, columnspan=2, padx=12, pady=(0, 4), sticky="ew")
        self.progress_bar.set(0)
        self.progress_bar.grid_remove()  # Hidden initially

        # ---- Status label (spans both columns) ----
        self.status_label = ctk.CTkLabel(
            self,
            text="",
            text_color=MUTED_COLOR,
            font=ctk.CTkFont(size=12),
        )
        self.status_label.grid(row=2, column=0, columnspan=2, padx=12, pady=(0, 8), sticky="w")

    # -----------------------------------------------------------------------
    # Placeholder helpers
    # -----------------------------------------------------------------------
    def _apply_input_placeholder(self):
        self.input_box.delete("1.0", "end")
        self.input_box.insert("1.0", INPUT_PLACEHOLDER)
        self.input_box.configure(text_color=MUTED_COLOR)
        self._input_has_placeholder = True

    def _on_input_focus_in(self, event=None):
        if self._input_has_placeholder:
            self.input_box.delete("1.0", "end")
            self.input_box.configure(text_color=TEXT_COLOR)
            self._input_has_placeholder = False

    def _on_input_focus_out(self, event=None):
        content = self.input_box.get("1.0", "end").strip()
        if not content:
            self._apply_input_placeholder()

    def _apply_output_placeholder(self):
        """Show placeholder text in the output box (read-only, muted color)."""
        tb = self.output_box._textbox
        tb.configure(state="normal")
        tb.delete("1.0", "end")
        tb.insert("1.0", OUTPUT_PLACEHOLDER, "placeholder")
        tb.configure(state="disabled")

        self._set_price_box_text(PRICE_PLACEHOLDER, placeholder=True)
        self._output_has_placeholder = True

    def _set_price_box_text(self, text: str, placeholder: bool = False):
        self.price_box.configure(state="normal")
        self.price_box.delete("1.0", "end")
        self.price_box.insert("1.0", text)
        color = MUTED_COLOR if placeholder else PRICE_COLOR
        self.price_box.configure(text_color=color, state="disabled")

    def _output_append(self, text: str, tag: str = ""):
        """Append a line to the output box with optional colour tag. Keeps box read-only."""
        tb = self.output_box._textbox
        tb.configure(state="normal")
        current = tb.get("1.0", "end")
        prefix = "" if current.strip() == "" else "\n"
        if tag:
            tb.insert("end", prefix + text, tag)
        else:
            tb.insert("end", prefix + text)
        tb.configure(state="disabled")

    # -----------------------------------------------------------------------
    # Scroll sync
    # -----------------------------------------------------------------------
    def _on_scroll(self, event):
        delta = -1 * (event.delta // 120)
        self.output_box._textbox.yview_scroll(delta, "units")
        self.price_box._textbox.yview_scroll(delta, "units")
        return "break"

    # -----------------------------------------------------------------------
    # Search
    # -----------------------------------------------------------------------
    def _on_search_clicked(self):
        if self._searching:
            return

        if self._input_has_placeholder:
            raw_text = ""
        else:
            raw_text = self.input_box.get("1.0", "end").strip()

        if not raw_text:
            self.status_label.configure(
                text="Please enter a card list first.", text_color=ERROR_COLOR
            )
            return

        cards, parse_errors = parse_decklist(raw_text)

        if not cards:
            self.status_label.configure(
                text="No valid cards found in input.", text_color=ERROR_COLOR
            )
            return

        # Clear output boxes
        tb = self.output_box._textbox
        tb.configure(state="normal")
        tb.delete("1.0", "end")
        tb.configure(state="disabled")
        self._set_price_box_text("", placeholder=False)
        self._output_has_placeholder = False
        self.total_label.configure(text="Total: $0.00")
        self.count_label.configure(text="0 cards  \u00b7  0 unique")

        # Show progress bar
        self.progress_bar.grid()
        self.progress_bar.set(0)
        self.status_label.configure(
            text=f"Starting search... (0 / {len(cards)})", text_color=MUTED_COLOR
        )

        # Disable search button
        self._searching = True
        self.search_btn.configure(state="disabled", text="Searching...")

        finder.start_search(
            cards,
            on_progress=self._cb_progress,
            on_complete=self._cb_complete,
            on_error=self._cb_error,
            discount_basics=self.discount_basics_var.get(),
        )

    # -----------------------------------------------------------------------
    # Callbacks (called from background thread — always use after())
    # -----------------------------------------------------------------------
    def _cb_progress(self, current, total, card_name, result_line, price_str, is_basic):
        def _update():
            if not self.winfo_exists():
                return

            self.progress_bar.set(current / total if total > 0 else 0)
            self.status_label.configure(
                text=f"Searching... {current} / {total}  ({card_name})",
                text_color=MUTED_COLOR,
            )

            # Pick colour tag for this line
            if is_basic:
                tag = "basic"
            elif result_line.startswith("# ERROR") or result_line.startswith("# WARNING"):
                tag = "error"
            else:
                tag = ""

            self._output_append(result_line, tag)

            # Append matching price line — one entry per card, always in sync with output box.
            # Use card index (not box content) for the prefix so empty error prices
            # don't cause the next card's price to fill the wrong row.
            self.price_box.configure(state="normal")
            p_prefix = "" if current == 1 else "\n"
            self.price_box._textbox.insert("end", p_prefix + (price_str or ""))
            self.price_box.configure(state="disabled")

        self.after(0, _update)

    def _cb_complete(self, result_lines, error_lines, total_price, total_cards, unique_cards):
        def _update():
            if not self.winfo_exists():
                return
            self.progress_bar.grid_remove()
            self.total_label.configure(text=f"Total: ${total_price:.2f}")
            self.count_label.configure(
                text=f"{total_cards} cards  \u00b7  {unique_cards} unique"
            )
            found = len(result_lines) - len(error_lines)
            self.status_label.configure(
                text=f"Done \u2014 {found} card(s) found, {len(error_lines)} error(s)",
                text_color=MUTED_COLOR,
            )
            self._searching = False
            self.search_btn.configure(state="normal", text="Find Cheapest Versions")

        self.after(0, _update)

    def _cb_error(self, message):
        def _update():
            if not self.winfo_exists():
                return
            self.progress_bar.grid_remove()
            self.status_label.configure(
                text=f"Error: {message}", text_color=ERROR_COLOR
            )
            self._searching = False
            self.search_btn.configure(state="normal", text="Find Cheapest Versions")

        self.after(0, _update)

    # -----------------------------------------------------------------------
    # Copy button
    # -----------------------------------------------------------------------
    def _on_copy_clicked(self):
        if self._output_has_placeholder:
            return

        content = self.output_box._textbox.get("1.0", "end").strip()
        if not content:
            return

        self.clipboard_clear()
        self.clipboard_append(content)

        self.copy_btn.configure(text="Copied!")
        self.after(1500, lambda: self.copy_btn.configure(text="Copy List"))
