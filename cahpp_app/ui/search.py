"""Passerelle entre le worker SQLite et le thread Tk ; aucun appel Tk du worker."""

from __future__ import annotations

import queue

from ..catalog_search import LatestCatalogSearchWorker


class AsyncProductSearch:
    def __init__(self, widget, database, on_result):
        self.widget = widget
        self.on_result = on_result
        self.results = queue.SimpleQueue()
        self.worker = LatestCatalogSearchWorker(database, self.results.put)
        self.generation = 0
        self.pending = False
        self.after_id = None
        self.closed = False

    def submit(self, **kwargs):
        self.generation = self.worker.submit(**kwargs)
        self.pending = True
        if self.after_id is None:
            self.after_id = self.widget.after(40, self._poll)

    def invalidate(self):
        self.generation = self.worker.invalidate()
        self.pending = False

    def _poll(self):
        self.after_id = None
        if self.closed:
            return
        while True:
            try:
                outcome = self.results.get_nowait()
            except queue.Empty:
                break
            if outcome.generation == self.generation:
                self.pending = False
                self.on_result(outcome)
        if self.pending:
            self.after_id = self.widget.after(40, self._poll)

    def close(self):
        self.closed = True
        self.worker.close()
        if self.after_id is not None:
            self.widget.after_cancel(self.after_id)
            self.after_id = None
