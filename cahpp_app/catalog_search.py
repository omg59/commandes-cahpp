from __future__ import annotations

import threading
import logging
from dataclasses import dataclass
from typing import Callable

from .database import (
    Database,
    ProductSearchResult,
    SearchCancelled,
)
from .app_logging import log_failure

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SearchRequest:
    generation: int
    query: str
    supplier_id: int | None
    favorite_only: bool
    limit: int
    allow_slow_fallback: bool
    fallback_to_all: bool = False
    review_only: bool = False


@dataclass(frozen=True)
class SearchOutcome:
    generation: int
    result: ProductSearchResult | None = None
    error: Exception | None = None


class LatestCatalogSearchWorker:
    """Worker unique : seule la saisie la plus récente est conservée."""

    def __init__(
        self,
        database: Database,
        deliver: Callable[[SearchOutcome], None],
    ) -> None:
        self.database = database
        self.deliver = deliver
        self._condition = threading.Condition()
        self._generation = 0
        self._pending: SearchRequest | None = None
        self._current_cancel: threading.Event | None = None
        self._closed = False
        self._thread = threading.Thread(
            target=self._run,
            name="catalog-search",
            daemon=True,
        )
        self._thread.start()

    def submit(
        self,
        *,
        query: str,
        supplier_id: int | None,
        favorite_only: bool,
        limit: int,
        allow_slow_fallback: bool,
        fallback_to_all: bool = False,
        review_only: bool = False,
    ) -> int:
        with self._condition:
            if self._closed:
                return self._generation
            self._generation += 1
            request = SearchRequest(
                self._generation,
                query,
                supplier_id,
                favorite_only,
                limit,
                allow_slow_fallback,
                fallback_to_all,
                review_only,
            )
            self._pending = request
            if self._current_cancel is not None:
                self._current_cancel.set()
            self._condition.notify()
            return request.generation

    def invalidate(self) -> int:
        """Annule dès la frappe, sans attendre la soumission après le délai UI."""
        with self._condition:
            self._generation += 1
            self._pending = None
            if self._current_cancel is not None:
                self._current_cancel.set()
            return self._generation

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._pending = None
            if self._current_cancel is not None:
                self._current_cancel.set()
            self._condition.notify()

    def _run(self) -> None:
        while True:
            with self._condition:
                while self._pending is None and not self._closed:
                    self._condition.wait()
                if self._closed:
                    return
                request = self._pending
                self._pending = None
                cancel_event = threading.Event()
                self._current_cancel = cancel_event
            if request is None:
                continue
            try:
                result = self.database.search_products_detailed(
                    query=request.query,
                    supplier_id=request.supplier_id,
                    favorite_only=request.favorite_only,
                    limit=request.limit,
                    allow_slow_fallback=request.allow_slow_fallback,
                    cancel_event=cancel_event,
                    **({"review_only": True} if request.review_only else {}),
                )
                if (request.fallback_to_all and not request.query.strip()
                        and request.favorite_only and not result.rows):
                    result = self.database.search_products_detailed(
                        supplier_id=request.supplier_id, favorite_only=False,
                        limit=request.limit, cancel_event=cancel_event,
                    )
            except SearchCancelled:
                continue
            except Exception as exc:
                log_failure(logger, "recherche_echec", exc)
                outcome = SearchOutcome(request.generation, error=exc)
            else:
                logger.info(
                    "recherche_terminee mode=%s duree_ms=%d resultats=%d repare=%s",
                    result.mode, result.elapsed_ms, len(result.rows), result.repaired,
                )
                outcome = SearchOutcome(request.generation, result=result)
            with self._condition:
                self._current_cancel = None
                obsolete = request.generation != self._generation
                closed = self._closed
            if not obsolete and not closed:
                self.deliver(outcome)
