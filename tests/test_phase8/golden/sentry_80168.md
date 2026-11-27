# Code Review Context

## 1. Git Diff (What Changed)

<diff>
diff --git a/src/sentry/incidents/grouptype.py b/src/sentry/incidents/grouptype.py
index 5b01444..a17a843 100644
--- a/src/sentry/incidents/grouptype.py
+++ b/src/sentry/incidents/grouptype.py
@@ -4,17 +4,12 @@ from sentry.incidents.utils.types import QuerySubscriptionUpdate
 from sentry.issues.grouptype import GroupCategory, GroupType
 from sentry.ratelimits.sliding_windows import Quota
 from sentry.types.group import PriorityLevel
-from sentry.workflow_engine.models import DataPacket
-from sentry.workflow_engine.processors.detector import DetectorEvaluationResult, DetectorHandler
+from sentry.workflow_engine.processors.detector import StatefulDetectorHandler
 
 
 # TODO: This will be a stateful detector when we build that abstraction
-class MetricAlertDetectorHandler(DetectorHandler[QuerySubscriptionUpdate]):
-    def evaluate(
-        self, data_packet: DataPacket[QuerySubscriptionUpdate]
-    ) -> list[DetectorEvaluationResult]:
-        # TODO: Implement
-        return []
+class MetricAlertDetectorHandler(StatefulDetectorHandler[QuerySubscriptionUpdate]):
+    pass
 
 
 # Example GroupType and detector handler for metric alerts. We don't create these issues yet, but we'll use something
diff --git a/src/sentry/workflow_engine/models/detector.py b/src/sentry/workflow_engine/models/detector.py
index 1b72815..2f293ac 100644
--- a/src/sentry/workflow_engine/models/detector.py
+++ b/src/sentry/workflow_engine/models/detector.py
@@ -1,5 +1,6 @@
 from __future__ import annotations
 
+import builtins
 import logging
 from typing import TYPE_CHECKING
 
@@ -9,6 +10,7 @@ from django.db.models import UniqueConstraint
 from sentry.backup.scopes import RelocationScope
 from sentry.db.models import DefaultFieldsModel, FlexibleForeignKey, region_silo_model
 from sentry.issues import grouptype
+from sentry.issues.grouptype import GroupType
 from sentry.models.owner_base import OwnerModel
 
 if TYPE_CHECKING:
@@ -53,9 +55,13 @@ class Detector(DefaultFieldsModel, OwnerModel):
         # XXX: Temporary property until we add `project_id` to the model.
         return 1
 
+    @property
+    def group_type(self) -> builtins.type[GroupType] | None:
+        return grouptype.registry.get_by_slug(self.type)
+
     @property
     def detector_handler(self) -> DetectorHandler | None:
-        group_type = grouptype.registry.get_by_slug(self.type)
+        group_type = self.group_type
         if not group_type:
             logger.error(
                 "No registered grouptype for detector",
diff --git a/src/sentry/workflow_engine/processors/detector.py b/src/sentry/workflow_engine/processors/detector.py
index 4e2e9b0..898b593 100644
--- a/src/sentry/workflow_engine/processors/detector.py
+++ b/src/sentry/workflow_engine/processors/detector.py
@@ -14,6 +14,7 @@ from sentry.issues.issue_occurrence import IssueOccurrence
 from sentry.issues.producer import PayloadType, produce_occurrence_to_kafka
 from sentry.issues.status_change_message import StatusChangeMessage
 from sentry.models.group import GroupStatus
+from sentry.types.group import PriorityLevel
 from sentry.utils import metrics, redis
 from sentry.utils.function_cache import cache_func_for_models
 from sentry.utils.iterators import chunked
@@ -45,7 +46,7 @@ class DetectorEvaluationResult:
 
 def process_detectors(
     data_packet: DataPacket, detectors: list[Detector]
-) -> list[tuple[Detector, list[DetectorEvaluationResult]]]:
+) -> list[tuple[Detector, dict[DetectorGroupKey, DetectorEvaluationResult]]]:
     results = []
 
     for detector in detectors:
@@ -55,25 +56,11 @@ def process_detectors(
             continue
 
         detector_results = handler.evaluate(data_packet)
-        detector_group_keys = set()
-
-        for result in detector_results:
-            if result.group_key in detector_group_keys:
-                # This shouldn't happen - log an error and continue on, but we should investigate this.
-                logger.error(
-                    "Duplicate detector state group keys found",
-                    extra={
-                        "detector_id": detector.id,
-                        "group_key": result.group_key,
-                    },
-                )
-                continue
 
+        for result in detector_results.values():
             if result.result is not None:
                 create_issue_occurrence_from_result(result)
 
-            detector_group_keys.add(result.group_key)
-
         if detector_results:
             results.append((detector, detector_results))
 
@@ -136,7 +123,9 @@ class DetectorHandler(abc.ABC, Generic[T]):
             self.conditions = []
 
     @abc.abstractmethod
-    def evaluate(self, data_packet: DataPacket[T]) -> list[DetectorEvaluationResult]:
+    def evaluate(
+        self, data_packet: DataPacket[T]
+    ) -> dict[DetectorGroupKey, DetectorEvaluationResult]:
         pass
 
     def commit_state_updates(self):
@@ -174,6 +163,12 @@ class StatefulDetectorHandler(DetectorHandler[T], abc.ABC):
         """
         pass
 
+    @abc.abstractmethod
+    def build_occurrence_and_event_data(
+        self, group_key: DetectorGroupKey, value: int, new_status: PriorityLevel
+    ) -> tuple[IssueOccurrence, dict[str, Any]]:
+        pass
+
     def build_fingerprint(self, group_key) -> list[str]:
         """
         Builds a fingerprint to uniquely identify a detected issue
@@ -228,7 +223,9 @@ class StatefulDetectorHandler(DetectorHandler[T], abc.ABC):
             )
         return results
 
