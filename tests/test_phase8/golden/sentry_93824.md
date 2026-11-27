# Code Review Context

## 1. Git Diff (What Changed)

<diff>
diff --git a/CLAUDE.md b/CLAUDE.md
index 97b7d0f..cc56fcd 100644
--- a/CLAUDE.md
+++ b/CLAUDE.md
@@ -445,6 +445,17 @@ for org in organizations:
 
 # RIGHT: Use prefetch_related
 organizations.prefetch_related('projects')
+
+# WRONG: Use hasattr() for unions
+x: str | None = "hello"
+if hasattr(x, "replace"):
+    x = x.replace("e", "a")
+
+# RIGHT: Use isinstance()
+x: str | None = "hello"
+if isinstance(x, str):
+    x = x.replace("e", "a")
+
 ```
 
 ### Frontend
diff --git a/src/sentry/consumers/__init__.py b/src/sentry/consumers/__init__.py
index 345912e..0aa60a4 100644
--- a/src/sentry/consumers/__init__.py
+++ b/src/sentry/consumers/__init__.py
@@ -427,7 +427,15 @@ KAFKA_CONSUMERS: Mapping[str, ConsumerDefinition] = {
         "topic": Topic.INGEST_SPANS,
         "dlq_topic": Topic.INGEST_SPANS_DLQ,
         "strategy_factory": "sentry.spans.consumers.process.factory.ProcessSpansStrategyFactory",
-        "click_options": multiprocessing_options(default_max_batch_size=100),
+        "click_options": [
+            *multiprocessing_options(default_max_batch_size=100),
+            click.Option(
+                ["--flusher-processes", "flusher_processes"],
+                default=1,
+                type=int,
+                help="Maximum number of processes for the span flusher. Defaults to 1.",
+            ),
+        ],
     },
     "process-segments": {
         "topic": Topic.BUFFERED_SEGMENTS,
diff --git a/src/sentry/spans/consumers/process/factory.py b/src/sentry/spans/consumers/process/factory.py
index 8a4e8a6..90ef08f 100644
--- a/src/sentry/spans/consumers/process/factory.py
+++ b/src/sentry/spans/consumers/process/factory.py
@@ -38,6 +38,7 @@ class ProcessSpansStrategyFactory(ProcessingStrategyFactory[KafkaPayload]):
         num_processes: int,
         input_block_size: int | None,
         output_block_size: int | None,
+        flusher_processes: int | None = None,
         produce_to_pipe: Callable[[KafkaPayload], None] | None = None,
     ):
         super().__init__()
@@ -48,6 +49,7 @@ class ProcessSpansStrategyFactory(ProcessingStrategyFactory[KafkaPayload]):
         self.input_block_size = input_block_size
         self.output_block_size = output_block_size
         self.num_processes = num_processes
+        self.flusher_processes = flusher_processes
         self.produce_to_pipe = produce_to_pipe
 
         if self.num_processes != 1:
@@ -69,6 +71,7 @@ class ProcessSpansStrategyFactory(ProcessingStrategyFactory[KafkaPayload]):
         flusher = self._flusher = SpanFlusher(
             buffer,
             next_step=committer,
+            max_processes=self.flusher_processes,
             produce_to_pipe=self.produce_to_pipe,
         )
 
diff --git a/src/sentry/spans/consumers/process/flusher.py b/src/sentry/spans/consumers/process/flusher.py
index 359c0bf..ae9ec08 100644
--- a/src/sentry/spans/consumers/process/flusher.py
+++ b/src/sentry/spans/consumers/process/flusher.py
@@ -15,6 +15,7 @@ from arroyo.types import FilteredPayload, Message
 
 from sentry import options
 from sentry.conf.types.kafka_definition import Topic
+from sentry.processing.backpressure.memory import ServiceMemory
 from sentry.spans.buffer import SpansBuffer
 from sentry.utils import metrics
 from sentry.utils.arroyo import run_with_initialized_sentry
@@ -27,7 +28,8 @@ logger = logging.getLogger(__name__)
 
 class SpanFlusher(ProcessingStrategy[FilteredPayload | int]):
     """
-    A background thread that polls Redis for new segments to flush and to produce to Kafka.
+    A background multiprocessing manager that polls Redis for new segments to flush and to produce to Kafka.
+    Creates one process per shard for parallel processing.
 
     This is a processing step to be embedded into the consumer that writes to
     Redis. It takes and fowards integer messages that represent recently
@@ -42,27 +44,53 @@ class SpanFlusher(ProcessingStrategy[FilteredPayload | int]):
         self,
         buffer: SpansBuffer,
         next_step: ProcessingStrategy[FilteredPayload | int],
+        max_processes: int | None = None,
         produce_to_pipe: Callable[[KafkaPayload], None] | None = None,
     ):
-        self.buffer = buffer
         self.next_step = next_step
+        self.max_processes = max_processes or len(buffer.assigned_shards)
 
         self.mp_context = mp_context = multiprocessing.get_context("spawn")
         self.stopped = mp_context.Value("i", 0)
         self.redis_was_full = False
         self.current_drift = mp_context.Value("i", 0)
-        self.backpressure_since = mp_context.Value("i", 0)
-        self.healthy_since = mp_context.Value("i", 0)
-        self.process_restarts = 0
         self.produce_to_pipe = produce_to_pipe
 
-        self._create_process()
-
-    def _create_process(self):
+        # Determine which shards get their own processes vs shared processes
+        self.num_processes = min(self.max_processes, len(buffer.assigned_shards))
+        self.process_to_shards_map: dict[int, list[int]] = {
+            i: [] for i in range(self.num_processes)
+        }
+        for i, shard in enumerate(buffer.assigned_shards):
+            process_index = i % self.num_processes
+            self.process_to_shards_map[process_index].append(shard)
+
+        self.processes: dict[int, multiprocessing.context.SpawnProcess | threading.Thread] = {}
+        self.process_healthy_since = {
+            process_index: mp_context.Value("i", int(time.time()))
+            for process_index in range(self.num_processes)
+        }
+        self.process_backpressure_since = {
+            process_index: mp_context.Value("i", 0) for process_index in range(self.num_processes)
+        }
+        self.process_restarts = {process_index: 0 for process_index in range(self.num_processes)}
+        self.buffers: dict[int, SpansBuffer] = {}
+
+        self._create_processes()
+
+    def _create_processes(self):
+        # Create processes based on shard mapping
+        for process_index, shards in self.process_to_shards_map.items():
+            self._create_process_for_shards(process_index, shards)
+
+    def _create_process_for_shards(self, process_index: int, shards: list[int]):
         # Optimistically reset healthy_since to avoid a race between the
         # starting process and the next flush cycle. Keep back pressure across
         # the restart, however.
-        self.healthy_since.value = int(time.time())
+        self.process_healthy_since[process_index].value = int(time.time())
+
+        # Create a buffer for these specific shards
+        shard_buffer = SpansBuffer(shards)
 
         make_process: Callable[..., multiprocessing.context.SpawnProcess | threading.Thread]
         if self.produce_to_pipe is None:
@@ -72,37 +100,50 @@ class SpanFlusher(ProcessingStrategy[FilteredPayload | int]):
                 # pickled separately. at the same time, pickling
                 # synchronization primitives like multiprocessing.Value can
                 # only be done by the Process
-                self.buffer,
+                shard_buffer,
             )
             make_process = self.mp_context.Process
         else:
-            target = partial(SpanFlusher.main, self.buffer)
+            target = partial(SpanFlusher.main, shard_buffer)
             make_process = threading.Thread
 
-        self.process = make_process(
+        process = make_process(
             target=target,
             args=(
+                shards,
                 self.stopped,
                 self.current_drift,
-                self.backpressure_since,
-                self.healthy_since,
+                self.process_backpressure_since[process_index],
+                self.process_healthy_since[process_index],
                 self.produce_to_pipe,
             ),
             daemon=True,
         )
 
-        self.process.start()
+        process.start()
+        self.processes[process_index] = process
+        self.buffers[process_index] = shard_buffer
+
+    def _create_process_for_shard(self, shard: int):
+        # Find which process this shard belongs to and restart that process
+        for process_index, shards in self.process_to_shards_map.items():
+            if shard in shards:
+                self._create_process_for_shards(process_index, shards)
+                break
 
     @staticmethod
     def main(
         buffer: SpansBuffer,
+        shards: list[int],
         stopped,
         current_drift,
         backpressure_since,
         healthy_since,
         produce_to_pipe: Callable[[KafkaPayload], None] | None,
     ) -> None:
+        shard_tag = ",".join(map(str, shards))
         sentry_sdk.set_tag("sentry_spans_buffer_component", "flusher")
+        sentry_sdk.set_tag("sentry_spans_buffer_shards", shard_tag)
 
         try:
             producer_futures = []
@@ -134,23 +175,28 @@ class SpanFlusher(ProcessingStrategy[FilteredPayload | int]):
                 else:
                     backpressure_since.value = 0
 
+                # Update healthy_since for all shards handled by this process
                 healthy_since.value = system_now
 
                 if not flushed_segments:
                     time.sleep(1)
                     continue
 
-                with metrics.timer("spans.buffer.flusher.produce"):
-                    for _, flushed_segment in flushed_segments.items():
+                with metrics.timer("spans.buffer.flusher.produce", tags={"shard": shard_tag}):
+                    for flushed_segment in flushed_segments.values():
                         if not flushed_segment.spans:
                             continue
 
                         spans = [span.payload for span in flushed_segment.spans]
                         kafka_payload = KafkaPayload(None, orjson.dumps({"spans": spans}), [])
-                        metrics.timing("spans.buffer.segment_size_bytes", len(kafka_payload.value))
+                        metrics.timing(
+                            "spans.buffer.segment_size_bytes",
+                            len(kafka_payload.value),
+                            tags={"shard": shard_tag},
+                        )
                         produce(kafka_payload)
 
-                with metrics.timer("spans.buffer.flusher.wait_produce"):
+                with metrics.timer("spans.buffer.flusher.wait_produce", tags={"shards": shard_tag}):
                     for future in producer_futures:
                         future.result()
 
@@ -169,27 +215,48 @@ class SpanFlusher(ProcessingStrategy[FilteredPayload | int]):
     def poll(self) -> None:
         self.next_step.poll()
 
-    def _ensure_process_alive(self) -> None:
+    def _ensure_processes_alive(self) -> None:
         max_unhealthy_seconds = options.get("spans.buffer.flusher.max-unhealthy-seconds")
-        if not self.process.is_alive():
-            exitcode = getattr(self.process, "exitcode", "unknown")
-            cause = f"no_process_{exitcode}"
-        elif int(time.time()) - self.healthy_since.value > max_unhealthy_seconds:
-            cause = "hang"
-        else:
-            return  # healthy
 
-        metrics.incr("spans.buffer.flusher_unhealthy", tags={"cause": cause})
-        if self.process_restarts > MAX_PROCESS_RESTARTS:
-            raise RuntimeError(f"flusher process crashed repeatedly ({cause}), restarting consumer")
+        for process_index, process in self.processes.items():
+            if not process:
+                continue
+
+            shards = self.process_to_shards_map[process_index]
+
+            cause = None
+            if not process.is_alive():
+                exitcode = getattr(process, "exitcode", "unknown")
+                cause = f"no_process_{exitcode}"
+            elif (
+                int(time.time()) - self.process_healthy_since[process_index].value
+                > max_unhealthy_seconds
+            ):
+                # Check if any shard handled by this process is unhealthy
+                cause = "hang"
+
+            if cause is None:
+                continue  # healthy
+
+            # Report unhealthy for all shards handled by this process
+            for shard in shards:
+                metrics.incr(
+                    "spans.buffer.flusher_unhealthy", tags={"cause": cause, "shard": shard}
+                )
 
-        try:
-            self.process.kill()
-        except ValueError:
-            pass  # Process already closed, ignore
+            if self.process_restarts[process_index] > MAX_PROCESS_RESTARTS:
+                raise RuntimeError(
+                    f"flusher process for shards {shards} crashed repeatedly ({cause}), restarting consumer"
+                )
+            self.process_restarts[process_index] += 1
 
-        self.process_restarts += 1
-        self._create_process()
+            try:
+                if isinstance(process, multiprocessing.Process):
+                    process.kill()
+            except (ValueError, AttributeError):
+                pass  # Process already closed, ignore
+
+            self._create_process_for_shards(process_index, shards)
 
     def submit(self, message: Message[FilteredPayload | int]) -> None:
         # Note that submit is not actually a hot path. Their message payloads
@@ -197,18 +264,22 @@ class SpanFlusher(ProcessingStrategy[FilteredPayload | int]):
         # per second at most. If anything, self.poll() might even be called
         # more often than submit()
 
-        self._ensure_process_alive()
+        self._ensure_processes_alive()
 
-        self.buffer.record_stored_segments()
+        for buffer in self.buffers.values():
+            buffer.record_stored_segments()
 
         # We pause insertion into Redis if the flusher is not making progress
         # fast enough. We could backlog into Redis, but we assume, despite best
         # efforts, it is still always going to be less durable than Kafka.
         # Minimizing our Redis memory usage also makes COGS easier to reason
         # about.
-        if self.backpressure_since.value > 0:
-            backpressure_secs = options.get("spans.buffer.flusher.backpressure-seconds")
-            if int(time.time()) - self.backpressure_since.value > backpressure_secs:
+        backpressure_secs = options.get("spans.buffer.flusher.backpressure-seconds")
+        for backpressure_since in self.process_backpressure_since.values():
+            if (
+                backpressure_since.value > 0
+                and int(time.time()) - backpressure_since.value > backpressure_secs
+            ):
                 metrics.incr("spans.buffer.flusher.backpressure")
                 raise MessageRejected()
 
@@ -225,7 +296,9 @@ class SpanFlusher(ProcessingStrategy[FilteredPayload | int]):
         # wait until the situation is improved manually.
         max_memory_percentage = options.get("spans.buffer.max-memory-percentage")
         if max_memory_percentage < 1.0:
-            memory_infos = list(self.buffer.get_memory_info())
+            memory_infos: list[ServiceMemory] = []
+            for buffer in self.buffers.values():
+                memory_infos.extend(buffer.get_memory_info())
             used = sum(x.used for x in memory_infos)
             available = sum(x.available for x in memory_infos)
             if available > 0 and used / available > max_memory_percentage:
@@ -253,15 +326,22 @@ class SpanFlusher(ProcessingStrategy[FilteredPayload | int]):
         self.next_step.close()
 
     def join(self, timeout: float | None = None):
-        # set stopped flag first so we can "flush" the background thread while
+        # set stopped flag first so we can "flush" the background threads while
         # next_step is also shutting down. we can do two things at once!
         self.stopped.value = True
         deadline = time.time() + timeout if timeout else None
 
         self.next_step.join(timeout)
 
-        while self.process.is_alive() and (deadline is None or deadline > time.time()):
-            time.sleep(0.1)
+        # Wait for all processes to finish
+        for process_index, process in self.processes.items():
+            if deadline is not None:
+                remaining_time = deadline - time.time()
+                if remaining_time <= 0:
+                    break
+
+            while process.is_alive() and (deadline is None or deadline > time.time()):
+                time.sleep(0.1)
 
-        if isinstance(self.process, multiprocessing.Process):
-            self.process.terminate()
+            if isinstance(process, multiprocessing.Process):
+                process.terminate()
diff --git a/tests/sentry/spans/consumers/process/test_consumer.py b/tests/sentry/spans/consumers/process/test_consumer.py
index f12a7ab..c216de2 100644
--- a/tests/sentry/spans/consumers/process/test_consumer.py
+++ b/tests/sentry/spans/consumers/process/test_consumer.py
@@ -1,3 +1,4 @@
+import time
 from datetime import datetime
 
 import pytest
@@ -8,7 +9,7 @@ from arroyo.types import BrokerValue, Message, Partition, Topic
 from sentry.spans.consumers.process.factory import ProcessSpansStrategyFactory
 
 
-@pytest.mark.django_db
+@pytest.mark.django_db(transaction=True)
 def test_basic(monkeypatch):
     # Flush very aggressively to make test pass instantly
     monkeypatch.setattr("time.sleep", lambda _: None)
@@ -56,6 +57,10 @@ def test_basic(monkeypatch):
     step.poll()
     fac._flusher.current_drift.value = 9000  # "advance" our "clock"
 
+    step.poll()
+    # Give flusher threads time to process after drift change
+    time.sleep(0.1)
+
     step.join()
 
     (msg,) = messages
@@ -74,3 +79,45 @@ def test_basic(monkeypatch):
             },
         ],
     }
+
+
+@pytest.mark.django_db(transaction=True)
+def test_flusher_processes_limit(monkeypatch):
+    """Test that flusher respects the max_processes limit"""
+    # Flush very aggressively to make test pass instantly
+    monkeypatch.setattr("time.sleep", lambda _: None)
+
+    topic = Topic("test")
+    messages: list[KafkaPayload] = []
+
+    # Create factory with limited flusher processes
+    fac = ProcessSpansStrategyFactory(
+        max_batch_size=10,
+        max_batch_time=10,
+        num_processes=1,
+        input_block_size=None,
+        output_block_size=None,
+        flusher_processes=2,  # Limit to 2 processes even if more shards
+        produce_to_pipe=messages.append,
+    )
+
+    commits = []
+
+    def add_commit(offsets, force=False):
+        commits.append(offsets)
+
+    # Create with 4 partitions/shards to test process sharing
+    partitions = {Partition(topic, i): 0 for i in range(4)}
+    step = fac.create_with_partitions(add_commit, partitions)
+
+    # Verify that flusher uses at most 2 processes
+    flusher = fac._flusher
+    assert len(flusher.processes) == 2
+    assert flusher.max_processes == 2
+    assert flusher.num_processes == 2
+
+    # Verify shards are distributed across processes
+    total_shards = sum(len(shards) for shards in flusher.process_to_shards_map.values())
+    assert total_shards == 4  # All 4 shards should be assigned
+
+    step.join()
diff --git a/tests/sentry/spans/consumers/process/test_flusher.py b/tests/sentry/spans/consumers/process/test_flusher.py
index 6365653..0e886ff 100644
--- a/tests/sentry/spans/consumers/process/test_flusher.py
+++ b/tests/sentry/spans/consumers/process/test_flusher.py
@@ -80,4 +80,4 @@ def test_backpressure(monkeypatch):
 
     assert messages
 
-    assert flusher.backpressure_since.value
+    assert any(x.value for x in flusher.process_backpressure_since.values())

</diff>

## 2. Changed Code (Modified Files with Context)

<file name="CLAUDE.md" lines="448-458" type="changed">
```python
 445  
 446  # RIGHT: Use prefetch_related
 447  organizations.prefetch_related('projects')
 448  
 449  # WRONG: Use hasattr() for unions
 450  x: str | None = "hello"
 451  if hasattr(x, "replace"):
 452      x = x.replace("e", "a")
 453  
 454  # RIGHT: Use isinstance()
 455  x: str | None = "hello"
 456  if isinstance(x, str):
 457      x = x.replace("e", "a")
 458  
 459  ```
 460  
 461  ### Frontend
```
</file>

