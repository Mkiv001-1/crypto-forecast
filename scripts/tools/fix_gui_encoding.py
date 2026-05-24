"""Fix mojibake inside quoted strings in client GUI sources."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLIENT = ROOT / "scripts" / "client"

MOJIBAKE_HINTS = ("â", "ð", "ï¸", "Å", "Ã")


def _needs_fix(text: str) -> bool:
    return any(h in text for h in MOJIBAKE_HINTS)


def fix_mojibake_run(s: str) -> str | None:
    buf = bytearray()
    for c in s:
        try:
            buf.extend(c.encode("cp1252"))
        except UnicodeEncodeError:
            if ord(c) < 256:
                buf.append(ord(c))
            else:
                return None
    try:
        return buf.decode("utf-8")
    except UnicodeDecodeError:
        return None


def fix_quoted_string(inner: str) -> str:
    if not _needs_fix(inner):
        return inner
    fixed = fix_mojibake_run(inner)
    if fixed is not None:
        return fixed
    # Mixed: fix leading/trailing mojibake runs only
    parts: list[str] = []
    i = 0
    while i < len(inner):
        if inner[i] not in ("â", "ð"):
            parts.append(inner[i])
            i += 1
            continue
        j = i
        while j < len(inner):
            try:
                inner[j].encode("cp1252")
                j += 1
            except UnicodeEncodeError:
                if ord(inner[j]) < 256:
                    j += 1
                else:
                    break
        run = inner[i:j]
        fixed_run = fix_mojibake_run(run) if run else None
        parts.append(fixed_run if fixed_run is not None else run)
        i = max(j, i + 1)
    return "".join(parts)


def fix_line(line: str) -> str:
    if not _needs_fix(line):
        return line

    def repl(match: re.Match) -> str:
        inner = match.group(1)
        fixed = fix_quoted_string(inner)
        if fixed == inner:
            return match.group(0)
        return f'"{fixed}"'

    return re.sub(r'"([^"\\]*(?:\\.[^"\\]*)*)"', repl, line)


def fix_file(path: Path) -> bool:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    changed = False
    new_lines = []
    for line in lines:
        bare = line.rstrip("\n")
        fixed = fix_line(bare)
        if fixed != bare:
            changed = True
            new_lines.append(fixed + ("\n" if line.endswith("\n") else ""))
        else:
            new_lines.append(line)
    if changed:
        path.write_text("".join(new_lines), encoding="utf-8", newline="")
    return changed


def main() -> None:
    for path in sorted(CLIENT.rglob("*.py")):
        if fix_file(path):
            print("Fixed:", path.relative_to(ROOT))


if __name__ == "__main__":
    main()
