"""Interface publique ; écrans et composants sont définis par domaine."""

from tkinter import messagebox
from .components import TreeviewSorter, TreeviewColumnSizer, FeedbackButton
from .base import BasePage
from .app import App
from .dashboard import DashboardPage
from .catalog import CatalogPage, ProductEditDialog
from .suggestions import SuggestionsPage
from .order import OrderPage, ManualProductDialog
from .documents import DocumentPropertiesDialog, OrderDocumentsDialog
from .tracking import ReceiptEntryDialog, OrderTrackingDialog
from .history import SelectiveDuplicateDialog, OrdersPage
from .statistics import StatisticsPage
from .suppliers import SuppliersPage
from .import_catalog import PriceChangesDialog, ImportPage
from .settings import SettingsPage, DiagnosticDialog
from .common import (
    COLORS,
    SYNC_INTERVAL_OPTIONS,
    DOCUMENT_TYPES,
    format_number,
    format_price,
    supplier_field_display_value,
    product_field_display_value,
    format_timestamp,
    months_before,
    timestamp_is_due,
    centered_window_position,
    format_pack,
    open_path,
    safe_filename,
    filter_supplier_names,
    configured_pdf_directory,
    suggested_pdf_filename,
    fractional_carton_lines,
    choose_pdf_path,
)

__all__ = [
    "TreeviewSorter",
    "TreeviewColumnSizer",
    "FeedbackButton",
    "BasePage",
    "App",
    "DashboardPage",
    "CatalogPage",
    "ProductEditDialog",
    "SuggestionsPage",
    "OrderPage",
    "ManualProductDialog",
    "DocumentPropertiesDialog",
    "OrderDocumentsDialog",
    "ReceiptEntryDialog",
    "OrderTrackingDialog",
    "SelectiveDuplicateDialog",
    "OrdersPage",
    "StatisticsPage",
    "SuppliersPage",
    "PriceChangesDialog",
    "ImportPage",
    "SettingsPage",
    "DiagnosticDialog",
    "COLORS",
    "SYNC_INTERVAL_OPTIONS",
    "DOCUMENT_TYPES",
    "format_number",
    "format_price",
    "supplier_field_display_value",
    "product_field_display_value",
    "format_timestamp",
    "months_before",
    "timestamp_is_due",
    "centered_window_position",
    "format_pack",
    "open_path",
    "safe_filename",
    "filter_supplier_names",
    "configured_pdf_directory",
    "suggested_pdf_filename",
    "fractional_carton_lines",
    "choose_pdf_path",
    "messagebox",
]
