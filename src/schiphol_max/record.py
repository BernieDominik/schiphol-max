"""J2: the short summary a person can read, and the FORECAST.md page."""

from __future__ import annotations

from datetime import date

from .timeutil import AMS, parse_iso


def _pct(p: float) -> str:
    return f"{round(p * 100):>3d}%"


def summary_text(rec: dict) -> str:
    day = date.fromisoformat(rec["target_day"])
    issued = parse_iso(rec["issued_at_utc"]).astimezone(AMS)
    lines = [f"{day:%a} {day.day} {day:%b}, issued {issued:%a %H:%M}"]
    for row in rec["table"]:
        tag = "   most likely" if row["degree"] == rec["top_degree"] else ""
        lines.append(f"  {row['degree']:>3d} °C {_pct(row['probability'])}{tag}")
    lines.append(f"  other  {_pct(rec['outside_table'])}")
    if rec.get("max_so_far") is not None:
        lines.append(f"Maximum so far today: {rec['max_so_far']} °C.")
    std = rec["standard_forecast"]
    lines.append(f"Standard forecast {std} °C: {round(rec['p_above_standard'] * 100)}% chance the maximum is higher, "
                 f"{round(rec['p_below_standard'] * 100)}% lower.")
    typical = rec.get("p_miss_2_or_more_typical")
    typical_txt = f" (typical {round(typical * 100)}%)" if typical is not None else ""
    lines.append(f"Chance of a miss of 2 °C or more against the standard forecast: "
                 f"{round(rec['p_miss_2_or_more'] * 100)}%{typical_txt}.")
    if rec.get("degraded"):
        lines.append("Note: fewer than three weather models were available (degraded).")
    return "\n".join(lines)


def forecast_page(latest: list[dict], outlook: list[dict], status: str | None = None) -> str:
    """FORECAST.md: the newest forecast for each upcoming day."""
    out = ["# Schiphol daily maximum", "",
           "Highest temperature of the Amsterdam day at Schiphol, in whole °C: the highest half-hourly airport report "
           "(the figure the Weather Underground history page is built from). Each degree gets its own probability.", ""]
    for rec in latest:
        out += ["```", summary_text(rec), "```", ""]
    if outlook:
        out += ["## Next days (evening run)", "", "| Day | Most likely | Probability | Five listed degrees cover |",
                "| --- | --- | --- | --- |"]
        for rec in outlook:
            d = date.fromisoformat(rec["target_day"])
            out.append(f"| {d:%a %d %b} | {rec['top_degree']} °C | {round(rec['top_probability'] * 100)}% | "
                       f"{round((1 - rec['outside_table']) * 100)}% |")
        out.append("")
    if status:
        out += [f"**System status:** {status}", ""]
    out.append("Data: Open-Meteo (CC BY 4.0), KNMI, DWD, Iowa Environmental Mesonet, NOAA Aviation Weather Center.")
    return "\n".join(out) + "\n"