-    def evaluate(self, data_packet: DataPacket[T]) -> list[DetectorEvaluationResult]:
+    def evaluate(
+        self, data_packet: DataPacket[T]
+    ) -> dict[DetectorGroupKey, DetectorEvaluationResult]:
         """
         Evaluates a given data packet and returns a list of `DetectorEvaluationResult`.
         There will be one result for each group key result in the packet, unless the
@@ -237,13 +234,13 @@ class StatefulDetectorHandler(DetectorHandler[T], abc.ABC):
         dedupe_value = self.get_dedupe_value(data_packet)
         group_values = self.get_group_key_values(data_packet)
         all_state_data = self.get_state_data(list(group_values.keys()))
-        results = []
+        results = {}
         for group_key, group_value in group_values.items():
             result = self.evaluate_group_key_value(
                 group_key, group_value, all_state_data[group_key], dedupe_value
             )
             if result:
-                results.append(result)
+                results[result.group_key] = result
         return results
 
     def evaluate_group_key_value(
@@ -289,7 +286,7 @@ class StatefulDetectorHandler(DetectorHandler[T], abc.ABC):
             is_active = new_status != DetectorPriorityLevel.OK
             self.enqueue_state_update(group_key, is_active, new_status)
             event_data = None
-            result = None
+            result: StatusChangeMessage | IssueOccurrence
             if new_status == DetectorPriorityLevel.OK:
                 # If we've determined that we're now ok, we just want to resolve the issue
                 result = StatusChangeMessage(
@@ -298,8 +295,10 @@ class StatefulDetectorHandler(DetectorHandler[T], abc.ABC):
                     new_status=GroupStatus.RESOLVED,
                     new_substatus=None,
                 )
-
-            # TODO: Add hook here for generating occurrence
+            else:
+                result, event_data = self.build_occurrence_and_event_data(
+                    group_key, value, PriorityLevel(new_status)
+                )
             return DetectorEvaluationResult(
                 group_key=group_key,
                 is_active=is_active,
diff --git a/tests/sentry/workflow_engine/processors/test_detector.py b/tests/sentry/workflow_engine/processors/test_detector.py
index 7ac44a7..d56b02d 100644
--- a/tests/sentry/workflow_engine/processors/test_detector.py
+++ b/tests/sentry/workflow_engine/processors/test_detector.py
@@ -1,10 +1,16 @@
 import unittest
+from datetime import datetime, timezone
+from typing import Any
 from unittest import mock
+from unittest.mock import call
 
 from sentry.issues.grouptype import GroupCategory, GroupType
+from sentry.issues.issue_occurrence import IssueOccurrence
+from sentry.issues.producer import PayloadType
 from sentry.issues.status_change_message import StatusChangeMessage
 from sentry.testutils.abstract import Abstract
-from sentry.testutils.cases import TestCase
+from sentry.testutils.helpers.datetime import freeze_time
+from sentry.types.group import PriorityLevel
 from sentry.workflow_engine.models import DataPacket, Detector, DetectorState
 from sentry.workflow_engine.processors.detector import (
     DetectorEvaluationResult,
@@ -14,13 +20,34 @@ from sentry.workflow_engine.processors.detector import (
     get_redis_client,
     process_detectors,
 )
-from sentry.workflow_engine.types import DetectorPriorityLevel
+from sentry.workflow_engine.types import DetectorGroupKey, DetectorPriorityLevel
 from tests.sentry.issues.test_grouptype import BaseGroupTypeTest
 
 
-class TestProcessDetectors(BaseGroupTypeTest):
+class MockDetectorStateHandler(StatefulDetectorHandler[dict]):
+    counter_names = ["test1", "test2"]
+
+    def get_dedupe_value(self, data_packet: DataPacket[dict]) -> int:
+        return data_packet.packet.get("dedupe", 0)
+
+    def get_group_key_values(self, data_packet: DataPacket[dict]) -> dict[str, int]:
+        return data_packet.packet.get("group_vals", {})
+
+    def build_occurrence_and_event_data(
+        self, group_key: DetectorGroupKey, value: int, new_status: PriorityLevel
+    ) -> tuple[IssueOccurrence, dict[str, Any]]:
+        return build_mock_occurrence_and_event(self, group_key, value, new_status)
+
+
+class BaseDetectorHandlerTest(BaseGroupTypeTest):
+    __test__ = Abstract(__module__, __qualname__)
+
     def setUp(self):
         super().setUp()
+        self.sm_comp_patcher = mock.patch.object(
+            StatusChangeMessage, "__eq__", status_change_comparator
+        )
+        self.sm_comp_patcher.__enter__()
 
         class NoHandlerGroupType(GroupType):
             type_id = 1
@@ -29,8 +56,10 @@ class TestProcessDetectors(BaseGroupTypeTest):
             category = GroupCategory.METRIC_ALERT.value
 
         class MockDetectorHandler(DetectorHandler[dict]):
-            def evaluate(self, data_packet: DataPacket[dict]) -> list[DetectorEvaluationResult]:
-                return [DetectorEvaluationResult(None, True, DetectorPriorityLevel.HIGH)]
+            def evaluate(
+                self, data_packet: DataPacket[dict]
+            ) -> dict[DetectorGroupKey, DetectorEvaluationResult]:
+                return {None: DetectorEvaluationResult(None, True, DetectorPriorityLevel.HIGH)}
 
         class HandlerGroupType(GroupType):
             type_id = 2
@@ -39,18 +68,6 @@ class TestProcessDetectors(BaseGroupTypeTest):
             category = GroupCategory.METRIC_ALERT.value
             detector_handler = MockDetectorHandler
 
-        class MockDetectorStateHandler(DetectorHandler[dict]):
-            def evaluate(self, data_packet: DataPacket[dict]) -> list[DetectorEvaluationResult]:
-                group_keys = data_packet.packet.get("group_keys", [None])
-                return [
-                    DetectorEvaluationResult(
-                        group_key,
-                        True,
-                        DetectorPriorityLevel.HIGH,
-                    )
-                    for group_key in group_keys
-                ]
-
         class HandlerStateGroupType(GroupType):
             type_id = 3
             slug = "handler_with_state"
@@ -62,9 +79,57 @@ class TestProcessDetectors(BaseGroupTypeTest):
         self.handler_type = HandlerGroupType
         self.handler_state_type = HandlerStateGroupType
 
+    def tearDown(self):
+        super().tearDown()
+        self.sm_comp_patcher.__exit__(None, None, None)
+
+    def create_detector_and_conditions(self, type: str | None = None):
+        if type is None:
+            type = "handler_with_state"
+        detector = self.create_detector(
+            workflow_condition_group=self.create_data_condition_group(),
+            type=type,
+        )
+        self.create_data_condition(
+            condition="gt",
+            comparison=5,
+            condition_result=DetectorPriorityLevel.HIGH,
+            condition_group=detector.workflow_condition_group,
+        )
+        return detector
+
+    def build_handler(
+        self, detector: Detector | None = None, detector_type=None
+    ) -> MockDetectorStateHandler:
+        if detector is None:
+            detector = self.create_detector_and_conditions(detector_type)
+        return MockDetectorStateHandler(detector)
+
+    def assert_updates(self, handler, group_key, dedupe_value, counter_updates, active, priority):
+        if dedupe_value is not None:
+            assert handler.dedupe_updates.get(group_key) == dedupe_value
+        else:
+            assert group_key not in handler.dedupe_updates
+        if counter_updates is not None:
+            assert handler.counter_updates.get(group_key) == counter_updates
+        else:
+            assert group_key not in handler.counter_updates
+        if active is not None or priority is not None:
+            assert handler.state_updates.get(group_key) == (active, priority)
+        else:
+            assert group_key not in handler.state_updates
+
+
+@freeze_time()
+class TestProcessDetectors(BaseDetectorHandlerTest):
+    def setUp(self):
+        super().setUp()
+
     def build_data_packet(self, **kwargs):
         query_id = "1234"
-        return DataPacket[dict](query_id, {"query_id": query_id, "some": "data", **kwargs})
+        return DataPacket[dict](
+            query_id, {"query_id": query_id, "group_vals": {"group_1": 6}, **kwargs}
+        )
 
     def test(self):
         detector = self.create_detector(type=self.handler_type.slug)
@@ -73,64 +138,88 @@ class TestProcessDetectors(BaseGroupTypeTest):
         assert results == [
             (
                 detector,
-                [DetectorEvaluationResult(None, True, DetectorPriorityLevel.HIGH)],
+                {None: DetectorEvaluationResult(None, True, DetectorPriorityLevel.HIGH)},
             )
         ]
 
-    def test_state_results(self):
-        detector = self.create_detector(type=self.handler_state_type.slug)
-        data_packet = self.build_data_packet()
+    @mock.patch("sentry.workflow_engine.processors.detector.produce_occurrence_to_kafka")
+    def test_state_results(self, mock_produce_occurrence_to_kafka):
+        detector = self.create_detector_and_conditions(type=self.handler_state_type.slug)
+        data_packet = DataPacket("1", {"dedupe": 2, "group_vals": {None: 6}})
         results = process_detectors(data_packet, [detector])
+        occurrence, event_data = build_mock_occurrence_and_event(
+            detector.detector_handler, None, 6, PriorityLevel.HIGH
+        )
+
         result = DetectorEvaluationResult(
             None,
             True,
             DetectorPriorityLevel.HIGH,
+            occurrence,
+            event_data,
         )
         assert results == [
             (
                 detector,
-                [result],
+                {result.group_key: result},
             )
         ]
+        mock_produce_occurrence_to_kafka.assert_called_once_with(
+            payload_type=PayloadType.OCCURRENCE,
+            occurrence=occurrence,
+            status_change=None,
+            event_data=event_data,
+        )
 
-    def test_state_results_multi_group(self):
-        detector = self.create_detector(type=self.handler_state_type.slug)
-        data_packet = self.build_data_packet(group_keys=["group_1", "group_2"])
+    @mock.patch("sentry.workflow_engine.processors.detector.produce_occurrence_to_kafka")
+    def test_state_results_multi_group(self, mock_produce_occurrence_to_kafka):
+        detector = self.create_detector_and_conditions(type=self.handler_state_type.slug)
+        data_packet = DataPacket("1", {"dedupe": 2, "group_vals": {"group_1": 6, "group_2": 10}})
         results = process_detectors(data_packet, [detector])
+        occurrence, event_data = build_mock_occurrence_and_event(
+            detector.detector_handler, "group_1", 6, PriorityLevel.HIGH
+        )
+
         result_1 = DetectorEvaluationResult(
             "group_1",
             True,
             DetectorPriorityLevel.HIGH,
+            occurrence,
+            event_data,
+        )
+        occurrence_2, event_data_2 = build_mock_occurrence_and_event(
+            detector.detector_handler, "group_2", 6, PriorityLevel.HIGH
         )
         result_2 = DetectorEvaluationResult(
             "group_2",
             True,
             DetectorPriorityLevel.HIGH,
+            occurrence_2,
+            event_data_2,
         )
         assert results == [
             (
                 detector,
-                [result_1, result_2],
+                {result_1.group_key: result_1, result_2.group_key: result_2},
             )
         ]
-
-    def test_state_results_multi_group_dupe(self):
-        detector = self.create_detector(type=self.handler_state_type.slug)
-        data_packet = self.build_data_packet(group_keys=["dupe", "dupe"])
-        with mock.patch("sentry.workflow_engine.processors.detector.logger") as mock_logger:
-            results = process_detectors(data_packet, [detector])
-            assert mock_logger.error.call_args[0][0] == "Duplicate detector state group keys found"
-        result = DetectorEvaluationResult(
-            "dupe",
-            True,
-            DetectorPriorityLevel.HIGH,
+        mock_produce_occurrence_to_kafka.assert_has_calls(
+            [
+                call(
+                    payload_type=PayloadType.OCCURRENCE,
+                    occurrence=occurrence,
+                    status_change=None,
+                    event_data=event_data,
+                ),
+                call(
+                    payload_type=PayloadType.OCCURRENCE,
+                    occurrence=occurrence_2,
+                    status_change=None,
+                    event_data=event_data_2,
+                ),
+            ],
+            any_order=True,
         )
-        assert results == [
-            (
-                detector,
-                [result, result],
-            )
-        ]
 
     def test_no_issue_type(self):
         detector = self.create_detector(type="invalid slug")
@@ -152,14 +241,38 @@ class TestProcessDetectors(BaseGroupTypeTest):
         assert results == []
 
 
-class MockDetectorStateHandler(StatefulDetectorHandler[dict]):
-    counter_names = ["test1", "test2"]
-
-    def get_dedupe_value(self, data_packet: DataPacket[dict]) -> int:
-        return data_packet.packet.get("dedupe", 0)
-
-    def get_group_key_values(self, data_packet: DataPacket[dict]) -> dict[str, int]:
-        return data_packet.packet.get("group_vals", {})
+def build_mock_occurrence_and_event(
+    handler: StatefulDetectorHandler,
+    group_key: DetectorGroupKey,
+    value: int,
+    new_status: PriorityLevel,
+) -> tuple[IssueOccurrence, dict[str, Any]]:
+    assert handler.detector.group_type is not None
+    occurrence = IssueOccurrence(
+        id="eb4b0acffadb4d098d48cb14165ab578",
+        project_id=handler.detector.project_id,
+        event_id="43878ab4419f4ab181f6379ac376d5aa",
+        fingerprint=handler.build_fingerprint(group_key),
+        issue_title="Some Issue",
+        subtitle="Some subtitle",
+        resource_id=None,
+        evidence_data={},
+        evidence_display=[],
+        type=handler.detector.group_type,
+        detection_time=datetime.now(timezone.utc),
+        level="error",
+        culprit="Some culprit",
+        initial_issue_priority=new_status.value,
+    )
+    event_data = {
+        "timestamp": occurrence.detection_time,
+        "project_id": occurrence.project_id,
+        "event_id": occurrence.event_id,
+        "platform": "python",
+        "received": occurrence.detection_time,
+        "tags": {},
+    }
+    return occurrence, event_data
 
 
 class TestKeyBuilders(unittest.TestCase):
@@ -211,49 +324,7 @@ def status_change_comparator(self: StatusChangeMessage, other: StatusChangeMessa
     )
 
 
-class StatefulDetectorHandlerTestMixin(TestCase):
-    __test__ = Abstract(__module__, __qualname__)
-
-    def setUp(self):
-        super().setUp()
-        self.sm_comp_patcher = mock.patch.object(
-            StatusChangeMessage, "__eq__", status_change_comparator
-        )
-        self.sm_comp_patcher.__enter__()
-
-    def tearDown(self):
-        super().tearDown()
-        self.sm_comp_patcher.__exit__(None, None, None)
-
-    def build_handler(self, detector: Detector | None = None) -> MockDetectorStateHandler:
-        if detector is None:
-            detector = self.create_detector(
-                workflow_condition_group=self.create_data_condition_group()
-            )
-            self.create_data_condition(
-                condition="gt",
-                comparison=5,
-                condition_result=DetectorPriorityLevel.HIGH,
-                condition_group=detector.workflow_condition_group,
-            )
-        return MockDetectorStateHandler(detector)
-
-    def assert_updates(self, handler, group_key, dedupe_value, counter_updates, active, priority):
-        if dedupe_value is not None:
-            assert handler.dedupe_updates.get(group_key) == dedupe_value
-        else:
-            assert group_key not in handler.dedupe_updates
-        if counter_updates is not None:
-            assert handler.counter_updates.get(group_key) == counter_updates
-        else:
-            assert group_key not in handler.counter_updates
-        if active is not None or priority is not None:
-            assert handler.state_updates.get(group_key) == (active, priority)
-        else:
-            assert group_key not in handler.state_updates
-
-
-class TestGetStateData(StatefulDetectorHandlerTestMixin):
+class TestGetStateData(BaseDetectorHandlerTest):
     def test_new(self):
         handler = self.build_handler()
         key = "test_key"
@@ -305,7 +376,7 @@ class TestGetStateData(StatefulDetectorHandlerTestMixin):
         }
 
 
-class TestCommitStateUpdateData(StatefulDetectorHandlerTestMixin):
+class TestCommitStateUpdateData(BaseDetectorHandlerTest):
     def test(self):
         handler = self.build_handler()
         redis = get_redis_client()
@@ -348,35 +419,46 @@ class TestCommitStateUpdateData(StatefulDetectorHandlerTestMixin):
         assert redis.get(counter_key_2) == "20"
 
 
-class TestEvaluate(StatefulDetectorHandlerTestMixin):
+@freeze_time()
+class TestEvaluate(BaseDetectorHandlerTest):
     def test(self):
         handler = self.build_handler()
-        assert handler.evaluate(DataPacket("1", {"dedupe": 1})) == []
-        assert handler.evaluate(DataPacket("1", {"dedupe": 2, "group_vals": {"val1": 6}})) == [
-            DetectorEvaluationResult(
+        assert handler.evaluate(DataPacket("1", {"dedupe": 1})) == {}
+        occurrence, event_data = build_mock_occurrence_and_event(
+            handler, "val1", 6, PriorityLevel.HIGH
+        )
+        assert handler.evaluate(DataPacket("1", {"dedupe": 2, "group_vals": {"val1": 6}})) == {
+            "val1": DetectorEvaluationResult(
                 group_key="val1",
                 is_active=True,
                 priority=DetectorPriorityLevel.HIGH,
+                result=occurrence,
+                event_data=event_data,
             )
-        ]
+        }
         self.assert_updates(handler, "val1", 2, {}, True, DetectorPriorityLevel.HIGH)
 
     def test_above_below_threshold(self):
         handler = self.build_handler()
-        assert handler.evaluate(DataPacket("1", {"dedupe": 1, "group_vals": {"val1": 0}})) == []
+        assert handler.evaluate(DataPacket("1", {"dedupe": 1, "group_vals": {"val1": 0}})) == {}
         handler.commit_state_updates()
-        assert handler.evaluate(DataPacket("1", {"dedupe": 2, "group_vals": {"val1": 6}})) == [
-            DetectorEvaluationResult(
+        occurrence, event_data = build_mock_occurrence_and_event(
+            handler, "val1", 6, PriorityLevel.HIGH
+        )
+        assert handler.evaluate(DataPacket("1", {"dedupe": 2, "group_vals": {"val1": 6}})) == {
+            "val1": DetectorEvaluationResult(
                 group_key="val1",
                 is_active=True,
                 priority=DetectorPriorityLevel.HIGH,
+                result=occurrence,
+                event_data=event_data,
             )
-        ]
+        }
         handler.commit_state_updates()
-        assert handler.evaluate(DataPacket("1", {"dedupe": 3, "group_vals": {"val1": 6}})) == []
+        assert handler.evaluate(DataPacket("1", {"dedupe": 3, "group_vals": {"val1": 6}})) == {}
         handler.commit_state_updates()
-        assert handler.evaluate(DataPacket("1", {"dedupe": 4, "group_vals": {"val1": 0}})) == [
-            DetectorEvaluationResult(
+        assert handler.evaluate(DataPacket("1", {"dedupe": 4, "group_vals": {"val1": 0}})) == {
+            "val1": DetectorEvaluationResult(
                 group_key="val1",
                 is_active=False,
                 result=StatusChangeMessage(
@@ -387,14 +469,14 @@ class TestEvaluate(StatefulDetectorHandlerTestMixin):
                 ),
                 priority=DetectorPriorityLevel.OK,
             )
-        ]
+        }
 
     def test_no_condition_group(self):
         detector = self.create_detector()
         handler = MockDetectorStateHandler(detector)
         with mock.patch("sentry.workflow_engine.processors.detector.metrics") as mock_metrics:
             assert (
-                handler.evaluate(DataPacket("1", {"dedupe": 2, "group_vals": {"val1": 100}})) == []
+                handler.evaluate(DataPacket("1", {"dedupe": 2, "group_vals": {"val1": 100}})) == {}
             )
             mock_metrics.incr.assert_called_once_with(
                 "workflow_engine.detector.skipping_invalid_condition_group"
@@ -404,46 +486,62 @@ class TestEvaluate(StatefulDetectorHandlerTestMixin):
     def test_results_on_change(self):
         handler = self.build_handler()
         result = handler.evaluate(DataPacket("1", {"dedupe": 2, "group_vals": {"val1": 100}}))
-        assert result == [
-            DetectorEvaluationResult(
+        occurrence, event_data = build_mock_occurrence_and_event(
+            handler, "val1", 6, PriorityLevel.HIGH
+        )
+        assert result == {
+            "val1": DetectorEvaluationResult(
                 group_key="val1",
                 is_active=True,
                 priority=DetectorPriorityLevel.HIGH,
+                result=occurrence,
+                event_data=event_data,
             )
-        ]
+        }
         self.assert_updates(handler, "val1", 2, {}, True, DetectorPriorityLevel.HIGH)
         handler.commit_state_updates()
         # This detector is already active, so no status change occurred. Should be no result
-        assert handler.evaluate(DataPacket("1", {"dedupe": 3, "group_vals": {"val1": 200}})) == []
+        assert handler.evaluate(DataPacket("1", {"dedupe": 3, "group_vals": {"val1": 200}})) == {}
 
     def test_dedupe(self):
         handler = self.build_handler()
         result = handler.evaluate(DataPacket("1", {"dedupe": 2, "group_vals": {"val1": 8}}))
-        assert result == [
-            DetectorEvaluationResult(
+        occurrence, event_data = build_mock_occurrence_and_event(
+            handler, "val1", 6, PriorityLevel.HIGH
+        )
+        assert result == {
+            "val1": DetectorEvaluationResult(
                 group_key="val1",
                 is_active=True,
                 priority=DetectorPriorityLevel.HIGH,
+                result=occurrence,
+                event_data=event_data,
             )
-        ]
+        }
         self.assert_updates(handler, "val1", 2, {}, True, DetectorPriorityLevel.HIGH)
         handler.commit_state_updates()
         with mock.patch("sentry.workflow_engine.processors.detector.metrics") as mock_metrics:
-            assert handler.evaluate(DataPacket("1", {"dedupe": 2, "group_vals": {"val1": 0}})) == []
+            assert handler.evaluate(DataPacket("1", {"dedupe": 2, "group_vals": {"val1": 0}})) == {}
             mock_metrics.incr.assert_called_once_with(
                 "workflow_engine.detector.skipping_already_processed_update"
             )
         self.assert_updates(handler, "val1", None, None, None, None)
 
 
-class TestEvaluateGroupKeyValue(StatefulDetectorHandlerTestMixin):
+@freeze_time()
+class TestEvaluateGroupKeyValue(BaseDetectorHandlerTest):
     def test_dedupe(self):
         handler = self.build_handler()
         with mock.patch("sentry.workflow_engine.processors.detector.metrics") as mock_metrics:
+            occurrence, event_data = build_mock_occurrence_and_event(
+                handler, "val1", 6, PriorityLevel.HIGH
+            )
             expected_result = DetectorEvaluationResult(
                 "group_key",
                 True,
                 DetectorPriorityLevel.HIGH,
+                result=occurrence,
+                event_data=event_data,
             )
             assert (
                 handler.evaluate_group_key_value(

</diff>

## 2. Changed Code (Modified Files with Context)

<file name="src/sentry/incidents/grouptype.py" lines="7-12" type="changed">
```python
   3  from sentry.incidents.utils.types import QuerySubscriptionUpdate
   4  from sentry.issues.grouptype import GroupCategory, GroupType
   5  from sentry.ratelimits.sliding_windows import Quota
   6  from sentry.types.group import PriorityLevel
   7  from sentry.workflow_engine.processors.detector import StatefulDetectorHandler
   8  
   9  
  10  # TODO: This will be a stateful detector when we build that abstraction
  11  class MetricAlertDetectorHandler(StatefulDetectorHandler[QuerySubscriptionUpdate]):
  12      pass
  13  
  14  
  15  # Example GroupType and detector handler for metric alerts. We don't create these issues yet, but we'll use something
  16  # like these when we're sending issues as alerts
  17  @dataclass(frozen=True)
  18  class MetricAlertFire(GroupType):
  19      type_id = 8001
```
</file>

<file name="src/sentry/workflow_engine/models/detector.py" lines="3-3" type="changed">
```python
   1  from __future__ import annotations
   2  
   3  import builtins
   4  import logging
   5  from typing import TYPE_CHECKING
   6  
   7  from django.db import models
   8  from django.db.models import UniqueConstraint
   9  
  10  from sentry.backup.scopes import RelocationScope
  11  from sentry.db.models import DefaultFieldsModel, FlexibleForeignKey, region_silo_model
```
</file>

<file name="src/sentry/workflow_engine/models/detector.py" lines="13-13" type="changed">
```python
   5  from typing import TYPE_CHECKING
   6  
   7  from django.db import models
   8  from django.db.models import UniqueConstraint
   9  
  10  from sentry.backup.scopes import RelocationScope
  11  from sentry.db.models import DefaultFieldsModel, FlexibleForeignKey, region_silo_model
  12  from sentry.issues import grouptype
  13  from sentry.issues.grouptype import GroupType
  14  from sentry.models.owner_base import OwnerModel
  15  
  16  if TYPE_CHECKING:
  17      from sentry.workflow_engine.processors.detector import DetectorHandler
  18  
  19  logger = logging.getLogger(__name__)
  20  
  21  
```
</file>

<file name="src/sentry/workflow_engine/models/detector.py" lines="58-64" type="changed">
```python
  52  
  53      @property
  54      def project_id(self):
  55          # XXX: Temporary property until we add `project_id` to the model.
  56          return 1
  57  
  58      @property
  59      def group_type(self) -> builtins.type[GroupType] | None:
  60          return grouptype.registry.get_by_slug(self.type)
  61  
  62      @property
  63      def detector_handler(self) -> DetectorHandler | None:
  64          group_type = self.group_type
  65          if not group_type:
  66              logger.error(
  67                  "No registered grouptype for detector",
  68                  extra={
```
</file>

<file name="src/sentry/workflow_engine/processors/detector.py" lines="17-17" type="changed">
```python
   9  from django.conf import settings
  10  from django.db.models import Q
  11  from sentry_redis_tools.retrying_cluster import RetryingRedisCluster
  12  
  13  from sentry.issues.issue_occurrence import IssueOccurrence
  14  from sentry.issues.producer import PayloadType, produce_occurrence_to_kafka
  15  from sentry.issues.status_change_message import StatusChangeMessage
  16  from sentry.models.group import GroupStatus
  17  from sentry.types.group import PriorityLevel
  18  from sentry.utils import metrics, redis
  19  from sentry.utils.function_cache import cache_func_for_models
  20  from sentry.utils.iterators import chunked
  21  from sentry.workflow_engine.models import (
  22      DataCondition,
  23      DataConditionGroup,
  24      DataPacket,
  25      Detector,
```
</file>

<file name="src/sentry/workflow_engine/processors/detector.py" lines="49-49" type="changed">
```python
  41      # TODO: This is only temporarily optional. We should always have a value here if returning a result
  42      result: IssueOccurrence | StatusChangeMessage | None = None
  43      # Event data to supplement the `IssueOccurrence`, if passed.
  44      event_data: dict[str, Any] | None = None
  45  
  46  
  47  def process_detectors(
  48      data_packet: DataPacket, detectors: list[Detector]
  49  ) -> list[tuple[Detector, dict[DetectorGroupKey, DetectorEvaluationResult]]]:
  50      results = []
  51  
  52      for detector in detectors:
  53          handler = detector.detector_handler
  54  
  55          if not handler:
  56              continue
  57  
```
</file>

<file name="src/sentry/workflow_engine/processors/detector.py" lines="58-63" type="changed">
```python
  52      for detector in detectors:
  53          handler = detector.detector_handler
  54  
  55          if not handler:
  56              continue
  57  
  58          detector_results = handler.evaluate(data_packet)
  59  
  60          for result in detector_results.values():
  61              if result.result is not None:
  62                  create_issue_occurrence_from_result(result)
  63  
  64          if detector_results:
  65              results.append((detector, detector_results))
  66  
  67          # Now that we've processed all results for this detector, commit any state changes
  68          handler.commit_state_updates()
```
</file>

<file name="src/sentry/workflow_engine/processors/detector.py" lines="126-128" type="changed">
```python
 119              self.condition_group: DataConditionGroup | None = results[0]
 120              self.conditions: list[DataCondition] = results[1]
 121          else:
 122              self.condition_group = None
 123              self.conditions = []
 124  
 125      @abc.abstractmethod
 126      def evaluate(
 127          self, data_packet: DataPacket[T]
 128      ) -> dict[DetectorGroupKey, DetectorEvaluationResult]:
 129          pass
 130  
 131      def commit_state_updates(self):
 132          pass
 133  
 134  
 135  class StatefulDetectorHandler(DetectorHandler[T], abc.ABC):
```
</file>

<file name="src/sentry/workflow_engine/processors/detector.py" lines="166-171" type="changed">
```python
 161          Extracts the values for all the group keys that exist in the given data packet,
 162          and returns then as a dict keyed by group_key.
 163          """
 164          pass
 165  
 166      @abc.abstractmethod
 167      def build_occurrence_and_event_data(
 168          self, group_key: DetectorGroupKey, value: int, new_status: PriorityLevel
 169      ) -> tuple[IssueOccurrence, dict[str, Any]]:
 170          pass
 171  
 172      def build_fingerprint(self, group_key) -> list[str]:
 173          """
 174          Builds a fingerprint to uniquely identify a detected issue
 175          """
 176          return [f"{self.detector.id}{':' + group_key if group_key is not None else ''}"]
 177  
