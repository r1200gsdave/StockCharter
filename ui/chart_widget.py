from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Signal
import pyqtgraph as pg


class ChartWidget(QWidget):

    # MUST be at class level (not inside __init__)
    clicked = Signal(str)

    def __init__(self, symbol, position=None):
        super().__init__()

        self.symbol = symbol
        self.position = position or None  # {"qty": float, "avg_cost": float}
        self._pos_line = None
        self._pos_text = None

        layout = QVBoxLayout(self)

        self.label = QLabel(symbol)
        layout.addWidget(self.label)

        self.plot = pg.PlotWidget()

        self.plot.setAxisItems({})

        self.plot.showGrid(x=True, y=True)

        layout.addWidget(self.plot)



    def set_data(self, data):

        if data is None:
            return

        x, y = data

        # FORCE proper numpy format
        import numpy as np

        x = np.asarray(x, dtype=float).flatten()
        y = np.asarray(y, dtype=float).flatten()
        min_len = min(len(x), len(y))
        x = x[:min_len]
        y = y[:min_len]
        # sanity check
        if len(x) == 0 or len(y) == 0:
            return

        if len(x) != len(y):
            print("Length mismatch:", len(x), len(y))
            return

        self.plot.clear()

        self.plot.plot(
            x=x,
            y=y,
            pen=pg.mkPen("#00ff7f", width=2)
        )


        # ---- 21-day moving average overlay (main window) ----
        try:
            ma_period = 21
            if len(y) >= ma_period:
                csum = np.cumsum(y, dtype=float)
                ma = np.full_like(y, np.nan, dtype=float)
                ma[ma_period - 1:] = (csum[ma_period - 1:] - np.concatenate(([0.0], csum[:-ma_period]))) / ma_period
                self.plot.plot(x=x, y=ma, pen=pg.mkPen((240, 240, 240, 200), width=1))
        except Exception:
            pass

        # ---- Position line + summary (if present) ----
        if self.position and "avg_cost" in self.position and "qty" in self.position:
            try:
                qty = float(self.position["qty"])
                avg = float(self.position["avg_cost"])
                last = float(y[-1])
            except Exception:
                qty = avg = last = None

            if qty is not None and avg is not None and last is not None:
                pl = (last - avg) * qty
                mv = last * qty
                pl_pct = ((last - avg) / avg) * 100.0 if avg else 0.0

                tag = (self.position or {}).get("acct_tag", "")
                prefix = f"{tag} " if tag else ""

                pl_color = "red" if pl < 0 else "black"

                self.label.setText(
                    f'{prefix}  {self.symbol}  {qty:g} @ {avg:.2f}   '
                    f'${mv:,.0f}    '
                    f'<span style="color:{pl_color};">'
                    f'  ${pl:,.0f}  ({pl_pct:+.1f}%)'
                    f'</span>'
                )

                # Horizontal avg-cost line: blue if above, red if below
                pen = pg.mkPen((60, 140, 255), width=2) if last >= avg else pg.mkPen((255, 60, 60), width=2)
                self._pos_line = pg.InfiniteLine(pos=avg, angle=0, movable=False, pen=pen)
                self.plot.addItem(self._pos_line, ignoreBounds=False)

                # Tiny overlay text near the line
                txt = pg.TextItem(
                    text=f"{qty:g} @ {avg:.2f}",
                    anchor=(0, 1),
                    color=(220, 220, 220),
                )
                txt.setPos(float(x[0]), float(avg))
                self._pos_text = txt
                self.plot.addItem(self._pos_text, ignoreBounds=True)

    # This emits the signal when clicked
    def mousePressEvent(self, event):

        self.clicked.emit(self.symbol)

        super().mousePressEvent(event)
