# SPDX-FileCopyrightText: 2026 Duncan McDougall
#
# SPDX-License-Identifier: Apache-2.0
from copy import copy

from pathlib import Path
import requests
from dateutil import parser
from datetime import datetime, timezone, timedelta
import tomllib
import json
from dataclasses import dataclass, asdict
from getpass import getpass
from icecream import ic
import numpy as np
from bokeh.plotting import figure, show
from bokeh.layouts import row, column


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
            assert cfg is not None
            conf = {
                "WALLABAG_BASE": cfg.get("WALLABAG_BASE", "").rstrip("/"),
                "CLIENT_ID": cfg.get("CLIENT_ID"),
                "CLIENT_SECRET": cfg.get("CLIENT_SECRET"),
                "USERNAME": cfg.get("USERNAME"),
                "ASSUME_MIN_PER_UNFETCHED": cfg.get("ASSUME_MIN_PER_UNFETCHED", 10),
                "PASSWORD": cfg.get("PASSWORD", None),
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


def fetch_all_entries(token, opt: Options, max_page: int | None = None):
    headers = {"Authorization": f"Bearer {token}"}
    entries = []
    page = 1
    while True:
        if max_page is not None and page > max_page:
            print("Reached max page count, stopping")
            break
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


@dataclass
class Entry:
    date: datetime
    minutes: float

    @staticmethod
    def from_json(data, opt: Options) -> "Entry":
        try:
            created = parse_date(data.get("created_at") or data.get("updated_at"))
        except:
            ic(data)
            raise
        reading_time = data.get("reading_time")
        try:
            minutes = (
                float(reading_time)
                if reading_time not in (None, "", "0")
                else opt.ASSUME_MIN_PER_UNFETCHED
            )
        except Exception:
            minutes = opt.ASSUME_MIN_PER_UNFETCHED
        return Entry(created, minutes)


@dataclass
class BarGraph:
    dates: list[datetime]
    articles: list[int]
    minutes: list[float]

    def sort(self):
        new_dates = np.array(self.dates)
        order = np.argsort(new_dates)

        self.dates = np.array(new_dates)[order].tolist()
        self.articles = np.array(self.articles)[order].tolist()
        self.minutes = np.array(self.minutes)[order].tolist()


def compute_graph(
    entries: list[Entry], most_recent_date: datetime, span: timedelta, opt: Options
) -> BarGraph:

    data = BarGraph([], [], [])

    data.dates.append(most_recent_date)
    data.articles.append(0)
    data.minutes.append(0.0)
    for e in entries:
        date_index = 0
        while e.date < data.dates[date_index]:
            if len(data.dates) == date_index + 1:
                data.dates.append(data.dates[-1] - span)
                data.articles.append(0)
                data.minutes.append(0)
            date_index += 1

        data.articles[date_index] += 1
        data.minutes[date_index] += e.minutes
    return data


def compute_stats(entries: list[Entry], opt: Options):
    now = datetime.now(timezone.utc)
    periods = {
        "week": now - timedelta(days=7),
        "month": now - timedelta(days=30),
        "year": now - timedelta(days=365),
    }
    stats = {}
    for k in periods:
        stats[k] = {"articles": 0, "minutes": 0.0, "days": 0}
    stats["week"]["days"] = 7
    stats["month"]["days"] = 30
    stats["year"]["days"] = 365

    for e in entries:
        for k, start in periods.items():
            if e.date >= start and e.date <= now:
                stats[k]["articles"] += 1
                stats[k]["minutes"] += e.minutes

    for k in stats:
        stats[k]["minutes"] = round(stats[k]["minutes"], 2)
    return stats


def compute_time_of_day(entries, opt: Options):
    hours = {
        "morning": (5, 12),
        "afternoon": (12, 18),
        "night": (18, 22),
        "late": (22, 5),
    }
    stats = {}
    for k in hours:
        stats[k] = {"articles": 0, "minutes": 0.0}

    for e in entries:
        for k, (start, end) in hours.items():
            if e.date.hour >= start and e.date.hour < end:
                stats[k]["articles"] += 1
                stats[k]["minutes"] += e.minutes

    for k in stats:
        stats[k]["minutes"] = round(stats[k]["minutes"], 2)
    return stats


class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            if obj.tzinfo is None:
                obj = obj.replace(tzinfo=timezone.utc)
            return obj.isoformat()
        return super().default(obj)


def datetime_decoder(pairs):
    outputs = []
    for k, v in pairs:
        if isinstance(v, list) and len(v) > 0 and isinstance(v[0], str):
            try:
                new_v = [datetime.fromisoformat(vv) for vv in v]
                outputs.append((k, new_v))
            except ValueError:
                outputs.append((k, v))
        else:
            outputs.append((k, v))
    return dict(outputs)


def gather():
    opt = Options.from_toml(Path("./config.toml"))
    if opt.PASSWORD is None:
        opt.PASSWORD = getpass()
    token = get_access_token(opt)
    raw_entries = fetch_all_entries(token, opt, max_page=None)
    entries = [Entry.from_json(e, opt) for e in raw_entries]

    now = datetime.now(timezone.utc)
    weekly = compute_graph(
        entries, now - timedelta(days=now.weekday()), timedelta(days=7), opt
    )
    monthly = compute_graph(
        entries,
        datetime(year=now.year, month=now.month, day=1, tzinfo=timezone.utc),
        timedelta(days=30),
        opt,
    )
    yearly = compute_graph(
        entries,
        datetime(year=now.year, month=1, day=1, tzinfo=timezone.utc),
        timedelta(days=365),
        opt,
    )
    weekly.sort()
    monthly.sort()
    yearly.sort()
    recent_stats = compute_stats(entries, opt)
    tod_stats = compute_time_of_day(entries, opt)

    output = {
        "weekly": asdict(weekly),
        "monthly": asdict(monthly),
        "yearly": asdict(yearly),
        "time_of_day_stats": tod_stats,
        "recent_stats": recent_stats,
    }

    with open("stats.json", "w") as fle:
        json.dump(output, fle, indent=2, cls=DateTimeEncoder)


def main():
    stats_fle = Path("stats.json")
    if not stats_fle.exists():
        gather()

    with open(stats_fle, "r") as fle:
        data = json.load(fle, object_pairs_hook=datetime_decoder)
        # data = json.load(fle)

    periods = ["weekly", "monthly", "yearly"]
    widths = [6.5, 29.5, 364.5]

    articles = []
    minutes = []
    for period, width in zip(periods, widths):
        p = figure(
            title=period,
            x_axis_label="date",
            x_axis_type="datetime",
            y_axis_label="articles",
            height=250,
            width=750,
            tools="hover",
            tooltips="@articles",
        )

        p.vbar(
            x="dates",
            top="articles",
            width=timedelta(days=width),
            source=data[period],
        )
        articles.append(p)
        p = figure(
            title=period,
            x_axis_label="date",
            x_axis_type="datetime",
            y_axis_label="minutes",
            height=250,
            width=750,
            tools="hover",
            tooltips="@minutes min",
        )

        p.vbar(
            x="dates", top="minutes", width=timedelta(days=width), source=data[period]
        )
        # p.vbar(
        #     x="dates",
        #     top="minutes",
        #     width=timedelta(days=6.5),
        #     source=data["weekly"],
        #     color="red",
        # )
        minutes.append(p)

    tod_times = [k for k in data["time_of_day_stats"]]
    tod_data = {"times": tod_times}
    tod_data["articles"] = [
        data["time_of_day_stats"][name]["articles"] for name in tod_times
    ]
    tod_data["minutes"] = [
        data["time_of_day_stats"][name]["minutes"] for name in tod_times
    ]
    tod_a_fig = figure(
        title="Time of day",
        x_range=tod_times,
        x_axis_label="Time of Day",
        y_axis_label="articles",
        height=250,
        width=750,
        tools="hover",
        tooltips="@articles",
    )
    tod_a_fig.vbar(x="times", top="articles", width=0.9, source=tod_data)
    tod_m_fig = figure(
        title="Time of day",
        x_range=tod_times,
        x_axis_label="Time of day",
        y_axis_label="minutes",
        height=250,
        width=750,
        tools="hover",
        tooltips="@minutes",
    )
    tod_m_fig.vbar(x="times", top="minutes", width=0.9, source=tod_data)

    show(row(column(*articles, tod_a_fig), column(*minutes, tod_m_fig)))


if __name__ == "__main__":
    main()