<file name="src/sentry/consumers/__init__.py" lines="430-438" type="changed">
```python
 426      "process-spans": {
 427          "topic": Topic.INGEST_SPANS,
 428          "dlq_topic": Topic.INGEST_SPANS_DLQ,
 429          "strategy_factory": "sentry.spans.consumers.process.factory.ProcessSpansStrategyFactory",
 430          "click_options": [
 431              *multiprocessing_options(default_max_batch_size=100),
 432              click.Option(
 433                  ["--flusher-processes", "flusher_processes"],
 434                  default=1,
 435                  type=int,
 436                  help="Maximum number of processes for the span flusher. Defaults to 1.",
 437              ),
 438          ],
 439      },
 440      "process-segments": {
 441          "topic": Topic.BUFFERED_SEGMENTS,
 442          "dlq_topic": Topic.BUFFERED_SEGMENTS_DLQ,
```
</file>

<file name="src/sentry/spans/consumers/process/factory.py" lines="41-41" type="changed">
```python
  33  
  34      def __init__(
  35          self,
  36          max_batch_size: int,
  37          max_batch_time: int,
  38          num_processes: int,
  39          input_block_size: int | None,
  40          output_block_size: int | None,
  41          flusher_processes: int | None = None,
  42          produce_to_pipe: Callable[[KafkaPayload], None] | None = None,
  43      ):
  44          super().__init__()
  45  
  46          # config
  47          self.max_batch_size = max_batch_size
  48          self.max_batch_time = max_batch_time
  49          self.input_block_size = input_block_size
```
</file>

