from __future__ import annotations

import sys

MAN_PAGE = """MD-TOOL(1)                    User Commands                    MD-TOOL(1)

NAME
    md-tool - utilities for processing Markdown files

SYNOPSIS
    md-tool <command> [options]
    md-tool pipeline -i <input> [=]<stage>[=...]
    md-tool man

DESCRIPTION
    md-tool provides a suite of commands for manipulating Markdown documents:
        split           Split a Markdown file into balanced paragraph parts.
        combine         Merge multiple Markdown files into one output.
        format-newlines Normalise paragraph spacing by duplicating single blanks.
        translate-md    Translate Markdown text while preserving structure.
        pipeline        Execute several commands in sequence without temporary files.

COMMANDS
    split <input> <parts> -o BASE
        Requires a file path outside pipeline mode.
        Standalone runs must include -o/--output BASE to name the emitted part files.
        In pipelines, -o is optional unless this is the final stage.

    combine [inputs...] [-l FILELIST] [-o OUTPUT]
        Merge explicit inputs or paths listed in FILELIST.

    format-newlines <input> -o OUTPUT
        Normalise spacing and write to OUTPUT (use the input path here for in-place updates).
        In pipelines, omit -o for intermediate stages; it is required when final.

    translate-md <input> --target LANG [options]
        Translate Markdown paragraphs concurrently. Respects all delay options.

    pipeline -i INPUT [=]STAGE[=STAGE...]
        Begin with a single global INPUT via -i/--input, then chain stages with '='.
        Single-input tools (translate-md, format-newlines, split) must NOT provide
        positional inputs inside pipelines; these are rejected before execution.
        Stage-level -o/--output BASE writes that stage’s result; pipeline-level
        -o/--output writes the final artifact. Pipelines with a final split or
        format-newlines stage must include -o/--output on that final stage.
        Pipelines no longer render Markdown to stdout; files are produced only
        when -o/--output is supplied at either the stage or pipeline level.

OPTIONS
    -o, --output BASE
        For split and format-newlines, required in standalone mode (or when the
        stage is final in a pipeline) to name their outputs. Stage-level: write
        the stage result using BASE as the output file base name. Pipeline-level:
        write the final pipeline artifact to the specified file. Without any -o,
        pipelines complete silently without emitting files.

    --no-output (pipeline)
        Reserved for backwards compatibility (stdout rendering is already disabled).

    --help
        Display help for md-tool or the chosen sub-command.

EXAMPLES
    md-tool split notes.md 4 -o notes_parts.md
    md-tool combine intro.md chapter1.md chapter2.md -o full.md
    md-tool pipeline -i draft.md = translate-md --target es = format-newlines -o draft_es.md

AUTHOR
    md-tool contributors.

REPORTING BUGS
    Open issues or pull requests in the project repository.
"""


def print_man_page(stream = sys.stdout) -> None:
    stream.write(MAN_PAGE)
    if not MAN_PAGE.endswith("\n"):
        stream.write("\n")


def print_man_page_err(stream = sys.stderr) -> None:
    stream.write(MAN_PAGE)
    if not MAN_PAGE.endswith("\n"):
        stream.write("\n")
