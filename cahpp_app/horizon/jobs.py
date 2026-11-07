"""Travaux Qt annulables : le worker ne détient aucun widget ni callback UI."""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal, Slot

from ..app_logging import log_failure
import logging

logger = logging.getLogger(__name__)


class WorkSignals(QObject):
    done = Signal(str, int, object, object)
    progress = Signal(str, int, int, str)


class Work(QRunnable):
    def __init__(self, key, generation, function, cancel):
        super().__init__()
        self.key, self.generation, self.function, self.cancel = (
            key,
            generation,
            function,
            cancel,
        )
        self.signals = WorkSignals()

    def run(self):
        result, error = None, None
        try:
            if not self.cancel.is_set():
                result = self.function(cancel=self.cancel, progress=self.report)
        except Exception as exc:
            if not self.cancel.is_set():
                log_failure(logger, "horizon_tache_echec", exc)
                error = exc
        self.signals.done.emit(self.key, self.generation, result, error)

    def report(self, current, total, text):
        if self.cancel.is_set():
            raise ValueError("Opération annulée avant validation.")
        self.signals.progress.emit(
            self.key, self.generation, int(100 * current / max(total, 1)), text
        )


class Jobs(QObject):
    progress = Signal(str, int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(2)
        self.tasks = {}
        self.latest = {}
        self.counter = 0
        self.closing = False

    def submit(self, key, function, callback):
        if self.closing:
            return
        for (old_key, _), (task, _) in self.tasks.items():
            if old_key == key:
                task.cancel.set()
        self.counter += 1
        generation = self.counter
        self.latest[key] = generation
        task = Work(key, generation, function, threading.Event())
        task.signals.done.connect(self._done, Qt.ConnectionType.QueuedConnection)
        task.signals.progress.connect(
            self._progress, Qt.ConnectionType.QueuedConnection
        )
        self.tasks[(key, generation)] = (task, callback)
        self.pool.start(task)

    @Slot(str, int, object, object)
    def _done(self, key, generation, result, error):
        record = self.tasks.pop((key, generation), None)
        if (
            record
            and not self.closing
            and self.latest.get(key) == generation
            and not record[0].cancel.is_set()
        ):
            record[1](result, error)
        if record:
            record[0].signals.deleteLater()

    @Slot(str, int, int, str)
    def _progress(self, key, generation, percent, text):
        if not self.closing and self.latest.get(key) == generation:
            self.progress.emit(key, percent, text)

    def close(self):
        self.closing = True
        for task, _ in self.tasks.values():
            task.cancel.set()

    def cancel(self, key):
        for (task_key, _), (task, _) in self.tasks.items():
            if task_key == key:
                task.cancel.set()

    @property
    def busy(self):
        return bool(self.pool.activeThreadCount())
