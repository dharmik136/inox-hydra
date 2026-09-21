import os
import zipfile
import tempfile
import pytest
from studio.backend.vault import encrypt_token, decrypt_token, get_vault_backend
from studio.backend import support, updates, paths


def test_vault_encrypt_decrypt_roundtrip():
    """Verify encrypt and decrypt round-trip with real credentials."""
    sample = "AQEDA_SAMPLE_LINKEDIN_TOKEN_1234567890_VERY_SECRET"
    enc = encrypt_token(sample)
    assert enc != sample
    assert enc.startswith(("dpapi:", "locenc:"))
    dec = decrypt_token(enc)
    assert dec == sample


def test_vault_null_and_empty_handling():
    """Verify encrypt and decrypt handle None, empty string, and non-string inputs safely."""
    assert encrypt_token(None) == ""
    assert encrypt_token("") == ""
    assert decrypt_token(None) == ""
    assert decrypt_token("") == ""

    # Non-string input
    enc_num = encrypt_token(12345)
    assert enc_num.startswith(("dpapi:", "locenc:"))
    assert decrypt_token(enc_num) == "12345"


def test_vault_huge_plaintext_bounded():
    """Verify oversized plaintext is bounded safely without memory exhaustion."""
    huge_input = "A" * 100000
    enc = encrypt_token(huge_input)
    assert enc.startswith(("dpapi:", "locenc:"))
    dec = decrypt_token(enc)
    assert len(dec) == 65536


def test_vault_malformed_ciphertext_handling():
    """Verify malformed or corrupted ciphertext with prefix returns empty string gracefully."""
    bad_dpapi = "dpapi:!@#$%NOT_VALID_BASE64!"
    assert decrypt_token(bad_dpapi) == ""

    bad_locenc = "locenc:!@#$%NOT_VALID_BASE64!"
    assert decrypt_token(bad_locenc) == ""


def test_vault_backend_diagnostic_helper():
    """Verify get_vault_backend reports a valid known backend."""
    backend = get_vault_backend()
    assert backend in ("DPAPI", "MACHINE_KEYED")


def test_support_create_backup_path_traversal_sanitized(monkeypatch):
    """Verify that path traversal sequences in backup label are strictly sanitized."""
    temp_home = tempfile.mkdtemp(prefix="inox_test_traversal_")
    monkeypatch.setenv("INOX_HYDRA_HOME", temp_home)

    # Initialize empty DB so backup can execute
    import sqlite3
    os.makedirs(paths.get_data_dir(), exist_ok=True)
    os.makedirs(paths.get_backups_dir(), exist_ok=True)
    conn = sqlite3.connect(paths.get_db_path())
    conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("PRAGMA user_version = 1")
    conn.commit()
    conn.close()

    try:
        archive = support.create_backup("../../evil_escape")
        backups_dir = os.path.abspath(paths.get_backups_dir())
        archive_abs = os.path.abspath(archive)
        assert archive_abs.startswith(backups_dir + os.sep)
        assert os.path.exists(archive)
    finally:
        import shutil
        shutil.rmtree(temp_home, ignore_errors=True)


def test_support_restore_backup_zip_slip_rejected(monkeypatch):
    """Verify Zip Slip directory traversal vulnerability is blocked on restore."""
    temp_home = tempfile.mkdtemp(prefix="inox_test_zipslip_")
    monkeypatch.setenv("INOX_HYDRA_HOME", temp_home)

    import sqlite3
    os.makedirs(paths.get_data_dir(), exist_ok=True)
    os.makedirs(paths.get_backups_dir(), exist_ok=True)
    os.makedirs(paths.get_assets_dir(), exist_ok=True)
    conn = sqlite3.connect(paths.get_db_path())
    conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("PRAGMA user_version = 1")
    conn.commit()
    conn.close()

    # Create a malicious zip with traversal path
    malicious_zip = os.path.join(temp_home, "malicious.zip")
    with zipfile.ZipFile(malicious_zip, "w") as z:
        # Include a valid db
        with open(paths.get_db_path(), "rb") as f:
            z.writestr("data/linkedin_studio.db", f.read())
        # Include Zip Slip attack file targeting outside assets
        z.writestr("assets/../../escaped_slip_file.txt", "Pwned!")

    try:
        support.restore_backup(malicious_zip, take_safety_backup=False)
        # Verify the escaped file was NOT created outside the assets root
        escaped_target = os.path.join(temp_home, "escaped_slip_file.txt")
        assert not os.path.exists(escaped_target), "Zip Slip vulnerability detected! Escaped file was created."
    finally:
        import shutil
        shutil.rmtree(temp_home, ignore_errors=True)


def test_support_restore_backup_nonexistent_or_invalid():
    """Verify restore_backup raises ValueError for missing or non-zip files."""
    with pytest.raises(ValueError, match="does not exist or is not a valid zip"):
        support.restore_backup("non_existent_file_path.zip")

    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        f.write(b"not a zip file")
        bad_file = f.name
    try:
        with pytest.raises(ValueError, match="does not exist or is not a valid zip"):
            support.restore_backup(bad_file)
    finally:
        if os.path.exists(bad_file):
            os.remove(bad_file)


def test_updates_check_disallowed_scheme_ssrf_rejected(monkeypatch):
    """Verify SSRF protection on update check rejects non-HTTPS schemes."""
    updates.set_enabled(True)
    for bad_scheme_url in [
        "http://insecure.internal/manifest.json",
        "file:///etc/passwd",
        "ftp://mirror.example.com/latest.json"
    ]:
        res = updates.check_for_update(url=bad_scheme_url)
        assert res["checked"] is False
        assert "Disallowed URL scheme" in res.get("error", "")


def test_updates_parse_version_bounded():
    """Verify parse_version bounds length and chunks cleanly."""
    huge_version = "1." * 1000 + "5"
    parsed = updates.parse_version(huge_version)
    assert len(parsed) <= 10
    assert isinstance(parsed, tuple)


def test_zero_em_dash_compliance():
    """Verify zero em-dash across hardened sovereign platform modules."""
    files_to_check = [
        os.path.abspath("studio/backend/vault.py"),
        os.path.abspath("studio/backend/support.py"),
        os.path.abspath("studio/backend/updates.py"),
        os.path.abspath("studio/backend/linkedin_client.py"),
        os.path.abspath(__file__)
    ]
    em_dash_char = chr(0x2014)
    for path in files_to_check:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            assert em_dash_char not in content, f"Em-dash detected in {path}"
