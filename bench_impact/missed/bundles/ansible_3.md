# ansible#3

Commit message of the reviewed change: Add support for Kali Linux detection. (#50331)

Oracle (fix location at buggy_commit): [{'file': 'lib/ansible/module_utils/facts/system/distribution.py', 'line_start': 323, 'line_end': 323}]

## Reviewed diff (introducing commit)
```diff
diff --git a/lib/ansible/module_utils/facts/system/distribution.py b/lib/ansible/module_utils/facts/system/distribution.py
index 49e57686c7..697eb3bd6c 100644
--- a/lib/ansible/module_utils/facts/system/distribution.py
+++ b/lib/ansible/module_utils/facts/system/distribution.py
@@ -322,6 +322,11 @@ class DistributionFiles:
         elif 'SteamOS' in data:
             debian_facts['distribution'] = 'SteamOS'
             # nothing else to do, SteamOS gets correct info from python functions
+        elif path == '/etc/lsb-release' and 'Kali' in data:
+            debian_facts['distribution'] = 'Kali'
+            release = re.search('DISTRIB_RELEASE=(.*)', data)
+            if release:
+                debian_facts['distribution_release'] = release.groups()[0]
         elif 'Devuan' in data:
             debian_facts['distribution'] = 'Devuan'
             release = re.search(r"PRETTY_NAME=[^(]+ \(?([^)]+?)\)", data)
@@ -446,7 +451,7 @@ class Distribution(object):
                                 'Ascendos', 'CloudLinux', 'PSBM', 'OracleLinux', 'OVS',
                                 'OEL', 'Amazon', 'Virtuozzo', 'XenServer', 'Alibaba'],
                      'Debian': ['Debian', 'Ubuntu', 'Raspbian', 'Neon', 'KDE neon',
-                                'Linux Mint', 'SteamOS', 'Devuan'],
+                                'Linux Mint', 'SteamOS', 'Devuan', 'Kali'],
                      'Suse': ['SuSE', 'SLES', 'SLED', 'openSUSE', 'openSUSE Tumbleweed',
                               'SLES_SAP', 'SUSE_LINUX', 'openSUSE Leap'],
                      'Archlinux': ['Archlinux', 'Antergos', 'Manjaro'],
diff --git a/test/units/module_utils/test_distribution_version.py b/test/units/module_utils/test_distribution_version.py
index 7df9ee4c05..87fba0d511 100644
--- a/test/units/module_utils/test_distribution_version.py
+++ b/test/units/module_utils/test_distribution_version.py
@@ -601,6 +601,31 @@ VERSION_ID="12.04"
                    "os_family": "Debian",
                    'distribution_version': u'12.04'}
     },
+    {
+        'name': 'Kali 2019.1',
+        'input': {
+            '/etc/os-release': ("PRETTY_NAME=\"Kali GNU/Linux Rolling\"\nNAME=\"Kali GNU/Linux\"\nID=kali\nVERSION=\"2019.1\"\n"
+                                "VERSION_ID=\"2019.1\"\nID_LIKE=debian\nANSI_COLOR=\"1;31\"\nHOME_URL=\"https://www.kali.org/\"\n"
+                                "SUPPORT_URL=\"https://forums.kali.org/\"\nBUG_REPORT_URL=\"https://bugs.kali.org/\"\n"),
+            '/etc/lsb-release': ("DISTRIB_ID=Kali\nDISTRIB_RELEASE=kali-rolling\nDISTRIB_CODENAME=kali-rolling\n"
+                                 "DISTRIB_DESCRIPTION=\"Kali GNU/Linux Rolling\"\n"),
+            '/usr/lib/os-release': ("PRETTY_NAME=\"Kali GNU/Linux Rolling\"\nNAME=\"Kali GNU/Linux\"\nID=kali\nVERSION=\"2019.1\"\n"
+                                    "VERSION_ID=\"2019.1\"\nID_LIKE=debian\nANSI_COLOR=\"1;31\"\nHOME_URL=\"https://www.kali.org/\"\n"
+                                    "SUPPORT_URL=\"https://forums.kali.org/\"\nBUG_REPORT_URL=\"https://bugs.kali.org/\"\n")
+        },
+        'platform.dist': [
+            'kali',
+            '2019.1',
+            ''
+        ],
+        'result': {
+            'distribution': 'Kali',
+            'distribution_version': '2019.1',
+            'distribution_release': 'kali-rolling',
+            'distribution_major_version': '2019',
+            'os_family': 'Debian'
+        }
+    },
     {
         "platform.dist": [
             "neon",

```

## Maintainer's fix (buggy_commit..fixed_commit, oracle files only)
```diff
diff --git a/lib/ansible/module_utils/facts/system/distribution.py b/lib/ansible/module_utils/facts/system/distribution.py
index 606dbc19bd..528b0e2b9e 100644
--- a/lib/ansible/module_utils/facts/system/distribution.py
+++ b/lib/ansible/module_utils/facts/system/distribution.py
@@ -318,11 +318,12 @@ class DistributionFiles:
             debian_facts['distribution'] = 'Ubuntu'
             # nothing else to do, Ubuntu gets correct info from python functions
         elif 'SteamOS' in data:
             debian_facts['distribution'] = 'SteamOS'
             # nothing else to do, SteamOS gets correct info from python functions
-        elif path == '/etc/lsb-release' and 'Kali' in data:
+        elif path in ('/etc/lsb-release', '/etc/os-release') and 'Kali' in data:
+            # Kali does not provide /etc/lsb-release anymore
             debian_facts['distribution'] = 'Kali'
             release = re.search('DISTRIB_RELEASE=(.*)', data)
             if release:
                 debian_facts['distribution_release'] = release.groups()[0]
         elif 'Devuan' in data:

```

## ODIS candidates: 0 total, path=small, tiers={'full': 0, 'signature': 0, 'counted': 0}
Shown to the reviewer (full = whole snippet, signature = one line):
