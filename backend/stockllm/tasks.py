from __future__ import annotations

import os
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
from threading import BoundedSemaphore, Lock

from .models.research import SelectionRunCreate
from .service import ResearchService


class ResearchTaskRunner:
    def __init__(self, service: ResearchService) -> None:
        workers = min(max(int(os.getenv("STOCKLLM_RESEARCH_WORKERS", "2")), 1), 8)
        queue_capacity = min(max(int(os.getenv("STOCKLLM_RESEARCH_QUEUE", "16")), 1), 100)
        self._service = service
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="stockllm-research")
        self._capacity = BoundedSemaphore(workers + queue_capacity)
        self._futures: set[Future[None]] = set()
        self._lock = Lock()

    def submit(self, run_id: str, request: SelectionRunCreate) -> bool:
        if not self._capacity.acquire(blocking=False):
            return False
        try:
            future = self._executor.submit(self._service.execute_run, run_id, request)
        except RuntimeError:
            self._capacity.release()
            return False
        with self._lock:
            self._futures.add(future)
        future.add_done_callback(lambda completed: self._completed(run_id, completed))
        return True

    def _completed(self, run_id: str, future: Future[None]) -> None:
        try:
            error = future.exception()
            if error is not None:
                self._service.fail_run(run_id, f"研究任务意外失败：{error}")
        except CancelledError:
            pass
        finally:
            with self._lock:
                self._futures.discard(future)
            self._capacity.release()

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
