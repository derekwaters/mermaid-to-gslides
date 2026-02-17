#!/usr/bin/env python3
"""
mermaid-to-gslides: Convert a Mermaid flowchart to a Google Slides diagram.

Usage:
  python main.py diagram.mmd
  python main.py diagram.mmd --presentation-id PRESENTATION_ID
  python main.py diagram.mmd --new
  echo "graph TD; A-->B; B-->C;" | python main.py -

Requires Google Cloud project with Slides API enabled and OAuth2 credentials.
See README for setup.
"""
import argparse
import sys
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from mermaid_parser import parse_mermaid
from slides_builder import create_diagram_slide

SCOPES = ["https://www.googleapis.com/auth/presentations", "https://www.googleapis.com/auth/drive.file"]


def get_credentials(credentials_path: str = "credentials.json", token_path: str = "token.json"):
    """Load or obtain OAuth2 credentials."""
    creds = None
    token_p = Path(token_path)
    creds_p = Path(credentials_path)
    if token_p.exists():
        creds = Credentials.from_authorized_user_file(str(token_p), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not creds_p.exists():
                print(
                    "Missing credentials.json. Download OAuth 2.0 client credentials from "
                    "Google Cloud Console and save as credentials.json",
                    file=sys.stderr,
                )
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_p), SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_p, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
    return creds


def create_new_presentation(service, title: str = "Mermaid Diagram"):
    """Create a new presentation and return its ID."""
    body = {"title": title}
    pres = service.presentations().create(body=body).execute()
    return pres.get("presentationId"), pres.get("presentationUrl", "")


def main():
    parser = argparse.ArgumentParser(
        description="Convert a Mermaid flowchart to a Google Slides diagram.",
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="-",
        help="Path to .mmd file or - for stdin",
    )
    parser.add_argument(
        "--presentation-id",
        "-p",
        help="Existing presentation ID to add the diagram slide to",
    )
    parser.add_argument(
        "--new",
        "-n",
        action="store_true",
        help="Create a new presentation (default if no --presentation-id)",
    )
    parser.add_argument(
        "--title",
        "-t",
        default="Mermaid Diagram",
        help="Title for new presentation (default: Mermaid Diagram)",
    )
    parser.add_argument(
        "--credentials",
        default="credentials.json",
        help="Path to OAuth2 credentials JSON (default: credentials.json)",
    )
    parser.add_argument(
        "--token",
        default="token.json",
        help="Path to store OAuth2 token (default: token.json)",
    )
    args = parser.parse_args()

    if args.input == "-":
        source = sys.stdin.read()
    else:
        path = Path(args.input)
        if not path.exists():
            print(f"File not found: {path}", file=sys.stderr)
            sys.exit(1)
        source = path.read_text(encoding="utf-8")

    diagram = parse_mermaid(source)
    if not diagram.nodes and not diagram.edges:
        print("No nodes or edges parsed. Check your Mermaid syntax.", file=sys.stderr)
        sys.exit(1)

    creds = get_credentials(args.credentials, args.token)
    service = build("slides", "v1", credentials=creds)

    presentation_id = args.presentation_id
    if not presentation_id:
        if args.new or not args.presentation_id:
            presentation_id, url = create_new_presentation(service, title=args.title)
            print(f"Created presentation: {url}")
        else:
            print("Specify --presentation-id or --new", file=sys.stderr)
            sys.exit(1)

    slide_id = create_diagram_slide(service, presentation_id, diagram)
    if slide_id:
        pres = service.presentations().get(presentationId=presentation_id).execute()
        url = pres.get("presentationUrl", "")
        print(f"Diagram slide added. Open: {url}")
    else:
        print("Failed to create diagram slide.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
