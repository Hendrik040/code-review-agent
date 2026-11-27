# ansible#15

Commit message of the reviewed change: eos_eapi: adding the desired state config to the new vrf fixes #32111 (#32112)

Oracle (fix location at buggy_commit): [{'file': 'lib/ansible/modules/network/eos/eos_eapi.py', 'line_start': 267, 'line_end': 267}]

## Reviewed diff (introducing commit)
```diff
diff --git a/lib/ansible/modules/network/eos/eos_eapi.py b/lib/ansible/modules/network/eos/eos_eapi.py
index c3ae14f333..541b104a87 100644
--- a/lib/ansible/modules/network/eos/eos_eapi.py
+++ b/lib/ansible/modules/network/eos/eos_eapi.py
@@ -260,11 +260,17 @@ def map_obj_to_commands(updates, module, warnings):
         else:
             add('protocol unix-socket')
 
+    if needs_update('state') and not needs_update('vrf'):
+        if want['state'] == 'stopped':
+            add('shutdown')
+        elif want['state'] == 'started':
+            add('no shutdown')
+
 
     if needs_update('vrf'):
         add('vrf %s' % want['vrf'])
-
-    if needs_update('state'):
+        # switching operational vrfs here
+        # need to add the desired state as well
         if want['state'] == 'stopped':
             add('shutdown')
         elif want['state'] == 'started':
diff --git a/test/units/modules/network/eos/test_eos_eapi.py b/test/units/modules/network/eos/test_eos_eapi.py
index 5ef9a3b14f..dfb4e83f4a 100644
--- a/test/units/modules/network/eos/test_eos_eapi.py
+++ b/test/units/modules/network/eos/test_eos_eapi.py
@@ -134,6 +134,11 @@ class TestEosEapiModule(TestEosModule):
         commands = ['management api http-commands', 'vrf test', 'no shutdown']
         self.start_unconfigured(changed=True, commands=commands)
 
+    def test_eos_eapi_change_from_default_vrf(self):
+        set_module_args(dict(vrf='test'))
+        commands = ['management api http-commands', 'vrf test', 'no shutdown']
+        self.start_configured(changed=True, commands=commands)
+
     def test_eos_eapi_vrf_missing(self):
         set_module_args(dict(vrf='missing'))
         self.start_unconfigured(failed=True)

```

## Maintainer's fix (buggy_commit..fixed_commit, oracle files only)
```diff
diff --git a/lib/ansible/modules/network/eos/eos_eapi.py b/lib/ansible/modules/network/eos/eos_eapi.py
index 07eeaf93eb..d3825a30df 100644
--- a/lib/ansible/modules/network/eos/eos_eapi.py
+++ b/lib/ansible/modules/network/eos/eos_eapi.py
@@ -262,11 +262,11 @@ def map_obj_to_commands(updates, module, warnings):
         if want['socket'] is False:
             add('no protocol unix-socket')
         else:
             add('protocol unix-socket')
 
-    if needs_update('state') and not needs_update('vrf'):
+    if needs_update('state'):
         if want['state'] == 'stopped':
             add('shutdown')
         elif want['state'] == 'started':
             add('no shutdown')
 

```

## ODIS candidates: 77 total, path=jev, tiers={'full': 1, 'signature': 1, 'counted': 75}
Shown to the reviewer (full = whole snippet, signature = one line):
- [full] callee lib/ansible/modules/network/eos/eos_eapi.py:222 add | def add(cmd):
```python
 212      configured_vrfs.append('default')
 213      if value not in configured_vrfs:
 214          module.fail_json(msg='vrf `%s` is not configured on the system' % value)
 215  
 216  def map_obj_to_commands(updates, module, warnings):
 217      commands = list()
 218      want, have = updates
 219  
 220      needs_update = lambda x: want.get(x) is not None and (want.get(x) != have.get(x))
 221  
 222      def add(cmd):
 223          if 'management api http-commands' not in commands:
 224              commands.insert(0, 'management api http-commands')
 225          commands.append(cmd)
 226  
 227      if any((needs_update('http'), needs_update('http_port'))):
 228          if want['http'] is False:
 229              add('no protocol http')
 230          else:
 231              if have['http'] is False and want['http'] in (False, None):
 232                  warnings.append('protocol http is not enabled, not configuring http port value')
```
- [signature] callee test/units/modules/network/eos/eos_module.py:31 set_module_args | def set_module_args(args):
Counted only (75), first 15:
- callee lib/ansible/module_utils/netcfg.py:365 add
- callee lib/ansible/module_utils/netscaler.py:106 add
- callee lib/ansible/modules/cloud/digital_ocean/digital_ocean.py:269 add
- callee lib/ansible/modules/cloud/digital_ocean/digital_ocean.py:336 add
- callee lib/ansible/modules/cloud/digital_ocean/digital_ocean_domain.py:135 add
- callee lib/ansible/modules/clustering/consul.py:247 add
- callee lib/ansible/modules/clustering/consul_acl.py:557 add
- callee lib/ansible/modules/messaging/rabbitmq_user.py:196 add
- callee lib/ansible/modules/messaging/rabbitmq_vhost.py:87 add
- callee lib/ansible/modules/monitoring/logicmonitor.py:1273 add
- callee lib/ansible/modules/monitoring/logicmonitor.py:1794 add
- callee lib/ansible/modules/net_tools/ldap/ldap_attr.py:223 add
- callee lib/ansible/modules/net_tools/ldap/ldap_entry.py:204 add
- callee lib/ansible/modules/network/a10/a10_virtual_server.py:223 needs_update
- callee lib/ansible/modules/network/ios/ios_user.py:193 needs_update
