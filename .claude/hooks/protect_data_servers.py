#!/usr/bin/env python3
r"""PreToolUse hook: protect the lab's network data servers.

Policy (edit the tables below to change it)
-------------------------------------------
READ-ONLY  - reading allowed, ANY delete/write/rename/move blocked:
    Q:              \\cbsuruizfs1.biohpc.cornell.edu\storage
    S: T: U: V:     \\132.236.112.122\ayadataB4 / B2 / B3 / B1
    W: X: Y: Z:     \\132.236.112.212\ayadata4 / 3 / 2 / 1
FULL ACCESS - read/write allowed (server working space, not original data):
    N:              \\cbsuruizfs1.biohpc.cornell.edu\workdir
NO ACCESS  - blocked entirely (not part of the allowed set):
    M: P:           workdir/storage shares on cbsuruiz01

The original field data on these servers must never be modified or
deleted. This hook denies:
  * Write/Edit/NotebookEdit targeting a protected location
  * Read/Glob/Grep on the no-access locations
  * Bash/PowerShell commands that reference a no-access location at all
  * Bash/PowerShell commands that reference a read-only location together
    with a mutating verb, an output redirect, a copy/robocopy destination,
    or a -Destination/-OutFile/of= style write target

This is a guardrail against accidental agent writes, NOT a sandbox: a
script that opens a server file for writing internally cannot be seen
from its command line. Real protection should also exist at the share
level (read-only mount / ACLs).

Exit: prints a permissionDecision=deny JSON and exits 0 to block;
prints nothing to leave the normal permission flow untouched.
"""
import json
import re
import sys

READ_ONLY_DRIVES = set("QSTUVWXYZ")
NO_ACCESS_DRIVES = set("MP")

# UNC host policy: "ro" (read-only), "blocked", "allow" (unrestricted),
# or {share: policy} (for the dict form, any share not listed is blocked).
UNC_HOSTS = {
    "132.236.112.122": "ro",                       # ayadataB1-B4 (S: T: U: V:)
    "132.236.112.212": "ro",                       # ayadata1-4   (W: X: Y: Z:)
    "cbsuruizfs1.biohpc.cornell.edu": {"storage": "ro", "workdir": "allow"},  # Q: ro; N: rw
    "cbsuruizfs1": {"storage": "ro", "workdir": "allow"},
    "cbsuruiz01.biohpc.cornell.edu": "blocked",    # M: P:
    "cbsuruiz01": "blocked",
}

RO_MSG = (
    "READ-ONLY data-server policy: {loc} holds original field data "
    "(ayadata / Q: storage). Reading is allowed, but delete/write/rename/"
    "move/copy-onto is banned ({why}). Copy the data to a local drive "
    "(e.g. D:) if you need a writable version. If this command only "
    "reads, split it so no mutating operation appears in the same "
    "command as the server path."
)
BLOCK_MSG = (
    "{loc} is not an allowed server location for the agent. Allowed: "
    "ayadata drives (S: T: U: V: W: X: Y: Z:) and Q: read-only, and "
    "N: (workdir working space) read-write."
)

# Verbs/cmdlets that can change or delete data. If one appears in the
# same command as a read-only server path, the call is denied.
MUTATING_RE = re.compile(
    r"(?i)(?:(?<![\w.-])("
    r"rm|del|erase|rd|rmdir|unlink|shred|truncate|touch|ln|"
    r"mv|move|ren|rename|mkdir|md|"
    r"remove-item[a-z]*|move-item[a-z]*|rename-item[a-z]*|new-item[a-z]*|"
    r"clear-(?:content|item[a-z]*)|set-(?:content|item[a-z]*|acl)|"
    r"add-content|out-file|export-[a-z]+|"
    r"ri|rni|mi|ni|clc|ac|sc|"
    r"tee|tee-object|icacls|cacls|takeown|attrib"
    r")(?![\w.-])"
    r"|sed\s+-[a-z]*i"
    r"|::\s*(?:delete|move|copy|create|replace|openwrite|writeall\w*|appendall\w*)"
    r")"
)

COPY_VERBS_RE = re.compile(r"(?i)(?<![\w.-])(robocopy|xcopy|copy-item|cpi|cp|copy|rsync)\b")
ROBOCOPY_DANGER_RE = re.compile(r"(?i)/(mir|purge|mov|move)\b|--delete\b")


def classify_drive(letter):
    u = letter.upper()
    if u in READ_ONLY_DRIVES:
        return "ro"
    if u in NO_ACCESS_DRIVES:
        return "blocked"
    return None


def classify_unc(host, share):
    pol = UNC_HOSTS.get(host.lower())
    if pol is None:
        return None
    if isinstance(pol, dict):
        pol = pol.get(share.lower(), "blocked")
    return None if pol == "allow" else pol