<file name="src/sentry/spans/consumers/process/factory.py" lines="52-52" type="changed">
```python
  44          super().__init__()
  45  
  46          # config
  47          self.max_batch_size = max_batch_size
  48          self.max_batch_time = max_batch_time
  49          self.input_block_size = input_block_size
  50          self.output_block_size = output_block_size
  51          self.num_processes = num_processes
  52          self.flusher_processes = flusher_processes
  53          self.produce_to_pipe = produce_to_pipe
  54  
  55          if self.num_processes != 1:
  56              self.__pool = MultiprocessingPool(num_processes)
  57  
  58      def create_with_partitions(
  59          self,
  60          commit: Commit,
```
</file>

<file name="src/sentry/spans/consumers/process/factory.py" lines="74-74" type="changed">
```python
  66  
  67          buffer = SpansBuffer(assigned_shards=[p.index for p in partitions])
  68  
  69          # patch onto self just for testing
  70          flusher: ProcessingStrategy[FilteredPayload | int]
  71          flusher = self._flusher = SpanFlusher(
  72              buffer,
  73              next_step=committer,
  74              max_processes=self.flusher_processes,
  75              produce_to_pipe=self.produce_to_pipe,
  76          )
  77  
  78          if self.num_processes != 1:
  79              run_task = run_task_with_multiprocessing(
  80                  function=partial(process_batch, buffer),
  81                  next_step=flusher,
  82                  max_batch_size=self.max_batch_size,
```
</file>

