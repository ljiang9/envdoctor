#!/usr/bin/env python3
"""envdoctor: 检查 .env.example 与代码实际引用的环境变量是否一致。

纯本地、纯标准库。用法：
    python -m envdoctor ./your-project
    python -m envdoctor ./your-project --strict   # 有缺失则 exit 1（CI 用）
    python -m envdoctor ./your-project --fix      # 把缺失变量追加进 .env.example
"""
import argparse
import json
import os
import re
import sys

EXAMPLE_NAMES = (".env.example", ".env.sample", ".env.template")
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv",
             "dist", "build", "target", ".tox", ".mypy_cache", "vendor"}
CODE_EXTS = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
             ".go", ".rs", ".sh", ".bash", ".zsh", ".yml", ".yaml"}

V = r"[A-Za-z_][A-Za-z0-9_]*"

# (正则, 变量分组, 默认值分组或None, 无分组即视为有默认值)
PATTERNS = [
    (re.compile(r'os\.environ\[\s*["\'](' + V + r')["\']\s*\]'), 1, None, False),
    (re.compile(r'os\.environ\.get\(\s*["\'](' + V + r')["\']\s*(?:,\s*([^)]*))?\)'), 1, 2, False),
    (re.compile(r'os\.getenv\(\s*["\'](' + V + r')["\']\s*(?:,\s*([^)]*))?\)'), 1, 2, False),
    (re.compile(r'(?<![\w.])getenv\(\s*["\'](' + V + r')["\']\s*(?:,\s*([^)]*))?\)'), 1, 2, False),
    (re.compile(r'os\.environ\.setdefault\(\s*["\'](' + V + r')["\']'), 1, None, True),
    (re.compile(r'process\.env\.([A-Za-z_][A-Za-z0-9_]*)'), 1, None, False),
    (re.compile(r'process\.env\[\s*["\'](' + V + r')["\']\s*\]'), 1, None, False),
    (re.compile(r'import\.meta\.env\.([A-Za-z_][A-Za-z0-9_]*)'), 1, None, False),
    (re.compile(r'Deno\.env\.get\(\s*["\'](' + V + r')["\']'), 1, None, False),
    (re.compile(r'os\.Getenv\(\s*"' + V + r'"\s*\)'.replace(V, '(' + V + ')')), 1, None, False),
    (re.compile(r'os\.LookupEnv\(\s*"' + V + r'"\s*\)'.replace(V, '(' + V + ')')), 1, None, False),
    (re.compile(r'std::env::var\(\s*"' + V + r'"\s*\)'.replace(V, '(' + V + ')')), 1, None, False),
    (re.compile(r'(?<![\w:])env!\(\s*"' + V + r'"\s*\)'.replace(V, '(' + V + ')')), 1, None, False),
    (re.compile(r'option_env!\(\s*"' + V + r'"\s*\)'.replace(V, '(' + V + ')')), 1, None, True),
    (re.compile(r'\$\{(' + V + r'):[^}]*\}'), 1, None, True),   # ${VAR:-def} / ${VAR:=def}
    (re.compile(r'\$\{(' + V + r')\}'), 1, None, False),
    (re.compile(r'\$(' + V + r')\b'), 1, None, False),
]


def find_example(root):
    for name in EXAMPLE_NAMES:
        p = os.path.join(root, name)
        if os.path.isfile(p):
            return p
    return None


def strip_inline_comment(val):
    """去掉行尾注释（引号内的 # 保留）。"""
    val = val.strip()
    if val[:1] in ("'", '"'):
        q = val[0]
        end = val.find(q, 1)
        if end != -1:
            return val[1:end]
        return val[1:]
    # 非引号值：第一个 " #" 之后算注释
    idx = val.find(" #")
    if idx != -1:
        val = val[:idx]
    return val.strip().strip("'\"")


def parse_example(path):
    defined = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            m = re.match(r"(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", s)
            if m:
                defined[m.group(1)] = strip_inline_comment(m.group(2))
    return defined


def scan_file(path):
    """返回 {变量名: 是否有默认值}。"""
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except OSError:
        return {}
    found = {}
    for rx, vg, dg, always_default in PATTERNS:
        for m in rx.finditer(text):
            name = m.group(vg)
            if always_default:
                has_default = True
            elif dg is not None:
                g = m.group(dg)
                has_default = g is not None and g.strip() != ""
            else:
                has_default = False
            found[name] = found.get(name, False) or has_default
    return found