def classify_path(p):
    """Classify a single path string: 'ro', 'blocked', or None."""
    if not p:
        return None
    s = str(p).strip().strip("'\"")
    m = re.match(r"^\\\\([\w.-]+)[\\/]+([^\\/]+)", s)
    if m:
        return classify_unc(m.group(1), m.group(2))
    m = re.match(r"^//([\w.-]+)/+([^/]+)", s)
    if m:
        return classify_unc(m.group(1), m.group(2))
    m = re.match(r"^([A-Za-z]):", s)
    if m:
        return classify_drive(m.group(1))
    m = re.match(r"^/([A-Za-z])(?:/|$)", s)  # git-bash /q/... form
    if m:
        return classify_drive(m.group(1))
    return None


def scan_refs(cmd):
    """Find every protected-location reference inside a command string."""
    refs = {"ro": set(), "blocked": set()}

    def add(c, txt):
        if c:
            refs[c].add(txt)

    for m in re.finditer(r"\\\\([\w.-]+)[\\/]([^\\/\s'\";|>]+)", cmd):
        add(classify_unc(m.group(1), m.group(2)), m.group(0))
    for m in re.finditer(r"(?<![:\w])//([\w.-]+)/([^/\s'\";|>]+)", cmd):
        add(classify_unc(m.group(1), m.group(2)), m.group(0))
    for m in re.finditer(r"(?<![\w.$])([A-Za-z]):", cmd):
        add(classify_drive(m.group(1)), m.group(1).upper() + ":")
    for m in re.finditer(r"(?<![\w.:/\\-])/([A-Za-z])(?=[/\s]|$)", cmd):
        add(classify_drive(m.group(1)), "/" + m.group(1).lower() + "/")
    return refs


def copy_dest(cmd):
    """Best-effort destination of copy-like verbs (robocopy: 2nd arg,
    others: last path-ish token). Returns the dest token or None."""
    for seg in re.split(r"[;|&\n]+", cmd):
        m = COPY_VERBS_RE.search(seg)
        if not m:
            continue
        if re.search(r"(?i)-destination", seg):
            continue  # explicit flag handled by iter_write_targets
        verb = m.group(1).lower()
        toks = []
        for t in re.findall(r"\"[^\"]*\"|'[^']*'|\S+", seg[m.end():]):
            t = t.strip("'\"")
            if not t or t.startswith("-"):
                continue
            if verb in ("robocopy", "xcopy") and re.match(r"^/[a-z0-9:.]+$", t, re.I):
                continue  # /E /MIR style switches
            toks.append(t)
        if verb == "robocopy":
            if len(toks) >= 2:
                return toks[1]
        elif len(toks) >= 2:
            return toks[-1]
    return None


def iter_write_targets(cmd):
    """Tokens the command writes INTO: redirects, dest-style flags, dd of=."""
    for m in re.finditer(r">>?\s*['\"]?([^\s'\">|;&]+)", cmd):
        yield m.group(1)
    for m in re.finditer(
        r"(?i)-(?:destination|outfile|filepath|targetpath|literalpath|newname)"
        r"\s*[:\s]\s*['\"]?([^\s'\">|;&]+)",
        cmd,
    ):
        yield m.group(1)
    for m in re.finditer(r"(?i)(?<![\w-])of=['\"]?([^\s'\"]+)", cmd):
        yield m.group(1)
    d = copy_dest(cmd)
    if d:
        yield d


def deny(reason):
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        },
        sys.stdout,
    )
    sys.exit(0)


def check_command(cmd):
    refs = scan_refs(cmd)
    if refs["blocked"]:
        deny(BLOCK_MSG.format(loc=", ".join(sorted(refs["blocked"]))))
    for target in iter_write_targets(cmd):
        if classify_path(target):
            deny(RO_MSG.format(loc=target, why="command writes into it"))
    if refs["ro"]:
        loc = ", ".join(sorted(refs["ro"]))
        m = MUTATING_RE.search(cmd)
        if m:
            deny(RO_MSG.format(loc=loc, why="mutating operation '%s' found" % m.group(0).strip()))
        if re.search(r"(?i)\b(robocopy|rsync)\b", cmd) and ROBOCOPY_DANGER_RE.search(cmd):
            deny(RO_MSG.format(loc=loc, why="robocopy/rsync purge/move/delete flag found"))


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return  # unparsable input: stay out of the way
    tool = data.get("tool_name", "")
    ti = data.get("tool_input") or {}

    if tool in ("Write", "Edit", "NotebookEdit"):
        path = ti.get("file_path") or ti.get("notebook_path")
        c = classify_path(path)
        if c == "blocked":
            deny(BLOCK_MSG.format(loc=path))
        if c == "ro":
            deny(RO_MSG.format(loc=path, why="file modification tool"))
    elif tool in ("Read", "Glob", "Grep"):
        for key in ("file_path", "path", "pattern"):
            if classify_path(ti.get(key)) == "blocked":
                deny(BLOCK_MSG.format(loc=ti.get(key)))
    elif tool in ("Bash", "PowerShell"):
        check_command(ti.get("command") or "")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:  # never break the session on a hook bug
        print("protect_data_servers hook error: %r" % (e,), file=sys.stderr)
        sys.exit(0)