```
</file>

<file name="src/sentry/workflow_engine/processors/detector.py" lines="226-228" type="changed">
```python
 219                      else DetectorPriorityLevel.OK
 220                  ),
 221                  dedupe_value=group_key_dedupe_values[gk],
 222                  counter_updates=counter_updates[gk],
 223              )
 224          return results
 225  
 226      def evaluate(
 227          self, data_packet: DataPacket[T]
 228      ) -> dict[DetectorGroupKey, DetectorEvaluationResult]:
 229          """
 230          Evaluates a given data packet and returns a list of `DetectorEvaluationResult`.
 231          There will be one result for each group key result in the packet, unless the
 232          evaluation is skipped due to various rules.
 233          """
 234          dedupe_value = self.get_dedupe_value(data_packet)
 235          group_values = self.get_group_key_values(data_packet)
```
</file>

<file name="src/sentry/workflow_engine/processors/detector.py" lines="237-237" type="changed">
```python
 229          """
 230          Evaluates a given data packet and returns a list of `DetectorEvaluationResult`.
 231          There will be one result for each group key result in the packet, unless the
 232          evaluation is skipped due to various rules.
 233          """
 234          dedupe_value = self.get_dedupe_value(data_packet)
 235          group_values = self.get_group_key_values(data_packet)
 236          all_state_data = self.get_state_data(list(group_values.keys()))
 237          results = {}
 238          for group_key, group_value in group_values.items():
 239              result = self.evaluate_group_key_value(
 240                  group_key, group_value, all_state_data[group_key], dedupe_value
 241              )
 242              if result:
 243                  results[result.group_key] = result
 244          return results
 245  
