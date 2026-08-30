#!/usr/bin/env python3
"""Agent Intercom — a git-backed message, lock and deadline system for teams of AI coding agents (stdlib only)."""
import argparse, json, os, re, subprocess, sys, time, secrets
from datetime import datetime, timezone, timedelta

def local_hm(ts_iso):
    """UTC ISO timestamp -> local date/time for display."""
    try:
        return datetime.fromisoformat(ts_iso).astimezone().strftime("%m-%d %H:%M")
    except Exception:
        return "?"

ROOT = os.environ.get("INTERCOM_ROOT") or os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(ROOT, "intercom.json")
DEFAULT_CONFIG = {"roles": ["human", "lead", "builder", "verifier"], "branch": "intercom",
                  "remote": "origin", "extra_remotes": [], "silence_alert_minutes": 60,
                  "heartbeat_alert_minutes": 45, "auto_ping_cooldown_minutes": 30,
                  "human_roles": ["human"],
                  "activity_sources": {}}

def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        try:
            cfg.update(json.load(open(CONFIG_PATH, encoding="utf-8")))
        except Exception as exc:
            raise SystemExit(f"intercom.json is not valid JSON: {exc}")
    return cfg

CONFIG = load_config()
ROLES = list(CONFIG["roles"]) + ["all"]
TYPES = ["task", "handoff", "gate", "decision", "question", "answer", "correction", "plan", "ping", "ack", "fyi", "block"]
REMOTE = os.environ.get("INTERCOM_REMOTE", CONFIG["remote"])
BRANCH = os.environ.get("INTERCOM_BRANCH", CONFIG["branch"])

def git(*args, check=True):
    r = subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise SystemExit(f"git {' '.join(args)}: {r.stderr.strip()[:300]}")
    return r

def now_utc():
    return datetime.now(timezone.utc)

def has_remote(name):
    return git("remote", "get-url", name, check=False).returncode == 0

def sync(push=True):
    """Fetch+rebase the branch, then push; retries on conflict. Works offline (local-only) if the remote is absent."""
    if not has_remote(REMOTE):
        return True  # local-only mode: no remote configured yet
    for attempt in range(3):
        git("fetch", "-q", REMOTE, BRANCH, check=False)
        git("pull", "-q", "--rebase", REMOTE, BRANCH, check=False)
        if not push:
            return True
        r = git("push", "-q", REMOTE, f"HEAD:{BRANCH}", check=False)
        if r.returncode == 0:
            for extra in CONFIG.get("extra_remotes", []):
                if has_remote(extra):
                    git("push", "-q", extra, f"HEAD:{BRANCH}", check=False)
            return True
        time.sleep(1 + attempt)
    raise SystemExit("push failed (conflict or network) — run `intercom.py sync` again")

def commit(paths, msg):
    git("add", "-A")
    if git("diff", "--cached", "--quiet", check=False).returncode == 0:
        return False
    git("commit", "-q", "-m", msg)
    return True

def parse_message(path):
    text = open(path, encoding="utf-8").read()
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if not m:
        return None
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    meta["to"] = [t.strip() for t in meta.get("to", "").split(",") if t.strip()]
    meta["refs"] = [t.strip() for t in meta.get("refs", "").split(";") if t.strip()]
    meta["needs_ack"] = meta.get("needs_ack", "false").lower() == "true"
    meta["body"] = m.group(2).strip()
    meta["path"] = os.path.relpath(path, ROOT)
    return meta

def all_messages():
    out = []
    d = os.path.join(ROOT, "messages")
    for name in sorted(os.listdir(d)):
        if name.endswith(".md") and not name.startswith("."):
            msg = parse_message(os.path.join(d, name))
            if msg:
                out.append(msg)
    return out

def acked_ids(msgs, by=None):
    return {m.get("re") for m in msgs if m.get("type") == "ack" and (by is None or m.get("from") == by)}

def addressed(msg, role):
    return role in msg["to"] or "all" in msg["to"]

