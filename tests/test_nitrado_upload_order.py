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

TERRITORY_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<territory-type>
    <territory color="4286611584">
        <zone name="HuntingGround" smin="0" smax="0" dmin="2" dmax="2" x="5000" z="5000" r="90" />
    </territory>
</territory-type>
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
        self.original_discover_ce_file_paths = bot.discover_console_ce_file_paths
        self.original_backup = bot.upload_ce_latest_backup_to_nitrado
        self.original_cleanup = bot.cleanup_wanderingbot_backups_for_path
        self.original_ftp_verify_retry_seconds = bot.PROTECTED_FTP_VERIFY_RETRY_SECONDS
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
        bot.discover_console_ce_file_paths = self.original_discover_ce_file_paths
        bot.upload_ce_latest_backup_to_nitrado = self.original_backup
        bot.cleanup_wanderingbot_backups_for_path = self.original_cleanup
        bot.PROTECTED_FTP_VERIFY_RETRY_SECONDS = self.original_ftp_verify_retry_seconds

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

    def test_custom_animal_territory_file_uses_protected_upload_verification(self):
        def api_upload(*_args):
            self.calls.append("api")
            return True, "Uploaded successfully via Nitrado API."

        def verify(*_args):
            self.calls.append("verify")
            return True, "verified"

        bot.upload_text_file_to_nitrado_api = api_upload
        bot.verify_uploaded_protected_dayz_xml_text = verify

        ok, message = bot.upload_text_file_to_nitrado(
            {},
            "/dayzxb_missions/dayzOffline.enoch/env/wanderingbot_animal_bear_territories.xml",
            TERRITORY_XML,
        )

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

    def test_native_ce_upload_rolls_back_when_final_bundle_mismatches(self):
        original_build = bot.build_console_ce_event_files
        original_validate = bot.validate_console_ce_xml_bundle
        original_backup = bot.backup_remote_ce_sources_before_upload
        original_upload = bot.upload_protected_ce_file_to_nitrado
        original_final = bot.verify_uploaded_console_ce_xml_bundle
        original_rollback = bot.restore_console_ce_bundle_from_memory
        try:
            built = {
                "messages": ["built"],
                "events_path": "/dayzxb_missions/dayzOffline.enoch/db/events.xml",
                "events_text": "<events></events>",
                "spawns_path": "/dayzxb_missions/dayzOffline.enoch/cfgeventspawns.xml",
                "spawns_text": "<eventposdef></eventposdef>",
                "restore_texts": {
                    "/dayzxb_missions/dayzOffline.enoch/db/events.xml": "<events><event name=\"old\" /></events>",
                    "/dayzxb_missions/dayzOffline.enoch/cfgeventspawns.xml": "<eventposdef><event name=\"old\" /></eventposdef>",
                },
            }

            def build(*_args, **_kwargs):
                self.calls.append("build")
                return built

            def validate(_built):
                self.calls.append("validate")
                return True, ["validated"]

            def backup(*_args):
                self.calls.append("backup")
                return True, ["backed up"]

            def upload(_config, label, _path, _text, restore_text=None, prefer_ftp=False):
                self.calls.append(("upload", label, bool(restore_text), prefer_ftp))
                return True, f"{label} uploaded"

            def final_verify(*_args):
                self.calls.append("final")
                return False, ["Final remote CE bundle verification failed after upload.", "mixed names"]

            def rollback(_config, _built):
                self.calls.append("rollback")
                return True, ["rollback restored"]

            bot.build_console_ce_event_files = build
            bot.validate_console_ce_xml_bundle = validate
            bot.backup_remote_ce_sources_before_upload = backup
            bot.upload_protected_ce_file_to_nitrado = upload
            bot.verify_uploaded_console_ce_xml_bundle = final_verify
            bot.restore_console_ce_bundle_from_memory = rollback

            ok, _built, messages = bot.upload_console_ce_event_files(123, {})

            self.assertFalse(ok)
            self.assertIn("rollback restored", messages)
            self.assertEqual([
                "build",
                "validate",
                "backup",
                ("upload", "events.xml", True, True),
                ("upload", "cfgeventspawns.xml", True, True),
                "final",
                "rollback",
            ], self.calls)
        finally:
            bot.build_console_ce_event_files = original_build
            bot.validate_console_ce_xml_bundle = original_validate
            bot.backup_remote_ce_sources_before_upload = original_backup
            bot.upload_protected_ce_file_to_nitrado = original_upload
            bot.verify_uploaded_console_ce_xml_bundle = original_final
            bot.restore_console_ce_bundle_from_memory = original_rollback

    def test_native_ce_upload_uses_protected_writer_for_animal_territory_files(self):
        original_build = bot.build_console_ce_event_files
        original_validate = bot.validate_console_ce_xml_bundle
        original_backup = bot.backup_remote_ce_sources_before_upload
        original_upload = bot.upload_protected_ce_file_to_nitrado
        original_upload_text = bot.upload_text_file_to_nitrado
        original_final = bot.verify_uploaded_console_ce_xml_bundle
        original_rollback = bot.restore_console_ce_bundle_from_memory
        try:
            territory_path = "/dayzxb_missions/dayzOffline.enoch/env/wanderingbot_animal_bear_territories.xml"
            built = {
                "messages": ["built"],
                "events_path": "/dayzxb_missions/dayzOffline.enoch/db/events.xml",
                "events_text": "<events></events>",
                "spawns_path": "/dayzxb_missions/dayzOffline.enoch/cfgeventspawns.xml",
                "spawns_text": "<eventposdef></eventposdef>",
                "animal_territory_files": [
                    {
                        "path": territory_path,
                        "text": TERRITORY_XML,
                        "event_names": ["AnimalWanderingBot_animal_bear"],
                    }
                ],
                "restore_texts": {
                    "/dayzxb_missions/dayzOffline.enoch/db/events.xml": "<events><event name=\"old\" /></events>",
                    "/dayzxb_missions/dayzOffline.enoch/cfgeventspawns.xml": "<eventposdef><event name=\"old\" /></eventposdef>",
                },
            }

            def build(*_args, **_kwargs):
                self.calls.append("build")
                return built

            def validate(_built):
                self.calls.append("validate")
                return True, ["validated"]

            def backup(*_args):
                self.calls.append("backup")
                return True, ["backed up"]

            def upload(_config, label, _path, _text, restore_text=None, prefer_ftp=False):
                self.calls.append(("upload", label, bool(restore_text), prefer_ftp))
                return True, f"{label} uploaded"

            def upload_text(*_args):
                self.fail("Animal territory files must use the protected CE uploader, not the generic text uploader.")

            def final_verify(*_args):
                self.calls.append("final")
                return False, ["Final remote CE bundle verification failed after upload."]

            def rollback(_config, _built):
                self.calls.append("rollback")
                return True, ["rollback restored"]

            bot.build_console_ce_event_files = build
            bot.validate_console_ce_xml_bundle = validate
            bot.backup_remote_ce_sources_before_upload = backup
            bot.upload_protected_ce_file_to_nitrado = upload
            bot.upload_text_file_to_nitrado = upload_text
            bot.verify_uploaded_console_ce_xml_bundle = final_verify
            bot.restore_console_ce_bundle_from_memory = rollback

            ok, _built, messages = bot.upload_console_ce_event_files(123, {})

            self.assertFalse(ok)
            self.assertIn("rollback restored", messages)
            self.assertEqual([
                "build",
                "validate",
                "backup",
                ("upload", "events.xml", True, True),
                ("upload", "cfgeventspawns.xml", True, True),
                ("upload", "wanderingbot_animal_bear_territories.xml", False, True),
                "final",
                "rollback",
            ], self.calls)
        finally:
            bot.build_console_ce_event_files = original_build
            bot.validate_console_ce_xml_bundle = original_validate
            bot.backup_remote_ce_sources_before_upload = original_backup
            bot.upload_protected_ce_file_to_nitrado = original_upload
            bot.upload_text_file_to_nitrado = original_upload_text
            bot.verify_uploaded_console_ce_xml_bundle = original_final
            bot.restore_console_ce_bundle_from_memory = original_rollback

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
        self.assertEqual(("upload_ftp", "/dayzxb_missions/dayzOffline.enoch/cfgeventspawns.xml"), self.calls[0])
        self.assertEqual(5, len([call for call in self.calls if call[0] == "download_ftp"]))

    def test_verified_ftp_write_retries_empty_exact_read_before_failing(self):
        def ftp_upload(_config, path, _text):
            self.calls.append(("upload_ftp", path))
            return True, "Uploaded successfully via ukln138.gamedata.io."

        def ftp_download(_config, path, exact_only=False):
            self.calls.append(("download_ftp", path, exact_only))
            if len([call for call in self.calls if call[0] == "download_ftp"]) == 1:
                return True, "Downloaded successfully via FTP.", ""
            return True, "Downloaded successfully via FTP.", SPAWNS_XML

        bot.upload_text_file_to_nitrado_ftp = ftp_upload
        bot.download_text_file_from_nitrado_ftp = ftp_download
        bot.PROTECTED_FTP_VERIFY_RETRY_SECONDS = 0

        ok, message = bot.upload_protected_dayz_xml_to_nitrado_ftp_verified(
            {},
            "/dayzxb_missions/dayzOffline.enoch/cfgeventspawns.xml",
            SPAWNS_XML,
        )

        self.assertTrue(ok, message)
        self.assertIn("after 2 attempt(s)", message)
        self.assertEqual([
            ("upload_ftp", "/dayzxb_missions/dayzOffline.enoch/cfgeventspawns.xml"),
            ("download_ftp", "/dayzxb_missions/dayzOffline.enoch/cfgeventspawns.xml", True),
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

    def test_cleanup_preserves_static_woodencrate_revamp_proto(self):
        original = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<prototype>
    <group name="StaticObj_Misc_WoodenCrate_5x" lootmax="80">
        <container name="lootFloor" lootmax="80">
            <category name="tools" />
            <tag name="floor" />
            <point pos="0 0 0" range="0.5" height="0.5" flags="32" />
        </container>
    </group>
</prototype>
"""
        root = ET.fromstring(original)

        changed, removed_groups, removed_values = bot.cleanup_stale_mapgroupproto_airdrop_nodes(root)

        self.assertFalse(changed)
        self.assertEqual(0, removed_groups)
        self.assertEqual(0, removed_values)
        self.assertIsNotNone(root.find("./group[@name='StaticObj_Misc_WoodenCrate_5x']"))

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

    def test_scope_guard_allows_livonia_static_helicrash_proto_restore(self):
        original = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<prototype>
    <group name="Wreck_Mi8_Crashed" />
    <group name="Wreck_Mi8_Crashed" lootmax="15">
        <container name="lootFloor" lootmax="15">
            <category name="weapons" />
            <tag name="floor" />
            <point pos="0 0 0" range="0.5" height="0.5" />
        </container>
    </group>
</prototype>
"""
        root = ET.fromstring(original)
        repaired = bot.repair_vanilla_static_helicrash_mapgroupproto(root, "livonia")
        self.assertEqual(["Wreck_Mi8_Crashed"], repaired)

        ok, message = bot.validate_managed_ce_xml_scope(
            "mapgroupproto.xml",
            original,
            bot.xml_text_from_root(root),
            map_key="livonia",
        )

        self.assertTrue(ok)
        self.assertIn("only WanderingBot-managed", message)

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

    def test_final_bundle_missing_animal_territory_file_is_hard_failure(self):
        original_download = bot.download_text_file_from_nitrado
        original_download_ftp = bot.download_text_file_from_nitrado_ftp
        try:
            def ftp_download(*_args, **_kwargs):
                self.calls.append("ftp")
                return False, "FTP file not found", ""

            def download(*_args):
                self.calls.append("download")
                return False, "API file not found", ""

            bot.download_text_file_from_nitrado_ftp = ftp_download
            bot.download_text_file_from_nitrado = download
            built = {
                "animal_territory_files": [
                    {
                        "path": "/dayzxb_missions/dayzOffline.enoch/env/wanderingbot_animal_bear_territories.xml",
                        "text": TERRITORY_XML,
                        "event_names": ["AnimalWanderingBot_animal_bear"],
                    }
                ]
            }

            ok, messages = bot.verify_uploaded_console_ce_xml_bundle({}, built)

            self.assertFalse(ok)
            self.assertTrue(any("could not be re-downloaded" in message for message in messages))
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

    def test_successful_rollback_messages_do_not_hide_original_failure(self):
        messages = [
            "Final remote CE bundle verification failed after upload.",
            "`AnimalWanderingBot_animal_bear` is a custom animal event but is missing matching Herd template `HerdWanderingBot_animal_bear` in `cfgenvironment.xml`.",
            "Native CE rollback attempted after bundle mismatch: `4` restored, `0` failed.",
            "`cfgenvironment.xml` rollback restored from in-memory pre-upload copy. Uploaded successfully via ukln138.gamedata.io. cfgenvironment.xml post-upload re-download matched with <env> root.",
            "`zombie_territories.xml` rollback restored from in-memory pre-upload copy. Uploaded successfully via ukln138.gamedata.io. zombie_territories.xml post-upload re-download matched with <territory-type> root.",
        ]

        status = bot.native_ce_failed_status_text(messages)

        self.assertIn("Final remote CE bundle verification failed", status)
        self.assertIn("missing matching Herd template", status)
        self.assertNotIn("rollback restored", status)

    def test_console_ce_source_download_uses_discovered_ce_file_path(self):
        guild_id = "livonia-ce-discovery"
        discovered_path = "/dayzxb_missions/custom/dayzOffline.enoch/mapgroupproto.xml"
        previous_config = bot.guild_configs.get(guild_id)

        def fake_discover(_config, wanted_guild_id, key):
            self.assertEqual(guild_id, wanted_guild_id)
            self.assertEqual("mapgroupproto_path", key)
            return [discovered_path]

        def fake_download(_config, path):
            self.calls.append(path)
            if path == discovered_path:
                return True, "Downloaded discovered live mapgroupproto.xml.", "<map></map>"
            return False, "missing", None

        try:
            bot.guild_configs[guild_id] = {"server_map": "livonia", "server_platform": "xbox"}
            bot.discover_console_ce_file_paths = fake_discover
            bot.download_text_file_from_nitrado = fake_download

            text, path, message = bot.download_console_ce_source({}, guild_id, "mapgroupproto_path")

            self.assertEqual("<map></map>", text)
            self.assertEqual(discovered_path, path)
            self.assertIn("Downloaded discovered", message)
            self.assertIn(discovered_path, self.calls)
        finally:
            if previous_config is None:
                bot.guild_configs.pop(guild_id, None)
            else:
                bot.guild_configs[guild_id] = previous_config


class PruneStaleAnimalTerritoryFilesTests(unittest.TestCase):
    def setUp(self):
        self.original_list_ftp = bot.list_remote_directory_from_ftp
        self.original_list_api = bot.list_remote_directory_from_nitrado_api
        self.original_delete = bot.delete_remote_file_from_nitrado
        self.deleted = []

    def tearDown(self):
        bot.list_remote_directory_from_ftp = self.original_list_ftp
        bot.list_remote_directory_from_nitrado_api = self.original_list_api
        bot.delete_remote_file_from_nitrado = self.original_delete

    def test_prune_removes_only_orphaned_wanderingbot_territory_files(self):
        base = "/dayzxb_missions/dayzOffline.enoch"
        env_listing = [
            {"name": "bear_territories.xml", "path": f"{base}/env/bear_territories.xml"},
            {"name": "wolf_territories.xml", "path": f"{base}/env/wolf_territories.xml"},
            {"name": "zombie_territories.xml", "path": f"{base}/env/zombie_territories.xml"},
            {
                "name": "zombie_territories.xml.wanderingbot-backup-latest",
                "path": f"{base}/env/zombie_territories.xml.wanderingbot-backup-latest",
            },
            {
                "name": "wanderingbot_animal_bear_territories.xml",
                "path": f"{base}/env/wanderingbot_animal_bear_territories.xml",
            },
            {
                "name": "wanderingbot_animal_bear_territories.xml.wanderingbot-backup-latest",
                "path": f"{base}/env/wanderingbot_animal_bear_territories.xml.wanderingbot-backup-latest",
            },
            {
                "name": "wanderingbot_animal_wolf_territories.xml",
                "path": f"{base}/env/wanderingbot_animal_wolf_territories.xml",
            },
            {
                "name": "wanderingbot_animalwanderingbot17animalpack_territories.xml",
                "path": f"{base}/env/wanderingbot_animalwanderingbot17animalpack_territories.xml",
            },
            {
                "name": "wanderingbot_bearwanderingbot1_territories.xml",
                "path": f"{base}/env/wanderingbot_bearwanderingbot1_territories.xml",
            },
            {
                "name": "wanderingbot_animalbearblissbeargroupbeh_territories.xml",
                "path": f"{base}/env/wanderingbot_animalbearblissbeargroupbeh_territories.xml",
            },
            {
                "name": "wanderingbot_animal_wanderingbot_animal_bear_territories.xml",
                "path": f"{base}/env/wanderingbot_animal_wanderingbot_animal_bear_territories.xml",
            },
            {
                "name": "wanderingbot_animalwanderingbot10animalpack_territories.xml.wanderingbot-backup-latest",
                "path": f"{base}/env/wanderingbot_animalwanderingbot10animalpack_territories.xml.wanderingbot-backup-latest",
            },
        ]

        bot.list_remote_directory_from_ftp = lambda _config, _folder, **_kw: list(env_listing)
        bot.list_remote_directory_from_nitrado_api = lambda _config, _folder, **_kw: []

        def fake_delete(_config, target_path):
            self.deleted.append(target_path)
            return True, "deleted"

        bot.delete_remote_file_from_nitrado = fake_delete

        built = {
            "mission_base": base,
            "events_path": f"{base}/db/events.xml",
            "spawns_path": f"{base}/cfgeventspawns.xml",
            "animal_territory_files": [
                {"path": f"{base}/env/wanderingbot_animal_bear_territories.xml"},
                {"path": f"{base}/env/wanderingbot_animal_wolf_territories.xml"},
            ],
        }

        deleted, failed = bot.prune_stale_animal_territory_files({}, built)

        self.assertEqual([], failed)
        self.assertEqual(
            {
                "wanderingbot_animalwanderingbot17animalpack_territories.xml",
                "wanderingbot_bearwanderingbot1_territories.xml",
                "wanderingbot_animalbearblissbeargroupbeh_territories.xml",
                "wanderingbot_animal_wanderingbot_animal_bear_territories.xml",
                "wanderingbot_animalwanderingbot10animalpack_territories.xml.wanderingbot-backup-latest",
            },
            set(deleted),
        )
        deleted_names = {os.path.basename(path) for path in self.deleted}
        for keep in (
            "bear_territories.xml",
            "wolf_territories.xml",
            "zombie_territories.xml",
            "zombie_territories.xml.wanderingbot-backup-latest",
            "wanderingbot_animal_bear_territories.xml",
            "wanderingbot_animal_bear_territories.xml.wanderingbot-backup-latest",
            "wanderingbot_animal_wolf_territories.xml",
        ):
            self.assertNotIn(keep, deleted_names)


if __name__ == "__main__":
    unittest.main()
