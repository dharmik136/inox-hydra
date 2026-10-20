"""
Inox Hydra Support CLI.
=======================
The self-service toolkit for a product nobody can log into.

Run from a source checkout:
    python -m studio.cli <command>

Run from the portable artifact:
    InoxHydra-CLI.bat <command>

Commands:
    doctor      Health summary, and a redacted bundle to attach to an issue
    paths       Where this installation keeps its data
    backup      Snapshot the database and media into a single ZIP
    restore     Replace current state with a backup, after a safety snapshot
    export      Write your content to JSON, CSV, or an Obsidian vault
    reset       Clear configuration while keeping all content
    migrate     Show or apply pending database schema migrations
    update      Check for a newer release, opt in, or opt out

doctor, backup, restore and export act on the active creator profile unless
--profile <id> names another; backup and export also take --all.

Strict Invariants:
- Zero em-dashes.
- Destructive commands require explicit confirmation.
"""

import argparse
import json
import os
import sqlite3
import sys
import zipfile

try:
    from .backend import paths, sqlite_open, support, updates
    from .backend import migrations as migration_ledger
    from .__version__ import __version__
except ImportError:  # executed as a loose script
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from studio.backend import paths, sqlite_open, support, updates
    from studio.backend import migrations as migration_ledger
    from studio.__version__ import __version__


def _print_kv(title, mapping, indent="  "):
    print(title)
    for key, value in mapping.items():
        print(f"{indent}{key:26s} {value}")


def _profile_label(profile_id=None) -> str:
    """'Name (id)' for a creator profile, the active one by default."""
    pid = profile_id or paths.get_active_profile_id()
    try:
        try:
            from .backend import accounts
        except ImportError:
            from studio.backend import accounts
        entry = accounts.get_account(pid)
        if entry and entry.get("name"):
            return f"{entry['name']} ({pid})"
    except Exception:
        pass
    return pid


def _chosen_profiles(args):
    """
    The profiles a command runs in: None for the active one, or a list.

    A backup, export or diagnosis covers one creator profile. With several,
    the CLI used to act on the active one alone, and never said which.
    """
    if getattr(args, "all_profiles", False):
        return paths.registered_profile_ids()
    chosen = getattr(args, "profile", None)
    if not chosen:
        return None
    known = paths.registered_profile_ids()
    if chosen not in known:
        raise ValueError(f"There is no creator profile '{chosen}'. Profiles on this machine: {', '.join(known)}.")
    return [chosen]


def cmd_doctor(args) -> int:
    report = support.collect_diagnostics()

    print(f"Inox Hydra {report['app_version']} on {report['platform']['system']} "
          f"{report['platform']['release']} (Python {report['platform']['python']})")
    print(f"Profile: {_profile_label()}")
    print()

    p = report["paths"]
    schema = report.get("schema") or {}
    if schema:
        if not p["db_exists"]:
            # A fresh install has no database yet. Saying "migrations pending"
            # here would read as a fault when nothing is wrong.
            print("  schema                     not initialized "
                  "(created on first launch)")
        else:
            state = "current" if schema.get("up_to_date") else (
                "NEWER THAN THIS BUILD" if schema.get("too_new") else "migrations pending")
            print(f"  schema                     v{schema.get('current_version')} "
                  f"of v{schema.get('target_version')} ({state})")

    print(f"  data location              {p['app_home']}")
    print(f"  resolved by                {p['resolved_by']}")
    print(f"  database                   "
          f"{'present, ' + format(p['db_size_bytes'], ',') + ' bytes' if p['db_exists'] else 'not created yet'}")
    print(f"  backups on disk            {len(report['backups'])}")
    print()

    content = {k: v for k, v in report["tables"].items()
               if k in support.EXPORTABLE_TABLES and isinstance(v, int)}
    if content:
        _print_kv("  content:", content, indent="    ")
        print()

    if report["errors"]:
        print("  problems found:")
        for err in report["errors"]:
            print(f"    - {err}")
        print()
        if any(str(err).startswith("database unreadable") for err in report["errors"]):
            # The one problem a creator cannot work around: say exactly what to run.
            backups = support.restorable_backups()
            if backups:
                print("  The database cannot be read. Restore your newest backup with:")
                print(f"    {support.restore_command(backups[0]['path'])}")
                print("  A safety copy of the damaged files is kept first.")
            else:
                print("  The database cannot be read, and there is no backup to restore.")
                print(f"  Quit the studio, move {paths.get_db_path()} out of that folder,")
                print("  and start the studio again. It starts empty.")
            print()
    else:
        print("  no problems found")
        print()

    if args.bundle:
        destination = support.write_diagnostics_bundle(args.output)
        print(f"Diagnostics bundle written to:\n  {destination}")
        print()
        print("It holds versions, folder layout, table counts and the last log lines.")
        print("Session cookies and API keys are redacted, and so are query strings,")
        print("quoted text, profile addresses and emails in the log lines. Open it in")
        print("a text editor and read it before you attach it to a public issue.")
    else:
        print("Run with --bundle to write a redacted report you can attach to an issue.")
    return 0


