from __future__ import annotations

import os
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from _bot_loader import import_bot_module  # noqa: E402

bot = import_bot_module()


SPAWNS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<eventposdef>
    <event name="StaticWanderingBot_test">
        <pos x="1" z="2" a="0" />
    </event>
</eventposdef>
"""


class ProtectedXmlUploadOrderTests(unittest.TestCase):
    def setUp(self):
        self.original_api = bot.upload_text_file_to_nitrado_api
        self.original_ftp = bot.upload_text_file_to_nitrado_ftp
        self.original_upload_text = bot.upload_text_file_to_nitrado
        self.original_verified_ftp = bot.upload_protected_dayz_xml_to_nitrado_ftp_verified
        self.original_verify = bot.verify_uploaded_protected_dayz_xml_text
        self.original_verify_remote = bot.verify_remote_protected_dayz_xml
        self.original_restore = bot.restore_remote_ce_file_from_latest_backup
        self.original_download_ftp = bot.download_text_file_from_nitrado_ftp
        self.original_download = bot.download_text_file_from_nitrado
        self.original_backup = bot.upload_ce_latest_backup_to_nitrado
        self.original_cleanup = bot.cleanup_wanderingbot_backups_for_path
        self.calls = []

    def tearDown(self):
        bot.upload_text_file_to_nitrado_api = self.original_api
        bot.upload_text_file_to_nitrado_ftp = self.original_ftp
        bot.upload_text_file_to_nitrado = self.original_upload_text
        bot.upload_protected_dayz_xml_to_nitrado_ftp_verified = self.original_verified_ftp
        bot.verify_uploaded_protected_dayz_xml_text = self.original_verify
        bot.verify_remote_protected_dayz_xml = self.original_verify_remote
        bot.restore_remote_ce_file_from_latest_backup = self.original_restore
        bot.download_text_file_from_nitrado_ftp = self.original_download_ftp
        bot.download_text_file_from_nitrado = self.original_download
        bot.upload_ce_latest_backup_to_nitrado = self.original_backup
        bot.cleanup_wanderingbot_backups_for_path = self.original_cleanup

    def test_protected_xml_uses_api_before_ftp(self):
        def api_upload(*_args):
            self.calls.append("api")
            return True, "Uploaded successfully via Nitrado API."

        def ftp_upload(*_args):
            self.calls.append("ftp")
            return True, "Uploaded successfully via FTP."

        def verify(*_args):
            self.calls.append("verify")
            return True, "verified"

        bot.upload_text_file_to_nitrado_api = api_upload
        bot.upload_text_file_to_nitrado_ftp = ftp_upload
        bot.verify_uploaded_protected_dayz_xml_text = verify

        ok, message = bot.upload_text_file_to_nitrado({}, "/dayzxb_missions/dayzOffline.enoch/cfgeventspawns.xml", SPAWNS_XML)

        self.assertTrue(ok)
        self.assertIn("Nitrado API", message)
        self.assertEqual(["api", "verify"], self.calls)

    def test_protected_xml_does_not_ftp_after_api_verification_failure(self):
        def api_upload(*_args):
            self.calls.append("api")
            return True, "Uploaded successfully via Nitrado API."

        def ftp_upload(*_args):
            self.calls.append("ftp")
            return True, "Uploaded successfully via FTP."

        def verify(*_args):
            self.calls.append("verify")
            return False, "post-upload XML was malformed"

        bot.upload_text_file_to_nitrado_api = api_upload
        bot.upload_text_file_to_nitrado_ftp = ftp_upload
        bot.verify_uploaded_protected_dayz_xml_text = verify

        ok, message = bot.upload_text_file_to_nitrado({}, "/dayzxb_missions/dayzOffline.enoch/cfgeventspawns.xml", SPAWNS_XML)

        self.assertFalse(ok)
        self.assertIn("Post-upload verification failed", message)
        self.assertEqual(["api", "verify"], self.calls)

    def test_protected_xml_uses_verified_ftp_when_api_fails_before_write(self):
        def api_upload(*_args):
            self.calls.append("api")
            return False, "Nitrado API token or service ID is missing."

        def verified_upload(*_args):
            self.calls.append("verified_ftp")
            return True, "Uploaded successfully via ukln138.gamedata.io. verified"

        def verify(*_args):
            self.calls.append("verify")
            return True, "verified"

        bot.upload_text_file_to_nitrado_api = api_upload
        bot.upload_protected_dayz_xml_to_nitrado_ftp_verified = verified_upload
        bot.verify_uploaded_protected_dayz_xml_text = verify

        ok, message = bot.upload_text_file_to_nitrado({}, "/dayzxb_missions/dayzOffline.enoch/cfgeventspawns.xml", SPAWNS_XML)

        self.assertTrue(ok)
        self.assertIn("verified FTP live write was used", message)
        self.assertEqual(["api", "verified_ftp"], self.calls)

    def test_ce_latest_backup_can_use_ftp_without_touching_api(self):
        backup_path = "/dayzxb_missions/dayzOffline.enoch/cfgeventspawns.xml.wanderingbot-backup-latest"

        def api_upload(*_args):
            self.calls.append("api")
            return False, "Nitrado API token failed with status 429."

        def ftp_upload(*_args):
            self.calls.append("ftp")
            return True, "Uploaded successfully via ukln138.gamedata.io."

        def verify_remote(*_args):
            self.calls.append("verify_remote")
            return True, "backup verified"

        bot.upload_text_file_to_nitrado_api = api_upload
        bot.upload_text_file_to_nitrado_ftp = ftp_upload
        bot.verify_remote_protected_dayz_xml = verify_remote

        ok, message = bot.upload_ce_latest_backup_to_nitrado({}, "cfgeventspawns.xml", backup_path, SPAWNS_XML)

        self.assertTrue(ok)
        self.assertIn("ukln138.gamedata.io", message)
        self.assertEqual(["ftp", "verify_remote"], self.calls)

    def test_xml_compare_accepts_equivalent_structure(self):
        downloaded = """<eventposdef><event name="StaticWanderingBot_test"><pos a="0" z="2" x="1" /></event></eventposdef>"""

        ok, message = bot.verify_protected_dayz_xml_content_matches(
            "cfgeventspawns.xml",
            "/dayzxb_missions/dayzOffline.enoch/cfgeventspawns.xml",
            SPAWNS_XML,
            downloaded,
        )

        self.assertTrue(ok)
        self.assertIn("matched XML structure", message)

    def test_failed_remote_latest_backup_keeps_in_memory_restore_copy(self):
        spawns_path = "/dayzxb_missions/dayzOffline.enoch/cfgeventspawns.xml"
        built = {"spawns_path": spawns_path}

        def download(*_args):
            self.calls.append("download")
            return True, "downloaded", SPAWNS_XML

        def backup(*_args):
            self.calls.append("backup")
            return False, "Backup verification failed: invalid XML"

        def cleanup(*_args, **_kwargs):
            self.calls.append("cleanup")
            return [], []

        bot.download_text_file_from_nitrado = download
        bot.upload_ce_latest_backup_to_nitrado = backup
        bot.cleanup_wanderingbot_backups_for_path = cleanup

        ok, messages = bot.backup_remote_ce_sources_before_upload({}, built)

        self.assertTrue(ok)
        self.assertEqual(SPAWNS_XML, built["restore_texts"][spawns_path])
        self.assertTrue(any("in-memory restore copy" in message for message in messages))
        self.assertEqual(["download", "backup"], self.calls)

    def test_ce_protected_upload_fails_when_remote_copy_is_stale_after_success(self):
        def upload(*_args):
            self.calls.append("upload")
            return True, "Uploaded successfully via Nitrado API."

        def verify(*_args):
            self.calls.append("verify")
            return False, "`cfgeventspawns.xml` post-upload re-download did not match the uploaded content"

        def restore(*_args, **_kwargs):
            self.calls.append("restore")
            return True, "`cfgeventspawns.xml` restored from in-memory pre-upload copy."

        bot.upload_text_file_to_nitrado = upload
        bot.verify_uploaded_protected_dayz_xml_text = verify
        bot.restore_remote_ce_file_from_latest_backup = restore

        ok, message = bot.upload_protected_ce_file_to_nitrado(
            {},
            "cfgeventspawns.xml",
            "/dayzxb_missions/dayzOffline.enoch/cfgeventspawns.xml",
            SPAWNS_XML,
            restore_text="<eventposdef></eventposdef>",
        )

        self.assertFalse(ok)
        self.assertIn("did not match the uploaded content", message)
        self.assertIn("Restore attempted", message)
        self.assertEqual(["upload", "verify", "restore"], self.calls)

    def test_verified_ftp_write_rechecks_same_file_via_ftp_not_api(self):
        def ftp_upload(_config, path, _text):
            self.calls.append(("upload_ftp", path))
            return True, "Uploaded successfully via ukln138.gamedata.io."

        def ftp_download(_config, path, exact_only=False):
            self.calls.append(("download_ftp", path, exact_only))
            return True, "Downloaded successfully via FTP.", SPAWNS_XML

        def generic_verify(*_args):
            self.calls.append(("generic_verify",))
            return False, "generic API-first verifier should not be used"

        bot.upload_text_file_to_nitrado_ftp = ftp_upload
        bot.download_text_file_from_nitrado_ftp = ftp_download
        bot.verify_uploaded_protected_dayz_xml_text = generic_verify

        ok, message = bot.upload_protected_dayz_xml_to_nitrado_ftp_verified(
            {},
            "/dayzxb_missions/dayzOffline.enoch/cfgeventspawns.xml",
            SPAWNS_XML,
        )

        self.assertTrue(ok, message)
        self.assertIn("post-upload re-download matched", message)
        self.assertEqual([
            ("upload_ftp", "/dayzxb_missions/dayzOffline.enoch/cfgeventspawns.xml"),
            ("download_ftp", "/dayzxb_missions/dayzOffline.enoch/cfgeventspawns.xml", True),
        ], self.calls)

    def test_verified_ftp_write_reports_stale_ftp_copy(self):
        stale_spawns = SPAWNS_XML.replace("StaticWanderingBot_test", "StaticWanderingBot_old")

        def ftp_upload(_config, path, _text):
            self.calls.append(("upload_ftp", path))
            return True, "Uploaded successfully via ukln138.gamedata.io."

        def ftp_download(_config, path, exact_only=False):
            self.calls.append(("download_ftp", path, exact_only))
            return True, "Downloaded successfully via FTP.", stale_spawns

        bot.upload_text_file_to_nitrado_ftp = ftp_upload
        bot.download_text_file_from_nitrado_ftp = ftp_download

        ok, message = bot.upload_protected_dayz_xml_to_nitrado_ftp_verified(
            {},
            "/dayzxb_missions/dayzOffline.enoch/cfgeventspawns.xml",
            SPAWNS_XML,
        )

        self.assertFalse(ok)
        self.assertIn("did not match the uploaded content", message)
        self.assertEqual([
            ("upload_ftp", "/dayzxb_missions/dayzOffline.enoch/cfgeventspawns.xml"),
            ("download_ftp", "/dayzxb_missions/dayzOffline.enoch/cfgeventspawns.xml", True),
        ], self.calls)

    def test_scope_guard_allows_only_wanderingbot_event_changes(self):
        original = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<events>
    <event name="StaticVanillaThing"><nominal>1</nominal></event>
    <event name="StaticWanderingBot_old"><nominal>1</nominal></event>
</events>
"""
        merged = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<events>
    <event name="StaticVanillaThing"><nominal>1</nominal></event>
    <!-- Wandering Bot: managed event definition StaticWanderingBot_new -->
    <event name="StaticWanderingBot_new"><nominal>1</nominal></event>
