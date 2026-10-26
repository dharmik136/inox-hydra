"""
Library Bundle: the Vendor's Side of the Signed Inox Library.
=============================================================
The Inox library is a file of forms, patterns and examples the company
wrote, signed once on the vendor's machine and verified by every studio
with the public key it ships (studio/backend/library_bundle.py,
PUBLIC_KEYS). Three commands, run on the vendor's machine and nowhere else:

  new-keypair   Creates the Ed25519 signing key. The secret half is written to
                a folder outside this repository, readable only by you; the
                public half is printed with its key id, to paste into
                PUBLIC_KEYS. The secret key is the whole library's integrity:
                anyone holding it can put words in front of every creator.
                Keep it offline, never in this repository, a chat or a CI
                secret a pull request can read.
  sign          Signs a source file of entries (JSON, below) into a bundle.
  verify        Checks a bundle against PUBLIC_KEYS (or --public) and prints
                what it holds, so a file is read before it is published.

Usage:
  python tools/library_bundle.py new-keypair --out ~/.config/inox-hydra/library-signing --key-id inox-library-2026-10
  python tools/library_bundle.py sign --key ~/.config/inox-hydra/library-signing/ed25519.secret \\
      --in entries.json --out library_v1.ilb --version 2026.10.1 --key-id inox-library-2026-10
  python tools/library_bundle.py verify --in library_v1.ilb

The source file (entries.json):

  {"entries": [{"id": "form-story-turn", "kind": "form", "title": "The turn",
                "text": "Open on the moment you changed your mind about [topic]...",
                "tags": ["story", "hiring"]}, ...]}

  id     lower-case letters, digits and hyphens, 3 to 80, unique
  kind   form, pattern or example
  title  up to 200 characters; text up to 2,000; at most 12 tags of 40
  Only material the company wrote, or holds written permission for: never a
  post copied from LinkedIn, never a link to one (ideas report decision 11).

The bundle file (what the studio fetches or imports), one line of ASCII:

  ILB1.<payload>.<signature>

  payload    base64url, no padding, of the UTF-8 JSON (keys sorted, no
             spaces) {"format": "inox-library", "format_version": 1,
             "version": ..., "signed_at": "YYYY-MM-DD", "key_id": ...,
             "publisher": "Inox Hydra", "content_policy": "company-authored",
             "entries": [... each with "author": "Inox Hydra" ...]}
  signature  base64url, no padding, of the Ed25519 signature over the ASCII
             bytes "ILB1.<payload>"

The same shape as the offline licence (IHL1), with its own prefix and its
own key, so a licence key can never sign a library and the reverse.

Strict Invariants:
- Zero em-dashes in any code, docstring or comment.
- The secret key is never written inside this repository.
"""

import argparse
import base64
import json
import os
import stat
import sys
from datetime import date
from typing import Any, Dict

REPO = os.path.realpath(os.path.join(os.path.dirname(os.path.realpath(__file__)), ".."))
sys.path.insert(0, os.path.join(REPO, "studio", "backend"))

import ed25519  # noqa: E402
import library_bundle  # noqa: E402

SECRET_NAME = "ed25519.secret"


def _inside_repo(path: str) -> bool:
    path = os.path.realpath(path)
    try:
        return os.path.commonpath([path, REPO]) == REPO
    except ValueError:
        return False


def new_keypair(out: str, key_id: str) -> int:
    out = os.path.abspath(os.path.expanduser(out))
    if _inside_repo(out):
        print(f"Refusing to write a signing key inside the repository ({out}).", file=sys.stderr)
        return 2
    target = os.path.join(out, SECRET_NAME)
    if os.path.exists(target):
        print(f"{target} already exists. Move it away first if you really mean to replace it: every bundle "
              "signed with it stops verifying once its public key is removed.", file=sys.stderr)
        return 2
    os.makedirs(out, mode=0o700, exist_ok=True)
    secret = os.urandom(32)
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(fd, "w", encoding="ascii") as handle:
        handle.write(secret.hex() + "\n")
    public = base64.b64encode(ed25519.public_key(secret)).decode("ascii")
    print(f"Secret key written to {target} (readable by you only). Back it up offline.")
    print("For PUBLIC_KEYS in studio/backend/library_bundle.py:")
    print(f'    "{key_id}": "{public}",')
    return 0


def build_content(source: Dict[str, Any], version: str, key_id: str, signed_at: str) -> Dict[str, Any]:
    entries = []
    for entry in source.get("entries") or []:
        entries.append({**{k: entry.get(k) for k in ("id", "kind", "title", "text", "tags")},
                        "author": library_bundle.PUBLISHER})
    return {"format": library_bundle.FORMAT, "format_version": library_bundle.FORMAT_VERSION, "version": version,
            "signed_at": signed_at, "key_id": key_id, "publisher": library_bundle.PUBLISHER,
            "content_policy": library_bundle.CONTENT_POLICY, "entries": entries}


def sign(key: str, source_path: str, out: str, version: str, key_id: str, signed_at: str = "") -> int:
    with open(os.path.expanduser(key), "r", encoding="ascii") as handle:
        secret = bytes.fromhex(handle.read().strip())
    with open(source_path, "r", encoding="utf-8") as handle:
        source = json.load(handle)
    content = build_content(source, version, key_id, signed_at or date.today().isoformat())
    try:
        library_bundle.validate(content)
    except library_bundle.LibraryRefused as refused:
        print(f"Not signed: {refused}", file=sys.stderr)
        return 1
    text = library_bundle.encode(content, lambda message: ed25519.sign(secret, message))
    public = base64.b64encode(ed25519.public_key(secret)).decode("ascii")
    library_bundle.verify(text, keys={key_id: public})
    with open(out, "w", encoding="ascii") as handle:
        handle.write(text + "\n")
    print(f"Signed {len(content['entries'])} entries as bundle {version} with key {key_id}: {out}")
    return 0


def verify(path: str, public: str = "", key_id: str = "") -> int:
    with open(path, "r", encoding="ascii") as handle:
        text = handle.read().strip()
    keys = {key_id: public} if public and key_id else None
    try:
        content = library_bundle.verify(text, keys=keys)
        entries = library_bundle.validate(content)
    except library_bundle.LibraryRefused as refused:
        print(f"Refused: {refused}", file=sys.stderr)
        return 1
    print(f"Bundle {content['version']}, signed {content['signed_at']} with {content['key_id']}: "
          f"{len(entries)} entries, " + ", ".join(sorted({e['kind'] for e in entries})))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    pair = commands.add_parser("new-keypair")
    pair.add_argument("--out", required=True)
    pair.add_argument("--key-id", required=True)
    signing = commands.add_parser("sign")
    signing.add_argument("--key", required=True)
    signing.add_argument("--in", dest="source", required=True)
    signing.add_argument("--out", required=True)
    signing.add_argument("--version", required=True)
    signing.add_argument("--key-id", required=True)
    signing.add_argument("--signed-at", default="")
    checking = commands.add_parser("verify")
    checking.add_argument("--in", dest="source", required=True)
    checking.add_argument("--public", default="", help="a base64 public key, instead of PUBLIC_KEYS")
    checking.add_argument("--key-id", default="")
    args = parser.parse_args(argv)
    if args.command == "new-keypair":
        return new_keypair(args.out, args.key_id)
    if args.command == "sign":
        return sign(args.key, args.source, args.out, args.version, args.key_id, args.signed_at)
    return verify(args.source, args.public, args.key_id)


if __name__ == "__main__":
    sys.exit(main())
