from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton
import pyqtgraph as pg
import numpy as np
from datetime import datetime


def sma(values: np.ndarray, period: int) -> np.ndarray:
    """Simple moving average that tolerates NaNs (e.g., leading NaNs)."""
    values = np.asarray(values, dtype=float)
    n = len(values)
    out = np.full(n, np.nan, dtype=float)
    if period <= 0 or n < period:
        return out

    for i in range(period - 1, n):
        w = values[i - period + 1:i + 1]
        out[i] = np.nan if np.all(np.isnan(w)) else float(np.nanmean(w))
    return out


def ema(values: np.ndarray, period: int) -> np.ndarray:
    """Exponential moving average that tolerates NaNs."""
    values = np.asarray(values, dtype=float)
    n = len(values)
    out = np.full(n, np.nan, dtype=float)
    if period <= 0 or n < period:
        return out

    finite = np.isfinite(values)
    if not np.any(finite):
        return out

    i0 = int(np.argmax(finite))
    if i0 + period > n:
        return out

    alpha = 2.0 / (period + 1.0)
    seed = float(np.nanmean(values[i0:i0 + period]))
    i_seed = i0 + period - 1
    out[i_seed] = seed

    for i in range(i_seed + 1, n):
        prev = out[i - 1]
        x = values[i]
        out[i] = prev if not np.isfinite(x) else (alpha * x + (1.0 - alpha) * prev)
    return out


def rsi(close: np.ndarray, period: int = 14) -> np.ndarray:
    close = np.asarray(close, dtype=float)
    if len(close) < period + 2:
        return np.full_like(close, np.nan)

    delta = np.diff(close, prepend=close[0])
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)

    avg_gain = np.empty_like(close); avg_gain[:] = np.nan
    avg_loss = np.empty_like(close); avg_loss[:] = np.nan

    avg_gain[period] = np.mean(gain[1:period + 1])
    avg_loss[period] = np.mean(loss[1:period + 1])

    for i in range(period + 1, len(close)):
        avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gain[i]) / period
        avg_loss[i] = (avg_loss[i - 1] * (period - 1) + loss[i]) / period

    rs = avg_gain / (avg_loss + 1e-12)
    return 100 - (100 / (1 + rs))


def stochastic(high: np.ndarray, low: np.ndarray, close: np.ndarray, k_period: int = 14, d_period: int = 3):
    """Returns (fast_k, fast_d)."""
    high = np.asarray(high, dtype=float)
    low = np.asarray(low, dtype=float)
    close = np.asarray(close, dtype=float)

    n = len(close)
    fast_k = np.full(n, np.nan, dtype=float)
    if n < k_period:
        return fast_k, np.full(n, np.nan, dtype=float)

    for i in range(k_period - 1, n):
        hh = np.nanmax(high[i - k_period + 1:i + 1])
        ll = np.nanmin(low[i - k_period + 1:i + 1])
        denom = (hh - ll)
        fast_k[i] = 0.0 if denom == 0 else 100.0 * (close[i] - ll) / denom

    fast_d = sma(fast_k, d_period)
    return fast_k, fast_d