</events>
"""

        ok, message = bot.validate_managed_ce_xml_scope("events.xml", original, merged)

        self.assertTrue(ok)
        self.assertIn("only WanderingBot-managed", message)

    def test_scope_guard_blocks_non_wanderingbot_event_changes(self):
        original = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<events>
    <event name="StaticVanillaThing"><nominal>1</nominal></event>
</events>
"""
        merged = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<events>
    <event name="StaticVanillaThing"><nominal>2</nominal></event>
</events>
"""

        ok, message = bot.validate_managed_ce_xml_scope("events.xml", original, merged)

        self.assertFalse(ok)
        self.assertIn("non-WanderingBot", message)
        self.assertIn("StaticVanillaThing", message)

    def test_scope_guard_allows_managed_proto_append_after_legacy_live_proto(self):
        original = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<prototype>
    <group name="WoodenCrate" lootmax="80">
        <usage name="Military" />
        <point pos="0 0 0" range="0.5" height="0.5" />
    </group>
</prototype>
"""
        merged = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<prototype>
    <group name="WoodenCrate" lootmax="80">
        <usage name="Military" />
        <point pos="0 0 0" range="0.5" height="0.5" />
    </group>
    <!-- Wandering Bot: managed mapgroupproto group WoodenCrate -->
    <group name="WoodenCrate" lootmax="80">
        <usage name="Military" />
        <container name="lootFloor" lootmax="80">
            <category name="weapons" />
            <tag name="floor" />
            <point pos="0 0 0" range="0.5" height="0.5" flags="32" />
        </container>
    </group>
