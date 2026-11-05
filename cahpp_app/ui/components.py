from __future__ import annotations

import re
import tkinter as tk
from tkinter import ttk
from typing import Callable
from .common import COLORS


class TreeviewSorter:
    def __init__(
        self,
        tree: ttk.Treeview,
        headings: dict[str, str],
        numeric_columns: set[str] | None = None,
    ):
        self.tree = tree
        self.headings = headings
        self.numeric_columns = numeric_columns or set()
        self.column = ""
        self.reverse = False
        for column, title in headings.items():
            self.tree.heading(
                column,
                text=title,
                command=lambda selected=column: self.sort(selected),
            )

    @staticmethod
    def _number(value: str) -> tuple[int, float]:
        normalized = (
            value.replace("\u00a0", " ")
            .replace("€", "")
            .replace("%", "")
            .replace(" ", "")
            .replace(",", ".")
        )
        match = re.search(r"-?\d+(?:\.\d+)?", normalized)
        return (0, float(match.group(0))) if match else (1, 0.0)

    def _key(self, item_id: str, column: str):
        value = str(self.tree.set(item_id, column) or "").strip()
        if column in self.numeric_columns:
            return self._number(value)
        return value.casefold()

    def sort(self, column: str) -> None:
        self.reverse = not self.reverse if self.column == column else False
        self.column = column
        items = list(self.tree.get_children(""))
        items.sort(
            key=lambda item_id: self._key(item_id, column),
            reverse=self.reverse,
        )
        for index, item_id in enumerate(items):
            self.tree.move(item_id, "", index)
        for name, title in self.headings.items():
            marker = (" ▼" if self.reverse else " ▲") if name == self.column else ""
            self.tree.heading(name, text=title + marker)

    def reapply(self) -> None:
        if not self.column:
            return
        previous_reverse = self.reverse
        self.reverse = not previous_reverse
        self.sort(self.column)


class TreeviewColumnSizer:
    """Ajuste les colonnes une fois que la largeur réelle du tableau est connue."""

    def __init__(
        self,
        tree: ttk.Treeview,
        preferred_widths: dict[str, int],
        flexible_column: str,
        minimum_widths: dict[str, int] | None = None,
    ):
        self.tree = tree
        self.preferred_widths = preferred_widths
        self.flexible_column = flexible_column
        self.minimum_widths = minimum_widths or {}
        self._after_id: str | None = None
        self._last_width = 0
        for column in preferred_widths:
            self.tree.column(
                column,
                minwidth=self.minimum_widths.get(column, 35),
                stretch=False,
            )
        self.tree.bind("<Configure>", self._schedule, add="+")
        self.tree.after_idle(self.fit)

    @staticmethod
    def calculate_widths(
        available: int,
        preferred_widths: dict[str, int],
        flexible_column: str,
        minimum_widths: dict[str, int] | None = None,
    ) -> dict[str, int]:
        minimums = minimum_widths or {}
        fixed = [column for column in preferred_widths if column != flexible_column]
        fixed_preferred = sum(preferred_widths[column] for column in fixed)
        flex_minimum = minimums.get(flexible_column, 35)
        widths = dict(preferred_widths)
        if available >= fixed_preferred + flex_minimum:
            widths[flexible_column] = available - fixed_preferred
            return widths

        fixed_minimum = sum(minimums.get(column, 35) for column in fixed)
        target_fixed = max(fixed_minimum, available - flex_minimum)
        capacity = sum(
            preferred_widths[column] - minimums.get(column, 35) for column in fixed
        )
        if capacity > 0 and target_fixed > fixed_minimum:
            ratio = min(1.0, (target_fixed - fixed_minimum) / capacity)
            for column in fixed:
                minimum = minimums.get(column, 35)
                widths[column] = round(
                    minimum + (preferred_widths[column] - minimum) * ratio
                )
            delta = target_fixed - sum(widths[column] for column in fixed)
            if fixed:
                widths[fixed[0]] += delta
        else:
            for column in fixed:
                widths[column] = minimums.get(column, 35)
        widths[flexible_column] = flex_minimum
        return widths

    def _schedule(self, event=None) -> None:
        width = int(getattr(event, "width", 0) or self.tree.winfo_width())
        if width <= 1 or width == self._last_width:
            return
        self._last_width = width
        if self._after_id:
            self.tree.after_cancel(self._after_id)
        self._after_id = self.tree.after(25, self.fit)

    def fit(self) -> None:
        self._after_id = None
        available = self.tree.winfo_width() - 2
        if available <= 1:
            return
        widths = self.calculate_widths(
            available,
            self.preferred_widths,
            self.flexible_column,
            self.minimum_widths,
        )
        for column, width in widths.items():
            self.tree.column(column, width=width)


class FeedbackButton(tk.Button):
    """Bouton d'action avec confirmation visuelle temporaire non bloquante."""

    def __init__(
        self,
        parent,
        *,
        text: str,
        command: Callable[[], bool],
        success_text: str = "✓ Enregistré",
    ):
        self._action = command
        self._default_text = text
        self._success_text = success_text
        self._restore_after_id: str | None = None
        super().__init__(
            parent,
            text=text,
            command=self._run_action,
            bg=COLORS["accent"],
            activebackground=COLORS["nav_hover"],
            fg="white",
            activeforeground="white",
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=("Segoe UI Semibold", 9),
            padx=12,
            pady=7,
            cursor="hand2",
        )

    def _run_action(self) -> None:
        if self._action():
            self.show_success()

    def show_success(self) -> None:
        if self._restore_after_id:
            self.after_cancel(self._restore_after_id)
        self.configure(
            text=self._success_text,
            bg=COLORS["success"],
            activebackground=COLORS["success"],
        )
        self._restore_after_id = self.after(2000, self._restore)

    def _restore(self) -> None:
        self.configure(
            text=self._default_text,
            bg=COLORS["accent"],
            activebackground=COLORS["nav_hover"],
        )
        self._restore_after_id = None
