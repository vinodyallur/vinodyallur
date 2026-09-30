#!/usr/bin/env python3
"""Generate the animated SVG assets used by the profile README."""

from __future__ import annotations

import argparse
import calendar
import html
import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_USERNAME = "vinodyallur"
GRAPHQL_URL = "https://api.github.com/graphql"
REST_URL = "https://api.github.com"
FONT_STACK = "'Cascadia Code', 'SFMono-Regular', Consolas, 'Liberation Mono', monospace"
PALETTE = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353", "#69f0a0"]


def request_json(url: str, token: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "vinodyallur-profile-art",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    request = Request(url, data=body, headers=headers, method="POST" if body else "GET")
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API request failed ({error.code}): {detail}") from error


def fetch_profile_data(username: str, token: str) -> dict[str, Any]:
    profile = request_json(f"{REST_URL}/users/{username}", token)
    query = """
    query ProfileCalendar($login: String!) {
      user(login: $login) {
        contributionsCollection {
          contributionCalendar {
            totalContributions
            weeks {
              contributionDays {
                contributionCount
                contributionLevel
                date
                weekday
              }
            }
          }
        }
      }
    }
    """
    result = request_json(
        GRAPHQL_URL,
        token,
        {"query": query, "variables": {"login": username}},
    )
    if result.get("errors"):
        raise RuntimeError(f"GitHub GraphQL returned errors: {result['errors']}")

    user = result.get("data", {}).get("user")
    if user is None:
        raise RuntimeError(f"GitHub user {username!r} was not found")

    contribution_calendar = user["contributionsCollection"]["contributionCalendar"]
    days = [
        day
        for week in contribution_calendar["weeks"]
        for day in week["contributionDays"]
    ]
    generated_on = max(day["date"] for day in days)
    return {
        "generated_on": generated_on,
        "profile": {
            "login": profile["login"],
            "name": (profile.get("name") or profile["login"]).strip(),
            "bio": profile.get("bio") or "",
            "created_at": profile["created_at"],
            "followers": profile["followers"],
            "public_repos": profile["public_repos"],
            "twitter_username": profile.get("twitter_username"),
        },
        "calendar": contribution_calendar,
    }


def contribution_stats(data: dict[str, Any]) -> dict[str, Any]:
    days = sorted(
        (
            {
                "date": date.fromisoformat(day["date"]),
                "count": int(day["contributionCount"]),
            }
            for week in data["calendar"]["weeks"]
            for day in week["contributionDays"]
        ),
        key=lambda item: item["date"],
    )

    longest = 0
    running = 0
    for day in days:
        if day["count"] > 0:
            running += 1
            longest = max(longest, running)
        else:
            running = 0

    index = len(days) - 1
    if index >= 0 and days[index]["count"] == 0:
        index -= 1
    current = 0
    while index >= 0 and days[index]["count"] > 0:
        current += 1
        index -= 1

    best = max(days, key=lambda item: item["count"])
    return {
        "current_streak": current,
        "longest_streak": longest,
        "best_count": best["count"],
        "best_date": best["date"],
    }


def extract_portrait_lines(source: Path) -> list[str]:
    root = ET.parse(source).getroot()
    lines: list[str] = []
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] != "text":
            continue
        try:
            x = float(element.attrib.get("x", "999"))
            font_size = float(element.attrib.get("font-size", "999"))
        except ValueError:
            continue
        if x < 100 and font_size <= 9:
            lines.append("".join(element.itertext()).rstrip())
    if len(lines) < 20:
        raise RuntimeError(f"Expected portrait rows in {source}, found only {len(lines)}")
    return lines


def svg_document(width: int, height: int, label: str, body: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(label, quote=True)}">\n'
        f"{body}\n</svg>\n"
    )


def terminal_frame(width: int, height: int, title: str) -> str:
    safe_title = html.escape(title)
    return f"""  <rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="8" fill="#0d1117" stroke="#30363d"/>
  <circle cx="18" cy="18" r="4" fill="#ff7b72"/>
  <circle cx="32" cy="18" r="4" fill="#d29922"/>
  <circle cx="46" cy="18" r="4" fill="#3fb950"/>
  <text x="{width / 2:.1f}" y="22" text-anchor="middle" fill="#8b949e" font-family="{FONT_STACK}" font-size="11" letter-spacing="0">{safe_title}</text>"""