</prototype>
"""

        ok, message = bot.validate_managed_ce_xml_scope("mapgroupproto.xml", original, merged)

        self.assertTrue(ok)
        self.assertIn("only WanderingBot-managed", message)

    def test_scope_guard_allows_managed_proto_append_after_old_tier4_live_proto(self):
        original = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<prototype>
    <group name="WoodenCrate" lootmax="80">
        <value name="Tier4" />
        <container name="lootFloor" lootmax="0" />
    </group>
</prototype>
"""
        root = ET.fromstring(original)
        _changed, removed_groups, removed_values = bot.cleanup_stale_mapgroupproto_airdrop_nodes(root)
        self.assertEqual(0, removed_groups)
        self.assertEqual(0, removed_values)

        merged = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<prototype>
    <group name="WoodenCrate" lootmax="80">
        <value name="Tier4" />
        <container name="lootFloor" lootmax="0" />
    </group>
    <!-- Wandering Bot: managed mapgroupproto group WoodenCrate -->
    <group name="WoodenCrate">
        <container name="lootFloor" lootmax="80">
            <category name="weapons" />
            <category name="explosives" />
            <tag name="floor" />
            <point pos="0 0 0" range="0.5" height="0.5" flags="32" />
        </container>
    </group>
</prototype>
"""

        ok, message = bot.validate_managed_ce_xml_scope("mapgroupproto.xml", original, merged)

        self.assertTrue(ok)
        self.assertIn("only WanderingBot-managed", message)

    def test_scope_guard_blocks_real_woodencrate_proto_changes(self):
        original = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<prototype>
    <group name="WoodenCrate">
        <container name="lootFloor" lootmax="80">
            <category name="tools" />
            <tag name="floor" />
            <point pos="0 0 0" range="0.5" height="0.5" flags="32" />
        </container>
    </group>
</prototype>
"""
        merged = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<prototype>
    <group name="WoodenCrate">
        <container name="lootFloor" lootmax="80">
            <category name="tools" />
            <category name="weapons" />
            <tag name="floor" />
            <point pos="0 0 0" range="0.5" height="0.5" flags="32" />
        </container>
    </group>
