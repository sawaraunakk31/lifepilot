"""Build an .ics (iCalendar) file from a user's opportunity deadlines.

Pure standard library. Produces all-day events with a reminder alarm a week
before each deadline. Import into Google/Apple/Outlook calendar.
"""
from __future__ import annotations

from datetime import date, datetime, timezone


def _esc(text: str | None) -> str:
    if not text:
        return ""
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """RFC 5545 line folding at 75 octets."""
    if len(line) <= 75:
        return line
    chunks = [line[:75]]
    rest = line[75:]
    while rest:
        chunks.append(" " + rest[:74])
        rest = rest[74:]
    return "\r\n".join(chunks)


def build_ics(matches: list[dict], *, only_eligible: bool = True) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines: list[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//LifePilot//Opportunity Deadlines//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:LifePilot Deadlines",
    ]

    count = 0
    for m in matches:
        if only_eligible and not m.get("eligible"):
            continue
        deadline = m.get("deadline")
        if not deadline:
            continue
        try:
            d = date.fromisoformat(deadline)
        except ValueError:
            continue
        if (d - date.today()).days < 0:
            continue  # skip closed cycles

        count += 1
        uid = f"{m.get('opportunity_id', 'opp')}-{deadline}@lifepilot.local"
        dt = d.strftime("%Y%m%d")
        summary = _esc(f"Apply: {m.get('title', 'Opportunity')}")
        desc = _esc(
            f"{m.get('amount', '')} | Provider: {m.get('provider', '')} | {m.get('url', '')}"
        )
        lines += [
            "BEGIN:VEVENT",
            _fold(f"UID:{uid}"),
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{dt}",
            f"DTEND;VALUE=DATE:{dt}",
            _fold(f"SUMMARY:{summary}"),
            _fold(f"DESCRIPTION:{desc}"),
            "STATUS:CONFIRMED",
            "TRANSP:TRANSPARENT",
            "BEGIN:VALARM",
            "TRIGGER:-P7D",
            "ACTION:DISPLAY",
            "DESCRIPTION:Reminder: application deadline in 7 days",
            "END:VALARM",
            "END:VEVENT",
        ]

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
