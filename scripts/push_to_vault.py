#!/usr/bin/env python3
"""
Push a youtube-digest article set (main article + deck) into an Obsidian
vault repo and publish it to the vault's「深度分析」folder on both remotes.

Default behaviour (no additional prompt to the user):
    python3 push_to_vault.py <article.md> [deck.tsv]

    deck 省略时自动取同目录的 <article_stem>-deck.tsv。
    卡片包产物已于 blueprint v4.0 取消，本脚本不再接受 cards 参数。
    卡组进 vault 是有意的：Obsidian 里能直接看到它，也方便从手机导进 Anki。

It will:
  1. Locate the vault clone at $VAULT_DIR (default: workspace/obsidian-vault
     relative to the repo root; overridable via env VAULT_DIR).
  2. Create「深度分析」inside the vault if missing.
  3. Copy the two files in, keeping their original filenames.
  4. Commit + push to *both* vault remotes (GitHub and Gitee), resolving
     remote aliases by URL the same way SKILL.md step 7 does — never assume
     `origin` / `github` / `gitee` naming.

Exit codes:
    0  both remotes pushed, ls-remote verified
    1  git failure (clone missing, commit/push failed, ls-remote mismatch, …)
    2  bad arguments / missing input files / vault not a git repo

The script prints a JSON summary as its last stdout line.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

VAULT_SUBDIR = "深度分析"


def fail(msg, code=1, **extra):
    print(json.dumps({"ok": False, "error": msg, **extra}, ensure_ascii=False))
    sys.exit(code)


def repo_root():
    """youtube-digest repo root = parent of this script's directory."""
    return Path(__file__).resolve().parent.parent


def run(cmd, cwd=None, capture=True):
    """Run a git command; return CompletedProcess. Never prompt."""
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    return subprocess.run(
        cmd, cwd=cwd, env=env,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        text=True,
    )


def must_run(cmd, cwd=None, what=""):
    r = run(cmd, cwd=cwd)
    if r.returncode != 0:
        fail(f"git {what or cmd[1]} failed: {r.stderr.strip() or r.stdout.strip()}")
    return r


def resolve_remote(vault: Path, host: str):
    """Find the vault remote alias whose push URL contains `host`. None if absent."""
    r = must_run(["git", "remote", "-v"], cwd=vault, what="remote -v")
    for line in r.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 3 and host in parts[1] and parts[2] == "(push)":
            return parts[0]
    return None


def default_branch(vault: Path, remote: str):
    """Read the remote's HEAD symref, falling back to `main`."""
    r = run(["git", "ls-remote", "--symref", remote, "HEAD"], cwd=vault)
    if r.returncode == 0:
        for line in r.stdout.splitlines():
            if line.startswith("ref:") and line.endswith("\tHEAD"):
                ref = line.split()[1]
                if ref.startswith("refs/heads/"):
                    return ref[len("refs/heads/"):]
    return "main"


def main():
    if len(sys.argv) not in (2, 3):
        fail("usage: push_to_vault.py <article.md> [deck.tsv]", code=2)

    article = Path(sys.argv[1]).expanduser().resolve()
    if not article.is_file():
        fail(f"missing file: {article}", code=2)

    if len(sys.argv) == 3:
        deck = Path(sys.argv[2]).expanduser().resolve()
    else:
        deck = article.with_name(f"{article.stem}-deck.tsv")
    if not deck.is_file():
        fail(f"missing deck: {deck}（v4.0 起卡组是必交产物，先跑 build_deck.py）", code=2)

    vault = Path(os.environ.get(
        "VAULT_DIR",
        Path.home() / "Documents" / "Obsidian01",
    )).expanduser().resolve()
    if not vault.is_dir() or not (vault / ".git").exists():
        fail(
            f"vault clone not found at {vault}. "
            "Clone codebluce/Obsidian-Vault there first, or set VAULT_DIR "
            "(see SKILL.md step 7.5).",
            code=2,
        )

    target_dir = vault / VAULT_SUBDIR
    target_dir.mkdir(parents=True, exist_ok=True)

    copied = []
    for src in (article, deck):
        dst = target_dir / src.name
        shutil.copy2(src, dst)
        copied.append(str(dst.relative_to(vault)))

    gh = resolve_remote(vault, "github.com")
    gitee = resolve_remote(vault, "gitee.com")
    if not gh or not gitee:
        fail(
            f"vault remotes incomplete: github={gh or 'MISSING'} gitee={gitee or 'MISSING'}. "
            "Add both remotes inside the vault clone before pushing.",
            code=2,
        )

    branch = default_branch(vault, gh)

    # Stage & commit (skip cleanly if nothing changed)
    must_run(["git", "add", VAULT_SUBDIR], cwd=vault, what="add")
    diff = run(["git", "diff", "--cached", "--quiet"], cwd=vault)
    committed = False
    if diff.returncode != 0:
        subject = article.stem
        must_run(
            ["git", "commit", "-m", f"docs: {subject} 深度文章 + 卡片包"],
            cwd=vault, what="commit",
        )
        committed = True

    head = must_run(["git", "rev-parse", "HEAD"], cwd=vault, what="rev-parse").stdout.strip()

    pushes = {}
    for name, alias in (("github", gh), ("gitee", gitee)):
        r = run(["git", "push", alias, f"HEAD:{branch}"], cwd=vault)
        if r.returncode != 0:
            fail(f"push to {name} ({alias}) failed: {r.stderr.strip()}", pushed=pushes)
        # verify against actual remote, not local remote-tracking refs
        v = must_run(["git", "ls-remote", alias, branch], cwd=vault, what=f"ls-remote {alias}")
        remote_head = v.stdout.split()[0] if v.stdout.strip() else ""
        if remote_head != head:
            fail(
                f"{name} push reported success but ls-remote HEAD {remote_head[:8]} "
                f"!= local HEAD {head[:8]}",
                pushed=pushes,
            )
        pushes[name] = {"remote": alias, "head": head}

    print(json.dumps({
        "ok": True,
        "vault": str(vault),
        "target_dir": VAULT_SUBDIR,
        "files": copied,
        "branch": branch,
        "committed": committed,
        "head": head,
        "pushed": pushes,
    }, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
