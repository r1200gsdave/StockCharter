import sys
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow
from pathlib import Path
import csv

def load_positions(path: str, default_symbols: list[str]):
    p = Path(path)
    if not p.exists():
        print(f"[positions] file not found: {p.resolve()}")
        return default_symbols, {}

    totals = {}  # sym -> {"qty": float, "cost": float, "accts": set[str]}
    symbols_in_order = []

    with p.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f, skipinitialspace=True)
        for lineno, row in enumerate(reader, start=1):
            if not row:
                continue
            first = row[0].strip()
            if not first or first.startswith("#"):
                continue

            if len(row) < 4:
                print(f"[positions] skipped (need 4 fields) line {lineno}: {row}")
                continue

            acct = row[0].strip().upper()          # F / S / R
            sym  = row[1].strip().upper()
            try:
                qty = float(row[2])
                price = float(row[3])
            except ValueError:
                print(f"[positions] parse error line {lineno}: {row}")
                continue

            if not sym:
                continue

            if sym not in symbols_in_order:
                symbols_in_order.append(sym)

            rec = totals.setdefault(sym, {"qty": 0.0, "cost": 0.0, "accts": set()})
            rec["qty"] += qty
            rec["cost"] += qty * price
            if acct:
                rec["accts"].add(acct)

    positions = {}
    for sym, rec in totals.items():
        if rec["qty"] != 0:
            acct_tag = "&".join(sorted(rec["accts"]))  # e.g. F&R or F&R&S
            positions[sym] = {
                "qty": rec["qty"],
                "avg_cost": rec["cost"] / rec["qty"],
                "acct_tag": acct_tag,   # <-- store account(s) explicitly
            }

    symbols = symbols_in_order if symbols_in_order else default_symbols
    print(f"[positions] loaded {len(positions)} aggregated symbols from {p.name}")
    return symbols, positions




app = QApplication(sys.argv)

default_symbols = ["AAPL", "MSFT", "GOOG", "NVDA", "TSLA", "SPY", "QQQ"]
symbols, positions = load_positions("symbols.txt", default_symbols)

window = MainWindow(symbols=symbols, positions=positions)
window.showMaximized()

sys.exit(app.exec())
