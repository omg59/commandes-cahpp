from __future__ import annotations

import tkinter as tk
from datetime import datetime
from tkinter import ttk
from .base import BasePage
from .common import COLORS
from .common import format_number
from .common import format_timestamp
from .common import timestamp_is_due
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .history import OrdersPage


class DashboardPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.header(
            "Vue d'ensemble",
            "Catalogue, fournisseurs et commandes disponibles sur ce poste.",
        )
        self.cards = ttk.Frame(self)
        self.cards.pack(fill="x")
        self.card_values: dict[str, tk.Label] = {}
        for index, (key, label) in enumerate(
            [
                ("products", "Articles actifs"),
                ("suppliers", "Fournisseurs"),
                ("favorites", "Articles favoris"),
                ("orders", "Commandes"),
                ("pending_deliveries", "Livraisons en attente"),
                ("alert_count", "Alertes de suivi"),
            ]
        ):
            card = tk.Frame(
                self.cards,
                bg=COLORS["surface"],
                highlightbackground=COLORS["border"],
                highlightthickness=1,
                padx=16,
                pady=14,
            )
            card.grid(row=0, column=index, sticky="ew", padx=(0, 12))
            self.cards.columnconfigure(index, weight=1)
            value = tk.Label(
                card,
                text="0",
                bg=COLORS["surface"],
                fg=COLORS["accent"],
                font=("Segoe UI Semibold", 22),
                anchor="w",
            )
            value.pack(fill="x")
            tk.Label(
                card,
                text=label,
                bg=COLORS["surface"],
                fg=COLORS["muted"],
                font=("Segoe UI", 9),
                anchor="w",
            ).pack(fill="x")
            self.card_values[key] = value

        self.import_box = tk.Frame(
            self,
            bg=COLORS["surface"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            padx=18,
            pady=16,
        )
        self.import_box.pack(fill="x", pady=(20, 0))
        self.import_label = tk.Label(
            self.import_box,
            text="Aucun catalogue importé",
            bg=COLORS["surface"],
            fg=COLORS["text"],
            font=("Segoe UI Semibold", 11),
            anchor="w",
        )
        self.import_label.pack(fill="x")
        self.import_detail = tk.Label(
            self.import_box,
            text="",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9),
            anchor="w",
        )
        self.import_detail.pack(fill="x", pady=(4, 0))

        self.dashboard_panes = ttk.Panedwindow(
            self,
            orient="vertical",
        )
        self.dashboard_panes.pack(fill="both", expand=True, pady=(16, 0))

        self.delivery_box = tk.Frame(
            self.dashboard_panes,
            bg=COLORS["surface"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            padx=14,
            pady=12,
        )
        self.dashboard_panes.add(
            self.delivery_box,
            weight=3,
        )
        delivery_header = tk.Frame(self.delivery_box, bg=COLORS["surface"])
        delivery_header.pack(fill="x", pady=(0, 8))
        tk.Label(
            delivery_header,
            text="Commandes en attente de livraison",
            bg=COLORS["surface"],
            fg=COLORS["text"],
            font=("Segoe UI Semibold", 11),
        ).pack(side="left")
        ttk.Button(
            delivery_header,
            text="Voir dans l'historique",
            command=self.open_deliveries,
        ).pack(side="right")
        delivery_table = tk.Frame(self.delivery_box, bg=COLORS["surface"])
        delivery_table.pack(fill="both", expand=True)
        self.delivery_tree = ttk.Treeview(
            delivery_table,
            columns=("number", "sent", "supplier", "state", "remaining", "days"),
            show="headings",
            height=3,
        )
        delivery_scroll = ttk.Scrollbar(
            delivery_table,
            orient="vertical",
            command=self.delivery_tree.yview,
        )
        self.delivery_tree.configure(yscrollcommand=delivery_scroll.set)
        for column, title, width, anchor in (
            ("number", "N° commande", 130, "center"),
            ("sent", "Envoyée le", 135, "center"),
            ("supplier", "Fournisseur", 310, "w"),
            ("state", "Livraison", 145, "center"),
            ("remaining", "Unités restantes", 115, "center"),
            ("days", "Attente", 90, "center"),
        ):
            self.delivery_tree.heading(column, text=title)
            self.delivery_tree.column(
                column,
                width=width,
                anchor=anchor,
                stretch=column == "supplier",
            )
        delivery_scroll.pack(side="right", fill="y")
        self.delivery_tree.pack(side="left", fill="both", expand=True)
        self.delivery_tree.bind("<Double-1>", lambda event: self.open_deliveries())

        self.alert_box = tk.Frame(
            self.dashboard_panes,
            bg=COLORS["surface"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            padx=14,
            pady=10,
        )
        self.dashboard_panes.add(
            self.alert_box,
            weight=2,
        )
        tk.Label(
            self.alert_box,
            text="Alertes nécessitant une vérification",
            bg=COLORS["surface"],
            fg=COLORS["text"],
            font=("Segoe UI Semibold", 11),
        ).pack(anchor="w", pady=(0, 6))
        alerts_table = tk.Frame(self.alert_box, bg=COLORS["surface"])
        alerts_table.pack(fill="both", expand=True)
        self.alerts_tree = ttk.Treeview(
            alerts_table,
            columns=("number", "supplier", "type", "days"),
            show="headings",
            height=3,
        )
        alerts_scroll = ttk.Scrollbar(
            alerts_table,
            orient="vertical",
            command=self.alerts_tree.yview,
        )
        self.alerts_tree.configure(yscrollcommand=alerts_scroll.set)
        for column, title, width, anchor in (
            ("number", "N° commande", 130, "center"),
            ("supplier", "Fournisseur", 330, "w"),
            ("type", "Alerte", 260, "w"),
            ("days", "Retard / délai", 120, "center"),
        ):
            self.alerts_tree.heading(column, text=title)
            self.alerts_tree.column(
                column,
                width=width,
                anchor=anchor,
                stretch=column in {"supplier", "type"},
            )
        self.alerts_tree.tag_configure("warning", foreground=COLORS["danger"])
        alerts_scroll.pack(side="right", fill="y")
        self.alerts_tree.pack(side="left", fill="both", expand=True)
        self.alerts_tree.bind("<Double-1>", lambda event: self.open_alert())

        self.health_label = tk.Label(
            self,
            text="",
            bg=COLORS["background"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9),
            anchor="w",
        )
        self.health_label.pack(fill="x", pady=(10, 0))

        self.actions = ttk.Frame(self)
        self.actions.pack(fill="x", pady=(20, 0))
        ttk.Button(
            self.actions,
            text="Préparer une commande",
            style="Accent.TButton",
            command=lambda: self.app.show_page("new_order"),
        ).pack(side="left")
        ttk.Button(
            self.actions,
            text="Importer un catalogue",
            command=lambda: self.app.show_page("import"),
        ).pack(side="left", padx=8)
        self.after(180, self._set_initial_dashboard_sash)

    def _set_initial_dashboard_sash(self) -> None:
        """Donne un peu plus de place aux livraisons, puis laisse le réglage libre."""
        height = self.dashboard_panes.winfo_height()
        if height > 260:
            self.dashboard_panes.sashpos(0, int(height * 0.58))

    def open_deliveries(self) -> None:
        selected = self.delivery_tree.selection()
        order_id = int(selected[0]) if selected else None
        page: OrdersPage = self.app.pages["orders"]  # type: ignore[assignment]
        page.delivery_var.set("À recevoir")
        page.include_archived_var.set(False)
        self.app.show_page("orders")
        if order_id:
            page.select_order(order_id)

    def open_alert(self) -> None:
        selected = self.alerts_tree.selection()
        if not selected:
            return
        order_id = int(str(selected[0]).split(":", 1)[0])
        page: OrdersPage = self.app.pages["orders"]  # type: ignore[assignment]
        page.delivery_var.set("Toutes")
        page.include_archived_var.set(False)
        self.app.show_page("orders")
        page.select_order(order_id)

    def refresh(self) -> None:
        stats = self.database.dashboard_stats()
        for key, label in self.card_values.items():
            label.configure(text=f"{int(stats[key]):,}".replace(",", " "))
        latest = stats["latest_import"]
        if latest:
            when = datetime.fromisoformat(latest["imported_at"]).strftime(
                "%d/%m/%Y à %H:%M"
            )
            self.import_label.configure(text=latest["filename"])
            self.import_detail.configure(
                text=f"Dernier import le {when} • "
                f"{int(latest['row_count']):,} articles".replace(",", " ")
            )
        else:
            self.import_label.configure(text="Aucun catalogue importé")
            self.import_detail.configure(
                text="Commencez par importer la base tarifaire CAHPP."
            )
        self.delivery_tree.delete(*self.delivery_tree.get_children())
        for order in stats.get("delivery_orders", []):
            self.delivery_tree.insert(
                "",
                "end",
                iid=str(order["id"]),
                values=(
                    order["order_number"],
                    format_timestamp(order["sent_at"]),
                    order["supplier_name"],
                    order["delivery_status"],
                    format_number(
                        max(
                            0,
                            float(order["ordered_units"] or 0)
                            - float(order["received_units"] or 0),
                        ),
                        2,
                    ),
                    f"{max(0, int(order['waiting_days'] or 0))} j",
                ),
            )
        self.alerts_tree.delete(*self.alerts_tree.get_children())
        for index, alert in enumerate(stats.get("alerts", [])):
            self.alerts_tree.insert(
                "",
                "end",
                iid=f"{alert['id']}:{index}",
                tags=("warning",),
                values=(
                    alert["order_number"],
                    alert["supplier_name"],
                    alert["alert_type"],
                    f"{max(0, int(alert['overdue_days'] or 0))} j",
                ),
            )
        settings = self.database.get_settings()
        try:
            reminder_days = int(settings.get("backup_reminder_days", "14"))
        except ValueError:
            reminder_days = 14
        backup_due = timestamp_is_due(settings.get("last_backup_at", ""), reminder_days)
        backup_text = (
            "Sauvegarde recommandée"
            if backup_due
            else "Sauvegarde à jour au "
            + format_timestamp(settings.get("last_backup_at", ""))
        )
        integrity_result = settings.get("last_integrity_check_result", "")
        integrity_text = (
            "intégrité non contrôlée"
            if not integrity_result
            else "intégrité : " + integrity_result
        )
        self.health_label.configure(
            text=f"{backup_text}  •  {integrity_text}",
            fg=(
                COLORS["warning"]
                if backup_due or (integrity_result and integrity_result != "OK")
                else COLORS["success"]
            ),
        )
        self._valid = True