```
</file>

<file name="src/sentry/workflow_engine/processors/detector.py" lines="243-243" type="changed">
```python
 235          group_values = self.get_group_key_values(data_packet)
 236          all_state_data = self.get_state_data(list(group_values.keys()))
 237          results = {}
 238          for group_key, group_value in group_values.items():
 239              result = self.evaluate_group_key_value(
 240                  group_key, group_value, all_state_data[group_key], dedupe_value
 241              )
 242              if result:
 243                  results[result.group_key] = result
 244          return results
 245  
 246      def evaluate_group_key_value(
 247          self,
 248          group_key: DetectorGroupKey,
 249          value: int,
 250          state_data: DetectorStateData,
 251          dedupe_value: int,
```
</file>

<file name="src/sentry/workflow_engine/processors/detector.py" lines="289-289" type="changed">
```python
 281  
 282          # TODO: We'll increment and change these later, but for now they don't change so just pass an empty dict
 283          self.enqueue_counter_update(group_key, {})
 284  
 285          if state_data.status != new_status:
 286              is_active = new_status != DetectorPriorityLevel.OK
 287              self.enqueue_state_update(group_key, is_active, new_status)
 288              event_data = None
 289              result: StatusChangeMessage | IssueOccurrence
 290              if new_status == DetectorPriorityLevel.OK:
 291                  # If we've determined that we're now ok, we just want to resolve the issue
 292                  result = StatusChangeMessage(
 293                      fingerprint=self.build_fingerprint(group_key),
 294                      project_id=self.detector.project_id,
 295                      new_status=GroupStatus.RESOLVED,
 296                      new_substatus=None,
 297                  )
```
</file>

<file name="src/sentry/workflow_engine/processors/detector.py" lines="298-301" type="changed">
```python
 292                  result = StatusChangeMessage(
 293                      fingerprint=self.build_fingerprint(group_key),
 294                      project_id=self.detector.project_id,
 295                      new_status=GroupStatus.RESOLVED,
 296                      new_substatus=None,
 297                  )
 298              else:
 299                  result, event_data = self.build_occurrence_and_event_data(
 300                      group_key, value, PriorityLevel(new_status)
 301                  )
 302              return DetectorEvaluationResult(
 303                  group_key=group_key,
 304                  is_active=is_active,
 305                  priority=new_status,
 306                  result=result,
 307                  event_data=event_data,
 308              )
```
</file>

<file name="tests/sentry/workflow_engine/processors/test_detector.py" lines="2-13" type="changed">
```python
   1  import unittest
   2  from datetime import datetime, timezone
   3  from typing import Any
   4  from unittest import mock
   5  from unittest.mock import call
   6  
   7  from sentry.issues.grouptype import GroupCategory, GroupType
   8  from sentry.issues.issue_occurrence import IssueOccurrence
   9  from sentry.issues.producer import PayloadType
  10  from sentry.issues.status_change_message import StatusChangeMessage
  11  from sentry.testutils.abstract import Abstract
  12  from sentry.testutils.helpers.datetime import freeze_time
  13  from sentry.types.group import PriorityLevel
  14  from sentry.workflow_engine.models import DataPacket, Detector, DetectorState
  15  from sentry.workflow_engine.processors.detector import (
  16      DetectorEvaluationResult,
```
</file>

<file name="tests/sentry/workflow_engine/processors/test_detector.py" lines="23-50" type="changed">
```python
  29  
  30      def get_dedupe_value(self, data_packet: DataPacket[dict]) -> int:
  31          return data_packet.packet.get("dedupe", 0)
  32  
  33      def get_group_key_values(self, data_packet: DataPacket[dict]) -> dict[str, int]:
  34          return data_packet.packet.get("group_vals", {})
  35  
  36      def build_occurrence_and_event_data(
  37          self, group_key: DetectorGroupKey, value: int, new_status: PriorityLevel
  38      ) -> tuple[IssueOccurrence, dict[str, Any]]:
  39          return build_mock_occurrence_and_event(self, group_key, value, new_status)
  40  
  41  
  42  class BaseDetectorHandlerTest(BaseGroupTypeTest):
  43      __test__ = Abstract(__module__, __qualname__)
  44  
  45      def setUp(self):
```
</file>

<file name="tests/sentry/workflow_engine/processors/test_detector.py" lines="59-62" type="changed">
```python
  53              type_id = 1
  54              slug = "no_handler"
  55              description = "no handler"
  56              category = GroupCategory.METRIC_ALERT.value
  57  
  58          class MockDetectorHandler(DetectorHandler[dict]):
  59              def evaluate(
  60                  self, data_packet: DataPacket[dict]
  61              ) -> dict[DetectorGroupKey, DetectorEvaluationResult]:
  62                  return {None: DetectorEvaluationResult(None, True, DetectorPriorityLevel.HIGH)}
  63  
  64          class HandlerGroupType(GroupType):
  65              type_id = 2
  66              slug = "handler"
  67              description = "handler"
  68              category = GroupCategory.METRIC_ALERT.value
  69              detector_handler = MockDetectorHandler
```
</file>

<file name="tests/sentry/workflow_engine/processors/test_detector.py" lines="70-70" type="changed">
```python
  62                  return {None: DetectorEvaluationResult(None, True, DetectorPriorityLevel.HIGH)}
  63  
  64          class HandlerGroupType(GroupType):
  65              type_id = 2
  66              slug = "handler"
  67              description = "handler"
  68              category = GroupCategory.METRIC_ALERT.value
  69              detector_handler = MockDetectorHandler
  70  
  71          class HandlerStateGroupType(GroupType):
  72              type_id = 3
  73              slug = "handler_with_state"
  74              description = "handler with state"
  75              category = GroupCategory.METRIC_ALERT.value
  76              detector_handler = MockDetectorStateHandler
  77  
  78          self.no_handler_type = NoHandlerGroupType
```
</file>

<file name="tests/sentry/workflow_engine/processors/test_detector.py" lines="82-132" type="changed">
```python
  98          )
  99          return detector
 100  
 101      def build_handler(
 102          self, detector: Detector | None = None, detector_type=None
 103      ) -> MockDetectorStateHandler:
 104          if detector is None:
 105              detector = self.create_detector_and_conditions(detector_type)
 106          return MockDetectorStateHandler(detector)
 107  
 108      def assert_updates(self, handler, group_key, dedupe_value, counter_updates, active, priority):
 109          if dedupe_value is not None:
 110              assert handler.dedupe_updates.get(group_key) == dedupe_value
 111          else:
 112              assert group_key not in handler.dedupe_updates
 113          if counter_updates is not None:
 114              assert handler.counter_updates.get(group_key) == counter_updates
```
</file>

<file name="tests/sentry/workflow_engine/processors/test_detector.py" lines="141-191" type="changed">
```python
 162              (
 163                  detector,
 164                  {result.group_key: result},
 165              )
 166          ]
 167          mock_produce_occurrence_to_kafka.assert_called_once_with(
 168              payload_type=PayloadType.OCCURRENCE,
 169              occurrence=occurrence,
 170              status_change=None,
 171              event_data=event_data,
 172          )
 173  
 174      @mock.patch("sentry.workflow_engine.processors.detector.produce_occurrence_to_kafka")
 175      def test_state_results_multi_group(self, mock_produce_occurrence_to_kafka):
 176          detector = self.create_detector_and_conditions(type=self.handler_state_type.slug)
 177          data_packet = DataPacket("1", {"dedupe": 2, "group_vals": {"group_1": 6, "group_2": 10}})
 178          results = process_detectors(data_packet, [detector])