</prototype>
"""

        ok, message = bot.validate_managed_ce_xml_scope("mapgroupproto.xml", original, merged)

        self.assertFalse(ok)
        self.assertIn("non-WanderingBot", message)
        self.assertIn("WoodenCrate", message)

    def test_scope_guard_success_messages_do_not_fail_bundle_validation(self):
        events_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<events>
    <event name="StaticVanillaThing"><nominal>1</nominal></event>
</events>
"""
        spawns_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<eventposdef>
    <event name="StaticVanillaThing"><pos x="1" z="2" a="0" /></event>
</eventposdef>
"""
        built = {
            "events_text": events_xml,
            "events_source_text": events_xml,
            "spawns_text": spawns_xml,
            "spawns_source_text": spawns_xml,
            "source_fallbacks": [],
        }

        ok, messages = bot.validate_console_ce_xml_bundle(built)

        self.assertTrue(ok)
        self.assertTrue(any("snippet scope guard confirmed" in message for message in messages))
        self.assertTrue(any("Validated" in message for message in messages))

    def test_final_bundle_redownload_failure_is_warning_after_individual_verification(self):
        original_download = bot.download_text_file_from_nitrado
        original_download_ftp = bot.download_text_file_from_nitrado_ftp
        try:
            def ftp_download(*_args, **_kwargs):
                self.calls.append("ftp")
                return False, "FTP unavailable", ""

            def download(*_args):
                self.calls.append("download")
                return False, "Nitrado API download failed: 429 Cloudflare Just a moment", ""

            bot.download_text_file_from_nitrado_ftp = ftp_download
            bot.download_text_file_from_nitrado = download
            built = {
                "events_path": "/dayzxb_missions/dayzOffline.enoch/db/events.xml",
                "events_text": "<events></events>",
            }

            ok, messages = bot.verify_uploaded_console_ce_xml_bundle({}, built)

            self.assertTrue(ok)
            self.assertTrue(any("re-download warning" in message for message in messages))
            self.assertEqual(["ftp", "download"], self.calls)
        finally:
            bot.download_text_file_from_nitrado_ftp = original_download_ftp
            bot.download_text_file_from_nitrado = original_download

    def test_final_bundle_check_skips_scope_guard_on_redownloaded_copy(self):
        original_download = bot.download_text_file_from_nitrado
        original_download_ftp = bot.download_text_file_from_nitrado_ftp
        try:
            def ftp_download(*_args, **_kwargs):
                return False, "FTP unavailable", ""

            def download(_config, path):
                self.calls.append(path)
                if path.endswith("/cfgeventspawns.xml"):
                    return True, "downloaded", """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<eventposdef>
    <event name="StaticVanillaThing"><pos x="1" z="2" a="0" /></event>