def cmd_paths(args) -> int:
    _print_kv(f"Inox Hydra {__version__} locations:", paths.describe())
    return 0


def cmd_backup(args) -> int:
    print(f"Profile: {_profile_label()}")
    try:
        archive = support.create_backup(args.label)
    except ValueError as refused:
        print(f"No backup written. {refused}")
        return 1
    size = os.path.getsize(archive)
    print(f"Backup written:\n  {archive}\n  {size:,} bytes")
    print()
    print("Restore it later with:")
    print(f"  python -m studio.cli restore \"{archive}\" --yes")
    return 0


def cmd_restore(args) -> int:
    if not os.path.exists(args.archive):
        print(f"No such backup: {args.archive}")
        return 1

    try:
        info = support.inspect_backup(args.archive)
    except (ValueError, zipfile.BadZipFile) as unreadable:
        print(f"Not restored: {unreadable}")
        return 1
    manifest = info.get("manifest")
    if not isinstance(manifest, dict):
        # A manifest that is not an object (hand-edited, or cut short) says
        # nothing it can be trusted for; restore_backup refuses such a file.
        manifest = {}
    print(f"Backup: {args.archive}")
    if info.get("kind") == "database":
        # A pre-upgrade copy: the database alone, with no manifest to read.
        print("  kind         a copy of the database alone, taken before an upgrade")
        print(f"  created      {info.get('created_at') or 'unknown'}")
        print(f"  schema       {info.get('schema_version')}")
        print(f"  database     {'yes' if info['has_database'] else 'NO'}")
        print("  media files  none (your current media files are left as they are)")
    else:
        print(f"  created      {manifest.get('created_at', 'unknown')}")
        print(f"  app version  {manifest.get('app_version', 'unknown')}")
        print(f"  database     {'yes' if info['has_database'] else 'NO'}")
        print(f"  media files  {info['asset_count']}")
        print(f"  profile      {manifest.get('profile', 'not recorded (made before profiles were separate)')}")
    print(f"  restoring into the profile: {_profile_label()}")
    print()

    if not args.yes:
        print("This REPLACES your current drafts, leads and analytics.")
        print("A safety snapshot of your current state is taken first.")
        print("Re-run with --yes to proceed.")
        return 1

    try:
        result = support.restore_backup(args.archive, into_active_profile=args.into_active_profile)
    except support.RestoreFailed as failed:
        print(f"Not restored: {failed}")
        if failed.safety_backup:
            print(f"  safety snapshot       {failed.safety_backup}")
            print("  It holds your state from just before this restore.")
        return 1
    except support.ProfileMismatch as error:
        print(str(error))
        print("Pass --into-active-profile to restore it into the active profile anyway.")
        return 1
    except ValueError as error:
        print(f"Not restored: {error}")
        return 1
    print(f"Restored from {result['restored_from']}")
    print(f"  media files restored  {result['assets_restored']}")
    print(f"  safety snapshot       {result['safety_backup'] or 'none'}")
    if result.get("safety_note"):
        print(f"  {result['safety_note']}")
    print()
    print("Restart Inox Hydra for the restored data to take effect.")
    return 0


