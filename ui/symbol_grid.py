# ui/symbol_grid.py
from __future__ import annotations

import math
import numpy as np
from PySide6.QtCore import Qt, QSortFilterProxyModel, QTimer, QPoint, QThreadPool, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtGui import QStandardItemModel, QStandardItem, QColor, QFont
from PySide6.QtWidgets import (
    QWidget,
    QGridLayout,
    QScrollArea,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QTableView,
    QAbstractItemView,
    QHeaderView,
    QStackedWidget,
    QFrame,
    QSizePolicy,
    QDialog,
    QLineEdit,
    QDialogButtonBox,
    QFormLayout,
    QMessageBox,
    QComboBox,
    QDoubleSpinBox,
)

from PySide6.QtCore import Signal as _Signal, QObject as _QObject, QRunnable as _QRunnable

from core.zacks import ZacksClient
from core.barchart import get_opinion
from core.worker import Worker


class _RefreshSignals(_QObject):
    finished = _Signal()


class _RefreshWorker(_QRunnable):
    def __init__(self, data_manager, symbols, clear_cache=True):
        super().__init__()
        self.data_manager = data_manager
        self.symbols = symbols
        self.clear_cache = clear_cache
        self.signals = _RefreshSignals()

    def run(self):
        if self.clear_cache:
            self.data_manager.cache.clear()
            self.data_manager.ohlcv_cache.clear()
        self.data_manager.preload_all(self.symbols)
        self.signals.finished.emit()

from ui.chart_widget import ChartWidget


_NUM_ROLE = Qt.UserRole + 1

_GRADE_COLORS = {"A": "#44cc77", "B": "#88cc44", "C": "#ddaa44", "D": "#cc7744", "F": "#cc4444"}


def _grade_color(grade: str) -> str:
    return _GRADE_COLORS.get(grade.upper()[:1] if grade else "", "#aaaaaa")


_OPINION_COLORS = {
    "strong buy":  "#44cc77",
    "buy":         "#88cc44",
    "weak buy":    "#aacc44",
    "hold":        "#ddaa44",
    "weak sell":   "#cc7744",
    "sell":        "#cc5544",
    "strong sell": "#cc4444",
}


def _opinion_color(opinion: str) -> str:
    return _OPINION_COLORS.get(opinion.lower(), "#aaaaaa")


def _opinion_numeric(opinion: str) -> float:
    """Extract leading number from '100%', '96% Buy', etc. Returns NaN on failure."""
    try:
        token = opinion.strip().replace("%", " ").split()[0]
        return float(token)
    except (ValueError, AttributeError, IndexError):
        return float("nan")


# ---------------------------------------------------------------------------
# Momentum panel helpers
# ---------------------------------------------------------------------------

def _roc(close, period):
    if len(close) <= period:
        return None
    c0 = float(close[-period - 1])
    c1 = float(close[-1])
    if c0 == 0:
        return None
    return (c1 - c0) / c0 * 100.0


def _above_sma(close, period):
    if len(close) < period:
        return None
    ma = float(np.mean(close[-period:]))
    return float(close[-1]) > ma


def _rsi_last(close, period=14):
    if len(close) < period + 2:
        return None
    delta = np.diff(close.astype(float))
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    avg_g = float(np.mean(gain[-period:]))
    avg_l = float(np.mean(loss[-period:]))
    if avg_l == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + avg_g / avg_l)