<file name="src/sentry/spans/consumers/process/flusher.py" lines="18-18" type="changed">
```python
  10  import sentry_sdk
  11  from arroyo import Topic as ArroyoTopic
  12  from arroyo.backends.kafka import KafkaPayload, KafkaProducer, build_kafka_configuration
  13  from arroyo.processing.strategies.abstract import MessageRejected, ProcessingStrategy
  14  from arroyo.types import FilteredPayload, Message
  15  
  16  from sentry import options
  17  from sentry.conf.types.kafka_definition import Topic
  18  from sentry.processing.backpressure.memory import ServiceMemory
  19  from sentry.spans.buffer import SpansBuffer
  20  from sentry.utils import metrics
  21  from sentry.utils.arroyo import run_with_initialized_sentry
  22  from sentry.utils.kafka_config import get_kafka_producer_cluster_options, get_topic_definition
  23  
  24  MAX_PROCESS_RESTARTS = 10
  25  
  26  logger = logging.getLogger(__name__)
```
</file>

<file name="src/sentry/spans/consumers/process/flusher.py" lines="31-32" type="changed">
```python
  24  MAX_PROCESS_RESTARTS = 10
  25  
  26  logger = logging.getLogger(__name__)
  27  
  28  
  29  class SpanFlusher(ProcessingStrategy[FilteredPayload | int]):
  30      """
  31      A background multiprocessing manager that polls Redis for new segments to flush and to produce to Kafka.
  32      Creates one process per shard for parallel processing.
  33  
  34      This is a processing step to be embedded into the consumer that writes to
  35      Redis. It takes and fowards integer messages that represent recently
  36      processed timestamps (from the producer timestamp of the incoming span
  37      message), which are then used as a clock to determine whether segments have expired.
  38  
  39      :param topic: The topic to send segments to.
  40      :param produce_to_pipe: For unit-testing, produce to this multiprocessing Pipe instead of creating a kafka consumer.
```
</file>

