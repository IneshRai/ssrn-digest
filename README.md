# ssrn-digest

Weekly digest of the top 25 papers by downloads added to SSRN's Financial
Economics Network in the trailing 7 days. Pulls from SSRN's unofficial JSON
API (the same one that powers ssrn.com/browse), ranks by download count, and
prints a readable digest plus a JSON output file.

Roadmap: arXiv q-fin as a second source, downloads-per-day ranking, HTML
email delivery on a Monday morning schedule.

## Setup

```
pip install -r requirements.txt
```

## Usage

First run: confirm the API responds from your network and identify the
Financial Economics Network binding ID.

```
python ssrn_digest.py --discover
```

Normal run:

```
python ssrn_digest.py
```

Options:

```
python ssrn_digest.py --binding 203 --days 7 --top 25
```

## Outputs

- Digest printed to stdout
- `digest_YYYY-MM-DD.json` with the ranked papers (gitignored)
- `debug/` with every raw API response for troubleshooting (gitignored)

## Notes

- The binding ID for the Financial Economics Network defaults to 203 but is
  unverified. Use `--discover` to confirm.
- SSRN sits behind Cloudflare. If requests return 403, the fallback is
  swapping `requests` for `curl_cffi`.
- Papers with unparseable dates or missing download counts are skipped and
  reported; field-name candidates live at the top of `ssrn_digest.py`.