def cmd_export(args) -> int:
    print(f"Profile: {_profile_label()}")
    if getattr(args, "all_profiles", False) and args.output:
        print("Not exported: --all writes one export per profile, each into its own exports folder,")
        print("so it cannot share one --output. Leave --output out, or name one --profile.")
        return 1
    vault = None
    try:
        if args.format == "obsidian":
            # The vault export itself rather than through support, for what it
            # reports: notes it named around one of yours, notes you edited,
            # which it left alone, and notes about someone no longer here.
            try:
                from .backend.obsidian_export import export_obsidian_vault
            except ImportError:
                from studio.backend.obsidian_export import export_obsidian_vault
            vault = export_obsidian_vault(args.output)
            destination = vault["path"]
        else:
            destination = support.export_data(args.output, fmt=args.format)
    except ValueError as refused:
        print(f"Not exported: {refused}", file=sys.stderr)
        return 1
    if vault is not None:
        print(f"Wrote an Obsidian vault to:\n  {destination}")
        edited = set(vault["kept_edited"])
        for moved in vault["renamed"]:
            if moved["wanted"] not in edited:
                print(f"  {moved['wanted']} is a note of yours, so this one was written to {moved['written']}.")
        for path in vault["kept_edited"]:
            fresh = next((m["written"] for m in vault["renamed"] if m["wanted"] == path), None)
            print(f"  You edited {path}, so it was left as it is."
                  + (f" The refreshed copy is {fresh}." if fresh else ""))
        for path in vault["released"]:
            print(f"  {path} is about something no longer in the studio. Only what you wrote in it was kept.")
        print()
        print("Open it in Obsidian with \"Open folder as vault\". Export again into the same")
        print("folder to refresh it: notes you add, and anything under a \"## Your notes\"")
        print("heading, are kept.")
        return 0
    print(f"Exported {args.format.upper()} to:\n  {destination}")
    print()
    print("This contains your drafts, posts, leads and analytics. It deliberately")
    print("excludes credentials, so it is portable but not a backup. Use `backup`")
    print("if you want something you can restore.")
    return 0


def cmd_reset(args) -> int:
    if not args.yes:
        print("This clears configuration: AI provider settings and the stored LinkedIn")
        print("session. Your drafts, leads, analytics, queue and Brand Studio profile are")
        print("NOT touched, and a safety snapshot is taken first.")
        print()
        print("Re-run with --yes to proceed.")
        return 1

    try:
        result = support.reset_configuration(keep_data=True)
    except ValueError as refused:
        print(f"Nothing was reset. {refused}")
        return 1
    cleared = result.get("cleared_keys") or []
    print(f"  cleared {len(cleared)} settings: {', '.join(cleared) if cleared else 'none were set'}")
    print(f"  safety snapshot  {result['safety_backup']}")
    print()
    print("Reconfigure your AI provider with: python studio_cli.py ai configure")
    return 0


def cmd_migrate(args) -> int:
    if not os.path.exists(paths.get_db_path()):
        print(f"There is no studio database at {paths.get_db_path()} yet.")
        print("It is created, already at this build's schema, the first time the studio starts.")
        return 0
    status = migration_ledger.describe()
    print(f"Schema version {status['current_version']}, this build targets "
          f"{status['target_version']}.")

    if status["too_new"]:
        print()
        print("This database was written by a NEWER version of Inox Hydra.")
        print("Install that version again, or restore a backup from:")
        print(f"  {paths.get_backups_dir()}")
        return 1

    if not status["pending"]:
        print("No pending migrations.")
        return 0

    print()
    print("Pending migrations:")
    for entry in status["pending"]:
        print(f"  {entry['version']:>4}  {entry['description']}")

    if args.dry_run:
        print()
        print("Dry run. Nothing was applied. A backup is taken automatically when you")
        print("run this for real, or on the next application start.")
        return 0

    conn = sqlite_open.connect(paths.get_db_path())
    try:
        report = migration_ledger.ensure_schema(conn)
    finally:
        conn.close()

    if report["backup_path"]:
        print(f"\nBackup taken: {report['backup_path']}")
    for applied in report["applied"]:
        print(f"  applied {applied['version']}: {applied['description']}")
    print(f"\nSchema is now at version {report['to_version']}.")
    return 0