<file name="src/sentry/spans/consumers/process/flusher.py" lines="47-93" type="changed">
```python
  65              process_index = i % self.num_processes
  66              self.process_to_shards_map[process_index].append(shard)
  67  
  68          self.processes: dict[int, multiprocessing.context.SpawnProcess | threading.Thread] = {}
  69          self.process_healthy_since = {
  70              process_index: mp_context.Value("i", int(time.time()))
  71              for process_index in range(self.num_processes)
  72          }
  73          self.process_backpressure_since = {
  74              process_index: mp_context.Value("i", 0) for process_index in range(self.num_processes)
  75          }
  76          self.process_restarts = {process_index: 0 for process_index in range(self.num_processes)}
  77          self.buffers: dict[int, SpansBuffer] = {}
  78  
  79          self._create_processes()
  80  
  81      def _create_processes(self):
```
</file>

<file name="src/sentry/spans/consumers/process/flusher.py" lines="103-117" type="changed">
```python
 105              make_process = self.mp_context.Process
 106          else:
 107              target = partial(SpanFlusher.main, shard_buffer)
 108              make_process = threading.Thread
 109  
 110          process = make_process(
 111              target=target,
 112              args=(
 113                  shards,
 114                  self.stopped,
 115                  self.current_drift,
 116                  self.process_backpressure_since[process_index],
 117                  self.process_healthy_since[process_index],
 118                  self.produce_to_pipe,
 119              ),
 120              daemon=True,
 121          )
```
</file>

