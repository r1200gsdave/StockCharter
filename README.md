# Stock Portfolio Tracker

A desktop portfolio management application built with PySide6 that tracks stock positions, displays interactive price charts, and pulls analyst scores from Zacks and Barchart.

---

## Features

- **Portfolio ledger** — sortable table showing Symbol, Account, Quantity, Average Cost, Last Price, Market Value, P/L, P/L%, Zacks Rank, Zacks VGM Score, and Barchart Opinion
- **Interactive charts** — candlestick/line charts split across two chart pages, click any chart to open a full detail view
- **Portfolio momentum panel** — aggregate metrics including Advance/Decline, Breadth %, ROC (5/20/60 day), SMA50/200 coverage, Average RSI, and an overall momentum score
- **Zacks integration** — fetches Zacks Rank (1–5) and VGM Score (A–F) for all positions using your Zacks account credentials stored in KeePass
- **Barchart integration** — fetches Barchart Opinion percentage for all positions
- **Clickable data links** — click the Rank or VGM cell to open the Zacks quote page; click the Opinion cell to open the Barchart page in your browser
- **Add position** — dialog to add a new stock position (Account, Symbol, Quantity, Price); updates `symbols.txt`, fetches price data, and adds the chart automatically
- **Remove position** — select a row and remove the position from the portfolio, charts, and `symbols.txt`
- **Refresh prices** — re-fetches the latest price data from Yahoo Finance in the background
- **Sort by P/L%** — one-click sort toggle for profitability, ascending or descending

---

## Project Structure

```
stock.app/
├── main.py                  # Entry point, loads symbols.txt
├── symbols.txt              # Portfolio positions (CSV)
├── requirements.txt
├── core/
│   ├── data_manager.py      # Yahoo Finance price data fetching and caching
│   ├── worker.py            # QRunnable background worker
│   ├── zacks.py             # Zacks login and quote data scraper
│   └── barchart.py          # Barchart opinion fetcher (via w3m)
└── ui/
    ├── main_window.py       # QMainWindow shell
    ├── symbol_grid.py       # Main UI — ledger, charts, controls
    ├── chart_widget.py      # Per-symbol price chart widget
    └── chart_dialog.py      # Full-screen chart detail dialog
```

---

## Requirements

Install Python dependencies:

```bash
pip install PySide6 pyqtgraph yfinance requests beautifulsoup4 pykeepass
```

Also requires **w3m** (text-mode browser) for Barchart fetching:

```bash
# Arch / Manjaro
sudo pacman -S w3m

# Debian / Ubuntu
sudo apt install w3m
```

---

## Portfolio File Format

`symbols.txt` is a CSV file with four fields per line:

```
Account, Symbol, Quantity, Price
```

- **Account** — `F`, `S`, or `RH`
- **Symbol** — stock ticker (e.g. `AAPL`)
- **Quantity** — number of shares (supports decimals for funds)
- **Price** — average purchase price per share

Multiple entries for the same symbol are aggregated automatically.

Lines beginning with `#` are treated as comments.

**Example:**
```
F, AAPL, 50, 172.45
F, NVDA, 25, 480.00
RH, TSLA, 10, 215.50
S, SPY, 5, 510.00
```

---

## KeePass Integration

Zacks credentials are read from a KeePass database at:

```
/home/dave/Documents/Database.kdbx
```

The entry must be in a group named **`portfolio`** with the title **`Zacks`**, containing your Zacks username and password.

When you click **Fetch VGM**, you will be prompted for your KeePass master password. Credentials are not stored in the app.

---

## Running the App

```bash
cd stock.app
python main.py
```

The app launches maximized. Use the **◀ Page / Page ▶** buttons to switch between the Synopsis table, Charts page 1, and Charts page 2. Press `Esc` to exit fullscreen.

---

## Usage Tips

| Action | How |
|---|---|
| Sort any column | Click the column header |
| Open Zacks quote page | Click the Rank or VGM cell |
| Open Barchart page | Click the Opinion cell |
| Open detailed chart | Click any chart panel |
| Add a position | Click **Add Position** |
| Remove a position | Select a row → click **Remove Position** |
| Refresh prices | Click **Refresh Prices** |
| Fetch Zacks scores | Click **Fetch VGM** (prompts for KeePass password once) |
| Fetch Barchart opinions | Click **Fetch BC Opinion** |
