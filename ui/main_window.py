from PySide6.QtWidgets import QMainWindow

from ui.symbol_grid import SymbolGrid
from core.data_manager import DataManager
from PySide6.QtCore import Qt


class MainWindow(QMainWindow):

    # def __init__(self):
    #
    #     super().__init__()
    #
    #     self.setWindowTitle("Stock Grid")
    #
    #     self.resize(1400, 900)
    #     #self.setGeometry(100,100,1600,1000)
    #
    #     symbols = [
    #
    #         "AAPL", "MSFT", "GOOG", "NVDA",
    #         "TSLA", "META", "AMZN", "SPY",
    #         "QQQ", "AMD", "INTC", "NFLX",
    #         "BA", "DIS", "PLTR", "COIN"
    #
    #     ]

    def __init__(self, symbols=None, positions=None):
        super().__init__()

        if symbols is None:
            symbols = ["AAPL", "MSFT"]  # fallback

        if positions is None:
            positions = {}

        self.data_manager = DataManager()
        self.grid = SymbolGrid(symbols, self.data_manager, positions=positions)

        self.setCentralWidget(self.grid)



    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.showNormal()
        super().keyPressEvent(event)