<file name="src/sentry/spans/consumers/process/flusher.py" lines="123-137" type="changed">
```python
 120              daemon=True,
 121          )
 122  
 123          process.start()
 124          self.processes[process_index] = process
 125          self.buffers[process_index] = shard_buffer
 126  
 127      def _create_process_for_shard(self, shard: int):
 128          # Find which process this shard belongs to and restart that process
 129          for process_index, shards in self.process_to_shards_map.items():
 130              if shard in shards:
 131                  self._create_process_for_shards(process_index, shards)
 132                  break
 133  
 134      @staticmethod
 135      def main(
 136          buffer: SpansBuffer,
```
</file>

<file name="src/sentry/spans/consumers/process/flusher.py" lines="144-146" type="changed">
```python
 138          stopped,
 139          current_drift,
 140          backpressure_since,
 141          healthy_since,
 142          produce_to_pipe: Callable[[KafkaPayload], None] | None,
 143      ) -> None:
 144          shard_tag = ",".join(map(str, shards))
 145          sentry_sdk.set_tag("sentry_spans_buffer_component", "flusher")
 146          sentry_sdk.set_tag("sentry_spans_buffer_shards", shard_tag)
 147  
 148          try:
 149              producer_futures = []
 150  
 151              if produce_to_pipe is not None:
 152                  produce = produce_to_pipe
 153                  producer = None
 154              else:
```
</file>

<file name="src/sentry/spans/consumers/process/flusher.py" lines="178-178" type="changed">
```python
 170  
 171                  # Check backpressure flag set by buffer
 172                  if buffer.any_shard_at_limit:
 173                      if backpressure_since.value == 0:
 174                          backpressure_since.value = system_now
 175                  else:
 176                      backpressure_since.value = 0
 177  
 178                  # Update healthy_since for all shards handled by this process
 179                  healthy_since.value = system_now
 180  
 181                  if not flushed_segments:
 182                      time.sleep(1)
 183                      continue
 184  
 185                  with metrics.timer("spans.buffer.flusher.produce", tags={"shard": shard_tag}):
 186                      for flushed_segment in flushed_segments.values():
```
</file>

