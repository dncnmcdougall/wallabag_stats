# SPDX-FileCopyrightText: 2026 Duncan McDougall
#
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path
import requests
from dateutil import parser
from dateutil.relativedelta import relativedelta
from datetime import datetime, timezone
from collections import defaultdict
import tomllib
from dataclasses import dataclass
from getpass import getpass
from icecream import ic


@dataclass
class Options:
    WALLABAG_BASE: str
    CLIENT_ID: str
    CLIENT_SECRET: str
    USERNAME: str
    ASSUME_MIN_PER_UNFETCHED: int

    PASSWORD: str | None

    @staticmethod
    def from_toml(path: Path):
        with open(path, "rb") as config_fp:
            cfg = tomllib.load(config_fp).get("wallabag")
            conf = {
                "WALLABAG_BASE": cfg.get("WALLABAG_BASE", "").rstrip("/"),
                "CLIENT_ID": cfg.get("CLIENT_ID"),
                "CLIENT_SECRET": cfg.get("CLIENT_SECRET"),
                "USERNAME": cfg.get("USERNAME"),
                "ASSUME_MIN_PER_UNFETCHED": cfg.get("ASSUME_MIN_PER_UNFETCHED", 10),
                "PASSWORD": None,
            }

        return Options(**conf)


def get_access_token(opt: Options):
    token_url = f"{opt.WALLABAG_BASE}/oauth/v2/token"
    data = {
        "grant_type": "password",
        "client_id": opt.CLIENT_ID,
        "client_secret": opt.CLIENT_SECRET,
        "username": opt.USERNAME,
        "password": opt.PASSWORD,
    }
    r = requests.post(token_url, data=data)
    r.raise_for_status()
    return r.json()["access_token"]


def fetch_all_entries(token, opt: Options):
    headers = {"Authorization": f"Bearer {token}"}
    entries = []
    page = 1
    while True:
        print(f"Loading page: {page}.")
        url = f"{opt.WALLABAG_BASE}/api/entries.json?page={page}"
        r = requests.get(
            url, headers=headers, params=dict(archive=1, detail="metadata")
        )
        if not r.ok:
            print(r)
            print("Not OK, stopping")
            break
        r.raise_for_status()
        data = r.json()
        if not data:
            print(r)
            print("No data, stopping")
            break
        entries.extend(data["_embedded"]["items"])
        page += 1
    return entries


def parse_date(datestr):
    return parser.isoparse(datestr).astimezone(timezone.utc)


def compute_stats(entries, opt: Options):
    now = datetime.now(timezone.utc)
    periods = {
        "week": now - relativedelta(days=7),
        "month": now - relativedelta(days=30),
        "year": now - relativedelta(days=365),
    }
    stats = {}
    for k in periods:
        stats[k] = {"articles": 0, "minutes": 0.0, "days": 0}
    stats["week"]["days"] = 7
    stats["month"]["days"] = 30
    stats["year"]["days"] = 365

    for e in entries:
        try:
            created = parse_date(e.get("created_at") or e.get("updated_at"))
        except:
            ic(e)
            raise
        reading_time = e.get("reading_time")
        try:
            minutes = (
                float(reading_time)
                if reading_time not in (None, "", "0")
                else opt.ASSUME_MIN_PER_UNFETCHED
            )
        except Exception:
            minutes = opt.ASSUME_MIN_PER_UNFETCHED

        for k, start in periods.items():
            if created >= start and created <= now:
                stats[k]["articles"] += 1
                stats[k]["minutes"] += minutes

    for k in stats:
        stats[k]["minutes"] = round(stats[k]["minutes"], 2)
    return stats


def main():
    opt = Options.from_toml(Path("./config.toml"))
    opt.PASSWORD = getpass()
    token = get_access_token(opt)
    entries = fetch_all_entries(token, opt)
    stats = compute_stats(entries, opt)
    print("Wallabag reading stats (assume missing reading_time = 10 min):")
    for period in ("week", "month", "year"):
        articles = stats[period]["articles"]
        minutes = stats[period]["minutes"]
        days = stats[period]["days"]
        print(f"{period.capitalize(): >7}: {articles} articles , {minutes} minutes.")
        print(
            f"{' ' * 7}: {articles / days:.1f} articles and {minutes / days:.1f} minutes per day."
        )


if __name__ == "__main__":
    main()
