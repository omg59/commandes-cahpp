"""Verrous de plages d'octets, conservés pendant les sections critiques.

Les fichiers sentinelles sont permanents : remplacer/supprimer un fichier
verrouillé créerait deux objets verrouillables. Aucun repli sur un simple
fichier de présence n'est permis si le système refuse le verrou natif.
"""

from __future__ import annotations

import errno
import os
import threading
import weakref
from contextlib import contextmanager
from pathlib import Path


class FileLockBusy(OSError):
    """Une autre section critique utilise déjà cette sentinelle."""


class _Gate:
    def __init__(self):
        self.mutex = threading.RLock()
        self.depth = 0
        self.descriptor = None
        self.owner = None


_registry_mutex = threading.Lock()
_registry: weakref.WeakValueDictionary = weakref.WeakValueDictionary()


def _native_lock(descriptor: int, *, unlock=False) -> None:
    if os.name == "nt":
        import msvcrt

        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK if unlock else msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.lockf(
            descriptor,
            fcntl.LOCK_UN if unlock else fcntl.LOCK_EX | fcntl.LOCK_NB,
            1, 0, os.SEEK_SET,
        )


@contextmanager
def exclusive_file(path: Path, *, owner=None):
    """Section critique réentrante par thread, exclusive entre processus.

    Ne pas ouvrir/fermer un second descripteur de la même sentinelle dans
    ce processus : POSIX pourrait alors libérer le verrou du premier.
    L'attente est laissée à l'appelant ; les accès concurrents échouent vite.
    """
    key = (os.getpid(), os.path.normcase(str(path.resolve())))
    with _registry_mutex:
        gate = _registry.get(key)
        if gate is None:
            gate = _Gate()
            _registry[key] = gate
    if not gate.mutex.acquire(blocking=False):
        raise FileLockBusy(errno.EAGAIN, "Section critique occupée")
    try:
        if gate.depth and gate.owner is not owner:
            raise FileLockBusy(errno.EAGAIN, "Section critique occupée")
        if gate.depth == 0:
            path.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
            try:
                _native_lock(descriptor)
            except OSError as exc:
                os.close(descriptor)
                if exc.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                    raise FileLockBusy(exc.errno, "Section critique occupée") from exc
                raise
            gate.descriptor = descriptor
            gate.owner = owner
        gate.depth += 1
        try:
            yield
        finally:
            gate.depth -= 1
            if gate.depth == 0:
                descriptor, gate.descriptor = gate.descriptor, None
                gate.owner = None
                try:
                    _native_lock(descriptor, unlock=True)
                finally:
                    os.close(descriptor)
    finally:
        gate.mutex.release()
