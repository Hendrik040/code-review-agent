# Code Review Context

## 1. Git Diff (What Changed)

<diff>
diff --git a/src/sentry/monitors/logic/incident_occurrence.py b/src/sentry/monitors/logic/incident_occurrence.py
new file mode 100644
index 0000000..a752381
--- /dev/null
+++ b/src/sentry/monitors/logic/incident_occurrence.py
@@ -0,0 +1,171 @@
+from __future__ import annotations
+
+import logging
+import uuid
+from collections import Counter
+from collections.abc import Mapping, Sequence
+from datetime import datetime, timezone
+from typing import TYPE_CHECKING
+
+from django.utils.text import get_text_list
+from django.utils.translation import gettext_lazy as _
+
+from sentry.issues.grouptype import MonitorIncidentType
+from sentry.monitors.models import (
+    CheckInStatus,
+    MonitorCheckIn,
+    MonitorEnvironment,
+    MonitorIncident,
+)
+from sentry.monitors.types import SimpleCheckIn
+
+if TYPE_CHECKING:
+    from django.utils.functional import _StrPromise
+
+logger = logging.getLogger(__name__)
+
+
+def create_incident_occurrence(
+    failed_checkins: Sequence[SimpleCheckIn],
+    failed_checkin: MonitorCheckIn,
+    incident: MonitorIncident,
+    received: datetime | None,
+) -> None:
+    from sentry.issues.issue_occurrence import IssueEvidence, IssueOccurrence
+    from sentry.issues.producer import PayloadType, produce_occurrence_to_kafka
+
+    monitor_env = failed_checkin.monitor_environment
+
+    if monitor_env is None:
+        return
+
+    current_timestamp = datetime.now(timezone.utc)
+
+    # Get last successful check-in to show in evidence display
+    last_successful_checkin_timestamp = "Never"
+    last_successful_checkin = monitor_env.get_last_successful_checkin()
+    if last_successful_checkin:
+        last_successful_checkin_timestamp = last_successful_checkin.date_added.isoformat()
+
+    occurrence = IssueOccurrence(
+        id=uuid.uuid4().hex,
+        resource_id=None,
+        project_id=monitor_env.monitor.project_id,
+        event_id=uuid.uuid4().hex,
+        fingerprint=[incident.grouphash],
+        type=MonitorIncidentType,
+        issue_title=f"Monitor failure: {monitor_env.monitor.name}",
+        subtitle="Your monitor has reached its failure threshold.",
+        evidence_display=[
+            IssueEvidence(
+                name="Failure reason",
+                value=str(get_failure_reason(failed_checkins)),
+                important=True,
+            ),
+            IssueEvidence(
+                name="Environment",
+                value=monitor_env.get_environment().name,
+                important=False,
+            ),
+            IssueEvidence(
+                name="Last successful check-in",
+                value=last_successful_checkin_timestamp,
+                important=False,
+            ),
+        ],
+        evidence_data={},
+        culprit="",
+        detection_time=current_timestamp,
+        level="error",
+        assignee=monitor_env.monitor.owner_actor,
+    )
+
+    if failed_checkin.trace_id:
+        trace_id = failed_checkin.trace_id.hex
+    else:
+        trace_id = None
+
+    event_data = {
+        "contexts": {"monitor": get_monitor_environment_context(monitor_env)},
+        "environment": monitor_env.get_environment().name,
+        "event_id": occurrence.event_id,
+        "fingerprint": [incident.grouphash],
+        "platform": "other",
+        "project_id": monitor_env.monitor.project_id,
+        # We set this to the time that the checkin that triggered the occurrence was written to relay if available
+        "received": (received if received else current_timestamp).isoformat(),
+        "sdk": None,
+        "tags": {
+            "monitor.id": str(monitor_env.monitor.guid),
+            "monitor.slug": str(monitor_env.monitor.slug),
+            "monitor.incident": str(incident.id),
+        },
+        "timestamp": current_timestamp.isoformat(),
+    }
+
+    if trace_id:
+        event_data["contexts"]["trace"] = {"trace_id": trace_id, "span_id": None}
+
+    produce_occurrence_to_kafka(
+        payload_type=PayloadType.OCCURRENCE,
+        occurrence=occurrence,
+        event_data=event_data,
+    )
+
+
+HUMAN_FAILURE_STATUS_MAP: Mapping[int, _StrPromise] = {
+    CheckInStatus.ERROR: _("error"),
+    CheckInStatus.MISSED: _("missed"),
+    CheckInStatus.TIMEOUT: _("timeout"),
+}
+
+# Exists due to the vowel differences (A vs An) in the statuses
+SINGULAR_HUMAN_FAILURE_MAP: Mapping[int, _StrPromise] = {
+    CheckInStatus.ERROR: _("An error check-in was detected"),
+    CheckInStatus.MISSED: _("A missed check-in was detected"),
+    CheckInStatus.TIMEOUT: _("A timeout check-in was detected"),
+}
+
+
+def get_failure_reason(failed_checkins: Sequence[SimpleCheckIn]):
+    """
+    Builds a humam readible string from a list of failed check-ins.
+
+    "3 missed check-ins detected"
+    "2 missed check-ins, 1 timeout check-in and 1 error check-in were detected"
+    "A failed check-in was detected"
+    """
+
+    status_counts = Counter(
+        checkin["status"]
+        for checkin in failed_checkins
+        if checkin["status"] in HUMAN_FAILURE_STATUS_MAP.keys()
+    )
+
+    if sum(status_counts.values()) == 1:
+        return SINGULAR_HUMAN_FAILURE_MAP[list(status_counts.keys())[0]]
+
+    human_status = get_text_list(
+        [
+            "%(count)d %(status)s" % {"count": count, "status": HUMAN_FAILURE_STATUS_MAP[status]}
+            for status, count in status_counts.items()
+        ],
+        last_word=_("and"),
+    )
+
+    return _("%(problem_checkins)s check-ins detected") % {"problem_checkins": human_status}
+
+
+def get_monitor_environment_context(monitor_environment: MonitorEnvironment):
+    config = monitor_environment.monitor.config.copy()
+    if "schedule_type" in config:
+        config["schedule_type"] = monitor_environment.monitor.get_schedule_type_display()
+
+    return {
+        "id": str(monitor_environment.monitor.guid),
+        "slug": str(monitor_environment.monitor.slug),
+        "name": monitor_environment.monitor.name,
+        "config": monitor_environment.monitor.config,
+        "status": monitor_environment.get_status_display(),
+        "type": monitor_environment.monitor.get_type_display(),
+    }
diff --git a/src/sentry/monitors/logic/incidents.py b/src/sentry/monitors/logic/incidents.py
new file mode 100644
index 0000000..374f87e
--- /dev/null
+++ b/src/sentry/monitors/logic/incidents.py
@@ -0,0 +1,104 @@
+from __future__ import annotations
+
+import logging
+from datetime import datetime
+from typing import cast
+
+from sentry.monitors.logic.incident_occurrence import create_incident_occurrence
+from sentry.monitors.models import CheckInStatus, MonitorCheckIn, MonitorIncident, MonitorStatus
+from sentry.monitors.types import SimpleCheckIn
+
+logger = logging.getLogger(__name__)
+
+
+def try_incident_threshold(
+    failed_checkin: MonitorCheckIn,
+    failure_issue_threshold: int,
+    received: datetime | None,
+) -> bool:
+    from sentry.signals import monitor_environment_failed
+
+    monitor_env = failed_checkin.monitor_environment
+
+    if monitor_env is None:
+        return False
+
+    # check to see if we need to update the status
+    if monitor_env.status in [MonitorStatus.OK, MonitorStatus.ACTIVE]:
+        if failure_issue_threshold == 1:
+            previous_checkins: list[SimpleCheckIn] = [
+                {
+                    "id": failed_checkin.id,
+                    "date_added": failed_checkin.date_added,
+                    "status": failed_checkin.status,
+                }
+            ]
+        else:
+            previous_checkins = cast(
+                list[SimpleCheckIn],
+                # Using .values for performance reasons
+                MonitorCheckIn.objects.filter(
+                    monitor_environment=monitor_env, date_added__lte=failed_checkin.date_added
+                )
+                .order_by("-date_added")
+                .values("id", "date_added", "status"),
+            )
+
+            # reverse the list after slicing in order to start with oldest check-in
+            previous_checkins = list(reversed(previous_checkins[:failure_issue_threshold]))
+
+            # If we have any successful check-ins within the threshold of
+            # commits we have NOT reached an incident state
+            if any([checkin["status"] == CheckInStatus.OK for checkin in previous_checkins]):
+                return False
+
+        # change monitor status + update fingerprint timestamp
+        monitor_env.status = MonitorStatus.ERROR
+        monitor_env.save(update_fields=("status",))
+
+        starting_checkin = previous_checkins[0]
+
+        incident: MonitorIncident | None
+        incident, _ = MonitorIncident.objects.get_or_create(
+            monitor_environment=monitor_env,
+            resolving_checkin=None,
+            defaults={
+                "monitor": monitor_env.monitor,
+                "starting_checkin_id": starting_checkin["id"],
+                "starting_timestamp": starting_checkin["date_added"],
+            },
+        )
+
+    elif monitor_env.status == MonitorStatus.ERROR:
+        # if monitor environment has a failed status, use the failed
+        # check-in and send occurrence
+        previous_checkins = [
+            {
+                "id": failed_checkin.id,
+                "date_added": failed_checkin.date_added,
+                "status": failed_checkin.status,
+            }
+        ]
+
+        # get the active incident from the monitor environment
+        incident = monitor_env.active_incident
+    else:
+        # don't send occurrence for other statuses
+        return False
+
+    # Only create an occurrence if:
+    # - We have an active incident and fingerprint
+    # - The monitor and env are not muted
+    if not monitor_env.monitor.is_muted and not monitor_env.is_muted and incident:
+        checkins = MonitorCheckIn.objects.filter(id__in=[c["id"] for c in previous_checkins])
+        for checkin in checkins:
+            create_incident_occurrence(
+                previous_checkins,
+                checkin,
+                incident,
+                received=received,
+            )
+
+    monitor_environment_failed.send(monitor_environment=monitor_env, sender=type(monitor_env))
+
+    return True
diff --git a/src/sentry/monitors/logic/mark_failed.py b/src/sentry/monitors/logic/mark_failed.py
index 5f6ad72..b873e2d 100644
--- a/src/sentry/monitors/logic/mark_failed.py
+++ b/src/sentry/monitors/logic/mark_failed.py
@@ -1,30 +1,15 @@
 from __future__ import annotations
 
 import logging
