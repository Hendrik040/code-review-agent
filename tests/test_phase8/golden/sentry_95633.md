# Code Review Context

## 1. Git Diff (What Changed)

<diff>
diff --git a/src/sentry/consumers/__init__.py b/src/sentry/consumers/__init__.py
index 289c02c..431c65b 100644
--- a/src/sentry/consumers/__init__.py
+++ b/src/sentry/consumers/__init__.py
@@ -118,7 +118,7 @@ def uptime_options() -> list[click.Option]:
     options = [
         click.Option(
             ["--mode", "mode"],
-            type=click.Choice(["serial", "parallel", "batched-parallel"]),
+            type=click.Choice(["serial", "parallel", "batched-parallel", "thread-queue-parallel"]),
             default="serial",
             help="The mode to process results in. Parallel uses multithreading.",
         ),
@@ -138,7 +138,7 @@ def uptime_options() -> list[click.Option]:
             ["--max-workers", "max_workers"],
             type=int,
             default=None,
-            help="The maximum number of threads to spawn in parallel mode.",
+            help="The maximum amount of parallelism to use when in a parallel mode.",
         ),
         click.Option(["--processes", "num_processes"], default=1, type=int),
         click.Option(["--input-block-size"], type=int, default=None),
diff --git a/src/sentry/remote_subscriptions/consumers/queue_consumer.py b/src/sentry/remote_subscriptions/consumers/queue_consumer.py
new file mode 100644
index 0000000..4eed5c7
--- /dev/null
+++ b/src/sentry/remote_subscriptions/consumers/queue_consumer.py
@@ -0,0 +1,345 @@
+from __future__ import annotations
+
+import logging
+import queue
+import threading
+import time
+from collections import defaultdict
+from collections.abc import Callable
+from dataclasses import dataclass
+from typing import Any, Generic, TypeVar
+
+import sentry_sdk
+from arroyo.backends.kafka.consumer import KafkaPayload
+from arroyo.processing.strategies import ProcessingStrategy
+from arroyo.types import BrokerValue, FilteredPayload, Message, Partition
+
+from sentry.utils import metrics
+
+logger = logging.getLogger(__name__)
+
+T = TypeVar("T")
+
+
+@dataclass
+class WorkItem(Generic[T]):
+    """Work item that includes the original message for offset tracking."""
+
+    partition: Partition
+    offset: int
+    result: T
+    message: Message[KafkaPayload | FilteredPayload]
+
+
+class OffsetTracker:
+    """
+    Tracks outstanding offsets and determines which offsets are safe to commit.
+
+    - Tracks offsets per partition
+    - Only commits offsets when all prior offsets are processed
+    - Thread-safe for concurrent access with per-partition locks
+    """
+
+    def __init__(self) -> None:
+        self.all_offsets: dict[Partition, set[int]] = defaultdict(set)
+        self.outstanding: dict[Partition, set[int]] = defaultdict(set)
+        self.last_committed: dict[Partition, int] = {}
+        self.partition_locks: dict[Partition, threading.Lock] = {}
+
+    def _get_partition_lock(self, partition: Partition) -> threading.Lock:
+        """Get or create a lock for a partition."""
+        lock = self.partition_locks.get(partition)
+        if lock:
+            return lock
+        return self.partition_locks.setdefault(partition, threading.Lock())
+
+    def add_offset(self, partition: Partition, offset: int) -> None:
+        """Record that we've started processing an offset."""
+        with self._get_partition_lock(partition):
+            self.all_offsets[partition].add(offset)
+            self.outstanding[partition].add(offset)
+
+    def complete_offset(self, partition: Partition, offset: int) -> None:
+        """Mark an offset as completed."""
+        with self._get_partition_lock(partition):
+            self.outstanding[partition].discard(offset)
+
+    def get_committable_offsets(self) -> dict[Partition, int]:
+        """
+        Get the highest offset per partition that can be safely committed.
+
+        For each partition, finds the highest contiguous offset that has been processed.
+        """
+        committable = {}
+        for partition in list(self.all_offsets.keys()):
+            with self._get_partition_lock(partition):
+                all_offsets = self.all_offsets[partition]
+                if not all_offsets:
+                    continue
+
+                outstanding = self.outstanding[partition]
+                last_committed = self.last_committed.get(partition, -1)
+
+                min_offset = min(all_offsets)
+                max_offset = max(all_offsets)
+
+                start = max(last_committed + 1, min_offset)
+
+                highest_committable = last_committed
+                for offset in range(start, max_offset + 1):
+                    if offset in all_offsets and offset not in outstanding:
+                        highest_committable = offset
+                    else:
+                        break
+
+                if highest_committable > last_committed:
+                    committable[partition] = highest_committable
+
+        return committable
+
+    def mark_committed(self, partition: Partition, offset: int) -> None:
+        """Update the last committed offset for a partition."""
+        with self._get_partition_lock(partition):
+            self.last_committed[partition] = offset
+            # Remove all offsets <= committed offset
+            self.all_offsets[partition] = {o for o in self.all_offsets[partition] if o > offset}
+
+
+class OrderedQueueWorker(threading.Thread, Generic[T]):
+    """Worker thread that processes items from a queue in order."""
+
+    def __init__(
+        self,
+        worker_id: int,
+        work_queue: queue.Queue[WorkItem[T]],
+        result_processor: Callable[[str, T], None],
+        identifier: str,
+        offset_tracker: OffsetTracker,
+    ) -> None:
+        super().__init__(daemon=True)
+        self.worker_id = worker_id
+        self.work_queue = work_queue
+        self.result_processor = result_processor
+        self.identifier = identifier
+        self.offset_tracker = offset_tracker
+        self.shutdown = False
+
+    def run(self) -> None:
+        """Process items from the queue in order."""
+        while not self.shutdown:
+            try:
+                work_item = self.work_queue.get()
+            except queue.ShutDown:
+                break
+
+            try:
+                with sentry_sdk.start_transaction(
+                    op="queue_worker.process",
+                    name=f"monitors.{self.identifier}.worker_{self.worker_id}",
+                ):
+                    self.result_processor(self.identifier, work_item.result)
+
+            except queue.ShutDown:
+                break
+            except Exception:
+                logger.exception(
+                    "Unexpected error in queue worker", extra={"worker_id": self.worker_id}
+                )
+            finally:
+                self.offset_tracker.complete_offset(work_item.partition, work_item.offset)
+                metrics.gauge(
+                    "remote_subscriptions.queue_worker.queue_depth",
+                    self.work_queue.qsize(),
+                    tags={
+                        "identifier": self.identifier,
+                    },
+                )
+
+
+class FixedQueuePool(Generic[T]):
+    """
+    Fixed pool of queues that guarantees order within groups.
+
+    Key properties:
+    - Each group is consistently assigned to the same queue
+    - Each queue has exactly one worker thread
+    - Items within a queue are processed in FIFO order
+    - No dynamic reassignment that could break ordering
+    - Tracks offset completion for safe commits
+    """
+
+    def __init__(
+        self,
+        result_processor: Callable[[str, T], None],
+        identifier: str,
+        num_queues: int = 20,
+    ) -> None:
+        self.result_processor = result_processor
+        self.identifier = identifier
+        self.num_queues = num_queues
+        self.offset_tracker = OffsetTracker()
+        self.queues: list[queue.Queue[WorkItem[T]]] = []
+        self.workers: list[OrderedQueueWorker[T]] = []
+
+        for i in range(num_queues):
+            work_queue: queue.Queue[WorkItem[T]] = queue.Queue()
+            self.queues.append(work_queue)
+
+            worker = OrderedQueueWorker[T](
+                worker_id=i,
+                work_queue=work_queue,
+                result_processor=result_processor,
+                identifier=identifier,
+                offset_tracker=self.offset_tracker,
+            )
+            worker.start()
+            self.workers.append(worker)
+
+    def get_queue_for_group(self, group_key: str) -> int:
+        """
+        Get queue index for a group using consistent hashing.
+        """
+        return hash(group_key) % self.num_queues
+
+    def submit(self, group_key: str, work_item: WorkItem[T]) -> None:
+        """
+        Submit a work item to the appropriate queue.
+        """
+        queue_index = self.get_queue_for_group(group_key)
+        work_queue = self.queues[queue_index]
+
+        self.offset_tracker.add_offset(work_item.partition, work_item.offset)
+        work_queue.put(work_item)
+
+    def get_stats(self) -> dict[str, Any]:
+        """Get statistics about queue depths."""
+        queue_depths = [q.qsize() for q in self.queues]
+        return {
+            "queue_depths": queue_depths,
+            "total_items": sum(queue_depths),
+        }
+
+    def wait_until_empty(self, timeout: float = 5.0) -> bool:
+        """Wait until all queues are empty. Returns True if successful, False if timeout."""
+        start_time = time.time()
+        while time.time() - start_time < timeout:
+            if self.get_stats()["total_items"] == 0:
+                return True
+            time.sleep(0.01)
+        return False
+
+    def shutdown(self) -> None:
+        """Gracefully shutdown all workers."""
+        for worker in self.workers:
+            worker.shutdown = True
+
+        for q in self.queues:
+            try:
+                q.shutdown(immediate=False)
+            except Exception:
+                logger.exception("Error shutting down queue")
+
+        for worker in self.workers:
+            worker.join(timeout=5.0)
+
+
+class SimpleQueueProcessingStrategy(ProcessingStrategy[KafkaPayload], Generic[T]):
+    """
+    Processing strategy that uses a fixed pool of queues.
+
+    Guarantees:
+    - Items for the same group are processed in order
+    - No item is lost or processed out of order
+    - Natural backpressure when queues fill up
+    - Only commits offsets after successful processing
+    """
+
+    def __init__(
+        self,
+        queue_pool: FixedQueuePool[T],
+        decoder: Callable[[KafkaPayload | FilteredPayload], T | None],
+        grouping_fn: Callable[[T], str],
+        commit_function: Callable[[dict[Partition, int]], None],
+    ) -> None:
+        self.queue_pool = queue_pool
+        self.decoder = decoder
+        self.grouping_fn = grouping_fn
+        self.commit_function = commit_function
+        self.shutdown_event = threading.Event()
+
+        self.commit_thread = threading.Thread(target=self._commit_loop, daemon=True)
+        self.commit_thread.start()
+
+    def _commit_loop(self) -> None:
+        while not self.shutdown_event.is_set():
+            try:
+                self.shutdown_event.wait(1.0)
+
+                committable = self.queue_pool.offset_tracker.get_committable_offsets()
+
+                if committable:
+                    metrics.incr(
+                        "remote_subscriptions.queue_pool.offsets_committed",
+                        len(committable),
+                        tags={"identifier": self.queue_pool.identifier},
+                    )
+
+                    self.commit_function(committable)
+                    for partition, offset in committable.items():
+                        self.queue_pool.offset_tracker.mark_committed(partition, offset)
+            except Exception:
+                logger.exception("Error in commit loop")
+
+    def submit(self, message: Message[KafkaPayload | FilteredPayload]) -> None:
+        try:
+            result = self.decoder(message.payload)
+
+            assert isinstance(message.value, BrokerValue)
+            partition = message.value.partition
+            offset = message.value.offset
+
+            if result is None:
+                self.queue_pool.offset_tracker.add_offset(partition, offset)
+                self.queue_pool.offset_tracker.complete_offset(partition, offset)
+                return
+
+            group_key = self.grouping_fn(result)
+
+            work_item = WorkItem(
+                partition=partition,
+                offset=offset,
+                result=result,
+                message=message,
+            )
+
+            self.queue_pool.submit(group_key, work_item)
+
+        except Exception:
+            logger.exception("Error submitting message to queue")
+            if isinstance(message.value, BrokerValue):
+                self.queue_pool.offset_tracker.add_offset(
+                    message.value.partition, message.value.offset
+                )
+                self.queue_pool.offset_tracker.complete_offset(
+                    message.value.partition, message.value.offset
+                )
+
+    def poll(self) -> None:
+        stats = self.queue_pool.get_stats()
+        metrics.gauge(
+            "remote_subscriptions.queue_pool.total_queued",
+            stats["total_items"],
+            tags={"identifier": self.queue_pool.identifier},
+        )
+
+    def close(self) -> None:
+        self.shutdown_event.set()
+        self.commit_thread.join(timeout=5.0)
+        self.queue_pool.shutdown()
+
+    def terminate(self) -> None:
+        self.shutdown_event.set()
+        self.queue_pool.shutdown()
+
+    def join(self, timeout: float | None = None) -> None:
+        self.close()
diff --git a/src/sentry/remote_subscriptions/consumers/result_consumer.py b/src/sentry/remote_subscriptions/consumers/result_consumer.py
index acdfb9c..a6ab542 100644
--- a/src/sentry/remote_subscriptions/consumers/result_consumer.py
+++ b/src/sentry/remote_subscriptions/consumers/result_consumer.py
@@ -19,6 +19,10 @@ from arroyo.processing.strategies.run_task import RunTask
 from arroyo.types import BrokerValue, Commit, FilteredPayload, Message, Partition
 
 from sentry.conf.types.kafka_definition import Topic, get_topic_codec
