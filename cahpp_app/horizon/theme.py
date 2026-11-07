"""Palette issue du logo fourni et du projet associatif LADAPT 2024-2030."""

from PySide6.QtGui import QColor, QFont, QPalette

BLUE = "#1D4084"  # fond du logo fourni
YELLOW = "#FFC432"  # aplats du document de référence
SKY = "#58A5DB"


def apply_theme(app, dark=False):
    colors = {
        "background": "#14243C" if dark else "#F3F6FB",
        "panel": "#1B304C" if dark else "#FFFFFF",
        "text": "#EFF5FF" if dark else "#172F50",
        "muted": "#B3C7E1" if dark else "#5E7290",
        "border": "#38506D" if dark else "#DCE5F0",
        "tint": "#233E64" if dark else "#EAF1FB",
    }
    bg, panel, text, muted, border, tint = [
        colors[k] for k in ("background", "panel", "text", "muted", "border", "tint")
    ]
    palette = QPalette()
    for role, color in [
        (QPalette.ColorRole.Window, bg),
        (QPalette.ColorRole.WindowText, text),
        (QPalette.ColorRole.Base, panel),
        (QPalette.ColorRole.AlternateBase, tint),
        (QPalette.ColorRole.Text, text),
        (QPalette.ColorRole.Button, panel),
        (QPalette.ColorRole.ButtonText, text),
        (QPalette.ColorRole.Highlight, BLUE),
        (QPalette.ColorRole.HighlightedText, "#FFFFFF"),
        (QPalette.ColorRole.ToolTipBase, panel),
        (QPalette.ColorRole.ToolTipText, text),
    ]:
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(f"""
        QWidget {{ color:{text}; }}
        QMainWindow,QWidget#canvas {{ background:{bg}; }}
        QFrame#sidebar {{ background:{BLUE}; border:0; }}
        QFrame#sidebar QLabel {{ color:white; background:transparent; }}
        QLabel#brand {{ font-size:22px; font-weight:700; letter-spacing:2px; }}
        QLabel#brandSub {{ color:#C9D9EF; font-size:12px; }}
        QPushButton#nav {{ background:transparent; color:#D7E5F7; border:0; padding:13px 16px; text-align:left; border-radius:9px; font-weight:600; }}
        QPushButton#nav:hover {{ background:#2A5195; }}
        QPushButton#nav:checked {{ background:{YELLOW}; color:#17305B; }}
        QFrame#topbar {{ background:{panel}; border-bottom:1px solid {border}; }}
        QFrame#card {{ background:{panel}; border:1px solid {border}; border-radius:12px; }}
        QLabel {{ background:transparent; }}
        QLabel#title {{ font-size:27px; font-weight:700; }}
        QLabel#heading {{ font-size:16px; font-weight:700; }}
        QLabel#muted {{ color:{muted}; }}
        QLabel#metricValue {{ font-size:27px; font-weight:700; }}
        QLabel#eyebrow {{ color:{SKY if dark else BLUE}; font-size:11px; font-weight:700; letter-spacing:1px; }}
        QLabel#badge {{ background:{tint}; color:{text}; padding:5px 9px; border-radius:6px; font-size:11px; }}
        QLabel#warning {{ background:#FFF2C9; color:#6A4B00; padding:11px; border-radius:8px; }}
        QPushButton {{ border:1px solid {border}; background:{panel}; border-radius:7px; padding:9px 12px; font-weight:600; }}
        QPushButton:hover {{ background:{tint}; border-color:{SKY}; }}
        QPushButton:disabled {{ color:{muted}; background:{bg}; border-color:{border}; }}
        QPushButton#primary {{ background:{BLUE}; color:white; border:1px solid {BLUE}; }}
        QPushButton#primary:hover {{ background:#28569F; }}
        QPushButton#primary:disabled {{ background:{tint}; color:{muted}; border-color:{border}; }}
        QPushButton#accent {{ background:{YELLOW}; color:#17305B; border-color:{YELLOW}; }}
        QPushButton#accent:hover {{ background:#FFD45F; }}
        QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox,QTextEdit {{ background:{panel}; border:1px solid {border}; border-radius:7px; padding:8px; min-height:20px; selection-background-color:{BLUE}; selection-color:white; }}
        QLineEdit:focus,QComboBox:focus,QTextEdit:focus {{ border:2px solid {SKY}; }}
        QComboBox QAbstractItemView {{ background:{panel}; color:{text}; selection-background-color:{tint}; selection-color:{text}; }}
        QCheckBox {{ spacing:8px; padding:5px 0; }}
        QCheckBox::indicator {{ width:17px; height:17px; }}
        QTableView {{ background:{panel}; alternate-background-color:{panel}; border:0; gridline-color:{border}; selection-background-color:{tint}; selection-color:{text}; outline:0; }}
        QTableView::item {{ padding:8px; border-bottom:1px solid {border}; }}
        QTableView::item:selected {{ color:{text}; background:{tint}; }}
        QHeaderView::section {{ background:{tint}; color:{muted}; border:0; border-bottom:1px solid {border}; padding:11px 8px; font-weight:600; }}
        QScrollArea {{ border:0; background:transparent; }}
        QScrollBar:vertical {{ background:{bg}; width:10px; border:0; }}
        QScrollBar::handle:vertical {{ background:{border}; border-radius:5px; min-height:25px; }}
        QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {{ height:0; }}
        QSplitter::handle {{ background:{bg}; width:12px; }}
        QProgressBar {{ border:0; border-radius:3px; background:{tint}; min-height:6px; text-align:center; }}
        QProgressBar::chunk {{ background:{YELLOW}; border-radius:3px; }}
        QStatusBar {{ background:{panel}; border-top:1px solid {border}; color:{muted}; }}
        QToolTip {{ background:{panel}; color:{text}; border:1px solid {border}; padding:7px; }}
        QDialog {{ background:{bg}; }}
    """)
    app.setProperty("horizonColors", colors)
    app.setProperty("horizonDark", dark)
    return colors