def cmd_update(args) -> int:
    if args.action in ("enable", "disable") and not os.path.exists(paths.get_db_path()):
        print(f"No studio database at {paths.get_db_path()} yet, so one is created there to hold")
        print("this choice, as the first start would. If your data is somewhere else, run `paths`.")
        print()

    if args.action == "enable":
        updates.set_enabled(True)
        print("Update checks ENABLED.")
        print()
        print("Inox Hydra will fetch a small version file from GitHub when you ask it to.")
        print("Nothing about you or your content is sent. Disable anytime with:")
        print("  python -m studio.cli update disable")
        return 0

    if args.action == "disable":
        updates.set_enabled(False)
        print("Update checks DISABLED. No outbound requests will be made.")
        return 0

    if args.action == "status":
        _print_kv("Update check status:", updates.describe())
        return 0

    status = updates.check_for_update(force=args.force)
    if not status["checked"]:
        print(status["reason"])
        print()
        print("Enable with: python -m studio.cli update enable")
        print(f"Or check manually at: {updates.RELEASES_PAGE}")
        return 0

    if status.get("error"):
        print(f"Could not check for updates: {status['error']}")
        print(f"Check manually at: {status['releases_url']}")
        return 1

    print(f"Installed: {status['current_version']}")
    print(f"Latest:    {status['latest_version']}")
    print()
    if status["update_available"]:
        print("An update is available.")
        if status.get("notes"):
            print(f"\n{status['notes']}\n")
        print(f"Download it from: {status['releases_url']}")
        print()
        # In true portable mode, and in a source checkout, the data is inside
        # the folder. This used to tell everyone to delete that folder.
        data_home = paths.get_app_home()
        program_folder = os.path.dirname(os.path.abspath(paths._STUDIO_DIR))
        try:
            inside = os.path.commonpath([os.path.abspath(data_home), program_folder]) == program_folder
        except ValueError:
            inside = False
        if paths.is_portable() or inside:
            print(f"Your data is INSIDE the Inox Hydra folder, at {data_home}.")
            print("Do not delete that folder. First back up every profile with `backup --all`.")
            print("Then replace only the program files, and keep data, assets, backups, vault,")
            print("logs, profiles and exports where they are. The help article \"Check your")
            print("version and update the studio\" walks through it.")
        else:
            print("To upgrade: delete your Inox Hydra folder and extract the new one.")
            print(f"Your data lives outside that folder, in {data_home}, so it is not affected.")
    else:
        print("You are up to date.")
    return 0


def cmd_token(args) -> int:
    """
    Shows or rotates the token the API requires.

    Normally nobody needs this: the interface receives the token as a cookie
    and the extension reads it through the cookies permission. It exists for
    the case where a client needs pairing by hand, and for revoking access if
    the token is ever believed to have leaked.
    """
    from studio.backend import security

    if args.action == "reset":
        token = security.reset_token()
        print("A new token was issued. Every paired client must be reconnected.")
        print("Reload the studio in your browser, and reload the extension.")
    else:
        token = security.get_or_create_token()

    _print_kv("API token", {
        "token": token,
        "header": security.TOKEN_HEADER,
        "accepted origins": ", ".join(sorted(security.allowed_origins())) + ", chrome-extension://<id>",
    })
    print("\nTreat this like a password. Anything holding it can read and write your studio.\n")
    return 0


