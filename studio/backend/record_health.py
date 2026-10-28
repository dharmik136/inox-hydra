"""
From your record, on Health: the daily job, the model stage's spend and the library's signature.
================================================================================================
Health is where a creator looks when the rest of the studio looks wrong, so
the section's three moving parts are said there, each as the studio holds
it and each in a sentence:

  job       when the day's cards were last built, whether that batch was
            carried forward because nothing had changed, and how many cards
            failed a check (record_daily)
  model     what the model stage spent today against the daily ceiling,
            estimated from the dated price table, or why it spent nothing
            (record_model)
  library   whether a signed library is held, and whether the key it was
            signed with is still one this studio ships (library_bundle)

A read: nothing here builds, calls or fetches.

Strict Invariants:
- Zero em-dashes.
- Zero egress, and no write.
"""

from datetime import datetime
from typing import Any, Dict, Optional

try:
    from . import library_bundle, record_daily, record_model
except ImportError:  # top-level import mode
    import library_bundle
    import record_daily
    import record_model


def _clock(stamp: Optional[str]) -> str:
    if not stamp:
        return "a time not recorded"
    try:
        return datetime.fromisoformat(stamp).astimezone().strftime("%H:%M")
    except ValueError:
        return "a time not recorded"


def job() -> Dict[str, Any]:
    state = record_daily.status()
    last = state.get("last_run")
    if not last:
        sentence = ("Not built yet: the first batch is built a minute after the studio starts, then checked every "
                    "hour while it runs.")
    else:
        built = "today" if last["day"] == state["today"] else f"for {last['day']}"
        sentence = (f"{'Built' if state['today_built'] else 'Not built yet today; last built'} {built} at "
                    f"{_clock(last.get('finished_at'))}, "
                    + (f"carried forward from {last['carried_from']}, because nothing it is built from had changed"
                       if last.get("carried_from") else "built from your record"))
        dropped = last.get("dropped_cards") or 0
        if dropped:
            sentence += f"; {dropped} {'card' if dropped == 1 else 'cards'} failed a check and {'is' if dropped == 1 else 'are'} not shown"
        sentence += "."
    return {**state, "carried_from": (last or {}).get("carried_from"), "sentence": sentence}


def model() -> Dict[str, Any]:
    state = record_model.state()
    spent, ceiling = state.get("spent_today_usd"), state["ceiling_usd"]
    if not state["configured"]:
        sentence = "No AI provider is connected, so the model stage sends nothing and spends nothing."
    elif state["stage"] != "on":
        sentence = f"The model stage is off, so it spends nothing; the daily ceiling is ${ceiling:.2f}."
    elif spent:
        sentence = (f"${spent:.4f} of the ${ceiling:.2f} daily ceiling spent today, estimated from "
                    f"{state['provider_label'] or 'your provider'}'s prices of {state['price_date']}.")
    else:
        sentence = f"Nothing spent today, of a ${ceiling:.2f} daily ceiling. {state['reason'] or ''}".strip()
    return {key: state.get(key) for key in ("configured", "stage", "status", "provider_label", "model", "ceiling_usd",
                                            "spent_today_usd", "price_date", "priced")} | {"sentence": sentence}


def health() -> Dict[str, Any]:
    """The three parts, each with its sentence, for Health's block."""
    return {"job": job(), "model": model(), "library": library_bundle.signature_state()}
