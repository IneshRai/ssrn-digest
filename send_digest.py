import argparse
import glob
import json
import os
import re
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# smtp config comes from env vars or flags, works with any provider
#   SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD

TAG_COLORS = {
    "Fin Econ": "#1a3e6e",
    "Derivatives": "#5a7d2a",
    "Capital Markets": "#8a5a2a",
}


def latest_digest():
    files = sorted(glob.glob("digest_*.json"))
    if not files:
        sys.exit("no digest_*.json found, run ssrn_digest.py first")
    return files[-1]


def row(i, p):
    auth = ", ".join(p["authors"][:4]) + (" et al." if len(p["authors"]) > 4 else "")
    color = TAG_COLORS.get(p.get("network"), "#666")
    tag = (f'<span style="font-family:Helvetica,Arial,sans-serif;font-size:10px;color:#fff;'
           f'background:{color};border-radius:3px;padding:2px 6px;margin-left:8px;'
           f'vertical-align:middle;">{p.get("network", "")}</span>')
    return f"""
    <tr>
      <td style="padding:14px 12px;border-bottom:1px solid #e5e5e5;vertical-align:top;
                 font-family:Georgia,serif;font-size:15px;color:#999;width:28px;">{i}</td>
      <td style="padding:14px 12px 14px 0;border-bottom:1px solid #e5e5e5;">
        <a href="{p['url']}" style="font-family:Georgia,serif;font-size:16px;color:#1a3e6e;
           text-decoration:none;font-weight:bold;">{p['title']}</a>{tag}
        <div style="font-family:Helvetica,Arial,sans-serif;font-size:13px;color:#555;
                    margin-top:4px;">{auth}</div>
        <div style="font-family:Helvetica,Arial,sans-serif;font-size:12px;color:#999;
                    margin-top:3px;">Posted {p['posted']} &middot; {p['downloads']:,} downloads</div>
      </td>
    </tr>"""


def build_html(papers, date, days, composition):
    mix = ", ".join(f"{c['quota']} {c['label']}" for c in composition)
    rows = "".join(row(i, p) for i, p in enumerate(papers, 1))
    return f"""
<html>
<body style="margin:0;padding:0;background:#f5f5f2;">
  <div style="max-width:640px;margin:0 auto;padding:24px 16px;">
    <div style="background:#fff;border:1px solid #e0e0dc;border-radius:6px;padding:28px;">
      <h1 style="font-family:Georgia,serif;font-size:22px;color:#222;margin:0 0 4px 0;">
        SSRN Weekly Digest</h1>
      <p style="font-family:Helvetica,Arial,sans-serif;font-size:13px;color:#777;margin:0 0 20px 0;">
        Top {len(papers)} papers &middot; week ending {date} &middot; {mix}</p>
      <table style="width:100%;border-collapse:collapse;">{rows}</table>
      <p style="font-family:Helvetica,Arial,sans-serif;font-size:11px;color:#aaa;margin:20px 0 0 0;">
        Papers posted to SSRN in the last {days} days, ranked by downloads.
        Cross-listed papers appear once.</p>
    </div>
  </div>
</body>
</html>"""


def build_text(papers, date):
    lines = [f"SSRN Weekly Digest - week ending {date}", ""]
    for i, p in enumerate(papers, 1):
        lines.append(f"{i}. {p['title']} ({p.get('network', '')})")
        lines.append(f"   {', '.join(p['authors'][:4])}")
        lines.append(f"   {p['downloads']} downloads | {p['posted']} | {p['url']}")
        lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--to", default=os.environ.get("SSRN_DIGEST_TO"))
    ap.add_argument("--sender", default=os.environ.get("SSRN_DIGEST_FROM"))
    ap.add_argument("--file", default=None)
    ap.add_argument("--smtp-host", default=os.environ.get("SMTP_HOST"))
    ap.add_argument("--smtp-port", type=int, default=int(os.environ.get("SMTP_PORT", "465")))
    ap.add_argument("--smtp-user", default=os.environ.get("SMTP_USER"))
    args = ap.parse_args()

    if not args.sender or not args.to:
        sys.exit("need --to and --sender (or SSRN_DIGEST_TO / SSRN_DIGEST_FROM env vars)")
    if not args.smtp_host:
        sys.exit("need --smtp-host (or SMTP_HOST env var)")

    user = args.smtp_user or args.sender
    password = re.sub(r"\s", "", os.environ.get("SMTP_PASSWORD", ""))
    if not password:
        sys.exit("SMTP_PASSWORD not set")

    path = args.file or latest_digest()
    data = json.loads(open(path).read())
    papers = data["papers"]
    date = data["generated"]
    to_addrs = [a.strip() for a in args.to.split(",") if a.strip()]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"SSRN Weekly Digest: Top {len(papers)} Papers ({date})"
    msg["From"] = args.sender
    msg["To"] = ", ".join(to_addrs)
    msg.attach(MIMEText(build_text(papers, date), "plain"))
    msg.attach(MIMEText(build_html(papers, date, data["window_days"], data["composition"]), "html"))

    print(f"sending {path} ({len(papers)} papers) to {', '.join(to_addrs)} via {args.smtp_host}")
    if args.smtp_port == 587:
        server = smtplib.SMTP(args.smtp_host, args.smtp_port)
        server.starttls()
    else:
        server = smtplib.SMTP_SSL(args.smtp_host, args.smtp_port)
    with server:
        server.login(user, password)
        server.sendmail(args.sender, to_addrs, msg.as_string())
    print("sent")


if __name__ == "__main__":
    main()