def _profile_options(parser, allow_all: bool) -> None:
    parser.add_argument("--profile", metavar="ID",
                        help="The creator profile to act on (default: the active one). "
                             "Works for a profile the licence no longer opens, too")
    if allow_all:
        parser.add_argument("--all", dest="all_profiles", action="store_true",
                            help="Every creator profile on this machine, one after another")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="studio.cli",
        description=f"Inox Hydra {__version__} support toolkit.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"Inox Hydra {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("doctor", help="Health summary and diagnostics bundle")
    p.add_argument("--bundle", action="store_true", help="Write a redacted report to a file")
    p.add_argument("--output", help="Where to write the bundle")
    _profile_options(p, allow_all=False)
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("paths", help="Show where this installation keeps its data")
    p.set_defaults(func=cmd_paths)

    p = sub.add_parser("backup", help="Snapshot database and media into a ZIP")
    p.add_argument("--label", default="manual", help="Label included in the filename")
    _profile_options(p, allow_all=True)
    p.set_defaults(func=cmd_backup)

    p = sub.add_parser("restore", help="Replace current state with a backup")
    p.add_argument("archive", help="Path to a backup ZIP")
    p.add_argument("--yes", action="store_true", help="Confirm this destructive action")
    p.add_argument("--into-active-profile", action="store_true",
                   help="Restore a backup of another creator profile into the active one")
    _profile_options(p, allow_all=False)
    p.set_defaults(func=cmd_restore)

    p = sub.add_parser("export", help="Write your content to JSON, CSV, or an Obsidian vault")
    p.add_argument("--format", choices=list(support.EXPORT_FORMATS), default="json")
    p.add_argument("--output", help="Destination file, or folder for --format obsidian")
    _profile_options(p, allow_all=True)
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("reset", help="Clear configuration, keep all content")
    p.add_argument("--yes", action="store_true", help="Confirm")
    p.set_defaults(func=cmd_reset)

    p = sub.add_parser("migrate", help="Show or apply pending schema migrations")
    p.add_argument("--dry-run", action="store_true", help="List pending work without applying")
    p.set_defaults(func=cmd_migrate)

    p = sub.add_parser("token", help="Show or rotate this installation's API token")
    p.add_argument("action", nargs="?", default="show", choices=["show", "reset"])
    p.set_defaults(func=cmd_token)

    p = sub.add_parser("update", help="Check for a newer release")
    p.add_argument("action", nargs="?", default="check",
                   choices=["check", "enable", "disable", "status"])
    p.add_argument("--force", action="store_true", help="Ignore the ETag cache")
    p.set_defaults(func=cmd_update)

    p = sub.add_parser("monitor", help="Live stream monitor for data ingestion and bridge activity")
    p.add_argument("--host", default="127.0.0.1", help="Studio host (default: 127.0.0.1)")
    p.add_argument("--port", type=int, default=8000, help="Studio port (default: 8000)")
    p.add_argument("--interval", type=float, default=2.0, help="Poll interval in seconds (default: 2.0)")
    p.add_argument("--limit", type=int, default=5, help="Items per category to display (default: 5)")
    p.add_argument("--once", action="store_true", help="Print current status once and exit")
    p.add_argument("--json", action="store_true", help="Output stream as JSON")
    p.set_defaults(func=lambda args: __import__("studio.monitor", fromlist=["run_monitor"]).run_monitor(
        host=args.host,
        port=args.port,
        interval=args.interval,
        limit=args.limit,
        once=args.once,
        as_json=args.json,
    ))

    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        try:
            profiles = _chosen_profiles(args)
        except ValueError as refused:
            print(str(refused))
            return 1
        if profiles is None:
            return args.func(args)
        code = 0
        for index, profile_id in enumerate(profiles):
            if index:
                print()
            with paths.using_profile(profile_id):
                code = max(code, args.func(args))
        return code
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130
    except Exception as exc:
        print(f"Error: {exc}")
        print()
        print("If this keeps happening, run `doctor --bundle` and attach the file to an issue.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
