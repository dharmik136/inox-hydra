"""
Licence Keys: the Vendor's Side of the Offline Licence.
=======================================================
Two commands, run on the vendor's machine and nowhere else:

  new-keypair   Creates the Ed25519 signing key. The secret half is written to
                a folder outside this repository, readable only by you. The
                public half is printed, to paste into PUBLIC_KEYS in
                studio/backend/licensing.py.
  issue         Signs a licence for one buyer and prints the licence key they
                paste into Brand Studio, Licence.

The secret key is the whole licence system. Anyone holding it can issue a
licence for any tier. Keep one copy in a password manager or on an offline
drive, never in this repository, a chat, a ticket or a CI secret that a pull
request can read. A merchant-of-record webhook that issues licences on
purchase needs it too: give that service its own key, add its public half to
PUBLIC_KEYS, and you can withdraw it without reissuing everyone else.

Usage:
  python tools/licence_keys.py new-keypair --out ~/.config/inox-hydra/licence-signing
  python tools/licence_keys.py issue --key ~/.config/inox-hydra/licence-signing/ed25519.secret \\
      --email buyer@example.com --tier creator --kind annual
"""

import argparse
import base64
import json
import os
import stat
import sys
import uuid
from datetime import date, timedelta

REPO = os.path.realpath(os.path.join(os.path.dirname(os.path.realpath(__file__)), ".."))
sys.path.insert(0, os.path.join(REPO, "studio", "backend"))

import ed25519  # noqa: E402
import licensing  # noqa: E402

SECRET_NAME = "ed25519.secret"


def _inside_repo(path: str) -> bool:
    path = os.path.realpath(path)
    try:
        return os.path.commonpath([path, REPO]) == REPO
    except ValueError:
        # Different drives on Windows: certainly not inside.
        return False


def new_keypair(out: str) -> int:
    out = os.path.abspath(os.path.expanduser(out))
    if _inside_repo(out):
        print(f"Refusing to write a signing key inside the repository ({out}).", file=sys.stderr)
        return 2
    target = os.path.join(out, SECRET_NAME)
    if os.path.exists(target):
        print(f"{target} already exists. Move it away first if you really mean to replace it:", file=sys.stderr)
        print("every licence signed with it stops verifying once its public key is removed.", file=sys.stderr)
        return 2
    os.makedirs(out, mode=0o700, exist_ok=True)
    secret = os.urandom(32)
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(fd, "w", encoding="ascii") as handle:
        handle.write(secret.hex() + "\n")
    public = base64.b64encode(ed25519.public_key(secret)).decode("ascii")
    print(f"Secret key written to {target} (readable by you only). Back it up offline.")
    print("Public key, for PUBLIC_KEYS in studio/backend/licensing.py:")
    print(public)
    return 0


DEFAULT_DAYS = {"annual": 365, "monthly": 31, "lifetime": 365}


def build_payload(email: str, tier: str, kind: str, profiles: int = 0, days: int = 0, name: str = "",
                  today: date = None) -> dict:
    """
    The payload for one licence, or ValueError for one the price list does not sell.

    Creator is one profile, annual or lifetime. Agency is up to five profiles,
    monthly or annual, never lifetime. An annual or monthly licence lapses
    into the free tier on its end date; a lifetime one keeps its tier and is
    owed updates for `days` (a year by default).
    """
    if tier not in licensing.PAID_TIERS:
        raise ValueError(f"tier must be one of {', '.join(licensing.PAID_TIERS)}")
    if kind not in licensing.KINDS:
        raise ValueError(f"kind must be one of {', '.join(licensing.KINDS)}")
    if tier == "agency" and kind == "lifetime":
        raise ValueError("Agency is sold by the month or the year, not for life")
    if tier == "creator" and kind == "monthly":
        raise ValueError("Creator is sold by the year, or for life")
    limit = licensing.TIERS[tier]["profiles"]
    profiles = profiles or limit
    if not 1 <= profiles <= limit:
        raise ValueError(f"{licensing.TIERS[tier]['label']} covers 1 to {limit} profiles")
    days = days or DEFAULT_DAYS[kind]
    if days <= 0:
        raise ValueError("--days must be positive")
    if not email or "@" not in email:
        raise ValueError("--email must be the buyer's address")
    today = today or date.today()
    until = (today + timedelta(days=days)).isoformat()
    return {
        "v": 1,
        "id": str(uuid.uuid4()),
        "email": email,
        "name": name or "",
        "tier": tier,
        "kind": kind,
        "profiles": profiles,
        "issued_at": today.isoformat(),
        "expires_at": None if kind == "lifetime" else until,
        "updates_until": until,
    }


def issue(key: str, email: str, tier: str, kind: str, profiles: int, days: int, name: str) -> int:
    try:
        payload = build_payload(email, tier, kind, profiles, days, name)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    with open(os.path.expanduser(key), "r", encoding="ascii") as handle:
        secret = bytes.fromhex(handle.read().strip())
    licence = licensing.encode(payload, lambda message: ed25519.sign(secret, message))
    read = licensing.read_licence_text(licence)
    if not read["valid"]:
        print("The licence does not verify against PUBLIC_KEYS. Is that key's public half listed there?", file=sys.stderr)
        return 1
    print(licence)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    pair = commands.add_parser("new-keypair")
    pair.add_argument("--out", required=True)
    cut = commands.add_parser("issue")
    cut.add_argument("--key", required=True)
    cut.add_argument("--email", required=True)
    cut.add_argument("--name", default="")
    cut.add_argument("--tier", required=True, choices=list(licensing.PAID_TIERS))
    cut.add_argument("--kind", default="annual", choices=list(licensing.KINDS))
    cut.add_argument("--profiles", type=int, default=0)
    cut.add_argument("--days", type=int, default=365)
    args = parser.parse_args(argv)
    if args.command == "new-keypair":
        return new_keypair(args.out)
    return issue(args.key, args.email, args.tier, args.kind, args.profiles, args.days, args.name)


if __name__ == "__main__":
    sys.exit(main())