</eventposdef>
"""
                return True, "downloaded", """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<events>
    <event name="StaticVanillaThing"><nominal>2</nominal></event>
</events>
"""

            bot.download_text_file_from_nitrado_ftp = ftp_download
            bot.download_text_file_from_nitrado = download
            built = {
                "events_path": "/dayzxb_missions/dayzOffline.enoch/db/events.xml",
                "events_text": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<events>
    <event name="StaticVanillaThing"><nominal>1</nominal></event>
</events>
""",
                "events_source_text": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<events>
    <event name="StaticVanillaThing"><nominal>1</nominal></event>
</events>
""",
                "spawns_path": "/dayzxb_missions/dayzOffline.enoch/cfgeventspawns.xml",
                "spawns_text": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<eventposdef>
    <event name="StaticVanillaThing"><pos x="1" z="2" a="0" /></event>
</eventposdef>
""",
            }

            ok, messages = bot.verify_uploaded_console_ce_xml_bundle({}, built)

            self.assertTrue(ok, messages)
            self.assertTrue(any("Final remote CE bundle verified" in message for message in messages))
            self.assertEqual([
                "/dayzxb_missions/dayzOffline.enoch/db/events.xml",
                "/dayzxb_missions/dayzOffline.enoch/cfgeventspawns.xml",
            ], self.calls)
        finally:
            bot.download_text_file_from_nitrado_ftp = original_download_ftp
            bot.download_text_file_from_nitrado = original_download

    def test_final_bundle_prefers_exact_ftp_over_stale_api_download(self):
        original_download = bot.download_text_file_from_nitrado
        original_download_ftp = bot.download_text_file_from_nitrado_ftp
        events_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<events>
    <event name="StaticWanderingBot_48_gaszone">
        <nominal>1</nominal><min>1</min><max>1</max><lifetime>1800</lifetime>
        <restock>0</restock><saferadius>0</saferadius><distanceradius>80</distanceradius><cleanupradius>180</cleanupradius>
        <flags deletable="1" init_random="0" remove_damaged="0" />
        <position>fixed</position><limit>parent</limit><active>1</active>
        <children><child type="ContaminatedArea_Dynamic" min="1" max="1" lootmin="0" lootmax="0" /></children>
    </event>
