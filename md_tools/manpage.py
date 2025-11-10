from __future__ import annotations

import sys

MAN_PAGE = """MD-TOOL(1)                    User Commands                    MD-TOOL(1)

NAME
    md-tool - utilities for processing Markdown files

SYNOPSIS
    md-tool <command> [options]
    md-tool pipeline <stage>=<stage>[=...]
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

    pipeline STAGE[=STAGE...]
        Chain commands. Stage-level -o/--output BASE writes that stage’s result;
        pipeline-level -o/--output writes the final artifact. Pipelines with a
        final split or format-newlines stage must include -o/--output on that
        stage before execution begins. Use --no-output to suppress rendering.

OPTIONS
    -o, --output BASE
        For split and format-newlines, required in standalone mode (or when the
        stage is final in a pipeline) to name their outputs. Stage-level: write
        the stage result using BASE as the output file base name. Pipeline-level:
        write the final pipeline artifact to the specified file.

    --no-output (pipeline)
        Suppress final rendering when no pipeline-level output file is requested.

    --help
        Display help for md-tool or the chosen sub-command.

EXAMPLES
    md-tool split notes.md 4 -o notes_parts.md
    md-tool combine intro.md chapter1.md chapter2.md -o full.md
    md-tool pipeline translate-md draft.md --target es = format-newlines -o draft_es.md

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