def render_portrait(lines: list[str], username: str) -> str:
    width = 370
    height = 400
    x = 12
    start_y = 43
    line_height = 7.45
    clip_width = width - (x * 2)
    definitions: list[str] = []
    rows: list[str] = []
    for index, line in enumerate(lines):
        baseline = start_y + index * line_height
        delay = index * 0.045
        definitions.append(
            f'    <clipPath id="row-{index}"><rect x="{x}" y="{baseline - 6.2:.2f}" '
            f'width="{clip_width}" height="8"><animate attributeName="width" from="0" '
            f'to="{clip_width}" dur="0.55s" begin="{delay:.3f}s" fill="freeze"/></rect></clipPath>'
        )
        rows.append(
            f'  <text x="{x}" y="{baseline:.2f}" clip-path="url(#row-{index})" '
            f'fill="#c9d1d9" font-family="{FONT_STACK}" font-size="5.4" '
            f'letter-spacing="0" xml:space="preserve">{html.escape(line)}</text>'
        )

    body = "\n".join(
        [
            "  <defs>",
            *definitions,
            "  </defs>",
            terminal_frame(width, height, f"{username} / portrait.txt"),
            *rows,
        ]
    )
    return svg_document(width, height, f"Animated ASCII portrait of {username}", body)


def github_age(created_at: str, today: date) -> str:
    created = datetime.fromisoformat(created_at.replace("Z", "+00:00")).date()
    months = (today.year - created.year) * 12 + today.month - created.month
    if today.day < created.day:
        months -= 1
    years, remaining_months = divmod(max(0, months), 12)
    return f"{years}y {remaining_months}m"


def render_info_card(data: dict[str, Any], stats: dict[str, Any]) -> str:
    width = 490
    height = 400
    profile = data["profile"]
    today = date.fromisoformat(data["generated_on"])
    contact = (
        f"@{profile['twitter_username']}"
        if profile.get("twitter_username")
        else f"github.com/{profile['login']}"
    )
    rows = [
        ("ROLE", "Embedded systems / IoT / AI"),
        ("FOCUS", "Agents, LLMs, connected hardware"),
        ("STACK", "C / C++ / Python / TypeScript"),
        ("BUILDS", "ESP32, APIs, developer tools"),
        ("REPOS", f"{profile['public_repos']} public repositories"),
        ("CONTRIB", f"{data['calendar']['totalContributions']:,} in the last year"),
        (
            "STREAK",
            f"{stats['current_streak']} current / {stats['longest_streak']} longest",
        ),
        ("UPTIME", f"{github_age(profile['created_at'], today)} on GitHub"),
        ("CONTACT", contact),
    ]

    style = f"""  <style>
    .line {{ animation: line-in 0.45s ease-out both; }}
    @keyframes line-in {{
      from {{ opacity: 0; transform: translateX(-12px); }}
      to {{ opacity: 1; transform: translateX(0); }}
    }}
    @media (prefers-reduced-motion: reduce) {{ .line {{ animation: none; }} }}
  </style>"""
    content = [style, terminal_frame(width, height, f"{profile['login']}@github: ~")]
    content.append(
        f'  <text class="line" style="animation-delay:0.12s" x="28" y="66" '
        f'fill="#58a6ff" font-family="{FONT_STACK}" font-size="18" font-weight="700" '
        f'letter-spacing="0">{html.escape(profile["name"])}</text>'
    )
    content.append(
        f'  <text class="line" style="animation-delay:0.20s" x="28" y="86" '
        f'fill="#8b949e" font-family="{FONT_STACK}" font-size="12" letter-spacing="0">'
        f'{html.escape(profile["login"])}@github</text>'
    )
    content.append('  <line x1="28" y1="101" x2="462" y2="101" stroke="#30363d"/>')

    start_y = 128
    for index, (label, value) in enumerate(rows):
        y = start_y + index * 28
        delay = 0.30 + index * 0.09
        content.append(
            f'  <text class="line" style="animation-delay:{delay:.2f}s" x="28" y="{y}" '
            f'font-family="{FONT_STACK}" font-size="13" letter-spacing="0">'
            f'<tspan fill="#f0883e">{html.escape(label.ljust(8))}</tspan>'
            f'<tspan fill="#484f58"> :: </tspan>'
            f'<tspan fill="#c9d1d9">{html.escape(value)}</tspan></text>'
        )

    content.append(
        f'  <text x="462" y="382" text-anchor="end" fill="#484f58" '
        f'font-family="{FONT_STACK}" font-size="10" letter-spacing="0">'
        f'updated {html.escape(data["generated_on"])}</text>'
    )
    return svg_document(width, height, f"Neofetch profile card for {profile['login']}", "\n".join(content))