+from sentry.remote_subscriptions.consumers.queue_consumer import (
+    FixedQueuePool,
+    SimpleQueueProcessingStrategy,
+)
 from sentry.remote_subscriptions.models import BaseRemoteSubscription
 from sentry.utils import metrics
 from sentry.utils.arroyo import MultiprocessingPool, run_task_with_multiprocessing
@@ -89,13 +93,19 @@ class ResultsStrategyFactory(ProcessingStrategyFactory[KafkaPayload], Generic[T,
     Does the consumer process all messages in parallel.
     """
 
+    thread_queue_parallel = False
+    """
+    Does the consumer use thread-queue-parallel processing?
+    """
+
     multiprocessing_pool: MultiprocessingPool | None = None
+    queue_pool: FixedQueuePool | None = None
     input_block_size: int | None = None
     output_block_size: int | None = None
 
     def __init__(
         self,
-        mode: Literal["batched-parallel", "parallel", "serial"] = "serial",
+        mode: Literal["batched-parallel", "parallel", "serial", "thread-queue-parallel"] = "serial",
         max_batch_size: int | None = None,
         max_batch_time: int | None = None,
         max_workers: int | None = None,
@@ -105,6 +115,7 @@ class ResultsStrategyFactory(ProcessingStrategyFactory[KafkaPayload], Generic[T,
     ) -> None:
         self.mode = mode
         metric_tags = {"identifier": self.identifier, "mode": self.mode}
+        self.result_processor = self.result_processor_cls()
         if mode == "batched-parallel":
             self.batched_parallel = True
             self.parallel_executor = ThreadPoolExecutor(max_workers=max_workers)
@@ -117,6 +128,13 @@ class ResultsStrategyFactory(ProcessingStrategyFactory[KafkaPayload], Generic[T,
             if num_processes is None:
                 num_processes = multiprocessing.cpu_count()
             self.multiprocessing_pool = MultiprocessingPool(num_processes)
+        if mode == "thread-queue-parallel":
+            self.thread_queue_parallel = True
+            self.queue_pool = FixedQueuePool(
+                result_processor=self.result_processor,
+                identifier=self.identifier,
+                num_queues=max_workers or 20,  # Number of parallel queues
+            )
 
         metrics.incr(
             "remote_subscriptions.result_consumer.start",
@@ -133,8 +151,6 @@ class ResultsStrategyFactory(ProcessingStrategyFactory[KafkaPayload], Generic[T,
         if output_block_size is not None:
             self.output_block_size = output_block_size
 
-        self.result_processor = self.result_processor_cls()
-
     @property
     @abc.abstractmethod
     def topic_for_codec(self) -> Topic:
@@ -164,6 +180,9 @@ class ResultsStrategyFactory(ProcessingStrategyFactory[KafkaPayload], Generic[T,
     def shutdown(self) -> None:
         if self.parallel_executor:
             self.parallel_executor.shutdown()
+        if self.queue_pool:
+            self.queue_pool.shutdown()
+            self.queue_pool = None
 
     def decode_payload(self, topic_for_codec, payload: KafkaPayload | FilteredPayload) -> T | None:
         assert not isinstance(payload, FilteredPayload)
@@ -187,6 +206,8 @@ class ResultsStrategyFactory(ProcessingStrategyFactory[KafkaPayload], Generic[T,
             return self.create_thread_parallel_worker(commit)
         if self.parallel:
             return self.create_multiprocess_worker(commit)
+        if self.thread_queue_parallel:
+            return self.create_thread_queue_parallel_worker(commit)
         else:
             return self.create_serial_worker(commit)
 
@@ -220,6 +241,23 @@ class ResultsStrategyFactory(ProcessingStrategyFactory[KafkaPayload], Generic[T,
             next_step=batch_processor,
         )
 
+    def create_thread_queue_parallel_worker(
+        self, commit: Commit
+    ) -> ProcessingStrategy[KafkaPayload]:
+        assert self.queue_pool is not None
+
+        def commit_offsets(offsets: dict[Partition, int]):
+            # We add + 1 here because the committed offset should represent the next offset to read from
+            commit_data = {partition: offset + 1 for partition, offset in offsets.items()}
+            commit(commit_data)
+
+        return SimpleQueueProcessingStrategy(
+            queue_pool=self.queue_pool,
+            decoder=partial(self.decode_payload, self.topic_for_codec),
+            grouping_fn=self.build_payload_grouping_key,
+            commit_function=commit_offsets,
+        )
+
     def partition_message_batch(self, message: Message[ValuesBatch[KafkaPayload]]) -> list[list[T]]:
         """
         Takes a batch of messages and partitions them based on the `build_payload_grouping_key` method.
diff --git a/tests/sentry/remote_subscriptions/__init__.py b/tests/sentry/remote_subscriptions/__init__.py
new file mode 100644
index 0000000..e69de29
diff --git a/tests/sentry/remote_subscriptions/consumers/__init__.py b/tests/sentry/remote_subscriptions/consumers/__init__.py
new file mode 100644
index 0000000..e69de29
diff --git a/tests/sentry/remote_subscriptions/consumers/test_queue_consumer.py b/tests/sentry/remote_subscriptions/consumers/test_queue_consumer.py
new file mode 100644
index 0000000..b94b9c0
--- /dev/null
+++ b/tests/sentry/remote_subscriptions/consumers/test_queue_consumer.py
@@ -0,0 +1,421 @@
+"""
+Tests for the thread-queue-parallel result consumer implementation.
+"""
+
+import threading
+from datetime import datetime
+from typing import Any
+from unittest import mock
+
+from arroyo.backends.kafka import KafkaPayload
+from arroyo.types import BrokerValue, FilteredPayload, Message, Partition, Topic
+
+from sentry.remote_subscriptions.consumers.queue_consumer import (
+    FixedQueuePool,
+    OffsetTracker,
+    SimpleQueueProcessingStrategy,
+    WorkItem,
+)
+from sentry.testutils.cases import TestCase
+
+
+class TestOffsetTracker(TestCase):
+    def setUp(self):
+        self.tracker = OffsetTracker()
+        self.partition1 = Partition(Topic("test"), 0)
+        self.partition2 = Partition(Topic("test"), 1)
+
+    def test_simple_tracking(self):
+        """Test basic offset tracking and committing."""
+        self.tracker.add_offset(self.partition1, 100)
+        self.tracker.add_offset(self.partition1, 101)
+        self.tracker.add_offset(self.partition1, 102)
+
+        committable = self.tracker.get_committable_offsets()
+        assert committable == {}
+
+        self.tracker.complete_offset(self.partition1, 100)
+        committable = self.tracker.get_committable_offsets()
+        assert committable == {self.partition1: 100}
+
+        self.tracker.mark_committed(self.partition1, 100)
+        self.tracker.complete_offset(self.partition1, 102)
+        committable = self.tracker.get_committable_offsets()
+        assert committable == {}
+
+        self.tracker.complete_offset(self.partition1, 101)
+        committable = self.tracker.get_committable_offsets()
+        assert committable == {self.partition1: 102}
+
+    def test_multiple_partitions(self):
+        """Test tracking across multiple partitions."""
+        self.tracker.add_offset(self.partition1, 100)
+        self.tracker.add_offset(self.partition1, 101)
+        self.tracker.add_offset(self.partition2, 200)
+        self.tracker.add_offset(self.partition2, 201)
+
+        self.tracker.complete_offset(self.partition1, 100)
+        self.tracker.complete_offset(self.partition2, 200)
+        self.tracker.complete_offset(self.partition2, 201)
+
+        committable = self.tracker.get_committable_offsets()
+        assert committable == {self.partition1: 100, self.partition2: 201}
+
+
+class TestFixedQueuePool(TestCase):
+    def setUp(self):
+        self.processed_items: list[tuple[str, str]] = []
+        self.process_lock = threading.Lock()
+        self.process_complete_event = threading.Event()
+        self.items_processed = 0
+        self.expected_items = 0
+
+        def result_processor(identifier: str, item: str):
+            with self.process_lock:
+                self.processed_items.append((identifier, item))
+                self.items_processed += 1
+                if self.items_processed >= self.expected_items:
+                    self.process_complete_event.set()
+
+        self.pool = FixedQueuePool(
+            result_processor=result_processor,
+            identifier="test",
+            num_queues=3,
+        )
+
+    def tearDown(self):
+        self.pool.shutdown()
+
+    def test_consistent_group_assignment(self):
+        """Test that groups are consistently assigned to the same queue."""
+        group_key = "group1"
+        queue_index1 = self.pool.get_queue_for_group(group_key)
+        queue_index2 = self.pool.get_queue_for_group(group_key)
+        queue_index3 = self.pool.get_queue_for_group(group_key)
+
+        assert queue_index1 == queue_index2 == queue_index3
+
+    def test_different_groups_distributed(self):
+        """Test that different groups are distributed across queues."""
+        queue_indices = set()
+        for i in range(20):
+            group_key = f"group{i}"
+            queue_index = self.pool.get_queue_for_group(group_key)
+            queue_indices.add(queue_index)
+
+        assert len(queue_indices) == 3
+
+    def test_ordered_processing_within_group(self):
+        """Test that items within a group are processed in order."""
+        partition = Partition(Topic("test"), 0)
+        group_key = "ordered_group"
+
+        self.expected_items = 5
+        self.process_complete_event.clear()
+
+        for i in range(5):
+            work_item = WorkItem(
+                partition=partition,
+                offset=i,
+                result=f"item_{i}",
+                message=Message(
+                    BrokerValue(
+                        KafkaPayload(b"key", b"value", []),
+                        partition,
+                        i,
+                        datetime.now(),
+                    )
+                ),
+            )
+            self.pool.submit(group_key, work_item)
+
+        assert self.process_complete_event.wait(timeout=5.0), "Processing did not complete in time"
+
+        group_items = [item for _, item in self.processed_items if item.startswith("item_")]
+        assert group_items == ["item_0", "item_1", "item_2", "item_3", "item_4"]
+
+    def test_concurrent_processing_across_groups(self):
+        """Test that different groups are processed concurrently."""
+        partition = Partition(Topic("test"), 0)
+
+        self.expected_items = 6
+        self.process_complete_event.clear()
+
+        for i in range(6):
+            group_key = f"group_{i % 3}"
+            work_item = WorkItem(
+                partition=partition,
+                offset=i,
+                result=f"item_{group_key}_{i}",
+                message=Message(
+                    BrokerValue(
+                        KafkaPayload(b"key", b"value", []),
+                        partition,
+                        i,
+                        datetime.now(),
+                    )
+                ),
+            )
+            self.pool.submit(group_key, work_item)
+
+        assert self.process_complete_event.wait(timeout=5.0), "Processing did not complete in time"
+        assert len(self.processed_items) == 6
+
+        groups_seen = set()
+        for _, item in self.processed_items:
+            if item.startswith("item_group_"):
+                # Extract the group number (0, 1, or 2)
+                parts = item.split("_")
+                if len(parts) >= 3:
+                    group_num = parts[2]
+                    groups_seen.add(group_num)
+
+        assert len(groups_seen) == 3
+
+    def test_stats_reporting(self):
+        """Test queue statistics reporting."""
+        partition = Partition(Topic("test"), 0)
+
+        self.expected_items = 10
+        self.process_complete_event.clear()
+
+        for i in range(10):
+            group_key = f"group_{i % 4}"
+            work_item = WorkItem(
+                partition=partition,
+                offset=i,
+                result=f"item_{i}",
+                message=Message(
+                    BrokerValue(
+                        KafkaPayload(b"key", b"value", []),
+                        partition,
+                        i,
+                        datetime.now(),
+                    )
+                ),
+            )
+            self.pool.submit(group_key, work_item)
+
+        stats = self.pool.get_stats()
+        assert stats["total_items"] > 0
+        assert "queue_depths" in stats
+        assert len(stats["queue_depths"]) == 3
+        assert self.process_complete_event.wait(timeout=5.0), "Processing did not complete in time"
+
+        stats = self.pool.get_stats()
+        assert stats["total_items"] == 0
+
+
+class TestSimpleQueueProcessingStrategy(TestCase):
+    def setUp(self):
+        self.processed_results: list[Any] = []
+        self.committed_offsets: dict[Partition, int] = {}
+        self.process_lock = threading.Lock()
+        self.process_complete_event = threading.Event()
+        self.commit_event = threading.Event()
+        self.items_processed = 0
+        self.expected_items = 0
+
+        def result_processor(identifier: str, result: dict):
+            with self.process_lock:
+                self.processed_results.append(result)
+                self.items_processed += 1
+                if self.items_processed >= self.expected_items:
+                    self.process_complete_event.set()
+
+        self.queue_pool = FixedQueuePool(
+            result_processor=result_processor,
+            identifier="test",
+            num_queues=2,
+        )
+
+        def commit_function(offsets: dict[Partition, int]):
+            with self.process_lock:
+                self.committed_offsets.update(offsets)
+                self.commit_event.set()
+
+        def decoder(payload: KafkaPayload | FilteredPayload) -> dict | None:
+            if isinstance(payload, FilteredPayload):
+                return None
+            return {"subscription_id": payload.value.decode(), "data": "test"}
+
+        def grouping_fn(result: dict) -> str:
+            return result["subscription_id"]
+
+        self.strategy = SimpleQueueProcessingStrategy(
+            queue_pool=self.queue_pool,
+            decoder=decoder,
+            grouping_fn=grouping_fn,
+            commit_function=commit_function,
+        )
+
+    def tearDown(self):
+        self.strategy.close()
+
+    def create_message(self, subscription_id: str, partition: int, offset: int) -> Message:
+        """Helper to create a test message."""
+        payload = KafkaPayload(
+            key=None,
+            value=subscription_id.encode(),
+            headers=[],
+        )
+        return Message(
+            BrokerValue(
+                payload,
+                Partition(Topic("test"), partition),
+                offset,
+                datetime.now(),
+            )
+        )
+
+    def test_message_processing(self):
+        """Test basic message processing."""
+        partition = 0
+        message = self.create_message("sub1", partition, 100)
+
+        self.expected_items = 1
+        self.process_complete_event.clear()
+
+        self.strategy.submit(message)
+
+        assert self.process_complete_event.wait(timeout=5.0), "Processing did not complete in time"
+        assert len(self.processed_results) == 1
+        assert self.processed_results[0]["subscription_id"] == "sub1"
+
+    def test_offset_committing(self):
+        """Test that offsets are committed after processing."""
+        partition = Partition(Topic("test"), 0)
+
+        self.expected_items = 5
+        self.process_complete_event.clear()
+        self.commit_event.clear()
+        for i in range(5):
+            message = self.create_message("sub1", 0, 100 + i)
+            self.strategy.submit(message)
+
+        assert self.process_complete_event.wait(timeout=5.0), "Processing did not complete in time"
+        assert self.commit_event.wait(timeout=2.0), "Commit did not happen in time"
+
+        assert partition in self.committed_offsets
+        assert self.committed_offsets[partition] == 104
+
+    def test_preserves_order_within_group(self):
+        """Test that messages for the same subscription are processed in order."""
+        self.expected_items = 5
+        self.process_complete_event.clear()
+
+        for i in range(5):
+            message = self.create_message("sub1", 0, 100 + i)
+            self.strategy.submit(message)
+
+        assert self.process_complete_event.wait(timeout=5.0), "Processing did not complete in time"
+        assert len(self.processed_results) == 5
+
+    def test_concurrent_processing_different_groups(self):
+        """Test that different subscriptions are processed concurrently."""
+        self.expected_items = 4
+        self.process_complete_event.clear()
+
+        for i in range(4):
+            message = self.create_message(f"sub{i % 2}", 0, 100 + i)
+            self.strategy.submit(message)
+
+        assert self.process_complete_event.wait(timeout=5.0), "Processing did not complete in time"
+
+        assert len(self.processed_results) == 4
+
+    def test_handles_invalid_messages(self):
+        """Test that invalid messages don't block offset commits."""
+        partition = Partition(Topic("test"), 0)
+
+        self.expected_items = 1
+        self.process_complete_event.clear()
+        self.commit_event.clear()
+
+        invalid_message = Message(
+            BrokerValue(
+                FilteredPayload(),
+                partition,
+                100,
+                datetime.now(),
+            )
+        )
+
+        self.strategy.submit(invalid_message)
+        self.strategy.submit(self.create_message("sub1", 0, 101))
+
+        assert self.process_complete_event.wait(timeout=5.0), "Processing did not complete in time"
+        assert self.commit_event.wait(timeout=2.0), "Commit did not happen in time"
+        assert self.committed_offsets.get(partition) == 101
+
+    def test_offset_gaps_block_commits(self):
+        """Test that gaps in offsets prevent committing past the gap."""
+        partition = Partition(Topic("test"), 0)
+
+        self.expected_items = 3  # First batch
+        self.process_complete_event.clear()
+        self.commit_event.clear()
+
+        self.strategy.submit(self.create_message("sub1", 0, 100))
+        self.strategy.submit(self.create_message("sub1", 0, 102))
+        self.strategy.submit(self.create_message("sub1", 0, 103))
+
+        assert self.process_complete_event.wait(timeout=5.0), "Processing did not complete in time"
+        assert self.commit_event.wait(timeout=2.0), "Commit did not happen in time"
+        assert self.committed_offsets.get(partition) == 100
+
+        self.expected_items = 4
+        self.commit_event.clear()
+        self.strategy.submit(self.create_message("sub1", 0, 101))
+
+        assert self.commit_event.wait(timeout=2.0), "Second commit did not happen in time"
+        assert self.committed_offsets.get(partition) == 103
+
+
+class TestThreadQueueParallelIntegration(TestCase):
+    """Integration test with the ResultsStrategyFactory."""
+
+    def test_factory_creates_thread_queue_parallel_strategy(self):
+        """Test that the factory properly creates thread-queue-parallel strategy."""
+        from sentry.remote_subscriptions.consumers.result_consumer import (
+            ResultProcessor,
+            ResultsStrategyFactory,
+        )
+
+        class MockResultProcessor(ResultProcessor):
+            @property
+            def subscription_model(self):
+                return mock.Mock()
+
+            def get_subscription_id(self, result):
+                return result.get("subscription_id", "unknown")
+
+            def handle_result(self, subscription, result):
+                pass
+
+        class MockFactory(ResultsStrategyFactory):
+            @property
+            def topic_for_codec(self):
+                return Topic("test")
+
+            @property
+            def result_processor_cls(self):
+                return MockResultProcessor
+
+            def build_payload_grouping_key(self, result):
+                return result.get("subscription_id", "unknown")
+
+            @property
+            def identifier(self):
+                return "test"
+
+        factory = MockFactory(mode="thread-queue-parallel", max_workers=5)
+        commit = mock.Mock()
+        partition = Partition(Topic("test"), 0)
+        strategy = factory.create_with_partitions(commit, {partition: 0})
+
+        assert isinstance(strategy, SimpleQueueProcessingStrategy)
+        assert factory.queue_pool is not None
+        assert factory.queue_pool.num_queues == 5
+
+        factory.shutdown()
diff --git a/tests/sentry/uptime/consumers/test_results_consumer.py b/tests/sentry/uptime/consumers/test_results_consumer.py
index 3b8484d..c7f9f1e 100644
--- a/tests/sentry/uptime/consumers/test_results_consumer.py
+++ b/tests/sentry/uptime/consumers/test_results_consumer.py
@@ -1,5 +1,7 @@
 import abc
+import time
 import uuid
+from collections.abc import Mapping
 from datetime import datetime, timedelta, timezone
 from hashlib import md5
 from typing import Literal
@@ -8,9 +10,14 @@ from unittest.mock import call
 
 import pytest
 from arroyo import Message
-from arroyo.backends.kafka import KafkaPayload
+from arroyo.backends.kafka import KafkaConsumer, KafkaPayload, build_kafka_consumer_configuration
+from arroyo.commit import ONCE_PER_SECOND
+from arroyo.processing import StreamProcessor
 from arroyo.processing.strategies import ProcessingStrategy
 from arroyo.types import BrokerValue, Partition, Topic
+from confluent_kafka import Consumer, Producer, TopicPartition
+from confluent_kafka.admin import AdminClient
+from django.conf import settings
 from django.test import override_settings
 from sentry_kafka_schemas.schema_types.uptime_results_v1 import (
     CHECKSTATUS_FAILURE,
@@ -27,8 +34,10 @@ from sentry.conf.types.uptime import UptimeRegionConfig
 from sentry.constants import DataCategory
 from sentry.models.group import Group, GroupStatus
 from sentry.testutils.abstract import Abstract
+from sentry.testutils.cases import UptimeTestCase
 from sentry.testutils.helpers.datetime import freeze_time
 from sentry.testutils.helpers.options import override_options
+from sentry.testutils.skips import requires_kafka
 from sentry.uptime.consumers.eap_converter import convert_uptime_result_to_trace_items
 from sentry.uptime.consumers.results_consumer import (
     UptimeResultsStrategyFactory,
@@ -52,6 +61,8 @@ from sentry.uptime.models import (
 )
 from sentry.uptime.types import IncidentStatus, UptimeMonitorMode
 from sentry.utils import json
+from sentry.utils.batching_kafka_consumer import create_topics, wait_for_topics
+from sentry.utils.kafka_config import get_kafka_admin_cluster_options
 from tests.sentry.uptime.subscriptions.test_tasks import ConfigPusherTestMixin
 
 
@@ -1675,6 +1686,461 @@ class ProcessResultSerialTest(ProcessResultTest):
         assert group_1 == [result_1, result_2]
         assert group_2 == [result_3]
 
+    def test_thread_queue_parallel(self) -> None:
+        """
+        Validates that the consumer in thread-queue-parallel mode processes messages correctly
+        """
+        factory = UptimeResultsStrategyFactory(
+            mode="thread-queue-parallel",
+            max_workers=2,
+        )
+        consumer = factory.create_with_partitions(mock.Mock(), {self.partition: 0})
+
+        with mock.patch.object(type(factory.result_processor), "__call__") as mock_processor_call:
+            subscription_2 = self.create_uptime_subscription(
+                subscription_id=uuid.uuid4().hex, interval_seconds=300, url="http://santry.io"
+            )
+            self.create_project_uptime_subscription(uptime_subscription=subscription_2)
+
+            result_1 = self.create_uptime_result(
+                self.subscription.subscription_id,
+                scheduled_check_time=datetime.now() - timedelta(minutes=5),
+            )
+            result_2 = self.create_uptime_result(
+                subscription_2.subscription_id,
+                scheduled_check_time=datetime.now() - timedelta(minutes=4),
+            )
+
+            self.send_result(result_1, consumer=consumer)
+            self.send_result(result_2, consumer=consumer)
+
+            queue_pool = factory.queue_pool
+            max_wait = 50
+            for _ in range(max_wait):
+                assert queue_pool is not None
+                stats = queue_pool.get_stats()
+                if stats["total_items"] == 0 and mock_processor_call.call_count == 2:
+                    break
+                time.sleep(0.1)
+
+            assert mock_processor_call.call_count == 2
+            mock_processor_call.assert_has_calls(
+                [call("uptime", result_1), call("uptime", result_2)], any_order=True
+            )
+
+        factory.shutdown()
+
+    def test_thread_queue_parallel_preserves_order(self) -> None:
+        """
+        Test that thread-queue-parallel mode preserves order within subscriptions.
+        """
+        factory = UptimeResultsStrategyFactory(
+            mode="thread-queue-parallel",
+            max_workers=3,
+        )
+        consumer = factory.create_with_partitions(mock.Mock(), {self.partition: 0})
+
+        with mock.patch.object(type(factory.result_processor), "__call__") as mock_processor_call:
+            processed_guids = []
+
+            def track_calls(identifier, result):
+                processed_guids.append(result["guid"])
+
+            mock_processor_call.side_effect = track_calls
+
+            base_time = datetime.now()
+            expected_guids = []
+            results = []
+            for i in range(5):
+                result = self.create_uptime_result(
+                    self.subscription.subscription_id,
+                    scheduled_check_time=base_time - timedelta(minutes=5 - i),
+                )
+                guid = result["guid"]
+                expected_guids.append(guid)
+                results.append(result)
+                self.send_result(result, consumer=consumer)
+
+            queue_pool = factory.queue_pool
+            max_wait = 50
+            for _ in range(max_wait):
+                assert queue_pool is not None
+                stats = queue_pool.get_stats()
+                if stats["total_items"] == 0 and len(processed_guids) == 5:
+                    break
+                time.sleep(0.1)
+
+            assert len(processed_guids) == 5
+            assert (
+                processed_guids == expected_guids
+            ), f"Expected order {expected_guids}, got {processed_guids}"
+
+        factory.shutdown()
+
+    def test_thread_queue_parallel_concurrent_subscriptions(self) -> None:
+        """
+        Test that different subscriptions are processed concurrently in thread-queue-parallel mode.
+        """
+        factory = UptimeResultsStrategyFactory(
+            mode="thread-queue-parallel",
+            max_workers=2,
+        )
+        commit = mock.Mock()
+        consumer = factory.create_with_partitions(commit, {self.partition: 0})
+
+        subscription_2 = self.create_uptime_subscription(
+            subscription_id=uuid.uuid4().hex,
+            interval_seconds=300,
+            url="http://example2.com",
+        )
+        self.create_project_uptime_subscription(uptime_subscription=subscription_2)
+
+        with mock.patch.object(type(factory.result_processor), "__call__") as mock_processor_call:
+            result_1 = self.create_uptime_result(
+                self.subscription.subscription_id,
+                scheduled_check_time=datetime.now() - timedelta(minutes=5),
+            )
+            result_2 = self.create_uptime_result(
+                subscription_2.subscription_id,
+                scheduled_check_time=datetime.now() - timedelta(minutes=5),
+            )
+
+            self.send_result(result_1, consumer=consumer)
+            self.send_result(result_2, consumer=consumer)
+
+            queue_pool = factory.queue_pool
+            max_wait = 50
+            for _ in range(max_wait):
+                assert queue_pool is not None
+                stats = queue_pool.get_stats()
+                if stats["total_items"] == 0 and mock_processor_call.call_count == 2:
+                    break
+                time.sleep(0.1)
+
+            assert mock_processor_call.call_count == 2
+
+        factory.shutdown()
+
+    def test_thread_queue_parallel_offset_commit(self) -> None:
+        """
+        Test that offsets are committed after successful processing in thread-queue-parallel mode.
+        """
+        committed_offsets: dict[Partition, int] = {}
+
+        def track_commits(offsets: Mapping[Partition, int], force: bool = False) -> None:
+            committed_offsets.update(offsets)
+
+        factory = UptimeResultsStrategyFactory(
+            mode="thread-queue-parallel",
+            max_workers=2,
+        )
+
+        test_partition = Partition(Topic("test"), 1)
+        consumer = factory.create_with_partitions(track_commits, {test_partition: 0})
+
+        with mock.patch.object(type(factory.result_processor), "__call__"):
+            codec = kafka_definition.get_topic_codec(kafka_definition.Topic.UPTIME_RESULTS)
+
+            for offset in range(100, 105):
+                result = self.create_uptime_result(
+                    self.subscription.subscription_id,
+                    scheduled_check_time=datetime.now() - timedelta(minutes=10 - offset % 5),
+                )
+                message = Message(
+                    BrokerValue(
+                        KafkaPayload(None, codec.encode(result), []),
+                        test_partition,
+                        offset,
+                        datetime.now(),
+                    )
+                )
+                consumer.submit(message)
+
+            queue_pool = factory.queue_pool
+            max_wait = 20
+            for _ in range(max_wait):
+                assert queue_pool is not None
+                stats = queue_pool.get_stats()
+                if stats["total_items"] == 0 and len(committed_offsets) > 0:
+                    break
+
+                time.sleep(0.1)
+
+            assert test_partition in committed_offsets
+            assert committed_offsets[test_partition] == 105
+
+        factory.shutdown()
+
+    def test_thread_queue_parallel_error_handling(self) -> None:
+        """
+        Test that errors in processing don't block offset commits for other messages.
+        """
+        committed_offsets: dict[Partition, int] = {}
+
+        def track_commits(offsets: Mapping[Partition, int], force: bool = False) -> None:
+            committed_offsets.update(offsets)
+
+        factory = UptimeResultsStrategyFactory(
+            mode="thread-queue-parallel",
+            max_workers=2,
+        )
+
+        test_partition = Partition(Topic("test"), 1)
+        consumer = factory.create_with_partitions(track_commits, {test_partition: 0})
+
+        with mock.patch.object(type(factory.result_processor), "__call__") as mock_processor_call:
+            mock_processor_call.side_effect = [Exception("Processing failed"), None]
+
+            codec = kafka_definition.get_topic_codec(kafka_definition.Topic.UPTIME_RESULTS)
+
+            for offset, minutes in [(100, 5), (101, 4)]:
+                result = self.create_uptime_result(
+                    self.subscription.subscription_id,
+                    scheduled_check_time=datetime.now() - timedelta(minutes=minutes),
+                )
+                message = Message(
+                    BrokerValue(
+                        KafkaPayload(None, codec.encode(result), []),
+                        test_partition,
+                        offset,
+                        datetime.now(),
+                    )
+                )
+                consumer.submit(message)
+
+            queue_pool = factory.queue_pool
+            max_wait = 20
+            for _ in range(max_wait):
+                assert queue_pool is not None
+                stats = queue_pool.get_stats()
+                if stats["total_items"] == 0 and mock_processor_call.call_count >= 2:
+                    time.sleep(0.2)
+                    break
+                time.sleep(0.1)
+
+            assert mock_processor_call.call_count == 2
+            assert len(committed_offsets) == 0 or test_partition not in committed_offsets
+
+        factory.shutdown()
+
+    def test_thread_queue_parallel_offset_gaps(self) -> None:
+        """
+        Test that offset gaps prevent committing past the gap.
+        """
+        all_commits = []
+
+        def track_commits(offsets: Mapping[Partition, int], force: bool = False) -> None:
+            all_commits.append(dict(offsets))
+
+        factory = UptimeResultsStrategyFactory(
+            mode="thread-queue-parallel",
+            max_workers=1,
+        )
+
+        test_partition = Partition(Topic("test"), 1)
+        consumer = factory.create_with_partitions(track_commits, {test_partition: 0})
+
+        with mock.patch.object(type(factory.result_processor), "__call__"):
+            codec = kafka_definition.get_topic_codec(kafka_definition.Topic.UPTIME_RESULTS)
+            for offset in [100, 102, 103]:
+                result = self.create_uptime_result(
+                    self.subscription.subscription_id,
+                    scheduled_check_time=datetime.now() - timedelta(minutes=5),
+                )
+                message = Message(
+                    BrokerValue(
+                        KafkaPayload(None, codec.encode(result), []),
+                        test_partition,
+                        offset,
+                        datetime.now(),
+                    )
+                )
+                consumer.submit(message)
+
+            queue_pool = factory.queue_pool
+            max_wait = 20
+            for _ in range(max_wait):
+                assert queue_pool is not None
+                stats = queue_pool.get_stats()
+                if stats["total_items"] == 0 and len(all_commits) > 0:
+                    time.sleep(0.2)
+                    break
+                time.sleep(0.1)
+
+            assert len(all_commits) > 0, "No commits happened"
+
+            last_commit = all_commits[-1]
+            assert test_partition in last_commit
+            actual_offset = last_commit[test_partition]
+            assert (
+                actual_offset == 101
+            ), f"Expected to commit offset 101 (next to read after processing 100), but got {actual_offset}"
+
+            for commit in all_commits:
+                if test_partition in commit:
+                    assert (
+                        commit[test_partition] <= 101
+                    ), f"Should not commit past the gap, but got {commit[test_partition]}"
+
+        factory.shutdown()
+
+    def test_thread_queue_parallel_graceful_shutdown(self) -> None:
+        """
+        Test that the thread-queue-parallel consumer shuts down gracefully.
+        """
+        factory = UptimeResultsStrategyFactory(
+            mode="thread-queue-parallel",
+            max_workers=3,
+        )
+        consumer = factory.create_with_partitions(mock.Mock(), {self.partition: 0})
+
+        for i in range(5):
+            result = self.create_uptime_result(
+                self.subscription.subscription_id,
+                scheduled_check_time=datetime.now() - timedelta(minutes=i),
+            )
+            self.send_result(result, consumer=consumer)
+
+        factory.shutdown()
+        assert factory.queue_pool is None
+
 
 class ProcessResultParallelTest(ProcessResultTest):
     strategy_processing_mode = "parallel"
+
+
+class ProcessResultThreadQueueParallelKafkaTest(UptimeTestCase):
+    """
+    Integration test for thread-queue-parallel consumer with actual Kafka offset verification.
+    """
+
+    pytestmark = [requires_kafka]
+
+    def test_thread_queue_parallel_kafka_offset_commit(self) -> None:
+        """
+        Test that offsets are actually committed to Kafka consumer group.
+        """
+        subscription = self.create_uptime_subscription(
+            subscription_id=uuid.uuid4().hex, interval_seconds=300, region_slugs=["default"]
+        )
+        self.create_project_uptime_subscription(
+            uptime_subscription=subscription,
+            owner=self.user,
+        )
+
+        test_id = uuid.uuid4().hex[:8]
+        test_topic = f"uptime-test-{test_id}"
+        consumer_group = f"uptime-test-group-{test_id}"
+        cluster_options = get_kafka_admin_cluster_options(
+            "default", {"allow.auto.create.topics": "true"}
+        )
+        admin_client = AdminClient(cluster_options)
+        try:
+            create_topics("default", [test_topic])
+            wait_for_topics(admin_client, [test_topic])
+
+            producer_conf = settings.KAFKA_CLUSTERS["default"]["common"]
+            producer = Producer(producer_conf)
+
+            codec = kafka_definition.get_topic_codec(kafka_definition.Topic.UPTIME_RESULTS)
+            for i in range(5):
+                result = self.create_uptime_result(
+                    subscription.subscription_id,
+                    scheduled_check_time=datetime.now() - timedelta(minutes=5 - i),
+                )
+                encoded = codec.encode(result)
+                producer.produce(test_topic, value=encoded, partition=0)
+
+            producer.flush()
+
+            factory = UptimeResultsStrategyFactory(
+                mode="thread-queue-parallel",
+                max_workers=2,
+            )
+
+            with override_settings(
+                KAFKA_TOPIC_OVERRIDES={
+                    "uptime-results": test_topic,
+                }
+            ):
+                commit_count = 0
+                commits_made = []
+                original_create_with_partitions = factory.create_with_partitions
+
+                def create_with_partitions_tracking(commit, partitions):
+                    def tracked_commit(
+                        offsets: Mapping[Partition, int], force: bool = False
+                    ) -> None:
+                        nonlocal commit_count
+                        commit_count += 1
+                        commits_made.append(dict(offsets))
+                        return commit(offsets, force)
+
+                    return original_create_with_partitions(tracked_commit, partitions)
+
+                factory.create_with_partitions = create_with_partitions_tracking  # type: ignore[method-assign]
+                consumer_config = build_kafka_consumer_configuration(
+                    settings.KAFKA_CLUSTERS["default"]["common"],
+                    group_id=consumer_group,
+                    auto_offset_reset="earliest",
+                )
+
+                consumer = KafkaConsumer(consumer_config)
+                processor = StreamProcessor(
+                    consumer=consumer,
+                    topic=Topic(test_topic),
+                    processor_factory=factory,
+                    commit_policy=ONCE_PER_SECOND,
+                )
+
+                with mock.patch.object(
+                    type(factory.result_processor), "__call__"
+                ) as mock_processor:
+                    mock_processor.return_value = None
+
+                    start_time = time.time()
+                    while time.time() - start_time < 5:
+                        processor._run_once()
+                        time.sleep(0.1)
+
+                processor._shutdown()
+                factory.shutdown()
+
+                verify_consumer = Consumer(
+                    {
+                        **settings.KAFKA_CLUSTERS["default"]["common"],
+                        "group.id": consumer_group,
+                        "auto.offset.reset": "earliest",
+                        "enable.auto.commit": False,
+                    }
+                )
+
+                partitions = [TopicPartition(test_topic, 0)]
+                committed = verify_consumer.committed(partitions)
+                assert commit_count >= 1, f"Expected at least 1 commit, got {commit_count}"
+
+                if commits_made:
+                    last_commit = commits_made[-1]
+                    expected_partition = Partition(topic=Topic(test_topic), index=0)
+                    assert (
+                        expected_partition in last_commit
+                    ), f"Expected partition {expected_partition} in commit"
+                    assert (
+                        last_commit[expected_partition] == 5
+                    ), f"Expected offset 5, got {last_commit[expected_partition]}"
+
+                assert len(committed) == 1
+                assert committed[0].topic == test_topic
+                assert committed[0].partition == 0
+                # We sent 5 messages (0-4), so the committed offset should be 5
+                assert (
+                    committed[0].offset == 5
+                ), f"Expected committed offset 5, got {committed[0].offset}"
+
+                verify_consumer.close()
+
+        finally:
+            try:
+                admin_client.delete_topics([test_topic])
+            except Exception:
+                pass

</diff>

## 2. Changed Code (Modified Files with Context)

<file name="src/sentry/consumers/__init__.py" lines="121-121" type="changed">
```python
 113      return options
 114  
 115  
 116  def uptime_options() -> list[click.Option]:
 117      """Return a list of uptime-results options."""
 118      options = [
 119          click.Option(
 120              ["--mode", "mode"],
 121              type=click.Choice(["serial", "parallel", "batched-parallel", "thread-queue-parallel"]),
 122              default="serial",
 123              help="The mode to process results in. Parallel uses multithreading.",
 124          ),
 125          click.Option(
 126              ["--max-batch-size", "max_batch_size"],
 127              type=int,
 128              default=500,
 129              help="Maximum number of results to batch before processing in parallel.",
```
</file>

<file name="src/sentry/consumers/__init__.py" lines="141-141" type="changed">
```python
 133              type=int,
 134              default=1,
 135              help="Maximum time spent batching results to batch before processing in parallel.",
 136          ),
 137          click.Option(
 138              ["--max-workers", "max_workers"],
 139              type=int,
 140              default=None,
 141              help="The maximum amount of parallelism to use when in a parallel mode.",
 142          ),
 143          click.Option(["--processes", "num_processes"], default=1, type=int),
 144          click.Option(["--input-block-size"], type=int, default=None),
 145          click.Option(["--output-block-size"], type=int, default=None),
 146      ]
 147      return options
 148  
 149  
```
</file>

<file name="src/sentry/remote_subscriptions/consumers/queue_consumer.py" lines="1-345" type="changed">
```python
 165      - Each queue has exactly one worker thread
 166      - Items within a queue are processed in FIFO order
 167      - No dynamic reassignment that could break ordering
 168      - Tracks offset completion for safe commits
 169      """
 170  
 171      def __init__(
 172          self,
 173          result_processor: Callable[[str, T], None],
 174          identifier: str,
 175          num_queues: int = 20,
 176      ) -> None:
 177          self.result_processor = result_processor
 178          self.identifier = identifier
 179          self.num_queues = num_queues
 180          self.offset_tracker = OffsetTracker()
 181          self.queues: list[queue.Queue[WorkItem[T]]] = []
```
</file>

<file name="src/sentry/remote_subscriptions/consumers/result_consumer.py" lines="22-25" type="changed">
```python
  16  from arroyo.processing.strategies.batching import ValuesBatch
  17  from arroyo.processing.strategies.commit import CommitOffsets
  18  from arroyo.processing.strategies.run_task import RunTask
  19  from arroyo.types import BrokerValue, Commit, FilteredPayload, Message, Partition
  20  
  21  from sentry.conf.types.kafka_definition import Topic, get_topic_codec
  22  from sentry.remote_subscriptions.consumers.queue_consumer import (
  23      FixedQueuePool,
  24      SimpleQueueProcessingStrategy,
  25  )
  26  from sentry.remote_subscriptions.models import BaseRemoteSubscription
  27  from sentry.utils import metrics
  28  from sentry.utils.arroyo import MultiprocessingPool, run_task_with_multiprocessing
  29  
  30  logger = logging.getLogger(__name__)
  31  
  32  T = TypeVar("T")
```
</file>

<file name="src/sentry/remote_subscriptions/consumers/result_consumer.py" lines="96-102" type="changed">
```python
  91      parallel = False
  92      """
  93      Does the consumer process all messages in parallel.
  94      """
  95  
  96      thread_queue_parallel = False
  97      """
  98      Does the consumer use thread-queue-parallel processing?
  99      """
 100  
 101      multiprocessing_pool: MultiprocessingPool | None = None
 102      queue_pool: FixedQueuePool | None = None
 103      input_block_size: int | None = None
 104      output_block_size: int | None = None
 105  
 106      def __init__(
 107          self,
```
</file>

<file name="src/sentry/remote_subscriptions/consumers/result_consumer.py" lines="108-108" type="changed">
```python
 100  
 101      multiprocessing_pool: MultiprocessingPool | None = None
 102      queue_pool: FixedQueuePool | None = None
 103      input_block_size: int | None = None
 104      output_block_size: int | None = None
 105  
 106      def __init__(
 107          self,
 108          mode: Literal["batched-parallel", "parallel", "serial", "thread-queue-parallel"] = "serial",
 109          max_batch_size: int | None = None,
 110          max_batch_time: int | None = None,
 111          max_workers: int | None = None,
 112          num_processes: int | None = None,
 113          input_block_size: int | None = None,
 114          output_block_size: int | None = None,
 115      ) -> None:
 116          self.mode = mode
```
</file>

<file name="src/sentry/remote_subscriptions/consumers/result_consumer.py" lines="118-118" type="changed">
```python
 110          max_batch_time: int | None = None,
 111          max_workers: int | None = None,
 112          num_processes: int | None = None,
 113          input_block_size: int | None = None,
 114          output_block_size: int | None = None,
 115      ) -> None:
 116          self.mode = mode
 117          metric_tags = {"identifier": self.identifier, "mode": self.mode}
 118          self.result_processor = self.result_processor_cls()
 119          if mode == "batched-parallel":
 120              self.batched_parallel = True
 121              self.parallel_executor = ThreadPoolExecutor(max_workers=max_workers)
 122              if max_workers is None:
 123                  metric_tags["workers"] = "default"
 124              else:
 125                  metric_tags["workers"] = str(max_workers)
 126          if mode == "parallel":
```
</file>

<file name="src/sentry/remote_subscriptions/consumers/result_consumer.py" lines="131-137" type="changed">
```python
 126          if mode == "parallel":
 127              self.parallel = True
 128              if num_processes is None:
 129                  num_processes = multiprocessing.cpu_count()
 130              self.multiprocessing_pool = MultiprocessingPool(num_processes)
 131          if mode == "thread-queue-parallel":
 132              self.thread_queue_parallel = True
 133              self.queue_pool = FixedQueuePool(
 134                  result_processor=self.result_processor,
 135                  identifier=self.identifier,
 136                  num_queues=max_workers or 20,  # Number of parallel queues
 137              )
 138  
 139          metrics.incr(
 140              "remote_subscriptions.result_consumer.start",
 141              1,
 142              tags=metric_tags,
```
</file>

<file name="src/sentry/remote_subscriptions/consumers/result_consumer.py" lines="153-153" type="changed">
```python
 145          if max_batch_size is not None:
 146              self.max_batch_size = max_batch_size
 147          if max_batch_time is not None:
 148              self.max_batch_time = max_batch_time
 149          if input_block_size is not None:
 150              self.input_block_size = input_block_size
 151          if output_block_size is not None:
 152              self.output_block_size = output_block_size
 153  
 154      @property
 155      @abc.abstractmethod
 156      def topic_for_codec(self) -> Topic:
 157          pass
 158  
 159      @property
 160      @abc.abstractmethod
 161      def result_processor_cls(self) -> type[ResultProcessor[T, U]]:
```
</file>

<file name="src/sentry/remote_subscriptions/consumers/result_consumer.py" lines="183-185" type="changed">
```python
 176          A unique identifier for this consumer - used to differentiate it in stats
 177          """
 178          pass
 179  
 180      def shutdown(self) -> None:
 181          if self.parallel_executor:
 182              self.parallel_executor.shutdown()
 183          if self.queue_pool:
 184              self.queue_pool.shutdown()
 185              self.queue_pool = None
 186  
 187      def decode_payload(self, topic_for_codec, payload: KafkaPayload | FilteredPayload) -> T | None:
 188          assert not isinstance(payload, FilteredPayload)
 189  
 190          try:
 191              codec = get_topic_codec(topic_for_codec)
 192              return codec.decode(payload.value)
```
</file>

<file name="src/sentry/remote_subscriptions/consumers/result_consumer.py" lines="209-210" type="changed">
```python
 202          commit: Commit,
 203          partitions: Mapping[Partition, int],
 204      ) -> ProcessingStrategy[KafkaPayload]:
 205          if self.batched_parallel:
 206              return self.create_thread_parallel_worker(commit)
 207          if self.parallel:
 208              return self.create_multiprocess_worker(commit)
 209          if self.thread_queue_parallel:
 210              return self.create_thread_queue_parallel_worker(commit)
 211          else:
 212              return self.create_serial_worker(commit)
 213  
 214      def create_serial_worker(self, commit: Commit) -> ProcessingStrategy[KafkaPayload]:
 215          return RunTask(
 216              function=partial(self.process_single, self.result_processor, self.topic_for_codec),
 217              next_step=CommitOffsets(commit),
 218          )
```
</file>

<file name="src/sentry/remote_subscriptions/consumers/result_consumer.py" lines="244-260" type="changed">
```python
 244      def create_thread_queue_parallel_worker(
 245          self, commit: Commit
 246      ) -> ProcessingStrategy[KafkaPayload]:
 247          assert self.queue_pool is not None
 248  
 249          def commit_offsets(offsets: dict[Partition, int]):
 250              # We add + 1 here because the committed offset should represent the next offset to read from
 251              commit_data = {partition: offset + 1 for partition, offset in offsets.items()}
 252              commit(commit_data)
 253  
 254          return SimpleQueueProcessingStrategy(
 255              queue_pool=self.queue_pool,
 256              decoder=partial(self.decode_payload, self.topic_for_codec),
 257              grouping_fn=self.build_payload_grouping_key,
 258              commit_function=commit_offsets,
 259          )
 260  
```
</file>

<file name="tests/sentry/remote_subscriptions/consumers/test_queue_consumer.py" lines="1-421" type="changed">
```python
 203          assert self.process_complete_event.wait(timeout=5.0), "Processing did not complete in time"
 204  
 205          stats = self.pool.get_stats()
 206          assert stats["total_items"] == 0
 207  
 208  
 209  class TestSimpleQueueProcessingStrategy(TestCase):
 210      def setUp(self):
 211          self.processed_results: list[Any] = []
 212          self.committed_offsets: dict[Partition, int] = {}
 213          self.process_lock = threading.Lock()
 214          self.process_complete_event = threading.Event()
 215          self.commit_event = threading.Event()
 216          self.items_processed = 0
 217          self.expected_items = 0
 218  
 219          def result_processor(identifier: str, result: dict):
```
</file>

<file name="tests/sentry/uptime/consumers/test_results_consumer.py" lines="2-4" type="changed">
```python
   1  import abc
   2  import time
   3  import uuid
   4  from collections.abc import Mapping
   5  from datetime import datetime, timedelta, timezone
   6  from hashlib import md5
   7  from typing import Literal
   8  from unittest import mock
   9  from unittest.mock import call
  10  
  11  import pytest
  12  from arroyo import Message
```
</file>

<file name="tests/sentry/uptime/consumers/test_results_consumer.py" lines="13-20" type="changed">
```python
  10  
  11  import pytest
  12  from arroyo import Message
  13  from arroyo.backends.kafka import KafkaConsumer, KafkaPayload, build_kafka_consumer_configuration
  14  from arroyo.commit import ONCE_PER_SECOND
  15  from arroyo.processing import StreamProcessor
  16  from arroyo.processing.strategies import ProcessingStrategy
  17  from arroyo.types import BrokerValue, Partition, Topic
  18  from confluent_kafka import Consumer, Producer, TopicPartition
  19  from confluent_kafka.admin import AdminClient
  20  from django.conf import settings
  21  from django.test import override_settings
  22  from sentry_kafka_schemas.schema_types.uptime_results_v1 import (
  23      CHECKSTATUS_FAILURE,
  24      CHECKSTATUS_MISSED_WINDOW,
  25      CHECKSTATUS_SUCCESS,
  26      CHECKSTATUSREASONTYPE_TIMEOUT,
```
</file>

<file name="tests/sentry/uptime/consumers/test_results_consumer.py" lines="37-40" type="changed">
```python
  32  from sentry.conf.types.kafka_definition import get_topic_codec
  33  from sentry.conf.types.uptime import UptimeRegionConfig
  34  from sentry.constants import DataCategory
  35  from sentry.models.group import Group, GroupStatus
  36  from sentry.testutils.abstract import Abstract
  37  from sentry.testutils.cases import UptimeTestCase
  38  from sentry.testutils.helpers.datetime import freeze_time
  39  from sentry.testutils.helpers.options import override_options
  40  from sentry.testutils.skips import requires_kafka
  41  from sentry.uptime.consumers.eap_converter import convert_uptime_result_to_trace_items
  42  from sentry.uptime.consumers.results_consumer import (
  43      UptimeResultsStrategyFactory,
  44      build_last_seen_interval_key,
  45      build_last_update_key,
  46  )
  47  from sentry.uptime.detectors.ranking import _get_cluster
  48  from sentry.uptime.detectors.result_handler import (
```
</file>

<file name="tests/sentry/uptime/consumers/test_results_consumer.py" lines="64-65" type="changed">
```python
  57      UptimeStatus,
  58      UptimeSubscription,
  59      UptimeSubscriptionRegion,
  60      get_detector,
  61  )
  62  from sentry.uptime.types import IncidentStatus, UptimeMonitorMode
  63  from sentry.utils import json
  64  from sentry.utils.batching_kafka_consumer import create_topics, wait_for_topics
  65  from sentry.utils.kafka_config import get_kafka_admin_cluster_options
  66  from tests.sentry.uptime.subscriptions.test_tasks import ConfigPusherTestMixin
  67  
  68  
  69  class ProcessResultTest(ConfigPusherTestMixin, metaclass=abc.ABCMeta):
  70      __test__ = Abstract(__module__, __qualname__)
  71  
  72      @property
  73      @abc.abstractmethod
```
</file>

<file name="tests/sentry/uptime/consumers/test_results_consumer.py" lines="1689-2146" type="changed">
```python
1908                  )
1909                  consumer.submit(message)
1910  
1911              queue_pool = factory.queue_pool
1912              max_wait = 20
1913              for _ in range(max_wait):
1914                  assert queue_pool is not None
1915                  stats = queue_pool.get_stats()
1916                  if stats["total_items"] == 0 and mock_processor_call.call_count >= 2:
1917                      time.sleep(0.2)
1918                      break
1919                  time.sleep(0.1)
1920  
1921              assert mock_processor_call.call_count == 2
1922              assert len(committed_offsets) == 0 or test_partition not in committed_offsets
1923  
1924          factory.shutdown()
```
</file>

## 3. Impact Code (Contracts & Call Sites)

### CALLEES: Definitions that the changed code CALLS (check if changed code respects these contracts)
<callees>
None
</callees>

### CALLERS: Call sites that invoke the changed functions/classes (check if callers pass correct arguments)
<callers>
None
</callers>
