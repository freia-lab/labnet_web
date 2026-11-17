#!/usr/bin/env python3
"""Generate a hashed password for LABNET_PASS_HASH.

Usage:
    python3 gen_password_hash.py
"""
import getpass, secrets
from werkzeug.security import generate_password_hash

pw  = getpass.getpass("New password: ")
pw2 = getpass.getpass("Confirm: ")
if pw != pw2:
    print("Passwords do not match.")
else:
    h   = generate_password_hash(pw)
    sec = secrets.token_hex(32)
    print("\nAdd to your environment (e.g. ~/.bashrc or systemd unit).")
    print("NOTE: single quotes are required — the hash contains $ characters.\n")
    print(f"export LABNET_USER='admin'")
    print(f"export LABNET_PASS_HASH='{h}'")
    print(f"export LABNET_SECRET='{sec}'")
