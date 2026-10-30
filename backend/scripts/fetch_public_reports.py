"""Download the public research PDFs listed in data/public/manifest.json into data/public/pdfs/.

    python scripts/fetch_public_reports.py            download what is missing, verify every file
    python scripts/fetch_public_reports.py --check    only verify what is already downloaded
    python scripts/fetch_public_reports.py --force    download again even if present

Only official publisher URLs are used. Some publishers (bsp.gov.ph, adb.org) refuse scripted
downloads; the script does not try to get around that. It prints the URL instead: open it in a
browser, save the file as data/public/pdfs/<slug>.pdf, and run --check. Every file is verified
against the sha256 recorded in the manifest, so a changed or wrong file is reported, not used.

The PDFs are third-party material under their own licences (see the manifest) and are git-ignored.
Never commit them.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.public_sources import PDF_DIR, load_manifest  # noqa: E402

USER_AGENT = "si-evidence-assistant/0.2 (research prototype; fetches public reports for evaluation)"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(entry: dict, path: Path) -> str:
    if not path.exists():
        return "missing"
    data = path.read_bytes()
    if not data.startswith(b"%PDF"):
        return "not a PDF"
    if entry.get("sha256") and hashlib.sha256(data).hexdigest() != entry["sha256"]:
        return "checksum differs from the manifest (the publisher may have updated the file)"
    return "ok"


def download(entry: dict, path: Path, client: httpx.Client) -> str:
    tmp = path.with_suffix(".part")
    try:
        with client.stream("GET", entry["url"]) as response:
            if response.status_code != 200:
                return f"HTTP {response.status_code}"
            with tmp.open("wb") as fh:
                for chunk in response.iter_bytes():
                    fh.write(chunk)
    except httpx.HTTPError as exc:
        tmp.unlink(missing_ok=True)
        return f"download failed: {exc}"
    tmp.replace(path)
    return verify(entry, path)


def fetch(force: bool = False, check_only: bool = False, only: list[str] | None = None) -> dict[str, str]:
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    results: dict[str, str] = {}
    with httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=120) as client:
        for entry in (e for e in load_manifest() if not only or e["slug"] in only):
            path = PDF_DIR / f"{entry['slug']}.pdf"
            status = verify(entry, path)
            if not check_only and (force or status != "ok"):
                status = download(entry, path, client)
                if status != "ok" and verify(entry, path) == "ok":
                    status = "ok"   # the download failed but the file already there is the right one
                elif status != "ok" and path.exists():
                    path.unlink()   # never leave a wrong file where seeding would pick it up
            results[entry["slug"]] = status
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="verify downloaded files without fetching")
    parser.add_argument("--force", action="store_true", help="download again even if a valid file exists")
    parser.add_argument("--only", nargs="+", metavar="SLUG", help="limit to these manifest slugs")
    args = parser.parse_args()
    results = fetch(force=args.force, check_only=args.check, only=args.only)
    entries = {e["slug"]: e for e in load_manifest()}
    for slug, status in results.items():
        print(f"{'ok  ' if status == 'ok' else 'MISS'} {slug}: {status}")
        if status != "ok":
            print(f"     Save {entries[slug]['url']}\n     as {PDF_DIR / (slug + '.pdf')}")
    ok = sum(1 for s in results.values() if s == "ok")
    print(f"{ok} of {len(results)} public reports available in {PDF_DIR}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