<file name="src/sentry/spans/consumers/process/flusher.py" lines="185-186" type="changed">
```python
 178                  # Update healthy_since for all shards handled by this process
 179                  healthy_since.value = system_now
 180  
 181                  if not flushed_segments:
 182                      time.sleep(1)
 183                      continue
 184  
 185                  with metrics.timer("spans.buffer.flusher.produce", tags={"shard": shard_tag}):
 186                      for flushed_segment in flushed_segments.values():
 187                          if not flushed_segment.spans:
 188                              continue
 189  
 190                          spans = [span.payload for span in flushed_segment.spans]
 191                          kafka_payload = KafkaPayload(None, orjson.dumps({"spans": spans}), [])
 192                          metrics.timing(
 193                              "spans.buffer.segment_size_bytes",
 194                              len(kafka_payload.value),
```
</file>

<file name="src/sentry/spans/consumers/process/flusher.py" lines="192-199" type="changed">
```python
 187                          if not flushed_segment.spans:
 188                              continue
 189  
 190                          spans = [span.payload for span in flushed_segment.spans]
 191                          kafka_payload = KafkaPayload(None, orjson.dumps({"spans": spans}), [])
 192                          metrics.timing(
 193                              "spans.buffer.segment_size_bytes",
 194                              len(kafka_payload.value),
 195                              tags={"shard": shard_tag},
 196                          )
 197                          produce(kafka_payload)
 198  
 199                  with metrics.timer("spans.buffer.flusher.wait_produce", tags={"shards": shard_tag}):
 200                      for future in producer_futures:
 201                          future.result()
 202  
 203                  producer_futures.clear()
```
</file>

<file name="src/sentry/spans/consumers/process/flusher.py" lines="218-259" type="changed">
```python
 230                  cause = f"no_process_{exitcode}"
 231              elif (
 232                  int(time.time()) - self.process_healthy_since[process_index].value
 233                  > max_unhealthy_seconds
 234              ):
 235                  # Check if any shard handled by this process is unhealthy
 236                  cause = "hang"
 237  
 238              if cause is None:
 239                  continue  # healthy
 240  
 241              # Report unhealthy for all shards handled by this process
 242              for shard in shards:
 243                  metrics.incr(
 244                      "spans.buffer.flusher_unhealthy", tags={"cause": cause, "shard": shard}
 245                  )
 246  
```
</file>

<file name="src/sentry/spans/consumers/process/flusher.py" lines="267-270" type="changed">
```python
 261      def submit(self, message: Message[FilteredPayload | int]) -> None:
 262          # Note that submit is not actually a hot path. Their message payloads
 263          # are mapped from *batches* of spans, and there are a handful of spans
 264          # per second at most. If anything, self.poll() might even be called
 265          # more often than submit()
 266  
 267          self._ensure_processes_alive()
 268  
 269          for buffer in self.buffers.values():
 270              buffer.record_stored_segments()
 271  
 272          # We pause insertion into Redis if the flusher is not making progress
 273          # fast enough. We could backlog into Redis, but we assume, despite best
 274          # efforts, it is still always going to be less durable than Kafka.
 275          # Minimizing our Redis memory usage also makes COGS easier to reason
 276          # about.
 277          backpressure_secs = options.get("spans.buffer.flusher.backpressure-seconds")
```
</file>

<file name="src/sentry/spans/consumers/process/flusher.py" lines="277-282" type="changed">
```python
 272          # We pause insertion into Redis if the flusher is not making progress
 273          # fast enough. We could backlog into Redis, but we assume, despite best
 274          # efforts, it is still always going to be less durable than Kafka.
 275          # Minimizing our Redis memory usage also makes COGS easier to reason
 276          # about.
 277          backpressure_secs = options.get("spans.buffer.flusher.backpressure-seconds")
 278          for backpressure_since in self.process_backpressure_since.values():
 279              if (
 280                  backpressure_since.value > 0
 281                  and int(time.time()) - backpressure_since.value > backpressure_secs
 282              ):
 283                  metrics.incr("spans.buffer.flusher.backpressure")
 284                  raise MessageRejected()
 285  
 286          # We set the drift. The backpressure based on redis memory comes after.
 287          # If Redis is full for a long time, the drift will grow into a large
 288          # negative value, effectively pausing flushing as well.
```
</file>

<file name="src/sentry/spans/consumers/process/flusher.py" lines="299-301" type="changed">
```python
 292  
 293          # We also pause insertion into Redis if Redis is too full. In this case
 294          # we cannot allow the flusher to progress either, as it would write
 295          # partial/fragmented segments to buffered-segments topic. We have to
 296          # wait until the situation is improved manually.
 297          max_memory_percentage = options.get("spans.buffer.max-memory-percentage")
 298          if max_memory_percentage < 1.0:
 299              memory_infos: list[ServiceMemory] = []
 300              for buffer in self.buffers.values():
 301                  memory_infos.extend(buffer.get_memory_info())
 302              used = sum(x.used for x in memory_infos)
 303              available = sum(x.available for x in memory_infos)
 304              if available > 0 and used / available > max_memory_percentage:
 305                  if not self.redis_was_full:
 306                      logger.fatal("Pausing consumer due to Redis being full")
 307                  metrics.incr("spans.buffer.flusher.hard_backpressure")
 308                  self.redis_was_full = True
```
</file>