</events>
"""
        spawns_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<eventposdef>
    <event name="StaticWanderingBot_48_gaszone">
        <zone smin="0" smax="0" dmin="1" dmax="1" r="80" />
        <pos x="5000" z="5000" a="0" />
    </event>
</eventposdef>
"""
        stale_spawns_xml = spawns_xml.replace("StaticWanderingBot_48_gaszone", "StaticWanderingBot_48_gaszone_r2")
        try:
            def ftp_download(_config, path, exact_only=False):
                self.calls.append(("ftp", path, exact_only))
                if path.endswith("/cfgeventspawns.xml"):
                    return True, "Downloaded via exact FTP.", spawns_xml
                return True, "Downloaded via exact FTP.", events_xml

            def generic_download(_config, path):
                self.calls.append(("generic", path))
                if path.endswith("/cfgeventspawns.xml"):
                    return True, "Downloaded stale API copy.", stale_spawns_xml
                return True, "Downloaded API copy.", events_xml

            bot.download_text_file_from_nitrado_ftp = ftp_download
            bot.download_text_file_from_nitrado = generic_download
            built = {
                "events_path": "/dayzxb_missions/dayzOffline.enoch/db/events.xml",
                "events_text": events_xml,
                "spawns_path": "/dayzxb_missions/dayzOffline.enoch/cfgeventspawns.xml",
                "spawns_text": spawns_xml,
                "source_fallbacks": [],
            }

            ok, messages = bot.verify_uploaded_console_ce_xml_bundle({}, built)

            self.assertTrue(ok, messages)
            self.assertTrue(any("Final remote CE bundle verified" in message for message in messages))
            self.assertEqual([
                ("ftp", "/dayzxb_missions/dayzOffline.enoch/db/events.xml", True),
                ("ftp", "/dayzxb_missions/dayzOffline.enoch/cfgeventspawns.xml", True),
            ], self.calls)
        finally:
            bot.download_text_file_from_nitrado_ftp = original_download_ftp
            bot.download_text_file_from_nitrado = original_download

    def test_successful_ftp_fallback_message_does_not_mark_upload_blocked(self):
        messages = [
            "mapgroupproto.xml: Nitrado API upload token failed with status 429: Cloudflare. "
            "API upload failed, so verified FTP live write was used. Uploaded successfully via ukln138.gamedata.io. "
            "mapgroupproto.xml post-upload re-download matched with <prototype> root."
        ]

        self.assertFalse(bot.native_ce_upload_blocked_messages(messages))
        self.assertNotIn("mapgroupproto.xml", bot.native_ce_failed_status_text(messages))


if __name__ == "__main__":
    unittest.main()
