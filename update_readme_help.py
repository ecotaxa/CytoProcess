#!/usr/bin/env python3
"""Update the Commands reference section in README.md with current --help output."""

import sys
from pathlib import Path

from click.testing import CliRunner

from cytoprocess.cli import cli

SCRIPT_DIR = Path(__file__).parent
README = SCRIPT_DIR / "README.md"

MARKER_START = "Here are all cytoprocess commands\n"
MARKER_END = "\nRTFM"

runner = CliRunner()

# Main help
parts = [runner.invoke(cli, ["--help"], prog_name="cytoprocess").output.rstrip()]

# Each subcommand, in declaration order
for cmd_name in cli.list_commands(None):
    parts.append("```")
    parts.append("```")
    parts.append(runner.invoke(cli, [cmd_name, "--help"], prog_name="cytoprocess").output.rstrip())

help_text = "\n\n".join(parts)

readme = README.read_text()
start_idx = readme.find(MARKER_START)
end_idx = readme.find(MARKER_END, start_idx)

if start_idx == -1 or end_idx == -1:
    print("ERROR: could not find markers in README.md", file=sys.stderr)
    sys.exit(1)

new_readme = (
    readme[: start_idx + len(MARKER_START)]
    + "\n```\n"
    + help_text
    + "\n```\n"
    + readme[end_idx:]
)

README.write_text(new_readme)
print("README.md updated successfully.")