<file name="src/sentry/spans/consumers/process/flusher.py" lines="329-329" type="changed">
```python
 321  
 322      def close(self) -> None:
 323          # Do not shut down the flusher here -- this is running at the beginning
 324          # of rebalancing, so everytime we are rebalancing we will cause a huge
 325          # memory spike in redis
 326          self.next_step.close()
 327  
 328      def join(self, timeout: float | None = None):
 329          # set stopped flag first so we can "flush" the background threads while
 330          # next_step is also shutting down. we can do two things at once!
 331          self.stopped.value = True
 332          deadline = time.time() + timeout if timeout else None
 333  
 334          self.next_step.join(timeout)
 335  
 336          # Wait for all processes to finish
 337          for process_index, process in self.processes.items():
```
</file>

<file name="src/sentry/spans/consumers/process/flusher.py" lines="336-347" type="changed">
```python
 333  
 334          self.next_step.join(timeout)
 335  
 336          # Wait for all processes to finish
 337          for process_index, process in self.processes.items():
 338              if deadline is not None:
 339                  remaining_time = deadline - time.time()
 340                  if remaining_time <= 0:
 341                      break
 342  
 343              while process.is_alive() and (deadline is None or deadline > time.time()):
 344                  time.sleep(0.1)
 345  
 346              if isinstance(process, multiprocessing.Process):
 347                  process.terminate()
```
</file>

<file name="tests/sentry/spans/consumers/process/test_consumer.py" lines="1-1" type="changed">
```python
   1  import time
   2  from datetime import datetime
   3  
   4  import pytest
   5  import rapidjson
   6  from arroyo.backends.kafka import KafkaPayload
   7  from arroyo.types import BrokerValue, Message, Partition, Topic
   8  
   9  from sentry.spans.consumers.process.factory import ProcessSpansStrategyFactory
```
</file>

<file name="tests/sentry/spans/consumers/process/test_consumer.py" lines="12-12" type="changed">
```python
   4  import pytest
   5  import rapidjson
   6  from arroyo.backends.kafka import KafkaPayload
   7  from arroyo.types import BrokerValue, Message, Partition, Topic
   8  
   9  from sentry.spans.consumers.process.factory import ProcessSpansStrategyFactory
  10  
  11  
  12  @pytest.mark.django_db(transaction=True)
  13  def test_basic(monkeypatch):
  14      # Flush very aggressively to make test pass instantly
  15      monkeypatch.setattr("time.sleep", lambda _: None)
  16  
  17      topic = Topic("test")
  18      messages: list[KafkaPayload] = []
  19  
  20      fac = ProcessSpansStrategyFactory(
```
</file>

<file name="tests/sentry/spans/consumers/process/test_consumer.py" lines="60-63" type="changed">
```python
  54          )
  55      )
  56  
  57      step.poll()
  58      fac._flusher.current_drift.value = 9000  # "advance" our "clock"
  59  
  60      step.poll()
  61      # Give flusher threads time to process after drift change
  62      time.sleep(0.1)
  63  
  64      step.join()
  65  
  66      (msg,) = messages
  67  
  68      assert rapidjson.loads(msg.value) == {
  69          "spans": [
  70              {
```
</file>

<file name="tests/sentry/spans/consumers/process/test_consumer.py" lines="82-123" type="changed">
```python
  95          max_batch_size=10,
  96          max_batch_time=10,
  97          num_processes=1,
  98          input_block_size=None,
  99          output_block_size=None,
 100          flusher_processes=2,  # Limit to 2 processes even if more shards
 101          produce_to_pipe=messages.append,
 102      )
 103  
 104      commits = []
 105  
 106      def add_commit(offsets, force=False):
 107          commits.append(offsets)
 108  
 109      # Create with 4 partitions/shards to test process sharing
 110      partitions = {Partition(topic, i): 0 for i in range(4)}
 111      step = fac.create_with_partitions(add_commit, partitions)
```
</file>

<file name="tests/sentry/spans/consumers/process/test_flusher.py" lines="83-83" type="changed">
```python
  75      # have way too much to do due to `max_flush_segments=1` and enter
  76      # backpressure state.
  77  
  78      flusher.current_drift.value = 20000
  79      sleep(0.1)
  80  
  81      assert messages
  82  
  83      assert any(x.value for x in flusher.process_backpressure_since.values())
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