-import uuid
-from collections import Counter
-from collections.abc import Mapping, Sequence
-from datetime import datetime, timezone
-from typing import TYPE_CHECKING, TypedDict, cast
+from datetime import datetime
 
 from django.db.models import Q
-from django.utils.text import get_text_list
-from django.utils.translation import gettext_lazy as _
 
-from sentry.issues.grouptype import MonitorIncidentType
-from sentry.monitors.models import (
-    CheckInStatus,
-    MonitorCheckIn,
-    MonitorEnvironment,
-    MonitorIncident,
-    MonitorStatus,
-)
+from sentry.monitors.logic.incidents import try_incident_threshold
+from sentry.monitors.models import CheckInStatus, MonitorCheckIn, MonitorEnvironment
 
 logger = logging.getLogger(__name__)
 
-if TYPE_CHECKING:
-    from django.utils.functional import _StrPromise
-
 
 def mark_failed(
     failed_checkin: MonitorCheckIn,
@@ -91,258 +76,4 @@ def mark_failed(
     monitor_env.refresh_from_db()
 
     # Create incidents + issues
-    return mark_failed_threshold(failed_checkin, failure_issue_threshold, received)
-
-
-class SimpleCheckIn(TypedDict):
-    id: int
-    date_added: datetime
-    status: int
-
-
-def mark_failed_threshold(
-    failed_checkin: MonitorCheckIn,
-    failure_issue_threshold: int,
-    received: datetime | None,
-) -> bool:
-    from sentry.signals import monitor_environment_failed
-
-    monitor_env = failed_checkin.monitor_environment
-
-    if monitor_env is None:
-        return False
-
-    # check to see if we need to update the status
-    if monitor_env.status in [MonitorStatus.OK, MonitorStatus.ACTIVE]:
-        if failure_issue_threshold == 1:
-            previous_checkins: list[SimpleCheckIn] = [
-                {
-                    "id": failed_checkin.id,
-                    "date_added": failed_checkin.date_added,
-                    "status": failed_checkin.status,
-                }
-            ]
-        else:
-            previous_checkins = cast(
-                list[SimpleCheckIn],
-                # Using .values for performance reasons
-                MonitorCheckIn.objects.filter(
-                    monitor_environment=monitor_env, date_added__lte=failed_checkin.date_added
-                )
-                .order_by("-date_added")
-                .values("id", "date_added", "status"),
-            )
-
-            # reverse the list after slicing in order to start with oldest check-in
-            previous_checkins = list(reversed(previous_checkins[:failure_issue_threshold]))
-
-            # If we have any successful check-ins within the threshold of
-            # commits we have NOT reached an incident state
-            if any([checkin["status"] == CheckInStatus.OK for checkin in previous_checkins]):
-                return False
-
-        # change monitor status + update fingerprint timestamp
-        monitor_env.status = MonitorStatus.ERROR
-        monitor_env.save(update_fields=("status",))
-
-        starting_checkin = previous_checkins[0]
-
-        incident: MonitorIncident | None
-        incident, _ = MonitorIncident.objects.get_or_create(
-            monitor_environment=monitor_env,
-            resolving_checkin=None,
-            defaults={
-                "monitor": monitor_env.monitor,
-                "starting_checkin_id": starting_checkin["id"],
-                "starting_timestamp": starting_checkin["date_added"],
-            },
-        )
-
-    elif monitor_env.status == MonitorStatus.ERROR:
-        # if monitor environment has a failed status, use the failed
-        # check-in and send occurrence
-        previous_checkins = [
-            {
-                "id": failed_checkin.id,
-                "date_added": failed_checkin.date_added,
-                "status": failed_checkin.status,
-            }
-        ]
-
-        # get the active incident from the monitor environment
-        incident = monitor_env.active_incident
-    else:
-        # don't send occurrence for other statuses
-        return False
-
-    # Only create an occurrence if:
-    # - We have an active incident and fingerprint
-    # - The monitor and env are not muted
-    if not monitor_env.monitor.is_muted and not monitor_env.is_muted and incident:
-        checkins = MonitorCheckIn.objects.filter(id__in=[c["id"] for c in previous_checkins])
-        for checkin in checkins:
-            create_issue_platform_occurrence(
-                previous_checkins,
-                checkin,
-                incident,
-                received=received,
-            )
-
-    monitor_environment_failed.send(monitor_environment=monitor_env, sender=type(monitor_env))
-
-    return True
-
-
-def create_issue_platform_occurrence(
-    failed_checkins: Sequence[SimpleCheckIn],
-    failed_checkin: MonitorCheckIn,
-    incident: MonitorIncident,
-    received: datetime | None,
-) -> None:
-    from sentry.issues.issue_occurrence import IssueEvidence, IssueOccurrence
-    from sentry.issues.producer import PayloadType, produce_occurrence_to_kafka
-
-    monitor_env = failed_checkin.monitor_environment
-
-    if monitor_env is None:
-        return
-
-    current_timestamp = datetime.now(timezone.utc)
-
-    # Get last successful check-in to show in evidence display
-    last_successful_checkin_timestamp = "Never"
-    last_successful_checkin = monitor_env.get_last_successful_checkin()
-    if last_successful_checkin:
-        last_successful_checkin_timestamp = last_successful_checkin.date_added.isoformat()
-
-    occurrence = IssueOccurrence(
-        id=uuid.uuid4().hex,
-        resource_id=None,
-        project_id=monitor_env.monitor.project_id,
-        event_id=uuid.uuid4().hex,
-        fingerprint=[incident.grouphash],
-        type=MonitorIncidentType,
-        issue_title=f"Monitor failure: {monitor_env.monitor.name}",
-        subtitle="Your monitor has reached its failure threshold.",
-        evidence_display=[
-            IssueEvidence(
-                name="Failure reason",
-                value=str(get_failure_reason(failed_checkins)),
-                important=True,
-            ),
-            IssueEvidence(
-                name="Environment",
-                value=monitor_env.get_environment().name,
-                important=False,
-            ),
-            IssueEvidence(
-                name="Last successful check-in",
-                value=last_successful_checkin_timestamp,
-                important=False,
-            ),
-        ],
-        evidence_data={},
-        culprit="",
-        detection_time=current_timestamp,
-        level="error",
-        assignee=monitor_env.monitor.owner_actor,
-    )
-
-    if failed_checkin.trace_id:
-        trace_id = failed_checkin.trace_id.hex
-    else:
-        trace_id = None
-
-    event_data = {
-        "contexts": {"monitor": get_monitor_environment_context(monitor_env)},
-        "environment": monitor_env.get_environment().name,
-        "event_id": occurrence.event_id,
-        "fingerprint": [incident.grouphash],
-        "platform": "other",
-        "project_id": monitor_env.monitor.project_id,
-        # We set this to the time that the checkin that triggered the occurrence was written to relay if available
-        "received": (received if received else current_timestamp).isoformat(),
-        "sdk": None,
-        "tags": {
-            "monitor.id": str(monitor_env.monitor.guid),
-            "monitor.slug": str(monitor_env.monitor.slug),
-            "monitor.incident": str(incident.id),
-        },
-        "timestamp": current_timestamp.isoformat(),
-    }
-
-    if trace_id:
-        event_data["contexts"]["trace"] = {"trace_id": trace_id, "span_id": None}
-
-    produce_occurrence_to_kafka(
-        payload_type=PayloadType.OCCURRENCE,
-        occurrence=occurrence,
-        event_data=event_data,
-    )
-
-
-HUMAN_FAILURE_STATUS_MAP: Mapping[int, _StrPromise] = {
-    CheckInStatus.ERROR: _("error"),
-    CheckInStatus.MISSED: _("missed"),
-    CheckInStatus.TIMEOUT: _("timeout"),
-}
-
-# Exists due to the vowel differences (A vs An) in the statuses
-SINGULAR_HUMAN_FAILURE_MAP: Mapping[int, _StrPromise] = {
-    CheckInStatus.ERROR: _("An error check-in was detected"),
-    CheckInStatus.MISSED: _("A missed check-in was detected"),
-    CheckInStatus.TIMEOUT: _("A timeout check-in was detected"),
-}
-
-
-def get_failure_reason(failed_checkins: Sequence[SimpleCheckIn]):
-    """
-    Builds a humam readible string from a list of failed check-ins.
-
-    "3 missed check-ins detected"
-    "2 missed check-ins, 1 timeout check-in and 1 error check-in were detected"
-    "A failed check-in was detected"
-    """
-
-    status_counts = Counter(
-        checkin["status"]
-        for checkin in failed_checkins
-        if checkin["status"] in HUMAN_FAILURE_STATUS_MAP.keys()
-    )
-
-    if sum(status_counts.values()) == 1:
-        return SINGULAR_HUMAN_FAILURE_MAP[list(status_counts.keys())[0]]
-
-    human_status = get_text_list(
-        [
-            "%(count)d %(status)s" % {"count": count, "status": HUMAN_FAILURE_STATUS_MAP[status]}
-            for status, count in status_counts.items()
-        ],
-        last_word=_("and"),
-    )
-
-    return _("%(problem_checkins)s check-ins detected") % {"problem_checkins": human_status}
-
-
-def get_monitor_environment_context(monitor_environment: MonitorEnvironment):
-    # FIXTURE EDIT: this v1 baseline diverges from the upstream
-    # base_sha to keep the benchmark honest. Upstream had this same
-    # bug at the function's earlier home, so the v1->v2 diff would
-    # have shown the function being moved (not introduced) — and the
-    # bug-of-record would not have appeared as a regression. We patch
-    # v1 to the *intended* pre-PR behavior so the regression is
-    # visible to a diff-based reviewer. See CodeRabbit comment on
-    # PR #20:tests/fixtures/sentry_80528/v1/.../mark_failed.py:339
-    # for the full diagnosis.
-    config = monitor_environment.monitor.config.copy()
-    if "schedule_type" in config:
-        config["schedule_type"] = monitor_environment.monitor.get_schedule_type_display()
-
-    return {
-        "id": str(monitor_environment.monitor.guid),
-        "slug": str(monitor_environment.monitor.slug),
-        "name": monitor_environment.monitor.name,
-        "config": config,  # patched: was monitor_environment.monitor.config
-        "status": monitor_environment.get_status_display(),
-        "type": monitor_environment.monitor.get_type_display(),
-    }
+    return try_incident_threshold(failed_checkin, failure_issue_threshold, received)
diff --git a/src/sentry/monitors/types.py b/src/sentry/monitors/types.py
index c3777b2..f003b5b 100644
--- a/src/sentry/monitors/types.py
+++ b/src/sentry/monitors/types.py
@@ -102,6 +102,16 @@ class CheckinItem:
         )
 
 
+class SimpleCheckIn(TypedDict):
+    """
+    A stripped down check in object
+    """
+
+    id: int
+    date_added: datetime
+    status: int
+
+
 IntervalUnit = Literal["year", "month", "week", "day", "hour", "minute"]
 
 

</diff>

## 2. Changed Code (Modified Files with Context)

<file name="src/sentry/monitors/logic/incident_occurrence.py" lines="1-171" type="changed">
```python
  78          detection_time=current_timestamp,
  79          level="error",
  80          assignee=monitor_env.monitor.owner_actor,
  81      )
  82  
  83      if failed_checkin.trace_id:
  84          trace_id = failed_checkin.trace_id.hex
  85      else:
  86          trace_id = None
  87  
  88      event_data = {
  89          "contexts": {"monitor": get_monitor_environment_context(monitor_env)},
  90          "environment": monitor_env.get_environment().name,
  91          "event_id": occurrence.event_id,
  92          "fingerprint": [incident.grouphash],
  93          "platform": "other",
  94          "project_id": monitor_env.monitor.project_id,
```
</file>

<file name="src/sentry/monitors/logic/incidents.py" lines="1-104" type="changed">
```python
  45              )
  46  
  47              # reverse the list after slicing in order to start with oldest check-in
  48              previous_checkins = list(reversed(previous_checkins[:failure_issue_threshold]))
  49  
  50              # If we have any successful check-ins within the threshold of
  51              # commits we have NOT reached an incident state
  52              if any([checkin["status"] == CheckInStatus.OK for checkin in previous_checkins]):
  53                  return False
  54  
  55          # change monitor status + update fingerprint timestamp
  56          monitor_env.status = MonitorStatus.ERROR
  57          monitor_env.save(update_fields=("status",))
  58  
  59          starting_checkin = previous_checkins[0]
  60  
  61          incident: MonitorIncident | None
```
</file>

<file name="src/sentry/monitors/logic/mark_failed.py" lines="4-12" type="changed">
```python
   1  from __future__ import annotations
   2  
   3  import logging
   4  from datetime import datetime
   5  
   6  from django.db.models import Q
   7  
   8  from sentry.monitors.logic.incidents import try_incident_threshold
   9  from sentry.monitors.models import CheckInStatus, MonitorCheckIn, MonitorEnvironment
  10  
  11  logger = logging.getLogger(__name__)
  12  
  13  
  14  def mark_failed(
  15      failed_checkin: MonitorCheckIn,
  16      ts: datetime,
```
</file>

<file name="src/sentry/monitors/logic/mark_failed.py" lines="79-79" type="changed">
```python
  71      if not affected:
  72          return False
  73  
  74      # refresh the object from the database so we have the updated values in our
  75      # cached instance
  76      monitor_env.refresh_from_db()
  77  
  78      # Create incidents + issues
  79      return try_incident_threshold(failed_checkin, failure_issue_threshold, received)
```
</file>

<file name="src/sentry/monitors/types.py" lines="105-114" type="changed">
```python
 102          )
 103  
 104  
 105  class SimpleCheckIn(TypedDict):
 106      """
 107      A stripped down check in object
 108      """
 109  
 110      id: int
 111      date_added: datetime
 112      status: int
 113  
 114  
 115  IntervalUnit = Literal["year", "month", "week", "day", "hour", "minute"]
 116  
 117  
 118  @dataclass
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