```
</file>

<file name="tests/sentry/workflow_engine/processors/test_detector.py" lines="197-222" type="changed">
```python
 205          ]
 206          mock_produce_occurrence_to_kafka.assert_has_calls(
 207              [
 208                  call(
 209                      payload_type=PayloadType.OCCURRENCE,
 210                      occurrence=occurrence,
 211                      status_change=None,
 212                      event_data=event_data,
 213                  ),
 214                  call(
 215                      payload_type=PayloadType.OCCURRENCE,
 216                      occurrence=occurrence_2,
 217                      status_change=None,
 218                      event_data=event_data_2,
 219                  ),
 220              ],
 221              any_order=True,
```
</file>

<file name="tests/sentry/workflow_engine/processors/test_detector.py" lines="244-275" type="changed">
```python
 252          id="eb4b0acffadb4d098d48cb14165ab578",
 253          project_id=handler.detector.project_id,
 254          event_id="43878ab4419f4ab181f6379ac376d5aa",
 255          fingerprint=handler.build_fingerprint(group_key),
 256          issue_title="Some Issue",
 257          subtitle="Some subtitle",
 258          resource_id=None,
 259          evidence_data={},
 260          evidence_display=[],
 261          type=handler.detector.group_type,
 262          detection_time=datetime.now(timezone.utc),
 263          level="error",
 264          culprit="Some culprit",
 265          initial_issue_priority=new_status.value,
 266      )
 267      event_data = {
 268          "timestamp": occurrence.detection_time,
```
</file>

<file name="tests/sentry/workflow_engine/processors/test_detector.py" lines="327-327" type="changed">
```python
 319          isinstance(other, StatusChangeMessage)
 320          and self.fingerprint == other.fingerprint
 321          and self.project_id == other.project_id
 322          and self.new_status == other.new_status
 323          and self.new_substatus == other.new_substatus
 324      )
 325  
 326  
 327  class TestGetStateData(BaseDetectorHandlerTest):
 328      def test_new(self):
 329          handler = self.build_handler()
 330          key = "test_key"
 331          assert handler.get_state_data([key]) == {
 332              key: DetectorStateData(
 333                  key, False, DetectorPriorityLevel.OK, 0, {"test1": None, "test2": None}
 334              )
 335          }
