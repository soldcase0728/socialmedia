"""Command line for the content engine.

    python -m brandops today
    python -m brandops intake --event "AP Bio lab" --department Science \
        --contributor "Mr. Kowalski" --description "Students titrating" --file IMG_1.mov
    python -m brandops triage
    python -m brandops queue list
    python -m brandops weekly

State lives in JSON under `data/` (override with BRANDOPS_DATA).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from typing import Any, Sequence

from . import config, store
from .approval import ApprovalQueue, Decision, build_card
from .assets import Asset, from_intake, unresolved
from .audiences import Audience
from .brand import Pillar, scan_copy
from .calendar import default_calendar, ninety_day_campaigns, thirty_day_plan, week_plan
from .capture import build_capture_list, staff_one_pager
from .copywriting import write_package_copy
from .engine import run_today
from .llm import Claude, caption_prompt, hook_prompt, ideation_prompt
from .measurement import PostResult, weekly_report
from .memory import BrandMemory, learn_from_week
from .mix import analyze
from .packages import build_package
from .platforms import Platform
from .scoring import rubric
from .stack import summary as stack_summary, table as stack_table
from .triage import triage, triage_batch

ASSETS_KEY = "assets"
RESULTS_KEY = "results"
PUBLISHED_KEY = "published"
QUEUE_KEY = "queue"


# ---------------------------------------------------------------------------
# storage helpers
# ---------------------------------------------------------------------------

def load_assets() -> list[Asset]:
    return [Asset.from_dict(a) for a in store.load(ASSETS_KEY, {}).get("assets", [])]


def save_assets(assets: Sequence[Asset]) -> None:
    store.save(ASSETS_KEY, {"assets": [a.to_dict() for a in assets]})


def load_results() -> list[PostResult]:
    return [PostResult.from_dict(r) for r in store.load(RESULTS_KEY, {}).get("results", [])]


def load_published() -> list[dict[str, Any]]:
    return list(store.load(PUBLISHED_KEY, {}).get("records", []))


def load_queue() -> ApprovalQueue:
    return ApprovalQueue.from_dict(store.load(QUEUE_KEY, {}))


def save_queue(queue: ApprovalQueue) -> None:
    store.save(QUEUE_KEY, queue.to_dict())


def parse_date(value: str | None) -> date:
    return date.fromisoformat(value) if value else date.today()


def emit(payload: Any, as_json: bool, text: str) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False) if as_json else text)


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------

def cmd_today(args: argparse.Namespace) -> int:
    when = parse_date(args.date)
    brief = run_today(
        when,
        assets=load_assets(),
        events=default_calendar(when.year if when.month >= 8 else when.year - 1),
        published=load_published(),
        memory=BrandMemory.load(),
    )
    emit(brief.to_dict(), args.json, brief.as_text())
    return 0


def cmd_intake(args: argparse.Namespace) -> int:
    payload = {
        "event": args.event,
        "department": args.department,
        "contributor": args.contributor,
        "description": args.description,
        "filename": args.file or "",
        "captured_at": args.date or date.today().isoformat(),
        "subjects": args.subjects or "",
        "possible_story": args.story or "",
        "orientation": args.orientation,
        "duration_s": args.duration,
        "consent_ok": not args.no_consent,
        "sensitive": args.sensitive,
        "publish_now_ok": not args.hold,
    }
    asset = from_intake(payload)
    assets = load_assets()
    if any(a.asset_id == asset.asset_id for a in assets):
        print(f"asset {asset.asset_id} already exists", file=sys.stderr)
        return 1
    assets.append(asset)
    save_assets(assets)
    result = triage(asset)
    emit(
        {"asset": asset.to_dict(), "triage": result.to_dict()},
        args.json,
        f"{asset.asset_id}\n  {result.score.explain()}\n  pillar: "
        f"{result.primary_pillar.spec.name}\n  next: {result.recommended_status.value}",
    )
    return 0


def cmd_inbox(args: argparse.Namespace) -> int:
    assets = load_assets()
    pending = unresolved(assets)
    lines = [f"{len(pending)} unresolved of {len(assets)} total"]
    lines += [f"  {a.status.value:<20} {a.asset_id}  ({a.event})" for a in pending]
    emit([a.to_dict() for a in pending], args.json, "\n".join(lines))
    return 0


def cmd_triage(args: argparse.Namespace) -> int:
    assets = load_assets()
    if not assets:
        print("inbox is empty -- add assets with `intake`", file=sys.stderr)
        return 1
    results = triage_batch(assets, today=parse_date(args.date))
    lines = [f"{'score':>5}  {'verdict':<9} {'pillar':<26} asset"]
    for result in results:
        lines.append(
            f"{result.score.total:>5}  {result.verdict.value:<9} "
            f"{result.primary_pillar.spec.name:<26} {result.asset_id}"
        )
    emit([r.to_dict() for r in results], args.json, "\n".join(lines))
    return 0


def cmd_package(args: argparse.Namespace) -> int:
    assets = [a for a in load_assets() if a.asset_id == args.asset_id or a.event == args.asset_id]
    if not assets:
        print(f"no asset or event matching {args.asset_id!r}", file=sys.stderr)
        return 1
    result = triage_batch(assets)[0]
    package = build_package(result, assets)
    drafts = write_package_copy(
        [i for i in package.items if i.platform],
        story=assets[0].event,
        pillar=result.primary_pillar,
        hook=result.hooks[0] if result.hooks else None,
        evidence=[a.possible_story or a.description for a in assets],
    )
    lines = [f"{package.event} -- {package.pillar.spec.name}", ""]
    for draft in drafts:
        where = draft.platform.spec.name if draft.platform else "internal"
        lines += [f"--- {where} ---", draft.text]
        lines += [f"  ! {w}" for w in draft.warnings]
        lines.append("")
    emit(
        {"package": package.to_dict(), "copy": [d.to_dict() for d in drafts]},
        args.json,
        "\n".join(lines),
    )
    return 0


def cmd_capture(args: argparse.Namespace) -> int:
    when = parse_date(args.date)
    events = [e for e in default_calendar(when.year if when.month >= 8 else when.year - 1)
              if e.when == when]
    published = load_published()
    deficits = analyze(published).pillar_deficits() if published else []
    assignments = build_capture_list(when, events=events, pillar_deficits=deficits)
    emit(
        [a.to_dict() for a in assignments],
        args.json,
        f"CAPTURE LIST -- {when:%A %B %d}\n\n" + "\n\n".join(a.as_text() for a in assignments),
    )
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    when = parse_date(args.date)
    events = default_calendar(when.year if when.month >= 8 else when.year - 1)
    published = load_published()
    deficits = analyze(published).pillar_deficits() if published else []

    if args.horizon == "week":
        slots = week_plan(when, events=events, deficits=deficits)
        text = "\n".join(
            f"{s.when} {s.time:>5}  {s.platform.value:<16} "
            f"{(s.pillar.spec.name if s.pillar else 'open'):<26} "
            f"{(s.audience.spec.name if s.audience else ''):<20} {s.kind}"
            for s in slots
        )
        emit([s.to_dict() for s in slots], args.json, text)
    elif args.horizon == "30":
        weeks = thirty_day_plan(when, events)
        text = "\n".join(
            f"week of {w.start}: {w.theme}\n  pillar: {w.pillar.spec.name} | "
            f"audience: {w.audience.spec.name}\n  events: "
            f"{', '.join(e.name for e in w.events) or 'none scheduled'}"
            for w in weeks
        )
        emit([w.to_dict() for w in weeks], args.json, text)
    else:
        campaigns = ninety_day_campaigns(when)
        text = "\n".join(
            f"{c.start} to {c.end}  [{c.phase}]\n  objective: {c.objective}\n"
            f"  audience: {c.audience.spec.name} | pillars: "
            f"{', '.join(p.spec.name for p in c.pillars)}\n"
            f"  paid: {'yes' if c.paid else 'no'} | measure: {c.measurement}"
            for c in campaigns
        )
        emit([c.to_dict() for c in campaigns], args.json, text)
    return 0


def cmd_queue(args: argparse.Namespace) -> int:
    queue = load_queue()

    if args.action == "list":
        cards = queue.pending() if not args.all else queue.cards
        text = "\n\n".join(card.as_text() for card in cards) or "queue is empty"
        emit([c.to_dict() for c in cards], args.json, text)
        return 0

    if args.action == "build":
        assets = [a for a in load_assets()
                  if a.asset_id == args.card_id or a.event == args.card_id]
        if not assets:
            print(f"no asset or event matching {args.card_id!r}", file=sys.stderr)
            return 1
        result = triage_batch(assets)[0]
        package = build_package(result, assets)
        drafts = write_package_copy(
            [i for i in package.items if i.platform],
            story=assets[0].event,
            pillar=result.primary_pillar,
            hook=result.hooks[0] if result.hooks else None,
            evidence=[a.possible_story or a.description for a in assets],
        )
        added = 0
        for index, (item, draft) in enumerate(
            zip([i for i in package.items if i.platform], drafts)
        ):
            card_id = f"{assets[0].asset_id}:{item.key}"
            if any(c.card_id == card_id for c in queue.cards):
                continue
            queue.add(build_card(
                card_id,
                draft,
                pillar=result.primary_pillar,
                asset_ids=[a.asset_id for a in assets],
                score=result.score,
                strategic_purpose=item.purpose,
                hook=result.hooks[0].text if result.hooks else "",
                review_reasons=result.review_reasons,
                consent_ok=all(a.consent_ok for a in assets),
                publish_now_ok=all(a.publish_now_ok for a in assets),
                paid=item.paid,
            ))
            added += 1
        save_queue(queue)
        print(f"added {added} card(s) to the approval queue")
        return 0

    if args.action in ("approve", "reject", "hold", "edit"):
        if not args.by:
            print("--by is required: approval needs a named human", file=sys.stderr)
            return 1
        try:
            card = queue.decide(
                args.card_id, Decision(args.action.upper()), by=args.by, note=args.note or ""
            )
        except Exception as exc:
            print(str(exc), file=sys.stderr)
            return 1
        save_queue(queue)
        print(f"{card.card_id}: {card.decision.value} by {card.decided_by}")
        return 0

    if args.action == "clear-blocker":
        try:
            card = queue.clear_blocker(args.card_id, args.note or "", by=args.by or "unnamed")
        except Exception as exc:
            print(str(exc), file=sys.stderr)
            return 1
        save_queue(queue)
        print(f"{card.card_id}: blockers now {card.blockers or 'none'}")
        return 0

    print(f"unknown queue action {args.action!r}", file=sys.stderr)
    return 1


def cmd_record(args: argparse.Namespace) -> int:
    metrics: dict[str, float] = {}
    for pair in args.metric or []:
        if "=" not in pair:
            print(f"metric must be name=value, got {pair!r}", file=sys.stderr)
            return 1
        name, value = pair.split("=", 1)
        metrics[name.strip()] = float(value)

    result = PostResult(
        post_id=args.post_id,
        platform=args.platform,
        published_at=parse_date(args.date),
        pillar=Pillar(args.pillar),
        audience=Audience(args.audience),
        metrics=metrics,
        hook_structure=args.hook or "",
        fmt=args.format or "",
        event=args.event or "",
        paid=args.paid,
    )
    payload = store.load(RESULTS_KEY, {})
    payload.setdefault("results", []).append(result.to_dict())
    store.save(RESULTS_KEY, payload)

    published = store.load(PUBLISHED_KEY, {})
    published.setdefault("records", []).append({
        "post_id": result.post_id,
        "pillar": result.pillar.value,
        "audience": result.audience.value,
        "platform": result.platform,
        "event": result.event,
    })
    store.save(PUBLISHED_KEY, published)
    print(f"recorded {result.post_id}")
    return 0


def cmd_weekly(args: argparse.Namespace) -> int:
    results = load_results()
    if not results:
        print("no results recorded yet -- use `record`", file=sys.stderr)
        return 1
    end = parse_date(args.date)
    start = end.fromordinal(end.toordinal() - 6)
    report = weekly_report(results, start=start, end=end, history=results)
    if args.learn:
        memory = BrandMemory.load()
        learn_from_week(memory, report)
        memory.save()
    emit(report.to_dict(), args.json, report.as_text())
    return 0


def cmd_mix(args: argparse.Namespace) -> int:
    published = load_published()
    if not published:
        print("nothing published recorded yet", file=sys.stderr)
        return 1
    report = analyze(published)
    emit(report.to_dict(), args.json, report.as_text())
    return 0


def cmd_memory(args: argparse.Namespace) -> int:
    memory = BrandMemory.load()
    lines = ["BRAND MEMORY", ""]
    lines.append("Best hooks:")
    lines += [f"  {k}: {v.mean:.2f}x median over {v.n} (best {v.best_ref})"
              for k, v in memory.top_hooks(5, confident_only=False)] or ["  none recorded yet"]
    lines += ["", "Objections we should be answering:"]
    lines += [f"  \"{o['objection']}\" -> {o['answer']}" for o in memory.objections[:8]]
    lines += ["", f"Banked: {len(memory.testimonials)} quotes, "
                  f"{len(memory.statistics)} statistics "
                  f"({len(memory.verified_statistics())} verified), "
                  f"{len(memory.underused_stories)} unused stories"]
    emit(memory.to_dict(), args.json, "\n".join(lines))
    return 0


def cmd_lint(args: argparse.Namespace) -> int:
    text = args.text or sys.stdin.read()
    flags = scan_copy(text)
    if not flags:
        print("clean")
        return 0
    for flag in flags:
        print(flag)
    return 1


def cmd_prompt(args: argparse.Namespace) -> int:
    pillar = Pillar(args.pillar)
    audience = Audience(args.audience)
    if args.kind == "caption":
        prompt = caption_prompt(
            story=args.story, pillar=pillar, audience=audience,
            platform=Platform(args.platform), facts=args.fact or [],
        )
    elif args.kind == "hooks":
        prompt = hook_prompt(story=args.story, pillar=pillar, audience=audience,
                             facts=args.fact or [])
    else:
        prompt = ideation_prompt(
            when=date.today().isoformat(), yesterday=[], today=[args.story],
            this_week=[], deficits=[], phase="awareness",
        )
    if args.run:
        claude = Claude()
        try:
            print(claude.complete(prompt))
            return 0
        except RuntimeError as exc:
            print(exc, file=sys.stderr)
            return 1
    print(prompt.as_text())
    return 0


def cmd_stack(args: argparse.Namespace) -> int:
    print(stack_table())
    print()
    print(stack_summary())
    return 0


def cmd_rubric(args: argparse.Namespace) -> int:
    print(rubric())
    return 0


def cmd_onepager(args: argparse.Namespace) -> int:
    print(staff_one_pager())
    inbox = config.CONTENT_INBOX.get("upload_url") or "<<set CONTENT_INBOX['upload_url'] in brandops/config.py>>"
    print(f"\nUpload link behind the QR code: {inbox}")
    return 0


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="brandops", description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    sub = parser.add_subparsers(dest="command", required=True)

    today = sub.add_parser("today", help="run the morning content engine")
    today.add_argument("--date")
    today.set_defaults(func=cmd_today)

    intake = sub.add_parser("intake", help="add one asset from the content inbox")
    intake.add_argument("--event", required=True)
    intake.add_argument("--department", required=True)
    intake.add_argument("--contributor", required=True)
    intake.add_argument("--description", required=True)
    intake.add_argument("--file", dest="file")
    intake.add_argument("--date")
    intake.add_argument("--subjects", help="comma-separated names")
    intake.add_argument("--story", help="anything we would not know by looking at it")
    intake.add_argument("--orientation", default="vertical",
                        choices=["vertical", "horizontal", "square"])
    intake.add_argument("--duration", type=float)
    intake.add_argument("--no-consent", action="store_true",
                        help="photo release NOT confirmed")
    intake.add_argument("--sensitive", action="store_true")
    intake.add_argument("--hold", action="store_true", help="not publishable yet")
    intake.set_defaults(func=cmd_intake)

    inbox = sub.add_parser("inbox", help="show unresolved assets")
    inbox.set_defaults(func=cmd_inbox)

    tri = sub.add_parser("triage", help="triage and rank the inbox")
    tri.add_argument("--date")
    tri.set_defaults(func=cmd_triage)

    pkg = sub.add_parser("package", help="build a content package and its copy")
    pkg.add_argument("asset_id", help="asset id or event name")
    pkg.set_defaults(func=cmd_package)

    cap = sub.add_parser("capture", help="today's capture list")
    cap.add_argument("--date")
    cap.set_defaults(func=cmd_capture)

    plan = sub.add_parser("plan", help="7-day, 30-day or 90-day calendar")
    plan.add_argument("horizon", choices=["week", "30", "90"])
    plan.add_argument("--date")
    plan.set_defaults(func=cmd_plan)

    queue = sub.add_parser("queue", help="the approval queue")
    queue.add_argument("action",
                       choices=["list", "build", "approve", "reject", "hold", "edit",
                                "clear-blocker"])
    queue.add_argument("card_id", nargs="?", default="")
    queue.add_argument("--by", help="the human making the decision")
    queue.add_argument("--note")
    queue.add_argument("--all", action="store_true")
    queue.set_defaults(func=cmd_queue)

    record = sub.add_parser("record", help="record what a published post did")
    record.add_argument("post_id")
    record.add_argument("--platform", required=True)
    record.add_argument("--pillar", required=True, choices=[p.value for p in Pillar])
    record.add_argument("--audience", required=True, choices=[a.value for a in Audience])
    record.add_argument("--date")
    record.add_argument("--hook")
    record.add_argument("--format", dest="format")
    record.add_argument("--event")
    record.add_argument("--paid", action="store_true")
    record.add_argument("--metric", action="append",
                        help="name=value, repeatable (impressions=1200 shares=8)")
    record.set_defaults(func=cmd_record)

    weekly = sub.add_parser("weekly", help="the weekly intelligence report")
    weekly.add_argument("--date")
    weekly.add_argument("--learn", action="store_true", help="fold results into brand memory")
    weekly.set_defaults(func=cmd_weekly)

    mix = sub.add_parser("mix", help="content mix balance")
    mix.set_defaults(func=cmd_mix)

    memory = sub.add_parser("memory", help="what the system has learned")
    memory.set_defaults(func=cmd_memory)

    lint = sub.add_parser("lint", help="check copy for filler and clickbait")
    lint.add_argument("text", nargs="?")
    lint.set_defaults(func=cmd_lint)

    prompt = sub.add_parser("prompt", help="paste-ready LLM prompt (or --run it)")
    prompt.add_argument("kind", choices=["caption", "hooks", "ideation"])
    prompt.add_argument("--story", required=True)
    prompt.add_argument("--pillar", default=Pillar.CHALLENGED.value,
                        choices=[p.value for p in Pillar])
    prompt.add_argument("--audience", default=Audience.PROSPECTIVE_PARENT.value,
                        choices=[a.value for a in Audience])
    prompt.add_argument("--platform", default=Platform.INSTAGRAM_REEL.value,
                        choices=[p.value for p in Platform])
    prompt.add_argument("--fact", action="append")
    prompt.add_argument("--run", action="store_true", help="call the API instead of printing")
    prompt.set_defaults(func=cmd_prompt)

    stack = sub.add_parser("stack", help="software stack and cost per hour saved")
    stack.set_defaults(func=cmd_stack)

    rub = sub.add_parser("rubric", help="the content opportunity score rubric")
    rub.set_defaults(func=cmd_rubric)

    one = sub.add_parser("onepager", help="the staff capture one-pager")
    one.set_defaults(func=cmd_onepager)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