def contribution_level(day: dict[str, Any], best_count: int) -> int:
    count = int(day["contributionCount"])
    if count == 0:
        return 0
    levels = {
        "FIRST_QUARTILE": 1,
        "SECOND_QUARTILE": 2,
        "THIRD_QUARTILE": 3,
        "FOURTH_QUARTILE": 4,
    }
    level = levels.get(day.get("contributionLevel", ""), 1)
    return 5 if count == best_count and best_count > 0 else level


def render_heatmap(data: dict[str, Any], stats: dict[str, Any]) -> str:
    width = 860
    height = 190
    cell = 11
    gap = 3
    x_origin = 62
    y_origin = 39
    weeks = data["calendar"]["weeks"]

    style = """  <style>
    .day { animation: cell-in 0.38s cubic-bezier(.2,.8,.2,1) both; transform-box: fill-box; transform-origin: center; }
    @keyframes cell-in {
      from { opacity: 0; transform: translateY(-8px) scale(.72); }
      to { opacity: 1; transform: translateY(0) scale(1); }
    }
    @media (prefers-reduced-motion: reduce) { .day { animation: none; } }
  </style>"""
    content = [
        style,
        f'  <rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="8" fill="#0d1117" stroke="#30363d"/>',
        f'  <text x="22" y="22" fill="#8b949e" font-family="{FONT_STACK}" font-size="11" letter-spacing="0">last 53 weeks</text>',
    ]

    seen_months: set[tuple[int, int]] = set()
    for week_index, week in enumerate(weeks):
        x = x_origin + week_index * (cell + gap)
        for day in week["contributionDays"]:
            day_date = date.fromisoformat(day["date"])
            month_key = (day_date.year, day_date.month)
            if day_date.day <= 7 and month_key not in seen_months:
                seen_months.add(month_key)
                content.append(
                    f'  <text x="{x}" y="23" fill="#8b949e" font-family="{FONT_STACK}" '
                    f'font-size="10" letter-spacing="0">{calendar.month_abbr[day_date.month]}</text>'
                )

            weekday = int(day["weekday"])
            y = y_origin + weekday * (cell + gap)
            level = contribution_level(day, stats["best_count"])
            delay = (week_index + weekday * 0.7) * 0.018
            content.append(
                f'  <rect class="day" style="animation-delay:{delay:.3f}s" x="{x}" y="{y}" '
                f'width="{cell}" height="{cell}" rx="2" fill="{PALETTE[level]}">'
                f'<title>{html.escape(day["date"])}: {day["contributionCount"]} contributions</title></rect>'
            )

    for label, weekday in (("Mon", 1), ("Wed", 3), ("Fri", 5)):
        y = y_origin + weekday * (cell + gap) + cell - 2
        content.append(
            f'  <text x="22" y="{y}" fill="#8b949e" font-family="{FONT_STACK}" '
            f'font-size="9" letter-spacing="0">{label}</text>'
        )

    total = data["calendar"]["totalContributions"]
    footer = (
        f"{total:,} contributions  |  {stats['current_streak']} day current streak  |  "
        f"{stats['longest_streak']} day longest streak"
    )
    content.append(
        f'  <text x="22" y="174" fill="#c9d1d9" font-family="{FONT_STACK}" '
        f'font-size="12" letter-spacing="0">{html.escape(footer)}</text>'
    )
    content.append(
        f'  <text x="838" y="174" text-anchor="end" fill="#8b949e" font-family="{FONT_STACK}" '
        f'font-size="10" letter-spacing="0">Less  '
        + "  ".join(
            f'<tspan fill="{color}">&#9632;</tspan>' for color in PALETTE
        )
        + "  More</text>"
    )
    return svg_document(width, height, f"Contribution heatmap for {data['profile']['login']}", "\n".join(content))


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", default=DEFAULT_USERNAME)
    parser.add_argument("--root", type=Path, default=ROOT)
    arguments = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        parser.error("set GITHUB_TOKEN or GH_TOKEN before running the generator")

    root = arguments.root.resolve()
    data = fetch_profile_data(arguments.username, token)
    stats = contribution_stats(data)
    portrait_lines = extract_portrait_lines(root / "dark_mode.svg")

    write_text(root / "data" / "profile.json", json.dumps(data, indent=2) + "\n")
    write_text(root / "ascii-portrait.svg", render_portrait(portrait_lines, arguments.username))
    write_text(root / "info-card.svg", render_info_card(data, stats))
    write_text(root / "contrib-heatmap.svg", render_heatmap(data, stats))

    print(
        f"Generated profile art for {arguments.username}: "
        f"{data['calendar']['totalContributions']} contributions, "
        f"{len(portrait_lines)} portrait rows"
    )


if __name__ == "__main__":
    main()