```
</file>

<file name="tests/sentry/workflow_engine/processors/test_detector.py" lines="379-379" type="changed">
```python
 371          handler.commit_state_updates()
 372          assert handler.get_state_data([key_1, key_2, key_uncommitted]) == {
 373              key_1: state_data_1,
 374              key_2: state_data_2,
 375              key_uncommitted: state_data_uncommitted,
 376          }
 377  
 378  
 379  class TestCommitStateUpdateData(BaseDetectorHandlerTest):
 380      def test(self):
 381          handler = self.build_handler()
 382          redis = get_redis_client()
 383          group_key = None
 384          assert not DetectorState.objects.filter(
 385              detector=handler.detector, detector_group_key=group_key
 386          ).exists()
 387          dedupe_key = handler.build_dedupe_value_key(group_key)
```
</file>

<file name="tests/sentry/workflow_engine/processors/test_detector.py" lines="422-461" type="changed">
```python
 435                  result=occurrence,
 436                  event_data=event_data,
 437              )
 438          }
 439          self.assert_updates(handler, "val1", 2, {}, True, DetectorPriorityLevel.HIGH)
 440  
 441      def test_above_below_threshold(self):
 442          handler = self.build_handler()
 443          assert handler.evaluate(DataPacket("1", {"dedupe": 1, "group_vals": {"val1": 0}})) == {}
 444          handler.commit_state_updates()
 445          occurrence, event_data = build_mock_occurrence_and_event(
 446              handler, "val1", 6, PriorityLevel.HIGH
 447          )
 448          assert handler.evaluate(DataPacket("1", {"dedupe": 2, "group_vals": {"val1": 6}})) == {
 449              "val1": DetectorEvaluationResult(
 450                  group_key="val1",
 451                  is_active=True,
```
</file>

<file name="tests/sentry/workflow_engine/processors/test_detector.py" lines="472-472" type="changed">
```python
 464                  result=StatusChangeMessage(
 465                      fingerprint=[f"{handler.detector.id}:val1"],
 466                      project_id=1,
 467                      new_status=1,
 468                      new_substatus=None,
 469                  ),
 470                  priority=DetectorPriorityLevel.OK,
 471              )
 472          }
 473  
 474      def test_no_condition_group(self):
 475          detector = self.create_detector()
 476          handler = MockDetectorStateHandler(detector)
 477          with mock.patch("sentry.workflow_engine.processors.detector.metrics") as mock_metrics:
 478              assert (
 479                  handler.evaluate(DataPacket("1", {"dedupe": 2, "group_vals": {"val1": 100}})) == {}
 480              )