def macd(close: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9):
    close = np.asarray(close, dtype=float)
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def williams_r(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    high = np.asarray(high, dtype=float)
    low = np.asarray(low, dtype=float)
    close = np.asarray(close, dtype=float)
    n = len(close)
    out = np.full(n, np.nan, dtype=float)
    if n < period:
        return out

    for i in range(period - 1, n):
        hh = np.nanmax(high[i - period + 1:i + 1])
        ll = np.nanmin(low[i - period + 1:i + 1])
        denom = (hh - ll)
        out[i] = 0.0 if denom == 0 else -100.0 * (hh - close[i]) / denom
    return out


class CandlestickItem(pg.GraphicsObject):
    """Simple candlestick renderer for pyqtgraph."""
    def __init__(self, t, o, h, l, c):
        super().__init__()
        self.t = np.asarray(t, dtype=float)
        self.o = np.asarray(o, dtype=float)
        self.h = np.asarray(h, dtype=float)
        self.l = np.asarray(l, dtype=float)
        self.c = np.asarray(c, dtype=float)

        if len(self.t) > 1:
            self.w = float(0.7 * np.median(np.diff(self.t)))
        else:
            self.w = float(60 * 60 * 24 * 0.7)

        self._picture = None
        self._generate_picture()

    def _generate_picture(self):
        pic = pg.QtGui.QPicture()
        p = pg.QtGui.QPainter(pic)

        up_pen = pg.mkPen((0, 200, 120), width=1)
        dn_pen = pg.mkPen((220, 80, 80), width=1)
        up_brush = pg.mkBrush((0, 200, 120))
        dn_brush = pg.mkBrush((220, 80, 80))

        half = self.w / 2.0

        for x, o, h, l, c in zip(self.t, self.o, self.h, self.l, self.c):
            is_up = c >= o
            pen = up_pen if is_up else dn_pen
            brush = up_brush if is_up else dn_brush

            p.setPen(pen)
            p.drawLine(pg.QtCore.QPointF(x, l), pg.QtCore.QPointF(x, h))

            p.setBrush(brush)
            top = max(o, c)
            bot = min(o, c)
            rect_h = (top - bot) if top != bot else 1e-6
            rect = pg.QtCore.QRectF(x - half, bot, self.w, rect_h)
            p.drawRect(rect)

        p.end()
        self._picture = pic

    def paint(self, p, *args):
        if self._picture is not None:
            p.drawPicture(0, 0, self._picture)

    def boundingRect(self):
        if len(self.t) == 0:
            return pg.QtCore.QRectF()
        return pg.QtCore.QRectF(
            float(np.min(self.t)),
            float(np.min(self.l)),
            float(np.max(self.t) - np.min(self.t)),
            float(np.max(self.h) - np.min(self.l)),
        )


class ChartDialog(QDialog):
    def __init__(self, symbols, start_index, data_manager, positions=None):
        super().__init__()

        self.symbols = list(symbols)
        self.index = int(start_index)
        self.data_manager = data_manager
        self.positions = positions or {}

        self.pos_qty = None
        self.pos_avg = None
        self.position_line = None
        self.position_label = None
        self.ma_item = None

        self.setWindowState(Qt.WindowMaximized)
        self.setModal(True)

        # ----- top controls -----
        root = QVBoxLayout(self)
        controls = QHBoxLayout()
        root.addLayout(controls)

        self.prev_btn = QPushButton("◀")
        self.prev_btn.setFixedWidth(60)
        controls.addWidget(self.prev_btn)

        controls.addWidget(QLabel("Chart:"))
        self.chart_type = QComboBox()
        self.chart_type.addItems(["Candlesticks", "Close Line", "OHLC Bars"])
        controls.addWidget(self.chart_type)

        controls.addWidget(QLabel("Study:"))
        self.study_type = QComboBox()
        self.study_type.addItems([
            "RSI (14)",
            "Stochastic Fast (14,3)",
            "Stochastic Slow (14,3,3)",
            "MACD (12,26,9)",
            "Williams %R (14)",
        ])
        controls.addWidget(self.study_type)

        controls.addWidget(QLabel("MA:"))
        self.ma_type = QComboBox()
        self.ma_type.addItems(["Off", "SMA 7", "SMA 21", "SMA 42"])
        controls.addWidget(self.ma_type)

        self.readout = QLabel(" ")
        # user prefers black
        self.readout.setStyleSheet("color: black; font-family: monospace; padding: 4px;")
        self.readout.setFixedWidth(760)
        controls.addStretch(1)
        controls.addWidget(self.readout)

        self.next_btn = QPushButton("▶")
        self.next_btn.setFixedWidth(60)
        controls.addWidget(self.next_btn)

        # ----- 3 panel plots -----
        self.glw = pg.GraphicsLayoutWidget()
        root.addWidget(self.glw)

        # Price plot (top)
        self.price_plot = self.glw.addPlot(
            row=0, col=0,
            axisItems={"bottom": pg.DateAxisItem(orientation="bottom")}
        )
        self.price_plot.showGrid(x=True, y=True, alpha=0.15)
        self.price_plot.setLabel("left", "Price")

        # Study (middle)
        self.glw.nextRow()
        self.study_plot = self.glw.addPlot(
            row=1, col=0,
            axisItems={"bottom": pg.DateAxisItem(orientation="bottom")}
        )
        self.study_plot.showGrid(x=True, y=True, alpha=0.10)
        self.study_plot.setLabel("left", "Study")
        self.study_plot.setXLink(self.price_plot)

        # Volume (bottom)
        self.glw.nextRow()
        self.vol_plot = self.glw.addPlot(
            row=2, col=0,
            axisItems={"bottom": pg.DateAxisItem(orientation="bottom")}
        )
        self.vol_plot.showGrid(x=True, y=True, alpha=0.10)
        self.vol_plot.setLabel("left", "Volume")
        self.vol_plot.setXLink(self.price_plot)

        # sizing (price biggest; study medium; volume small)
        self.glw.ci.layout.setRowStretchFactor(0, 8)
        self.glw.ci.layout.setRowStretchFactor(1, 2)
        self.glw.ci.layout.setRowStretchFactor(2, 1)

        # Crosshair on price plot
        self.vline = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen(200, 200, 200, 120))
        self.hline = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen(200, 200, 200, 120))
        self.price_plot.addItem(self.vline, ignoreBounds=True)
        self.price_plot.addItem(self.hline, ignoreBounds=True)

        self.proxy = pg.SignalProxy(
            self.glw.scene().sigMouseMoved,
            rateLimit=60,
            slot=self.on_mouse_moved
        )

        # Data placeholders
        self.t = self.o = self.h = self.l = self.c = self.v = None

        # Wiring
        self.prev_btn.clicked.connect(self.prev_symbol)
        self.next_btn.clicked.connect(self.next_symbol)
        self.chart_type.currentIndexChanged.connect(self.redraw_all)
        self.study_type.currentIndexChanged.connect(self.redraw_all)
        self.ma_type.currentIndexChanged.connect(self.redraw_all)

        # Load initial symbol
        self.load_symbol(self.index)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
            return
        if event.key() == Qt.Key_Left:
            self.prev_symbol()
            return
        if event.key() == Qt.Key_Right:
            self.next_symbol()
            return
        super().keyPressEvent(event)

    def prev_symbol(self):
        self.load_symbol((self.index - 1) % len(self.symbols))

    def next_symbol(self):
        self.load_symbol((self.index + 1) % len(self.symbols))

    def load_symbol(self, new_index: int):
        self.index = int(new_index)
        symbol = str(self.symbols[self.index]).strip().upper()

        pos = self.positions.get(symbol)
        self.pos_qty = float(pos.get("qty")) if pos and pos.get("qty") is not None else None
        self.pos_avg = float(pos.get("avg_cost")) if pos and pos.get("avg_cost") is not None else None

        data = self.data_manager.get_symbol_ohlcv_with_dates(symbol)
        if data is None:
            self.readout.setText(f"{symbol}: No data")
            return

        self.setWindowTitle(symbol)
        self.price_plot.setTitle(symbol)

        t, o, h, l, c, v = data
        self.t = np.asarray(t, dtype=float).reshape(-1)
        self.o = np.asarray(o, dtype=float).reshape(-1)
        self.h = np.asarray(h, dtype=float).reshape(-1)
        self.l = np.asarray(l, dtype=float).reshape(-1)
        self.c = np.asarray(c, dtype=float).reshape(-1)
        self.v = np.asarray(v, dtype=float).reshape(-1)

        n = min(len(self.t), len(self.o), len(self.h), len(self.l), len(self.c), len(self.v))
        self.t, self.o, self.h, self.l, self.c, self.v = (
            self.t[:n], self.o[:n], self.h[:n], self.l[:n], self.c[:n], self.v[:n]
        )

        self.redraw_all()

        vb = self.price_plot.getViewBox()
        vb.enableAutoRange()
        vb.autoRange()
        vb.disableAutoRange()

    def redraw_all(self):
        if self.t is None or len(self.t) == 0:
            return

        self.price_plot.clear()
        self.study_plot.clear()
        self.vol_plot.clear()

        # restore crosshair (cleared)
        self.price_plot.addItem(self.vline, ignoreBounds=True)
        self.price_plot.addItem(self.hline, ignoreBounds=True)

        # remove any previous position line/label handles
        self.position_line = None
        self.position_label = None
        self.ma_item = None

        mode = self.chart_type.currentText()

        # ---- PRICE ----
        if mode == "Close Line":
            self.price_plot.plot(
                x=self.t, y=self.c,
                pen=pg.mkPen(color=(0, 200, 120), width=3)
            )
        elif mode == "OHLC Bars":
            w = 0.25 * np.median(np.diff(self.t)) if len(self.t) > 1 else 60 * 60 * 24 * 0.25

            up_x, up_y, dn_x, dn_y = [], [], [], []
            for tt, oo, hh, ll, cc in zip(self.t, self.o, self.h, self.l, self.c):
                if cc >= oo:
                    up_x += [tt, tt, np.nan]; up_y += [ll, hh, np.nan]
                else:
                    dn_x += [tt, tt, np.nan]; dn_y += [ll, hh, np.nan]
            self.price_plot.plot(x=np.array(up_x), y=np.array(up_y), pen=pg.mkPen((0, 200, 120), width=1))
            self.price_plot.plot(x=np.array(dn_x), y=np.array(dn_y), pen=pg.mkPen((220, 80, 80), width=1))

            # Open ticks (left)
            up_x, up_y, dn_x, dn_y = [], [], [], []
            for tt, oo, cc in zip(self.t, self.o, self.c):
                if cc >= oo:
                    up_x += [tt - w, tt, np.nan]; up_y += [oo, oo, np.nan]
                else:
                    dn_x += [tt - w, tt, np.nan]; dn_y += [oo, oo, np.nan]
            self.price_plot.plot(x=np.array(up_x), y=np.array(up_y), pen=pg.mkPen((0, 200, 120), width=1))
            self.price_plot.plot(x=np.array(dn_x), y=np.array(dn_y), pen=pg.mkPen((220, 80, 80), width=1))

            # Close ticks (right)
            up_x, up_y, dn_x, dn_y = [], [], [], []
            for tt, cc, oo in zip(self.t, self.c, self.o):
                if cc >= oo:
                    up_x += [tt, tt + w, np.nan]; up_y += [cc, cc, np.nan]
                else:
                    dn_x += [tt, tt + w, np.nan]; dn_y += [cc, cc, np.nan]
            self.price_plot.plot(x=np.array(up_x), y=np.array(up_y), pen=pg.mkPen((0, 200, 120), width=1))
            self.price_plot.plot(x=np.array(dn_x), y=np.array(dn_y), pen=pg.mkPen((220, 80, 80), width=1))
        else:
            self.price_plot.addItem(CandlestickItem(self.t, self.o, self.h, self.l, self.c))

        # ---- MA OVERLAY ----
        ma_sel = self.ma_type.currentText()
        ma_period = 0
        if ma_sel == "SMA 7":
            ma_period = 7
        elif ma_sel == "SMA 21":
            ma_period = 21
        elif ma_sel == "SMA 42":
            ma_period = 42

        if ma_period > 0:
            ma = sma(self.c, ma_period)
            self.ma_item = self.price_plot.plot(
                x=self.t, y=ma,
                pen=pg.mkPen((240, 240, 240, 200), width=2)
            )

        # ---- POSITION LINE + SUMMARY ----
        if self.pos_avg is not None and self.pos_qty is not None and len(self.c) > 0:
            avg = float(self.pos_avg)
            qty = float(self.pos_qty)
            last_close = float(self.c[-1])

            pen = pg.mkPen((60, 140, 255), width=2) if last_close >= avg else pg.mkPen((255, 60, 60), width=2)
            self.position_line = pg.InfiniteLine(pos=avg, angle=0, movable=False, pen=pen)
            self.price_plot.addItem(self.position_line, ignoreBounds=False)

            pl = (last_close - avg) * qty
            mv = last_close * qty
            pct = ((last_close / avg) - 1.0) * 100.0 if avg != 0 else 0.0

            self.position_label = pg.TextItem(
                text=f"{qty:g} @ {avg:.2f}   MV {mv:,.0f}   P/L {pl:,.0f} ({pct:+.1f}%)",
                anchor=(0, 1),
                color=(220, 220, 220),
            )
            self.position_label.setPos(float(self.t[0]), avg)
            self.price_plot.addItem(self.position_label, ignoreBounds=True)

        self.price_plot.showGrid(x=True, y=True, alpha=0.15)
        self.price_plot.setLabel("left", "Price")

        # ---- STUDY ----
        study = self.study_type.currentText()

        if study.startswith("RSI"):
            rr = rsi(self.c, 14)
            self.study_plot.plot(x=self.t, y=rr, pen=pg.mkPen((220, 220, 220, 200), width=2))
            self.study_plot.setLabel("left", "RSI(14)")
            self.study_plot.setYRange(0, 100)
            self.study_plot.addItem(pg.InfiniteLine(70, angle=0, pen=pg.mkPen((200, 200, 200, 120))))
            self.study_plot.addItem(pg.InfiniteLine(30, angle=0, pen=pg.mkPen((200, 200, 200, 120))))
        elif study.startswith("Stochastic Fast"):
            k, d = stochastic(self.h, self.l, self.c, 14, 3)
            self.study_plot.plot(x=self.t, y=k, pen=pg.mkPen((220, 220, 220, 200), width=2))
            self.study_plot.plot(x=self.t, y=d, pen=pg.mkPen((160, 160, 160, 200), width=2))
            self.study_plot.setLabel("left", "Stoch Fast %K/%D")
            self.study_plot.setYRange(0, 100)
            self.study_plot.addItem(pg.InfiniteLine(80, angle=0, pen=pg.mkPen((200, 200, 200, 120))))
            self.study_plot.addItem(pg.InfiniteLine(20, angle=0, pen=pg.mkPen((200, 200, 200, 120))))
        elif study.startswith("Stochastic Slow"):
            fast_k, fast_d = stochastic(self.h, self.l, self.c, 14, 3)
            slow_k = fast_d
            slow_d = sma(slow_k, 3)
            self.study_plot.plot(x=self.t, y=slow_k, pen=pg.mkPen((220, 220, 220, 200), width=2))
            self.study_plot.plot(x=self.t, y=slow_d, pen=pg.mkPen((160, 160, 160, 200), width=2))
            self.study_plot.setLabel("left", "Stoch Slow %K/%D")
            self.study_plot.setYRange(0, 100)
            self.study_plot.addItem(pg.InfiniteLine(80, angle=0, pen=pg.mkPen((200, 200, 200, 120))))
            self.study_plot.addItem(pg.InfiniteLine(20, angle=0, pen=pg.mkPen((200, 200, 200, 120))))
        elif study.startswith("MACD"):
            m, s, _h = macd(self.c, 12, 26, 9)
            self.study_plot.plot(x=self.t, y=m, pen=pg.mkPen((220, 220, 220, 200), width=2))
            self.study_plot.plot(x=self.t, y=s, pen=pg.mkPen((160, 160, 160, 200), width=2))
            self.study_plot.setLabel("left", "MACD")
            self.study_plot.addItem(pg.InfiniteLine(0, angle=0, pen=pg.mkPen((200, 200, 200, 120))))
        elif study.startswith("Williams"):
            wr = williams_r(self.h, self.l, self.c, 14)
            self.study_plot.plot(x=self.t, y=wr, pen=pg.mkPen((220, 220, 220, 200), width=2))
            self.study_plot.setLabel("left", "%R(14)")
            self.study_plot.setYRange(-100, 0)
            self.study_plot.addItem(pg.InfiniteLine(-20, angle=0, pen=pg.mkPen((200, 200, 200, 120))))
            self.study_plot.addItem(pg.InfiniteLine(-80, angle=0, pen=pg.mkPen((200, 200, 200, 120))))
        else:
            self.study_plot.setLabel("left", "Study")

        self.study_plot.setXLink(self.price_plot)

        # ---- VOLUME (bottom) ----
        w = 0.7 * np.median(np.diff(self.t)) if len(self.t) > 1 else 60 * 60 * 24 * 0.7
        vol = pg.BarGraphItem(
            x=self.t, height=self.v, width=w,
            brush=pg.mkBrush((120, 120, 200, 160)),
            pen=pg.mkPen((120, 120, 200, 160)),
        )
        self.vol_plot.addItem(vol)
        self.vol_plot.setXLink(self.price_plot)

    def on_mouse_moved(self, evt):
        if self.t is None or len(self.t) == 0:
            return

        pos = evt[0]
        if not self.price_plot.sceneBoundingRect().contains(pos):
            return

        vb = self.price_plot.getViewBox()
        mp = vb.mapSceneToView(pos)
        mx = float(mp.x())

        idx = int(np.searchsorted(self.t, mx))
        if idx <= 0:
            idx = 0
        elif idx >= len(self.t):
            idx = len(self.t) - 1
        else:
            if abs(self.t[idx] - mx) > abs(self.t[idx - 1] - mx):
                idx -= 1

        sx = float(self.t[idx])
        sy = float(self.c[idx])

        self.vline.setPos(sx)
        self.hline.setPos(sy)

        dt = datetime.fromtimestamp(sx)
        self.readout.setText(
            f"Date: {dt:%Y-%m-%d}   "
            f"O: {self.o[idx]:.2f}  H: {self.h[idx]:.2f}  "
            f"L: {self.l[idx]:.2f}  C: {self.c[idx]:.2f}  "
            f"V: {self.v[idx]:,.0f}"
        )
