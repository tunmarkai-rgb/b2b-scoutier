#!/usr/bin/env python3
"""Create the local, git-ignored working files (safe to re-run; never overwrites).

    python scripts/init_data.py
"""
import shutil

import queue_md
from common import (CSV_FILES, ENV_FILE, INBOXES_FILE, QUEUE_FILE, REPLIES_DIR, REPORTS, ROOT,
                    SENT_LOG, ensure_csv)


def main():
    created = []
    for name, path in CSV_FILES.items():
        if not path.exists():
            ensure_csv(name)
            created.append(path)
    if not QUEUE_FILE.exists():
        queue_md.save([])
        created.append(QUEUE_FILE)
    if not SENT_LOG.exists():
        SENT_LOG.parent.mkdir(parents=True, exist_ok=True)
        SENT_LOG.write_text("# Sent Log\n\nAppend-only record of every message sent.\n\n", encoding="utf-8")
        created.append(SENT_LOG)
    for src, dst in ((ROOT / "inboxes.example.json", INBOXES_FILE), (ROOT / ".env.example", ENV_FILE)):
        if not dst.exists() and src.exists():
            shutil.copyfile(src, dst)
            created.append(dst)
    for folder in (REPLIES_DIR, REPORTS, ROOT / "logs", ROOT / "outreach" / "work"):
        folder.mkdir(parents=True, exist_ok=True)
    for path in created:
        print(f"created {path.relative_to(ROOT)}")
    if not created:
        print("everything already in place")
    print("\nNext: fill in config/settings.json -> sender, inboxes.json, and app passwords in .env")


if __name__ == "__main__":
    main()
