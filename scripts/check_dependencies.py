#!/usr/bin/env python3
"""
Dependency preflight check for book-to-lab.

Checks for the external tools this skill actually touches and reports,
per platform, what's missing and how to install it. Never installs
anything itself - see CLAUDE.md invariant 9 (dependency installation is
proposed, never silent). The calling Claude Code session decides
whether to offer running the printed install command.

`python3` isn't in the checked list: this script needs python3 to run
at all, so its absence can't be reported by it - if you're reading this
script's output, python3 is already present by definition.

Exit code: 0 if every REQUIRED tool is present, 1 if any is missing.
Optional tools that are missing are reported but never affect the exit
code.

Run with: python3 scripts/check_dependencies.py
"""
import platform
import shutil
import sys

# Kept as a flat, hardcoded list of the handful of tools this skill
# actually depends on - not a general package-manager abstraction. See
# CLAUDE.md's design-decisions note on this script for why: this skill
# only ever needs to check these specific tools, and Linux package-
# manager fragmentation (apt/dnf/pacman/zypper/apk) makes "detect the
# right one reliably" not worth building for a 3-tool problem. Add an
# entry when a real feature needs a new tool, not preemptively.
TOOLS = [
    {
        "name": "pandoc",
        "command": "pandoc",
        "required": True,
        "why": "converts the epub to markdown (Phase 1)",
        "hint": {
            "Darwin": "brew install pandoc",
            "Linux": "apt install pandoc  (Debian/Ubuntu - if you're on "
                      "another distro, use its package manager, or see "
                      "https://pandoc.org/installing.html)",
            "Windows": "winget install --id JohnMacFarlane.Pandoc  (or see "
                       "https://pandoc.org/installing.html)",
        },
    },
    {
        "name": "node",
        "command": "node",
        "required": False,
        "why": "only needed if this book's exercises turn out to be JavaScript",
        "hint": {
            "Darwin": "brew install node",
            "Linux": "apt install nodejs  (Debian/Ubuntu - if you're on "
                      "another distro, use its package manager, or see "
                      "https://nodejs.org)",
            "Windows": "winget install OpenJS.NodeJS  (or see https://nodejs.org)",
        },
    },
    {
        "name": "claude",
        "command": "claude",
        "required": False,
        "why": "needed for live grading/review/synthesis in the generated "
               "app - those features degrade gracefully without it, but "
               "won't work",
        "hint": {
            "Darwin": "see https://docs.claude.com/en/docs/claude-code for install/login",
            "Linux": "see https://docs.claude.com/en/docs/claude-code for install/login",
            "Windows": "see https://docs.claude.com/en/docs/claude-code for install/login",
        },
    },
]


def check_all():
    """Returns (results, all_required_present). results is a list of
    dicts: {name, required, found, hint (only if not found)}."""
    system = platform.system()  # "Darwin" / "Linux" / "Windows"
    results = []
    all_required_present = True
    for tool in TOOLS:
        found = shutil.which(tool["command"]) is not None
        entry = {"name": tool["name"], "required": tool["required"], "found": found}
        if not found:
            entry["why"] = tool["why"]
            entry["hint"] = tool["hint"].get(system, tool["hint"]["Linux"])
            if tool["required"]:
                all_required_present = False
        results.append(entry)
    return results, all_required_present


def format_report(results, all_required_present):
    lines = ["Checking dependencies for book-to-lab...", ""]
    for entry in results:
        if entry["found"]:
            lines.append(f"  {entry['name']:<8} OK")
        else:
            tag = "MISSING (required)" if entry["required"] else "not found (optional)"
            lines.append(f"  {entry['name']:<8} {tag}")
            lines.append(f"    why:     {entry['why']}")
            lines.append(f"    install: {entry['hint']}")
    lines.append("")
    if all_required_present:
        lines.append("All required dependencies are present.")
    else:
        lines.append(
            "Missing a required dependency - install it with the command "
            "above, then re-run this check before continuing."
        )
    return "\n".join(lines)


def main():
    results, all_required_present = check_all()
    print(format_report(results, all_required_present))
    sys.exit(0 if all_required_present else 1)


if __name__ == "__main__":
    main()