class MomentumPanel(QFrame):
    """Aggregated portfolio momentum strip shown above the ledger."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("""
            MomentumPanel {
                background: #1a1a2e;
                border: 1px solid #333355;
                border-radius: 6px;
            }
        """)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 8, 12, 8)
        outer.setSpacing(4)

        title_lbl = QLabel("Portfolio Momentum")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(9)
        title_lbl.setFont(title_font)
        title_lbl.setStyleSheet("color: #aaaacc;")
        outer.addWidget(title_lbl)

        self._row = QHBoxLayout()
        self._row.setSpacing(24)
        outer.addLayout(self._row)

        self._stat_labels = {}
        self._placeholders()

    def _placeholders(self):
        specs = [
            ("advancing",      "Adv / Dec"),
            ("breadth_pct",    "Breadth"),
            ("roc5",           "ROC 5d"),
            ("roc20",          "ROC 20d"),
            ("roc60",          "ROC 60d"),
            ("above_50",       "Above SMA50"),
            ("above_200",      "Above SMA200"),
            ("avg_rsi",        "Avg RSI"),
            ("momentum_score", "Score"),
        ]
        for key, caption in specs:
            col = QVBoxLayout()
            col.setSpacing(1)
            cap_lbl = QLabel(caption)
            cap_lbl.setStyleSheet("color: #666688; font-size: 10px;")
            cap_lbl.setAlignment(Qt.AlignCenter)
            val_lbl = QLabel("—")
            val_lbl.setAlignment(Qt.AlignCenter)
            val_lbl.setStyleSheet("color: #cccccc; font-size: 13px; font-weight: bold;")
            col.addWidget(cap_lbl)
            col.addWidget(val_lbl)
            self._stat_labels[key] = val_lbl
            self._row.addLayout(col)
        self._row.addStretch(1)

    def _set(self, key, text, color="#cccccc"):
        lbl = self._stat_labels.get(key)
        if lbl:
            lbl.setText(text)
            lbl.setStyleSheet(f"color: {color}; font-size: 13px; font-weight: bold;")

    def refresh(self, symbols, data_manager):
        roc5_vals, roc20_vals, roc60_vals = [], [], []
        rsi_vals = []
        above50_count = above200_count = 0
        adv = dec = flat = 0
        n_with_data = 0

        for sym in symbols:
            data = data_manager.get_symbol_data(sym)
            if data is None:
                continue
            _, y = data
            y = np.asarray(y, dtype=float).flatten()
            if len(y) < 5:
                continue
            n_with_data += 1

            r5 = _roc(y, 5)
            if r5 is not None:
                roc5_vals.append(r5)
                if r5 > 0.5:
                    adv += 1
                elif r5 < -0.5:
                    dec += 1
                else:
                    flat += 1

            r20 = _roc(y, 20)
            if r20 is not None:
                roc20_vals.append(r20)

            r60 = _roc(y, 60)
            if r60 is not None:
                roc60_vals.append(r60)

            if _above_sma(y, 50) is True:
                above50_count += 1
            if _above_sma(y, 200) is True:
                above200_count += 1

            rv = _rsi_last(y)
            if rv is not None:
                rsi_vals.append(rv)

        if n_with_data == 0:
            return

        adv_color = "#44cc77" if adv > dec else ("#cc4444" if dec > adv else "#aaaaaa")
        self._set("advancing", f"{adv} / {dec}", adv_color)

        if adv + dec > 0:
            breadth = adv / (adv + dec) * 100.0
            bc = "#44cc77" if breadth >= 60 else ("#cc4444" if breadth <= 40 else "#ddaa44")
            self._set("breadth_pct", f"{breadth:.0f}%", bc)

        def _roc_color(v):
            return "#44cc77" if v > 0 else "#cc4444"

        if roc5_vals:
            med = float(np.median(roc5_vals))
            self._set("roc5", f"{med:+.1f}%", _roc_color(med))
        if roc20_vals:
            med = float(np.median(roc20_vals))
            self._set("roc20", f"{med:+.1f}%", _roc_color(med))
        if roc60_vals:
            med = float(np.median(roc60_vals))
            self._set("roc60", f"{med:+.1f}%", _roc_color(med))

        pct50 = above50_count / n_with_data * 100
        c50 = "#44cc77" if pct50 >= 60 else ("#cc4444" if pct50 <= 40 else "#ddaa44")
        self._set("above_50", f"{above50_count}/{n_with_data}  ({pct50:.0f}%)", c50)

        pct200 = above200_count / n_with_data * 100
        c200 = "#44cc77" if pct200 >= 60 else ("#cc4444" if pct200 <= 40 else "#ddaa44")
        self._set("above_200", f"{above200_count}/{n_with_data}  ({pct200:.0f}%)", c200)

        if rsi_vals:
            avg_rsi = float(np.mean(rsi_vals))
            rc = "#cc4444" if avg_rsi > 70 else ("#44cc77" if avg_rsi < 30 else "#cccccc")
            self._set("avg_rsi", f"{avg_rsi:.1f}", rc)

        score_parts = []
        if adv + dec > 0:
            score_parts.append((adv / (adv + dec), 0.30))
        if roc20_vals:
            med20 = float(np.median(roc20_vals))
            score_parts.append((max(0.0, min(1.0, (med20 + 10) / 20)), 0.20))
        if n_with_data > 0:
            score_parts.append((above50_count / n_with_data, 0.25))
        if rsi_vals:
            avg_rsi = float(np.mean(rsi_vals))
            score_parts.append((avg_rsi / 100.0, 0.25))

        if score_parts:
            total_w = sum(w for _, w in score_parts)
            score = sum(v * w for v, w in score_parts) / total_w * 100
            if score >= 65:
                sc, label = "#44cc77", "Bullish"
            elif score <= 35:
                sc, label = "#cc4444", "Bearish"
            else:
                sc, label = "#ddaa44", "Neutral"
            self._set("momentum_score", f"{score:.0f}  {label}", sc)



class LedgerSortProxy(QSortFilterProxyModel):
    """Sort numeric columns numerically, text columns alphabetically.

    We store numeric values in _NUM_ROLE. For text columns we fall back to DisplayRole.
    """

    def lessThan(self, left, right):  # noqa: N802 (Qt naming)
        ld = left.data(_NUM_ROLE)
        rd = right.data(_NUM_ROLE)

        # If both sides have numeric data, compare numerically (NaNs go last)
        try:
            if ld is not None and rd is not None:
                lf = float(ld)
                rf = float(rd)
                if math.isnan(lf) and math.isnan(rf):
                    return False
                if math.isnan(lf):
                    return False
                if math.isnan(rf):
                    return True
                return lf < rf
        except Exception:
            pass

        # Otherwise compare as text
        ls = str(left.data(Qt.DisplayRole) or "")
        rs = str(right.data(Qt.DisplayRole) or "")
        return ls.lower() < rs.lower()


class SymbolGrid(QWidget):
    def __init__(self, symbols, data_manager, positions=None):
        super().__init__()

        # Keep original order for re-sorting.
        self.base_symbols = list(dict.fromkeys(symbols))
        self.symbols = list(self.base_symbols)

        self.data_manager = data_manager
        self.positions = positions or {}

        # Sort settings
        self.sort_desc = True  # most profitable first

        # App pages:
        #   1) Synopsis table
        #   2) Charts (first half)
        #   3) Charts (second half)
        self.page = 0
        self.total_pages = 3

        # --- Top controls ----------------------------------------------------
        self.controls_bar = QWidget()
        controls = QHBoxLayout(self.controls_bar)
        controls.setContentsMargins(0, 0, 0, 0)

        self._vgm_scores: dict[str, str] = {}
        self._rank_scores: dict[str, str] = {}
        self._zacks_client: ZacksClient | None = None
        self._vgm_pending = 0
        self._bc_opinions: dict[str, str] = {}
        self._bc_pending = 0
        self._thread_pool = QThreadPool.globalInstance()

        self.sort_btn = QPushButton("Sort P/L ▼")
        self.sort_btn.setToolTip(
            "Sort by profitability (unrealized P/L %) — toggle ascending/descending"
        )
        self.sort_btn.clicked.connect(self.toggle_sort)
        controls.addWidget(self.sort_btn)

        self.refresh_btn = QPushButton("Refresh Prices")
        self.refresh_btn.setToolTip("Re-fetch latest price data from Yahoo Finance")
        self.refresh_btn.clicked.connect(self._refresh_prices)
        controls.addWidget(self.refresh_btn)

        self.add_btn = QPushButton("Add Position")
        self.add_btn.setToolTip("Add a new stock position")
        self.add_btn.clicked.connect(self._add_position)
        controls.addWidget(self.add_btn)

        self.remove_btn = QPushButton("Remove Position")
        self.remove_btn.setToolTip("Remove selected position from portfolio")
        self.remove_btn.clicked.connect(self._remove_position)
        controls.addWidget(self.remove_btn)

        self.vgm_btn = QPushButton("Fetch VGM")
        self.vgm_btn.setToolTip("Fetch Zacks VGM scores for all symbols")
        self.vgm_btn.clicked.connect(self._fetch_vgm)
        controls.addWidget(self.vgm_btn)

        self.bc_btn = QPushButton("Fetch BC Opinion")
        self.bc_btn.setToolTip("Fetch Barchart opinion for all symbols")
        self.bc_btn.clicked.connect(self._fetch_bc)
        controls.addWidget(self.bc_btn)

        controls.addStretch(1)

        self.page_lbl = QLabel("")
        self.page_lbl.setStyleSheet("color: #666666;")
        controls.addWidget(self.page_lbl)

        self.prev_page_btn = QPushButton("◀ Page")
        self.prev_page_btn.clicked.connect(self.prev_page)
        controls.addWidget(self.prev_page_btn)

        self.next_page_btn = QPushButton("Page ▶")
        self.next_page_btn.clicked.connect(self.next_page)
        controls.addWidget(self.next_page_btn)

        hint = QLabel("(Table headers sort; charts are split in half)")
        hint.setStyleSheet("color: #666666;")
        controls.addWidget(hint)

        # --- Ledger table ----------------------------------------------------
        self.ledger = QTableView()
        self.ledger.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.ledger.setSelectionMode(QAbstractItemView.SingleSelection)
        self.ledger.setAlternatingRowColors(True)
        self.ledger.setSortingEnabled(True)
        self.ledger.verticalHeader().setVisible(False)
        self.ledger.horizontalHeader().setStretchLastSection(True)
        # Let the table fill its container width.
        self.ledger.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        self.ledger_model = QStandardItemModel(0, 0, self)
        # Synopsis columns
        # NOTE: P/L% is unrealized percent based on last close vs avg cost.
        self.ledger_model.setHorizontalHeaderLabels(
            ["Symbol", "Acct", "Qty", "Avg", "Last", "MV", "P/L", "P/L%", "Rank", "VGM", "Opinion"]
        )
        self.ledger_proxy = LedgerSortProxy(self)
        self.ledger_proxy.setSourceModel(self.ledger_model)
        self.ledger.setModel(self.ledger_proxy)

        # Click a row to jump to that symbol on the chart pages
        self.ledger.clicked.connect(self._ledger_row_activated)

        # --- Pages -----------------------------------------------------------
        self.stack = QStackedWidget()

        # Page 1: Synopsis table (centered, ~2/3 width)
        synopsis_page = QWidget()
        synopsis_layout = QHBoxLayout(synopsis_page)
        synopsis_layout.setContentsMargins(0, 0, 0, 0)

        self._synopsis_wrap = QWidget()
        wrap_layout = QVBoxLayout(self._synopsis_wrap)
        wrap_layout.setContentsMargins(0, 0, 0, 0)
        wrap_layout.setSpacing(8)

        self.momentum_panel = MomentumPanel()
        wrap_layout.addWidget(self.momentum_panel)
        wrap_layout.addWidget(self.ledger)

        synopsis_layout.addStretch(1)
        synopsis_layout.addWidget(self._synopsis_wrap)
        synopsis_layout.addStretch(1)
        self.stack.addWidget(synopsis_page)

        # Page 2: Charts (first half)
        self.scroll_a = QScrollArea()
        self.container_a = QWidget()
        self.grid_a = QGridLayout(self.container_a)
        self.scroll_a.setWidget(self.container_a)
        self.scroll_a.setWidgetResizable(True)
        self.stack.addWidget(self.scroll_a)

        # Page 3: Charts (second half)
        self.scroll_b = QScrollArea()
        self.container_b = QWidget()
        self.grid_b = QGridLayout(self.container_b)
        self.scroll_b.setWidget(self.container_b)
        self.scroll_b.setWidgetResizable(True)
        self.stack.addWidget(self.scroll_b)

        layout = QVBoxLayout(self)
        layout.addWidget(self.controls_bar)
        layout.addWidget(self.stack)

        self.widgets: dict[str, ChartWidget] = {}
        self._initialized = False

        print("PRELOAD_ALL (batch)")
        self.data_manager.preload_all(self.symbols)

        print("CREATE_WIDGETS")
        self.create_widgets()

        # Build ledger after widgets have data
        self.rebuild_ledger()

        # Populate momentum panel
        self.momentum_panel.refresh(self.symbols, self.data_manager)

        # Default: sort by profitability descending
        self.apply_profit_sort()

        self.set_page(0)
        self._update_synopsis_width()
        self.layout_charts_pages()
        self._initialized = True

    # ------------------------- Ledger helpers ------------------------------

    def _num_item(self, text: str, value: float | None):
        it = QStandardItem(text)
        if value is None:
            it.setData(float("nan"), _NUM_ROLE)
        else:
            it.setData(float(value), _NUM_ROLE)
        # Right align numeric columns (still looks fine for NaNs)
        it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return it

    def rebuild_ledger(self):
        self.ledger_model.setRowCount(0)

        for sym in self.symbols:
            pos = self.positions.get(sym) or {}
            qty = pos.get("qty")
            avg = pos.get("avg_cost")
            tag = pos.get("acct_tag", "")

            # last close from preloaded series (y)
            last = None
            data = self.data_manager.get_symbol_data(sym)
            if data is not None:
                _, y = data
                try:
                    if y is not None and len(y) > 0:
                        last = float(y[-1])
                except Exception:
                    last = None

            mv = pl = pl_pct = None
            try:
                if qty is not None and avg is not None and last is not None:
                    qty_f = float(qty)
                    avg_f = float(avg)
                    last_f = float(last)
                    mv = last_f * qty_f
                    pl = (last_f - avg_f) * qty_f
                    pl_pct = ((last_f - avg_f) / avg_f) * 100.0 if avg_f else 0.0
            except Exception:
                mv = pl = pl_pct = None

            grade = self._vgm_scores.get(sym, "")
            vgm_item = QStandardItem(grade)
            vgm_item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)

            rank_item = QStandardItem(self._rank_scores.get(sym, ""))
            rank_item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)

            opinion = self._bc_opinions.get(sym, "")
            opinion_item = QStandardItem(opinion)
            opinion_item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
            opinion_item.setData(_opinion_numeric(opinion), _NUM_ROLE)

            row = [
                QStandardItem(sym),
                QStandardItem(str(tag)),
                self._num_item(f"{float(qty):g}" if qty is not None else "", qty),
                self._num_item(f"{float(avg):.2f}" if avg is not None else "", avg),
                self._num_item(f"{float(last):.2f}" if last is not None else "", last),
                self._num_item(f"${mv:,.0f}" if mv is not None else "", mv),
                self._num_item(f"${pl:,.0f}" if pl is not None else "", pl),
                self._num_item(f"{pl_pct:+.1f}%" if pl_pct is not None else "", pl_pct),
                rank_item,
                vgm_item,
                opinion_item,
            ]

            # Color negative P/L red (and green-ish for positive)
            if pl is not None:
                color = "#cc4444" if pl < 0 else "#1a7a1a"
                font = QFont()
                font.setBold(True)
                for col in (6, 7):
                    row[col].setForeground(QColor(color))
                    row[col].setFont(font)

            self.ledger_model.appendRow(row)

        # Default ledger sort: P/L% descending (matches your main sort)
        self.ledger.sortByColumn(7, Qt.DescendingOrder)

    def _ledger_row_activated(self, index):
        if not index.isValid():
            return
        src = self.ledger_proxy.mapToSource(index)
        sym_item = self.ledger_model.item(src.row(), 0)
        if sym_item is None:
            return
        sym = sym_item.text()
        col = src.column()
        if col in (8, 9):  # Rank or VGM
            QDesktopServices.openUrl(QUrl(f"https://www.zacks.com/stock/quote/{sym}"))
        elif col == 10:    # Barchart Opinion
            QDesktopServices.openUrl(QUrl(f"https://www.barchart.com/stocks/quotes/{sym}"))
        else:
            self.chart_clicked(sym)

    def show_symbol_on_charts(self, symbol: str):
        """Switch to the appropriate chart page and scroll to the symbol."""
        if symbol not in self.symbols:
            return

        split = max(1, math.ceil(len(self.symbols) / 2))
        idx = self.symbols.index(symbol)

        # Page index in the stacked widget: 0=Synopsis, 1=Charts 1, 2=Charts 2
        if idx < split:
            self.set_page(1)
            scroll = self.scroll_a
        else:
            self.set_page(2)
            scroll = self.scroll_b

        w = self.widgets.get(symbol)
        if w is None:
            return

        # Ensure layout has placed widgets before we scroll.
        self.layout_charts_pages()

        
# Defer until after the page switch + relayout so we reliably land on
        # the clicked symbol.

        def _do_scroll():
            try:
                # ensureWidgetVisible() is sometimes flaky right after a page swap,
                # so we also force the scroll bar to the widget's y-position.
                scroll.ensureWidgetVisible(w, 10, 10)
                pos = w.mapTo(scroll.widget(), QPoint(0, 0)).y()
                scroll.verticalScrollBar().setValue(max(0, pos - 10))
            except Exception:
                scroll.verticalScrollBar().setValue(0)

        # A tiny delay helps when switching stacked pages so the viewport is ready.
        QTimer.singleShot(30, _do_scroll)

        # ----------------------- Chart widget grid -----------------------------

    def create_widgets(self):
        for symbol in self.base_symbols:
            pos = self.positions.get(symbol)
            w = ChartWidget(symbol, position=pos)
            w.clicked.connect(self.chart_clicked)
            self.widgets[symbol] = w

            data = self.data_manager.get_symbol_data(symbol)
            if data is not None:
                w.set_data(data)

    def _profitability_pct(self, symbol: str):
        """Return unrealized P/L percent based on last close vs avg cost, or None."""
        pos = self.positions.get(symbol)
        if not pos:
            return None

        try:
            avg = float(pos.get("avg_cost"))
            if avg <= 0:
                return None
        except Exception:
            return None

        data = self.data_manager.get_symbol_data(symbol)
        if data is None:
            return None
        _, y = data
        if y is None or len(y) == 0:
            return None

        last = float(y[-1])
        return (last - avg) / avg

    def apply_profit_sort(self):
        """Sort self.symbols by profitability and rebuild layout."""
        prof = []
        rest = []

        for sym in self.base_symbols:
            pct = self._profitability_pct(sym)
            if pct is None:
                rest.append(sym)
            else:
                prof.append((sym, pct))

        prof.sort(key=lambda t: t[1], reverse=self.sort_desc)
        self.symbols = [s for s, _ in prof] + rest

        # Keep user on the same app page, but update chart splits.

        # Ledger should match the current overall ordering (but remains user-sortable via headers)
        self.rebuild_ledger()

        if self._initialized:
            self.layout_charts_pages()

    def toggle_sort(self):
        self.sort_desc = not self.sort_desc
        self.sort_btn.setText("Sort P/L ▼" if self.sort_desc else "Sort P/L ▲")
        self.apply_profit_sort()

    def _update_page_controls(self):
        self.page = max(0, min(self.page, self.total_pages - 1))
        names = ["Synopsis", "Charts 1", "Charts 2"]
        label = names[self.page] if 0 <= self.page < len(names) else f"Page {self.page + 1}"
        self.page_lbl.setText(f"{label}  (Page {self.page + 1} / {self.total_pages})")
        self.prev_page_btn.setEnabled(self.page > 0)
        self.next_page_btn.setEnabled(self.page < self.total_pages - 1)

    def next_page(self):
        if self.page < self.total_pages - 1:
            self.set_page(self.page + 1)

    def prev_page(self):
        if self.page > 0:
            self.set_page(self.page - 1)

    def set_page(self, page_index: int):
        self.page = max(0, min(int(page_index), self.total_pages - 1))
        self.stack.setCurrentIndex(self.page)
        self._update_page_controls()

    def _clear_grid_layout(self, layout: QGridLayout):
        """Safely remove all widgets from a grid layout.

        IMPORTANT: takeAt() alone doesn't detach the widget; we must unparent
        it or the geometry can get jumbled after repeated relayouts.
        """
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.setParent(None)

    def _layout_symbols_into_grid(self, symbols: list[str], layout: QGridLayout):
        width = self.width() if self.width() > 0 else 1200
        cols = max(1, width // 320)

        row = 0
        col = 0
        for symbol in symbols:
            w = self.widgets[symbol]
            layout.addWidget(w, row, col)
            w.setVisible(True)
            col += 1
            if col >= cols:
                col = 0
                row += 1

    def layout_charts_pages(self):
        """Lay out charts into two fixed pages: first half + second half."""
        if not self.widgets:
            return

        split = max(1, math.ceil(len(self.symbols) / 2))
        syms_a = self.symbols[:split]
        syms_b = self.symbols[split:]

        self._clear_grid_layout(self.grid_a)
        self._clear_grid_layout(self.grid_b)

        self._layout_symbols_into_grid(syms_a, self.grid_a)
        self._layout_symbols_into_grid(syms_b, self.grid_b)

    def _update_synopsis_width(self):
        """Keep synopsis table at ~2/3 of available width."""
        wrap = getattr(self, "_synopsis_wrap", None)
        if wrap is None:
            return
        w = int(self.width() * 0.66)
        w = max(900, w)
        wrap.setFixedWidth(w)

    def resizeEvent(self, event):
        self._update_synopsis_width()
        if getattr(self, "_initialized", False):
            self.layout_charts_pages()
        super().resizeEvent(event)

    # --------------------------- Refresh prices --------------------------------

    def _refresh_prices(self):
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText("Refreshing…")
        worker = _RefreshWorker(self.data_manager, self.symbols)
        worker.signals.finished.connect(self._on_refresh_done)
        self._thread_pool.start(worker)

    def _on_refresh_done(self):
        for sym, w in self.widgets.items():
            data = self.data_manager.get_symbol_data(sym)
            if data is not None:
                w.set_data(data)
        self.rebuild_ledger()
        self.momentum_panel.refresh(self.symbols, self.data_manager)
        self.apply_profit_sort()
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText("Refresh Prices")

    # --------------------------- Add position ----------------------------------

    def _add_position(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Add Position")
        form = QFormLayout(dlg)

        acct_field = QComboBox()
        acct_field.addItems(["F", "S", "RH"])
        form.addRow("Account:", acct_field)

        sym_field = QLineEdit()
        sym_field.setPlaceholderText("e.g. AAPL")
        form.addRow("Symbol:", sym_field)

        qty_field = QDoubleSpinBox()
        qty_field.setDecimals(4)
        qty_field.setMaximum(1_000_000)
        qty_field.setMinimum(0.0001)
        form.addRow("Quantity:", qty_field)

        price_field = QDoubleSpinBox()
        price_field.setDecimals(4)
        price_field.setMaximum(1_000_000)
        price_field.setPrefix("$ ")
        form.addRow("Price:", price_field)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)

        if dlg.exec() != QDialog.Accepted:
            return

        acct = acct_field.currentText()
        sym  = sym_field.text().strip().upper()
        qty  = qty_field.value()
        price = price_field.value()

        if not sym:
            QMessageBox.warning(self, "Add Position", "Symbol cannot be empty.")
            return

        # Append to symbols.txt
        try:
            with open("symbols.txt", "a", newline="", encoding="utf-8") as f:
                f.write(f"\n{acct},{sym},{qty},{price}")
        except Exception as e:
            QMessageBox.warning(self, "Add Position", f"Could not write symbols.txt:\n{e}")
            return

        # Merge into positions
        existing = self.positions.get(sym, {"qty": 0.0, "cost": 0.0, "accts": set()})
        new_qty  = existing["qty"] + qty
        new_cost = existing.get("cost", existing.get("avg_cost", 0.0) * existing["qty"]) + qty * price
        accts    = existing.get("accts", set()) | {acct}
        self.positions[sym] = {
            "qty":      new_qty,
            "avg_cost": new_cost / new_qty,
            "acct_tag": "&".join(sorted(accts)),
            "cost":     new_cost,
            "accts":    accts,
        }

        # Add to symbol lists if new
        if sym not in self.base_symbols:
            self.base_symbols.append(sym)
        if sym not in self.symbols:
            self.symbols.append(sym)

        # Fetch price data then update UI
        self.add_btn.setEnabled(False)
        self.add_btn.setText("Fetching…")
        worker = _RefreshWorker(self.data_manager, [sym], clear_cache=False)
        worker.signals.finished.connect(lambda: self._on_position_added(sym))
        self._thread_pool.start(worker)

    def _on_position_added(self, sym: str):
        # Create chart widget if new
        if sym not in self.widgets:
            from ui.chart_widget import ChartWidget
            pos = self.positions.get(sym)
            w = ChartWidget(sym, position=pos)
            w.clicked.connect(self.chart_clicked)
            self.widgets[sym] = w

        data = self.data_manager.get_symbol_data(sym)
        if data is not None:
            self.widgets[sym].set_data(data)

        self.rebuild_ledger()
        self.momentum_panel.refresh(self.symbols, self.data_manager)
        self.apply_profit_sort()
        self.layout_charts_pages()

        self.add_btn.setEnabled(True)
        self.add_btn.setText("Add Position")

    # -------------------------- Remove position --------------------------------

    def _remove_position(self):
        # Get selected symbol from the ledger
        indexes = self.ledger.selectedIndexes()
        if not indexes:
            QMessageBox.information(self, "Remove Position", "Select a row in the table first.")
            return
        src = self.ledger_proxy.mapToSource(indexes[0])
        sym_item = self.ledger_model.item(src.row(), 0)
        if sym_item is None:
            return
        sym = sym_item.text()

        confirm = QMessageBox.question(
            self, "Remove Position",
            f"Remove {sym} from the portfolio?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        # Remove from symbols.txt (all lines for this symbol)
        try:
            with open("symbols.txt", "r", encoding="utf-8") as f:
                lines = f.readlines()
            kept = []
            for line in lines:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    kept.append(line)
                    continue
                parts = [p.strip() for p in stripped.split(",")]
                if len(parts) >= 2 and parts[1].upper() == sym:
                    continue
                kept.append(line)
            with open("symbols.txt", "w", encoding="utf-8") as f:
                f.writelines(kept)
        except Exception as e:
            QMessageBox.warning(self, "Remove Position", f"Could not update symbols.txt:\n{e}")
            return

        # Remove chart widget from layouts and destroy it
        w = self.widgets.pop(sym, None)
        if w is not None:
            w.setParent(None)
            w.deleteLater()

        # Remove from all symbol lists and data caches
        self.base_symbols = [s for s in self.base_symbols if s != sym]
        self.symbols      = [s for s in self.symbols      if s != sym]
        self.positions.pop(sym, None)
        self.data_manager.cache.pop(sym, None)
        self._vgm_scores.pop(sym, None)
        self._rank_scores.pop(sym, None)
        self._bc_opinions.pop(sym, None)

        # Remove ohlcv cache entries for this symbol
        for key in [k for k in self.data_manager.ohlcv_cache if k[0] == sym]:
            del self.data_manager.ohlcv_cache[key]

        self.rebuild_ledger()
        self.momentum_panel.refresh(self.symbols, self.data_manager)
        self.apply_profit_sort()
        self.layout_charts_pages()

    # ----------------------------- Zacks VGM ----------------------------------

    def _fetch_vgm(self):
        if self._zacks_client is None:
            self._zacks_client = ZacksClient()

        if not self._zacks_client.logged_in:
            dlg = QDialog(self)
            dlg.setWindowTitle("KeePass Master Password")
            form = QFormLayout(dlg)
            kp_pw_field = QLineEdit()
            kp_pw_field.setEchoMode(QLineEdit.Password)
            form.addRow("Master password:", kp_pw_field)
            btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            btns.accepted.connect(dlg.accept)
            btns.rejected.connect(dlg.reject)
            form.addRow(btns)

            if dlg.exec() != QDialog.Accepted:
                return

            try:
                from pykeepass import PyKeePass
                kp = PyKeePass("/home/dave/Documents/Database.kdbx", password=kp_pw_field.text())
                group = kp.find_groups(name="portfolio", first=True)
                entry = kp.find_entries(title="Zacks", group=group, first=True) if group else None
                if entry is None:
                    entry = kp.find_entries(title="Zacks", first=True)
                if entry is None:
                    titles = [e.title for e in kp.entries]
                    QMessageBox.warning(self, "KeePass Error",
                        f"No entry titled 'Zacks' found.\nAvailable entries: {titles}")
                    self._zacks_client = None
                    return
                username = entry.username
                password = entry.password
            except Exception as e:
                QMessageBox.warning(self, "KeePass Error", f"Could not read credentials:\n{e}")
                self._zacks_client = None
                return

            ok = self._zacks_client.login(username, password)
            if not ok:
                QMessageBox.warning(self, "Zacks Login", "Login failed — check your credentials.")
                self._zacks_client = None
                return

        self.vgm_btn.setEnabled(False)
        self.vgm_btn.setText("Fetching…")
        self._vgm_pending = len(self.symbols)

        for sym in self.symbols:
            worker = Worker(self._zacks_client.get_quote_data, sym)
            worker.signals.finished.connect(self._on_vgm_result)
            worker.signals.error.connect(self._on_vgm_error)
            self._thread_pool.start(worker)

    def _on_vgm_result(self, sym: str, data: object):
        if isinstance(data, dict):
            vgm  = data.get("vgm", "N/A")
            rank = data.get("rank", "N/A")
        else:
            vgm, rank = str(data), "N/A"
        self._vgm_scores[sym]  = vgm
        self._rank_scores[sym] = rank
        self._update_vgm_cell(sym, vgm)
        self._update_rank_cell(sym, rank)
        self._vgm_pending -= 1
        if self._vgm_pending <= 0:
            self.vgm_btn.setEnabled(True)
            self.vgm_btn.setText("Fetch VGM")

    def _on_vgm_error(self, msg: str):
        self._vgm_pending -= 1
        if self._vgm_pending <= 0:
            self.vgm_btn.setEnabled(True)
            self.vgm_btn.setText("Fetch VGM")

    def _update_rank_cell(self, sym: str, rank: str):
        for row in range(self.ledger_model.rowCount()):
            if self.ledger_model.item(row, 0).text() == sym:
                item = self.ledger_model.item(row, 8)
                if item is None:
                    item = QStandardItem()
                    item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                    self.ledger_model.setItem(row, 8, item)
                item.setText(rank)
                break

    def _update_vgm_cell(self, sym: str, grade: str):
        for row in range(self.ledger_model.rowCount()):
            if self.ledger_model.item(row, 0).text() == sym:
                item = self.ledger_model.item(row, 9)
                if item is None:
                    item = QStandardItem()
                    item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                    self.ledger_model.setItem(row, 9, item)
                item.setText(grade)
                break

    # -------------------------- Barchart Opinion ------------------------------

    def _fetch_bc(self):
        self.bc_btn.setEnabled(False)
        self.bc_btn.setText("Fetching…")
        self._bc_pending = len(self.symbols)

        for sym in self.symbols:
            worker = Worker(get_opinion, sym)
            worker.signals.finished.connect(self._on_bc_result)
            worker.signals.error.connect(self._on_bc_error)
            self._thread_pool.start(worker)

    def _on_bc_result(self, sym: str, opinion: object):
        self._bc_opinions[sym] = str(opinion)
        self._update_bc_cell(sym, str(opinion))
        self._bc_pending -= 1
        if self._bc_pending <= 0:
            self.bc_btn.setEnabled(True)
            self.bc_btn.setText("Fetch BC Opinion")

    def _on_bc_error(self, msg: str):
        self._bc_pending -= 1
        if self._bc_pending <= 0:
            self.bc_btn.setEnabled(True)
            self.bc_btn.setText("Fetch BC Opinion")

    def _update_bc_cell(self, sym: str, opinion: str):
        for row in range(self.ledger_model.rowCount()):
            if self.ledger_model.item(row, 0).text() == sym:
                item = self.ledger_model.item(row, 10)
                if item is None:
                    item = QStandardItem()
                    item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                    self.ledger_model.setItem(row, 10, item)
                item.setText(opinion)
                item.setData(_opinion_numeric(opinion), _NUM_ROLE)
                break

    def chart_clicked(self, symbol):
        from ui.chart_dialog import ChartDialog

        idx = self.symbols.index(symbol) if symbol in self.symbols else 0
        dialog = ChartDialog(
            symbols=self.symbols,
            start_index=idx,
            data_manager=self.data_manager,
            positions=self.positions,
        )
        dialog.exec()