def write_message(args_from, to, mtype, subject, body, re_id="", needs_ack=False, deadline="", refs=""):
    if args_from not in ROLES or args_from == "all":
        raise SystemExit(f"--from must be one of: {ROLES[:-1]}")
    for t in to:
        if t not in ROLES:
            raise SystemExit(f"unknown recipient {t}; allowed: {ROLES}")
    if mtype not in TYPES:
        raise SystemExit(f"--type must be one of {TYPES}")
    ts = now_utc()
    mid = f"{ts.strftime('%Y%m%dT%H%M%SZ')}-{args_from}-{secrets.token_hex(2)}"
    path = os.path.join(ROOT, "messages", f"{mid}.md")
    front = [f"id: {mid}", f"ts: {ts.isoformat(timespec='seconds')}", f"from: {args_from}", f"to: {', '.join(to)}",
             f"type: {mtype}", f"subject: {subject}", f"re: {re_id}", f"needs_ack: {'true' if needs_ack else 'false'}",
             f"deadline: {deadline}", f"refs: {refs}"]
    open(path, "w", encoding="utf-8").write("---\n" + "\n".join(front) + "\n---\n" + body.strip() + "\n")
    return mid, path

def render_timeline(msgs, days=7):
    """Write TIMELINE.md: who talked to whom, in order, with ack latency and response-time stats."""
    cutoff = (now_utc() - timedelta(days=days)).isoformat(timespec="seconds")
    recent = [m for m in msgs if m.get("ts", "") >= cutoff]
    by_id = {m["id"]: m for m in msgs}
    ack_of = {}
    for m in msgs:
        if m["type"] == "ack" and m.get("re") and m["re"] not in ack_of:
            ack_of[m["re"]] = m
    def mins(a, b):
        try:
            return int((datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds() // 60)
        except Exception:
            return None
    out = [f"# Timeline — last {days} days", "", f"<!-- generated by intercom.py render — {now_utc().strftime('%Y-%m-%d %H:%M')} UTC -->", ""]
    out.append("## Response times (messages that required an ack)")
    out.append("| role | received | acked | median min to ack | slowest | still open |")
    out.append("|---|---|---|---|---|---|")
    for role in ROLES[:-1]:
        need = [m for m in recent if addressed(m, role) and m["needs_ack"] and m["type"] != "ack"]
        lat = sorted(x for x in (mins(m["ts"], ack_of[m["id"]]["ts"]) for m in need if m["id"] in ack_of and ack_of[m["id"]]["from"] == role) if x is not None)
        openn = sum(1 for m in need if m["id"] not in ack_of)
        med = lat[len(lat) // 2] if lat else "-"
        out.append(f"| {role} | {len(need)} | {len(lat)} | {med} | {lat[-1] if lat else '-'} | {openn} |")
    pairs = {}
    for m in recent:
        if m["type"] == "ack":
            continue
        for t in m["to"]:
            pairs[(m["from"], t)] = pairs.get((m["from"], t), 0) + 1
    out += ["", "## Who talks to whom (messages, acks excluded)"]
    for (a, b), n in sorted(pairs.items(), key=lambda kv: -kv[1])[:12]:
        out.append(f"- {a} → {b}: {n}")
    out.append("")
    day = None
    for m in recent:
        if m["type"] == "ack":
            continue
        d = m["ts"][:10]
        if d != day:
            day = d
            out += ["", f"## {d}"]
        hm = local_hm(m["ts"])
        tail = ""
        if m["needs_ack"]:
            a = ack_of.get(m["id"])
            tail = f" — acked by {a['from']} after {mins(m['ts'], a['ts'])} min" if a else " — **unacked**"
        re_note = ""
        if m.get("re") and m["re"] in by_id:
            re_note = f" ↩ re {by_id[m['re']]['from']}: {by_id[m['re']]['subject'][:50]}"
        out.append(f"- {hm} **{m['from']} → {', '.join(m['to'])}** [{m['type']}] {m['subject'][:100]}{re_note}{tail}")
    open(os.path.join(ROOT, "TIMELINE.md"), "w", encoding="utf-8").write("\n".join(out) + "\n")

def render_plan(msgs):
    """Write PLAN.md in the agenttrail convention: one component per role, open items as tasks."""
    acks_by = {r: acked_ids(msgs, by=r) for r in ROLES[:-1]}
    answered = {m.get("re") for m in msgs if m.get("re") and m.get("type") != "ack"}
    standby = standby_roles()
    title = CONFIG.get("project") or os.path.basename(os.path.abspath(ROOT))
    out = [f"# {title}", "", f"<!-- generated by intercom.py render — {now_utc().strftime('%Y-%m-%d %H:%M')} UTC; do not edit -->", ""]
    for role in ROLES[:-1]:
        mine = [m for m in msgs if addressed(m, role) and m["type"] != "ack" and m["needs_ack"]]
        open_items = [m for m in mine if m["id"] not in acks_by[role] and m["id"] not in answered]
        working = [m for m in mine if m["id"] in acks_by[role] and m["id"] not in answered]
        done = [m for m in mine if m["id"] in answered][-6:]
        waiting_on = sorted({t for m in msgs if m["from"] == role and m["needs_ack"] and m["type"] != "ack"
                             and m["id"] not in answered for t in m["to"] if t != role and t != "all"
                             and m["id"] not in acks_by.get(t, set()) | answered})
        ts, kind = role_activity(role, msgs)
        age = minutes_since(ts) if ts else None
        if role in CONFIG.get("human_roles", []):
            state = f"human — {len(open_items)} open"
        elif role in standby:
            state = "standby"
        else:
            state = f"{kind}, {age} min ago" if age is not None else "no sign of life yet"
        out.append(f"## {role.capitalize()} {{#{role}}}")
        out.append(f"tech: {state}")
        out.append(f"files: [messages/*-{role}-*.md, state/heartbeat-{role}.json]")
        if waiting_on:
            out.append(f"needs: [{', '.join(waiting_on)}]")
        if len(open_items) > 12:
            out.append(f"- [!] {len(open_items) - 12} older open items not shown {{#m-{role}-backlog}}")
            out.append(f"  by: {role}")
            open_items = open_items[-12:]
        for m in open_items:
            mark = "[!]" if m["type"] == "block" else "[ ]"
            dl = f" · due {m['deadline']}" if m.get("deadline") else ""
            out.append(f"- {mark} {m['subject'][:90]}{dl} {{#m-{m['id']}}}")
            out.append(f"  by: {role}")
            out.append(f"  from: {m['from']}")
        for m in working:
            out.append(f"- [~] {m['subject'][:90]} {{#m-{m['id']}}}")
            out.append(f"  by: {role}")
            out.append(f"  from: {m['from']}")
        for m in done:
            out.append(f"- [x] {m['subject'][:90]} {{#m-{m['id']}}}")
            out.append(f"  by: {role}")
        out.append("")
    decisions = [m for m in msgs if m["type"] == "decision"][-10:]
    if decisions:
        out.append("## decisions")
        for m in decisions:
            out.append(f"- {m['ts'][:10]}: {m['subject'][:120]} ({m['from']})")
        out.append("")
    open(os.path.join(ROOT, "PLAN.md"), "w", encoding="utf-8").write("\n".join(out) + "\n")

def render():
    msgs = all_messages()
    acks = acked_ids(msgs)
    for role in ROLES[:-1]:
        lines = [f"# Inbox {role} — generated {now_utc().strftime('%Y-%m-%d %H:%M')} UTC", ""]
        open_items = [m for m in msgs if addressed(m, role) and m["type"] != "ack" and m["needs_ack"] and m["id"] not in acked_ids(msgs, by=role)]
        lines.append(f"## Open (needs answer/ack: {len(open_items)})")
        for m in open_items:
            dl = f" · due {m['deadline']}" if m.get("deadline") else ""
            lines.append(f"- **{m['id']}** from `{m['from']}` [{m['type']}] {m['subject']}{dl}")
            for r in m["refs"]:
                lines.append(f"  - ref `{r}`")
            lines.append(f"  - {m['body'].splitlines()[0][:160] if m['body'] else ''}")
        lines.append("")
        lines.append("## Recent (everything addressed to this role, newest first)")
        for m in [x for x in msgs if addressed(x, role)][-20:][::-1]:
            state = "✔" if (not m["needs_ack"] or m["id"] in acks or m["type"] == "ack") else "○"
            lines.append(f"- {state} {m['id']} `{m['from']}` [{m['type']}] {m['subject']}")
        open(os.path.join(ROOT, f"INBOX-{role}.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    lock_lines = ["# Locks — active resource locks (worktree/branch/anything)", ""]
    for name in sorted(os.listdir(os.path.join(ROOT, "locks"))):
        if name.endswith(".json"):
            l = json.load(open(os.path.join(ROOT, "locks", name)))
            lock_lines.append(f"- `{l['resource']}` — {l['holder']} since {l['since']} until {l['expires']} · {l['purpose']}")
    open(os.path.join(ROOT, "LOCKS.md"), "w", encoding="utf-8").write("\n".join(lock_lines) + "\n")
    render_plan(msgs)
    render_timeline(msgs)

def cmd_post(a):
    body = open(a.body_file, encoding="utf-8").read() if a.body_file else (a.body or "")
    sync(push=False)
    mid, path = write_message(a.frm, a.to.split(","), a.type, a.subject, body, a.re or "", a.needs_ack, a.deadline or "", a.refs or "")
    render()
    commit(["messages", "INBOX-*.md", "LOCKS.md"], f"msg({a.frm}→{a.to}): [{a.type}] {a.subject}")
    sync()
    print(mid)

def cmd_ack(a):
    sync(push=False)
    mid, _ = write_message(a.frm, [next((m["from"] for m in all_messages() if m["id"] == a.id), "all")], "ack", f"ack {a.id}", a.note or "", a.id)
    render()
    commit(["messages", "INBOX-*.md"], f"ack({a.frm}): {a.id}")
    sync()
    print(mid)

def cmd_inbox(a):
    sync(push=False)
    msgs = all_messages()
    for m in msgs:
        if not addressed(m, a.role) or m["type"] == "ack":
            continue
        acked = m["id"] in acked_ids(msgs, by=a.role)
        if a.open and (not m["needs_ack"] or acked):
            continue
        flag = "○ OPEN" if (m["needs_ack"] and not acked) else "  "
        print(f"{flag} {m['id']} {local_hm(m.get('ts',''))} {m['from']:>8} [{m['type']}] {m['subject']}")
        if a.verbose:
            for r in m["refs"]:
                print(f"           ref {r}")
            print("           " + m["body"].replace("\n", "\n           "))

def state_path(role):
    return os.path.join(ROOT, "state", f"{role}.json")

def cmd_watch(a):
    """Wake-up loop: prints one line per new message addressed to ROLE; --once for hooks/cron.

    With --peers-every N the same loop also watches the OTHER roles and reports
    anyone who shows no sign of life; --auto-ping additionally sends them one
    wake-up message per silence episode."""
    watch_state = {"last_peer_check": 0.0}
    seen = set()
    if os.path.exists(state_path(a.role)):
        seen = set(json.load(open(state_path(a.role))).get("seen", []))
    while True:
        sync(push=False)
        msgs = [m for m in all_messages() if addressed(m, a.role) and m["from"] != a.role and m["id"] not in seen]
        for m in msgs:
            print(f"NEW {m['id']} ({local_hm(m.get('ts',''))} local) from {m['from']} [{m['type']}] {m['subject']}{' (ACK REQUIRED)' if m['needs_ack'] else ''}", flush=True)
            seen.add(m["id"])
        if msgs:
            json.dump({"seen": sorted(seen), "updated": now_utc().isoformat(timespec="seconds")}, open(state_path(a.role), "w"))
            commit(["state"], f"state({a.role}): {len(msgs)} seen")
            sync()
            if a.notify:
                subprocess.run(["osascript", "-e", f'display notification "{len(msgs)} new intercom message(s)" with title "Intercom · {a.role}"'], check=False)
        if a.peers_every and (time.time() - watch_state["last_peer_check"]) >= a.peers_every * 60:
            watch_state["last_peer_check"] = time.time()
            limit = CONFIG.get("heartbeat_alert_minutes", 20)
            all_msgs = all_messages()
            parked = standby_roles() | set(CONFIG.get("human_roles", []))
            for other in ROLES[:-1]:
                if other == a.role or other in parked:
                    continue
                ts, kind = role_activity(other, all_msgs)
                quiet = minutes_since(ts) if ts else None
                if ts is None or (quiet is not None and quiet >= limit):
                    label = f"{quiet}min since {kind}" if ts else "no sign of life at all"
                    print(f"PEER-QUIET {other}: {label}", flush=True)
                    if a.auto_ping:
                        auto_ping(a.role, other, quiet or 0, kind if ts else "nothing")
        if a.once:
            return
        time.sleep(a.interval)

def lock_file(resource):
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", resource).strip("_")
    return os.path.join(ROOT, "locks", f"{slug}.json")

def cmd_lock(a):
    sync(push=False)
    p = lock_file(a.resource)
    if a.action == "list":
        for name in sorted(os.listdir(os.path.join(ROOT, "locks"))):
            if name.endswith(".json"):
                l = json.load(open(os.path.join(ROOT, "locks", name)))
                print(f"{l['resource']:<45} {l['holder']:<9} until {l['expires']}  {l['purpose']}")
        return
    if a.action == "acquire":
        if os.path.exists(p):
            l = json.load(open(p))
            if l["holder"] != a.holder and datetime.fromisoformat(l["expires"]) > now_utc():
                print(f"BUSY: {l['resource']} held by {l['holder']} until {l['expires']} — {l['purpose']}. Do not take over; ask the holder with `intercom.py post --type question`.")
                raise SystemExit(2)
        lock = {"resource": a.resource, "holder": a.holder, "purpose": a.purpose, "since": now_utc().isoformat(timespec="seconds"),
                "expires": (now_utc() + timedelta(minutes=a.ttl_min)).isoformat(timespec="seconds")}
        json.dump(lock, open(p, "w"), indent=1)
        render()
        commit(["locks", "LOCKS.md"], f"lock({a.holder}): {a.resource}")
        sync()
        print(f"LOCKED for {a.holder} until {lock['expires']}")
    elif a.action == "release":
        if not os.path.exists(p):
            print("no such lock"); return
        l = json.load(open(p))
        if l["holder"] != a.holder:
            raise SystemExit(f"lock is held by {l['holder']}, not {a.holder}")
        os.remove(p)
        render()
        commit(["locks", "LOCKS.md"], f"unlock({a.holder}): {a.resource}")
        sync()
        print("RELEASED")

def standby_path():
    return os.path.join(ROOT, "state", "standby.json")

def standby_roles():
    try:
        return set(json.load(open(standby_path(), encoding="utf-8")).get("roles", []))
    except Exception:
        return set()

def cmd_standby(a):
    """Mark a role as having no running assignment — it will not be pinged while quiet."""
    roles = standby_roles()
    roles.discard(a.role) if a.off else roles.add(a.role)
    json.dump({"roles": sorted(roles)}, open(standby_path(), "w", encoding="utf-8"), indent=1)
    sync(push=False)
    commit(["state"], f"standby({a.role}): {'off' if a.off else 'on'}")
    sync()
    print(f"standby {'off' if a.off else 'on'} for {a.role}; currently: {', '.join(sorted(roles)) or '-'}")

def heartbeat_path(role):
    return os.path.join(ROOT, "state", f"heartbeat-{role}.json")

def read_heartbeat(role):
    p = heartbeat_path(role)
    if not os.path.exists(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None

def minutes_since(iso):
    try:
        return int((now_utc() - datetime.fromisoformat(iso)).total_seconds() // 60)
    except Exception:
        return None

def role_activity(role, msgs):
    """Newest sign of life for a role: heartbeat, own message, or a tracked git ref."""
    best, kind = None, "nothing"
    hb = read_heartbeat(role)
    if hb and hb.get("ts"):
        best, kind = hb["ts"], f"heartbeat ({hb.get('note', '')[:40]})" if hb.get("note") else "heartbeat"
    own = [m for m in msgs if m["from"] == role]
    if own:
        ts = own[-1].get("ts")
        if ts and (best is None or ts > best):
            best, kind = ts, f"message {own[-1]['id']}"
    src = CONFIG.get("activity_sources", {}).get(role)
    if src:
        # src: {"repo": "/path/to/repo", "refs": ["origin/feature-x", "origin/verify"]}
        repo = src.get("repo", ROOT)
        for ref in src.get("refs", []):
            r = subprocess.run(["git", "-C", repo, "log", "-1", "--format=%cI", ref],
                               capture_output=True, text=True)
            ts = r.stdout.strip()
            if r.returncode == 0 and ts:
                try:
                    ts = datetime.fromisoformat(ts).astimezone(timezone.utc).isoformat(timespec="seconds")
                except ValueError:
                    continue
                if best is None or ts > best:
                    best, kind = ts, f"commit on {ref}"
    return best, kind

def cmd_heartbeat(a):
    """Say 'I am alive and working on X'. Cheap: writes a file, no message traffic."""
    hb = {"role": a.role, "ts": now_utc().isoformat(timespec="seconds"), "note": a.note or ""}
    json.dump(hb, open(heartbeat_path(a.role), "w", encoding="utf-8"), indent=1)
    if not a.local:
        sync(push=False)
        commit(["state"], f"heartbeat({a.role})")
        sync()
    print(f"heartbeat {a.role} {hb['ts']}" + (f" — {hb['note']}" if hb["note"] else ""))

def cooldown_path(role):
    return os.path.join(ROOT, "state", f"autoping-{role}.json")

def auto_ping(from_role, silent_role, quiet_min, kind):
    """Post one ping per silence episode, never a storm."""
    cd = {}
    p = cooldown_path(from_role)
    if os.path.exists(p):
        try:
            cd = json.load(open(p, encoding="utf-8"))
        except Exception:
            cd = {}
    last = cd.get(silent_role)
    limit = CONFIG.get("auto_ping_cooldown_minutes", 30)
    if last and (minutes_since(last) or 0) < limit:
        return False
    body = (f"Automatic wake-up from {from_role}'s watchdog.\n\n"
            + (f"No sign of life from `{silent_role}` at all — no heartbeat, no message, "
               "no tracked commit.\n\n" if kind == "nothing at all" else
               f"No sign of life from `{silent_role}` for {quiet_min} minutes "
               f"(last signal: {kind}).\n\n")
            + "Please answer in one line: are you working (on what), blocked, waiting for a decision, "
            "or idle? If a prompt in your tool is waiting for confirmation, that looks exactly like "
            "silence from here.\n\n"
            + f"Send a heartbeat while you work so this does not fire again:\n"
            f"  intercom.py heartbeat {silent_role} --note \"<what you are doing>\"")
    tmp = os.path.join(ROOT, "state", ".autoping-body.md")
    open(tmp, "w", encoding="utf-8").write(body)
    try:
        mid, _ = write_message(from_role, [silent_role], "ping",
                               (f"Watchdog: no sign of life from {silent_role} at all" if kind == "nothing at all"
                                else f"Watchdog: no sign of life from {silent_role} for {quiet_min} min"),
                               body, needs_ack=True)
        cd[silent_role] = now_utc().isoformat(timespec="seconds")
        json.dump(cd, open(p, "w", encoding="utf-8"), indent=1)
        render()
        commit(["messages", "state"], f"watchdog({from_role}): ping {silent_role}")
        sync()
        print(f"AUTO-PING sent to {silent_role} ({mid})", flush=True)
        return True
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)

def cmd_peers(a):
    """Who is alive? One line per role, newest sign of life and its kind."""
    sync(push=False)
    msgs = all_messages()
    limit = a.quiet_min if a.quiet_min >= 0 else CONFIG.get("heartbeat_alert_minutes", 20)
    stale = False
    parked = standby_roles() | set(CONFIG.get("human_roles", []))
    for role in ROLES[:-1]:
        if role == a.me:
            continue
        if role in parked:
            print(f"parked {role}: no running assignment / human role (never auto-pinged)")
            continue
        ts, kind = role_activity(role, msgs)
        if ts is None:
            print(f"UNKNOWN {role}: no heartbeat, no message, no tracked commit")
            stale = True
            if a.auto_ping and a.me:
                auto_ping(a.me, role, 0, "nothing at all")
            continue
        quiet = minutes_since(ts) or 0
        flag = "QUIET  " if quiet >= limit else "alive  "
        if quiet >= limit:
            stale = True
        print(f"{flag}{role}: {quiet}min since {kind}")
        if quiet >= limit and a.auto_ping and a.me:
            auto_ping(a.me, role, quiet, kind)
    raise SystemExit(1 if stale else 0)

def cmd_due(a):
    """Deadline and silence watchdog: prints only what needs action. Exit 1 if anything is due."""
    sync(push=False)
    msgs = all_messages()
    now = now_utc()
    found = False
    for m in msgs:
        if m["type"] == "ack" or not m["needs_ack"]:
            continue
        if any(m["id"] in acked_ids(msgs, by=r) for r in m["to"]):
            continue
        dl = (m.get("deadline") or "").strip()
        overdue = False
        if dl:
            try:
                overdue = datetime.fromisoformat(dl).replace(tzinfo=timezone.utc) < now
            except ValueError:
                overdue = dl < now.strftime("%Y-%m-%d")
        age_min = 0
        try:
            age_min = int((now - datetime.fromisoformat(m["ts"])).total_seconds() // 60)
        except Exception:
            pass
        if overdue or (a.unanswered_min and age_min >= a.unanswered_min):
            found = True
            print(f"DUE {m['id']} to={','.join(m['to'])} [{m['type']}] {m['subject']}"
                  f" | age={age_min}min{' | deadline ' + dl if dl else ''}")
    limit = a.silence_min or CONFIG.get("silence_alert_minutes", 60)
    for role in ROLES[:-1]:
        ts, kind = role_activity(role, msgs)
        if ts is None:
            print(f"SILENT {role}: no heartbeat, no message, no tracked commit")
            found = True
            continue
        quiet = minutes_since(ts)
        if quiet is not None and quiet >= limit:
            print(f"SILENT {role}: {quiet}min since {kind}")
            found = True
    if not found and a.verbose:
        print("nothing due")
    raise SystemExit(1 if found else 0)

def cmd_init(a):
    roles = [r.strip() for r in a.roles.split(",") if r.strip()]
    if "all" in roles:
        raise SystemExit("'all' is reserved as a broadcast target")
    cfg = {"roles": roles, "branch": a.branch, "remote": a.remote,
           "extra_remotes": [r for r in (a.extra_remotes or "").split(",") if r],
           "silence_alert_minutes": a.silence_min}
    json.dump(cfg, open(CONFIG_PATH, "w", encoding="utf-8"), indent=2)
    for d in ("messages", "locks", "state"):
        os.makedirs(os.path.join(ROOT, d), exist_ok=True)
        keep = os.path.join(ROOT, d, ".gitkeep")
        open(keep, "a").close()
    print(f"wrote {CONFIG_PATH} with roles: {', '.join(roles)}")
    print("next: commit it on the intercom branch and push, then run: intercom.py watch <your-role>")

def main():
    for d in ("messages", "locks", "state"):
        os.makedirs(os.path.join(ROOT, d), exist_ok=True)
    ap = argparse.ArgumentParser(
        description="Agent Intercom — git-backed messages, locks and deadlines for AI agent teams.",
        epilog="examples:\n"
               "  intercom.py init --roles human,lead,builder,verifier\n"
               "  intercom.py post --from lead --to builder --type task --subject 'Add retry' --body-file task.md --needs-ack --deadline 2026-01-31\n"
               "  intercom.py inbox builder --open\n"
               "  intercom.py watch lead --notify\n"
               "  intercom.py due --silence-min 60\n"
               "  intercom.py lock acquire ~/worktree-a --holder builder --purpose 'refactor'",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("post"); p.add_argument("--from", dest="frm", required=True); p.add_argument("--to", required=True); p.add_argument("--type", required=True); p.add_argument("--subject", required=True); p.add_argument("--body"); p.add_argument("--body-file"); p.add_argument("--re"); p.add_argument("--needs-ack", action="store_true"); p.add_argument("--deadline"); p.add_argument("--refs", help="path@branch@commit; separate multiple with ;"); p.set_defaults(fn=cmd_post)
    p = sub.add_parser("ack"); p.add_argument("id"); p.add_argument("--from", dest="frm", required=True); p.add_argument("--note"); p.set_defaults(fn=cmd_ack)
    p = sub.add_parser("inbox"); p.add_argument("role"); p.add_argument("--open", action="store_true"); p.add_argument("-v", "--verbose", action="store_true"); p.set_defaults(fn=cmd_inbox)
    p = sub.add_parser("watch"); p.add_argument("role"); p.add_argument("--interval", type=int, default=60); p.add_argument("--once", action="store_true"); p.add_argument("--notify", action="store_true"); p.add_argument("--peers-every", type=int, default=0, metavar="MIN", help="also check the other roles every MIN minutes"); p.add_argument("--auto-ping", action="store_true", help="with --peers-every: send one wake-up message per silence episode"); p.set_defaults(fn=cmd_watch)
    p = sub.add_parser("lock"); p.add_argument("action", choices=["acquire", "release", "list"]); p.add_argument("resource", nargs="?", default=""); p.add_argument("--holder"); p.add_argument("--purpose", default=""); p.add_argument("--ttl-min", type=int, default=240); p.set_defaults(fn=cmd_lock)
    p = sub.add_parser("render"); p.set_defaults(fn=lambda a: (sync(push=False), render(), commit(["INBOX-*.md", "LOCKS.md"], "render"), sync()))
    p = sub.add_parser("sync"); p.set_defaults(fn=lambda a: sync())
    p = sub.add_parser("heartbeat", help="record that this role is alive and working"); p.add_argument("role"); p.add_argument("--note", default=""); p.add_argument("--local", action="store_true", help="write only, do not commit/push"); p.set_defaults(fn=cmd_heartbeat)
    p = sub.add_parser("standby", help="park a role: quiet is expected, do not ping it"); p.add_argument("role"); p.add_argument("--off", action="store_true"); p.set_defaults(fn=cmd_standby)
    p = sub.add_parser("peers", help="who is alive? exit 1 if anyone is quiet"); p.add_argument("--me", default=""); p.add_argument("--quiet-min", type=int, default=-1); p.add_argument("--auto-ping", action="store_true"); p.set_defaults(fn=cmd_peers)
    p = sub.add_parser("due", help="list overdue / unanswered messages and silent roles"); p.add_argument("--silence-min", type=int, default=0); p.add_argument("--unanswered-min", type=int, default=0); p.add_argument("-v", "--verbose", action="store_true"); p.set_defaults(fn=cmd_due)
    p = sub.add_parser("init", help="create intercom.json in this directory"); p.add_argument("--roles", default="human,lead,builder,verifier"); p.add_argument("--branch", default="intercom"); p.add_argument("--remote", default="origin"); p.add_argument("--extra-remotes", default=""); p.add_argument("--silence-min", type=int, default=60); p.set_defaults(fn=cmd_init)
    a = ap.parse_args()
    if a.cmd in ("lock",) and a.action != "list" and not a.holder:
        raise SystemExit("--holder is required")
    a.fn(a)

if __name__ == "__main__":
    main()
