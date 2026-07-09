"""
Send the SSRN digest as an HTML email via Gmail SMTP.

Configuration comes from flags or environment variables, nothing personal
is hardcoded:

    SSRN_DIGEST_APP_PASSWORD   Gmail app password (required)
    SSRN_DIGEST_FROM           Gmail address to send from (or use --sender)
    SSRN_DIGEST_TO             recipient address(es), comma separated (or use --to)

Gmail setup (one time, for the sending account):
    1. Google Account > Security > 2-Step Verification (must be on)
    2. Google Account > Security > App passwords > create one
    3. export SSRN_DIGEST_APP_PASSWORD="the 16 char code"
       (spaces from Google's display are fine, they get stripped)

Usage:
    python ssrn_digest.py
    python send_digest.py --sender you@gmail.com --to you@gmail.com

    python send_digest.py --sender you@gmail.com --to a@x.com,b@y.com --file digest_2026-07-09.json

If SSRN_DIGEST_FROM and SSRN_DIGEST_TO are exported, flags can be omitted:
    python send_digest.py
"""

import argparse
import glob
import json
import os
import re
import smtplib
import sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

APP_PASSWORD_ENV = "SSRN_DIGEST_APP_PASSWORD"
FROM_ENV = "SSRN_DIGEST_FROM"
TO_ENV = "SSRN_DIGEST_TO"


def find_latest_digest():
    files = sorted(glob.glob("digest_*.json"))
    if not files:
        print("No digest_*.json found in the current directory.")
        print("Run ssrn_digest.py first.")
        sys.exit(1)
    return files[-1]


def render_html(papers, digest_date):
    rows = []
    for i, p in enumerate(papers, 1):
        authors = ", ".join(p.get("authors", [])[:4])
        if len(p.get("authors", [])) > 4:
            authors += " et al."
        downloads = p.get("downloads")
        metric = f"{downloads:,} downloads" if downloads is not None else ""
        posted = p.get("posted", "")
        url = p.get("url", "#")
        title = p.get("title", "(no title)")

        rows.append(f"""
        <tr>
          <td style="padding:14px 12px;border-bottom:1px solid #e5e5e5;vertical-align:top;
                     font-family:Georgia,serif;font-size:15px;color:#999;width:28px;">{i}</td>
          <td style="padding:14px 12px 14px 0;border-bottom:1px solid #e5e5e5;">
            <a href="{url}" style="font-family:Georgia,serif;font-size:16px;color:#1a3e6e;
               text-decoration:none;font-weight:bold;">{title}</a>
            <div style="font-family:Helvetica,Arial,sans-serif;font-size:13px;color:#555;
                        margin-top:4px;">{authors}</div>
            <div style="font-family:Helvetica,Arial,sans-serif;font-size:12px;color:#999;
                        margin-top:3px;">Posted {posted} &middot; {metric}</div>
          </td>
        </tr>""")

    return f"""
<html>
<body style="margin:0;padding:0;background:#f5f5f2;">
  <div style="max-width:640px;margin:0 auto;padding:24px 16px;">
    <div style="background:#ffffff;border:1px solid #e0e0dc;border-radius:6px;padding:28px;">
      <h1 style="font-family:Georgia,serif;font-size:22px;color:#222;margin:0 0 4px 0;">
        SSRN Weekly Digest
      </h1>
      <p style="font-family:Helvetica,Arial,sans-serif;font-size:13px;color:#777;margin:0 0 20px 0;">
        Top {len(papers)} papers on the Financial Economics Network &middot; week ending {digest_date}
      </p>
      <table style="width:100%;border-collapse:collapse;">
        {''.join(rows)}
      </table>
      <p style="font-family:Helvetica,Arial,sans-serif;font-size:11px;color:#aaa;margin:20px 0 0 0;">
        Ranked by total downloads among papers posted in the last 7 days.
        Generated automatically from SSRN data.
      </p>
    </div>
  </div>
</body>
</html>"""


def render_plaintext(papers, digest_date):
    lines = [f"SSRN Weekly Digest - week ending {digest_date}", ""]
    for i, p in enumerate(papers, 1):
        authors = ", ".join(p.get("authors", [])[:4])
        lines.append(f"{i}. {p.get('title')}")
        if authors:
            lines.append(f"   {authors}")
        lines.append(f"   {p.get('downloads', '?')} downloads | posted {p.get('posted')} | {p.get('url')}")
        lines.append("")
    return "\n".join(lines)


def send(to_addrs, from_addr, digest_file):
    password = re.sub(r"\s", "", os.environ.get(APP_PASSWORD_ENV, "")) or None
    if not password:
        print(f"Environment variable {APP_PASSWORD_ENV} is not set.")
        print("Create a Gmail app password for the sending account")
        print("(Google Account > Security > App passwords), then run:")
        print(f'    export {APP_PASSWORD_ENV}="the 16 char code"')
        sys.exit(1)
    if len(password) != 16:
        print(f"Warning: app password is {len(password)} characters after stripping")
        print("whitespace, expected 16. Login will likely fail. Re-copy the code")
        print("from Google and re-export it.")

    with open(digest_file) as f:
        papers = json.load(f)

    digest_date = digest_file.replace("digest_", "").replace(".json", "")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"SSRN Weekly Digest: Top {len(papers)} Finance Papers ({digest_date})"
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_addrs)
    msg.attach(MIMEText(render_plaintext(papers, digest_date), "plain"))
    msg.attach(MIMEText(render_html(papers, digest_date), "html"))

    print(f"Sending {digest_file} ({len(papers)} papers) to {', '.join(to_addrs)} ...")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(from_addr, password)
        server.sendmail(from_addr, to_addrs, msg.as_string())
    print(f"Sent at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--to", default=os.environ.get(TO_ENV), help="recipient address(es), comma separated")
    ap.add_argument("--sender", default=os.environ.get(FROM_ENV), help="Gmail address to send from")
    ap.add_argument("--file", default=None, help="digest JSON file (default: newest digest_*.json)")
    args = ap.parse_args()

    if not args.sender:
        print(f"No sender address. Use --sender or export {FROM_ENV}.")
        sys.exit(1)
    if not args.to:
        print(f"No recipient address. Use --to or export {TO_ENV}.")
        sys.exit(1)

    to_addrs = [a.strip() for a in args.to.split(",") if a.strip()]
    digest_file = args.file or find_latest_digest()
    send(to_addrs, args.sender, digest_file)


if __name__ == "__main__":
    main()