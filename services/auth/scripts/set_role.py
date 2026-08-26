#!/usr/bin/env python3
"""Dev/ops tool: assigns an application role (and optionally a display
name) to a Firebase user via a custom claim.

This is NOT an API endpoint and is not exposed by the auth service - there
is no user-management feature yet (see the root CLAUDE.md's "Current
Goal"). It exists because without some way to set the `role` custom claim,
nothing can read one back: `/api/v1/me` and shared/auth/firebase.py's
AuthenticatedUser.role both depend on this claim already being set.

Requires FIREBASE_PROJECT_ID and FIREBASE_CREDENTIALS_PATH (a real Admin
SDK service account - see services/auth/README.md). Run from the repo
root or services/auth; either way the env vars must already be exported
or present in a loaded .env.

Usage:
    python services/auth/scripts/set_role.py --email teacher@example.com --role TEACHER
    python services/auth/scripts/set_role.py --uid abc123 --role STUDENT --display-name "Aarav Kumar"

Important: a user must sign in again (or force-refresh their ID token) to
see an updated claim - Firebase does not push claim changes to an already
issued token.
"""

from __future__ import annotations

import argparse
import os
import sys

import firebase_admin
from firebase_admin import auth, credentials

VALID_ROLES = ("SUPER_ADMIN", "SCHOOL_ADMIN", "TEACHER", "STUDENT")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    identity = parser.add_mutually_exclusive_group(required=True)
    identity.add_argument("--uid", help="Firebase UID of the user.")
    identity.add_argument("--email", help="Email of the user (resolved to a UID via the Admin SDK).")
    parser.add_argument("--role", required=True, choices=VALID_ROLES)
    parser.add_argument("--display-name", help="Optional: also set the user's Firebase displayName.")
    args = parser.parse_args()

    project_id = os.environ.get("FIREBASE_PROJECT_ID")
    credentials_path = os.environ.get("FIREBASE_CREDENTIALS_PATH")
    if not project_id:
        sys.exit("FIREBASE_PROJECT_ID must be set.")
    if not credentials_path:
        sys.exit(
            "FIREBASE_CREDENTIALS_PATH must be set to a service account JSON - "
            "setting custom claims requires Admin SDK write access, which Application "
            "Default Credentials typically don't grant for this project."
        )

    app = firebase_admin.initialize_app(
        credentials.Certificate(credentials_path), {"projectId": project_id}
    )

    uid = args.uid or auth.get_user_by_email(args.email, app=app).uid

    auth.set_custom_user_claims(uid, {"role": args.role}, app=app)
    if args.display_name:
        auth.update_user(uid, display_name=args.display_name, app=app)

    detail = f", display_name={args.display_name!r}" if args.display_name else ""
    print(f"Set role={args.role} for uid={uid}{detail}")
    print("The user must sign in again (or force-refresh their ID token) to see this change.")


if __name__ == "__main__":
    main()