def levenshtein(a, b):
    if abs(len(a) - len(b)) > 2:
        return 99
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1,
                           prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def suggest_typo(missing_name, candidates):
    best, best_d = None, 3
    for c in candidates:
        d = levenshtein(missing_name, c)
        if d < best_d:
            best, best_d = c, d
    return best


def scan_project(root):
    used, refs, files = {}, {}, 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if fn in EXAMPLE_NAMES or fn.startswith(".env"):
                continue
            if os.path.splitext(fn)[1].lower() not in CODE_EXTS:
                continue
            p = os.path.join(dirpath, fn)
            rel = os.path.relpath(p, root)
            found = scan_file(p)
            if found:
                files += 1
            for name, has_default in found.items():
                used[name] = used.get(name, False) or has_default
                refs.setdefault(name, set()).add(rel)
    return used, refs, files


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="envdoctor",
        description="检查 .env.example 与代码实际引用的环境变量是否一致")
    ap.add_argument("project", nargs="?", default=".",
                    help="要扫描的项目目录（默认当前目录）")
    ap.add_argument("--strict", action="store_true",
                    help="有缺失变量时 exit 1（CI 用）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--fix", action="store_true",
                    help="把缺失变量追加进示例文件")
    ap.add_argument("--dry-run", action="store_true",
                    help="配合 --fix：只显示将要追加的内容，不写文件")
    ap.add_argument("--version", action="version", version="envdoctor 0.1.0")
    args = ap.parse_args(argv)

    root = os.path.abspath(args.project)
    if not os.path.isdir(root):
        sys.stderr.write("error: 不是目录：%s\n" % args.project)
        return 2
    example = find_example(root)
    if not example:
        sys.stderr.write("error: 在 %s 下没找到 .env.example（或 .env.sample）\n" % args.project)
        return 2

    defined = parse_example(example)
    used, refs, files = scan_project(root)

    if args.fix:
        to_add = sorted(set(used) - set(defined))
        if to_add:
            lines = ["", "# envdoctor 自动追加（%s），请填写真实值：" % os.path.basename(example)]
            for n in to_add:
                lines.append("%s=  # TODO: fill" % n)
            block = "\n".join(lines) + "\n"
            if args.dry_run:
                sys.stdout.write("将要追加到 %s：\n%s" % (example, block))
            else:
                with open(example, "a", encoding="utf-8") as f:
                    f.write(block)
                sys.stdout.write("已追加 %d 个变量到 %s\n" % (len(to_add), example))
                defined = parse_example(example)  # 修完重读，报告反映最新状态

    missing = sorted(set(used) - set(defined))
    extra = sorted(set(defined) - set(used))
    unset = sorted(n for n, v in defined.items()
                   if v == "" and n in used and not used[n])

    result = {
        "project": root,
        "example_file": os.path.basename(example),
        "files_scanned": files,
        "missing": missing,
        "extra": extra,
        "unset": unset,
    }

    if args.json:
        sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    else:
        out = []
        out.append("环境变量检查：%s" % args.project)
        out.append("示例文件：%s（%d 个变量），扫描代码文件：%d 个" %
                   (os.path.basename(example), len(defined), files))
        out.append("")
        if missing:
            out.append("❌ 缺失（代码用了，示例里没有）：%d" % len(missing))
            for n in missing:
                tip = suggest_typo(n, list(defined))
                hint = "  ← 拼写？你是不是想写 %s？" % tip if tip else ""
                out.append("  %-22s ← %s%s" % (n, ", ".join(sorted(refs[n])), hint))
        else:
            out.append("✅ 无缺失")
        out.append("")
        if unset:
            out.append("⚠️ 未设值（示例里为空，且代码使用时没给默认值）：%d" % len(unset))
            for n in unset:
                out.append("  %-22s ← %s" % (n, ", ".join(sorted(refs[n]))))
        else:
            out.append("✅ 无未设值")
        out.append("")
        if extra:
            out.append("ℹ️ 多余（示例里有，代码没用到）：%d" % len(extra))
            for n in extra:
                out.append("  %s" % n)
        else:
            out.append("✅ 无多余")
        sys.stdout.write("\n".join(out) + "\n")

    if args.strict and missing:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