```
</file>

<file name="tests/sentry/workflow_engine/processors/test_detector.py" lines="479-479" type="changed">
```python
 471              )
 472          }
 473  
 474      def test_no_condition_group(self):
 475          detector = self.create_detector()
 476          handler = MockDetectorStateHandler(detector)
 477          with mock.patch("sentry.workflow_engine.processors.detector.metrics") as mock_metrics:
 478              assert (
 479                  handler.evaluate(DataPacket("1", {"dedupe": 2, "group_vals": {"val1": 100}})) == {}
 480              )
 481              mock_metrics.incr.assert_called_once_with(
 482                  "workflow_engine.detector.skipping_invalid_condition_group"
 483              )
 484              self.assert_updates(handler, "val1", 2, None, None, None)
 485  
 486      def test_results_on_change(self):
 487          handler = self.build_handler()
```
</file>

<file name="tests/sentry/workflow_engine/processors/test_detector.py" lines="489-524" type="changed">
```python
 501          self.assert_updates(handler, "val1", 2, {}, True, DetectorPriorityLevel.HIGH)
 502          handler.commit_state_updates()
 503          # This detector is already active, so no status change occurred. Should be no result
 504          assert handler.evaluate(DataPacket("1", {"dedupe": 3, "group_vals": {"val1": 200}})) == {}
 505  
 506      def test_dedupe(self):
 507          handler = self.build_handler()
 508          result = handler.evaluate(DataPacket("1", {"dedupe": 2, "group_vals": {"val1": 8}}))
 509          occurrence, event_data = build_mock_occurrence_and_event(
 510              handler, "val1", 6, PriorityLevel.HIGH
 511          )
 512          assert result == {
 513              "val1": DetectorEvaluationResult(
 514                  group_key="val1",
 515                  is_active=True,
 516                  priority=DetectorPriorityLevel.HIGH,
 517                  result=occurrence,
```
</file>

<file name="tests/sentry/workflow_engine/processors/test_detector.py" lines="531-544" type="changed">
```python
 529  
 530  
 531  @freeze_time()
 532  class TestEvaluateGroupKeyValue(BaseDetectorHandlerTest):
 533      def test_dedupe(self):
 534          handler = self.build_handler()
 535          with mock.patch("sentry.workflow_engine.processors.detector.metrics") as mock_metrics:
 536              occurrence, event_data = build_mock_occurrence_and_event(
 537                  handler, "val1", 6, PriorityLevel.HIGH
 538              )
 539              expected_result = DetectorEvaluationResult(
 540                  "group_key",
 541                  True,
 542                  DetectorPriorityLevel.HIGH,
 543                  result=occurrence,
 544                  event_data=event_data,
 545              )
```
</file>

## 3. Impact Code (Contracts & Call Sites)

### CALLEES: Definitions that the changed code CALLS (check if changed code respects these contracts)
<callees>
<file name="src/sentry/workflow_engine/processors/detector.py" symbol="DetectorEvaluationResult">
```python
  23      DataConditionGroup,
  24      DataPacket,
  25      Detector,
  26      DetectorState,
  27  )
  28  from sentry.workflow_engine.types import DetectorGroupKey, DetectorPriorityLevel
  29  
  30  logger = logging.getLogger(__name__)
  31  REDIS_TTL = int(timedelta(days=7).total_seconds())
  32  
  33  
  34  @dataclasses.dataclass(frozen=True)
  35  class DetectorEvaluationResult:
  36      group_key: DetectorGroupKey
  37      # TODO: Are these actually necessary? We're going to produce the occurrence in the detector, so we probably don't
  38      # need to know the other results externally
  39      is_active: bool
  40      priority: DetectorPriorityLevel
  41      # TODO: This is only temporarily optional. We should always have a value here if returning a result
  42      result: IssueOccurrence | StatusChangeMessage | None = None
  43      # Event data to supplement the `IssueOccurrence`, if passed.
  44      event_data: dict[str, Any] | None = None
  45  
  46  
  47  def process_detectors(
```
</file>
</callees>

### CALLERS: Call sites that invoke the changed functions/classes (check if callers pass correct arguments)
<callers>
None
</callers>
