from PySide6.QtCore import QRunnable, QObject, Signal


class WorkerSignals(QObject):

    finished = Signal(str, object)
    error = Signal(str)


class Worker(QRunnable):

    def __init__(self, fn, symbol):
        super().__init__()

        self.fn = fn
        self.symbol = symbol
        self.signals = WorkerSignals()

    def run(self):

        try:
            result = self.fn(self.symbol)

            self.signals.finished.emit(self.symbol, result)

        except Exception as e:
            self.signals.error.emit(str(e))
