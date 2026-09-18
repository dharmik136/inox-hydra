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
    export      Write drafts, leads and analytics to JSON or CSV
    reset       Clear configuration while keeping all content
    migrate     Show or apply pending database schema migrations
    update      Check for a newer release, opt in, or opt out

Strict Invariants:
- Zero em-dashes.
- Destructive commands require explicit confirmation.
"""

import argparse
import json
import os
import sqlite3
import sys

try:
    from .backend import paths, support, updates
    from .backend import migrations as migration_ledger
    from .__version__ import __version__
except ImportError:  # executed as a loose script
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from studio.backend import paths, support, updates
    from studio.backend import migrations as migration_ledger
    from studio.__version__ import __version__


def _print_kv(title, mapping, indent="  "):
    print(title)
    for key, value in mapping.items():
        print(f"{indent}{key:26s} {value}")


def cmd_doctor(args) -> int:
    report = support.collect_diagnostics()

    print(f"Inox Hydra {report['app_version']} on {report['platform']['system']} "
          f"{report['platform']['release']} (Python {report['platform']['python']})")
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
    else:
        print("  no problems found")
        print()

    if args.bundle:
        destination = support.write_diagnostics_bundle(args.output)
        print(f"Diagnostics bundle written to:\n  {destination}")
        print()
        print("This file is safe to attach to a public issue. Session cookies and API")
        print("keys are redacted. You can open it in any text editor to confirm.")
    else:
        print("Run with --bundle to write a redacted report you can attach to an issue.")
    return 0


def cmd_paths(args) -> int:
    _print_kv(f"Inox Hydra {__version__} locations:", paths.describe())
    return 0


def cmd_backup(args) -> int:
    archive = support.create_backup(args.label)
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

    info = support.inspect_backup(args.archive)
    manifest = info.get("manifest") or {}
    print(f"Backup: {args.archive}")
    print(f"  created      {manifest.get('created_at', 'unknown')}")
    print(f"  app version  {manifest.get('app_version', 'unknown')}")
    print(f"  database     {'yes' if info['has_database'] else 'NO'}")
    print(f"  media files  {info['asset_count']}")
    print()

    if not args.yes:
        print("This REPLACES your current drafts, leads and analytics.")
        print("A safety snapshot of your current state is taken first.")
        print("Re-run with --yes to proceed.")
        return 1

    result = support.restore_backup(args.archive)
    print(f"Restored from {result['restored_from']}")
    print(f"  media files restored  {result['assets_restored']}")
    print(f"  safety snapshot       {result['safety_backup']}")
    print()
    print("Restart Inox Hydra for the restored data to take effect.")
    return 0


def cmd_export(args) -> int:
    destination = support.export_data(args.output, fmt=args.format)
    print(f"Exported {args.format.upper()} to:\n  {destination}")
    print()
    print("This contains your drafts, posts, leads and analytics. It deliberately")
    print("excludes credentials, so it is portable but not a backup. Use `backup`")
    print("if you want something you can restore.")
    return 0


def cmd_reset(args) -> int:
    if not args.yes:
        print("This clears configuration: AI provider settings and the stored LinkedIn")
        print("session. Your drafts, leads and analytics are NOT touched, and a safety")
        print("snapshot is taken first.")
        print()
        print("Re-run with --yes to proceed.")
        return 1

    result = support.reset_configuration(keep_data=True)
    for table, count in result["cleared"].items():
        print(f"  cleared {count} rows from {table}")
    print(f"  safety snapshot  {result['safety_backup']}")
    print()
    print("Reconfigure your AI provider with: python studio_cli.py ai configure")
    return 0


def cmd_migrate(args) -> int:
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

    conn = sqlite3.connect(paths.get_db_path())
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
        print("To upgrade: delete your Inox Hydra folder and extract the new one.")
        print("Your data lives outside that folder, so it is not affected.")
    else:
        print("You are up to date.")
    return 0


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
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("paths", help="Show where this installation keeps its data")
    p.set_defaults(func=cmd_paths)

    p = sub.add_parser("backup", help="Snapshot database and media into a ZIP")
    p.add_argument("--label", default="manual", help="Label included in the filename")
    p.set_defaults(func=cmd_backup)

    p = sub.add_parser("restore", help="Replace current state with a backup")
    p.add_argument("archive", help="Path to a backup ZIP")
    p.add_argument("--yes", action="store_true", help="Confirm this destructive action")
    p.set_defaults(func=cmd_restore)

    p = sub.add_parser("export", help="Write your content to JSON or CSV")
    p.add_argument("--format", choices=["json", "csv"], default="json")
    p.add_argument("--output", help="Destination file")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("reset", help="Clear configuration, keep all content")
    p.add_argument("--yes", action="store_true", help="Confirm")
    p.set_defaults(func=cmd_reset)

    p = sub.add_parser("migrate", help="Show or apply pending schema migrations")
    p.add_argument("--dry-run", action="store_true", help="List pending work without applying")
    p.set_defaults(func=cmd_migrate)

    p = sub.add_parser("update", help="Check for a newer release")
    p.add_argument("action", nargs="?", default="check",
                   choices=["check", "enable", "disable", "status"])
    p.add_argument("--force", action="store_true", help="Ignore the ETag cache")
    p.set_defaults(func=cmd_update)

    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
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
