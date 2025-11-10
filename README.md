# MD Tool

Utilities for translating, splitting, combining, and normalising Markdown files.

## Installation

Clone the repository and install the CLI in editable mode:

```powershell
git clone https://github.com/liudesheng9/md_tool.git
cd md-tool
py -m pip install -e .
```

## Features

- **split** – divide a Markdown document into balanced paragraph groups.
- **combine** – merge multiple Markdown sources into one file.
- **format-newlines** – normalise paragraph spacing by duplicating isolated blank lines.
- **translate-md** – translate Markdown paragraph-by-paragraph while preserving tables, equations, and code.
- **pipeline** – execute any sequence of the above tools without writing intermediate results to disk.

### Pipeline highlights

- Stages are chained with `=` (for example, `split doc.md 3 = format-newlines`).
- Each stage reuses the same in-memory Markdown, eliminating temporary files unless `-o/--output` is used.
- Stage execution is logged to `stderr`, and progress indicators (e.g. from `translate-md`) remain visible.
- A pipeline-level `-o/--output` writes the final artifact; otherwise output is rendered to `stdout` unless `--no-output` is provided.
- Stage-level `-o/--output` flags write files for that stage only (and suppress rendering of that stage’s result).

## Usage Examples

Split a Markdown document into three balanced parts and write each part next to the original file:

```powershell
md-tool split path\to\file.md 3
```

Normalise paragraph spacing in-place:

```powershell
md-tool format-newlines path\to\file.md
```

Combine multiple sources into a single result:

```powershell
md-tool combine file1.md file2.md -o combined.md
# or read a list of files:
md-tool combine --file-list files.txt -o combined.md
```

Translate to French, tidy paragraph spacing, and capture the final result:

```powershell
md-tool pipeline translate-md input.md --target fr = format-newlines -o final.md
```

Split a document inside a pipeline without creating files, then normalise spacing and write the final output:

```powershell
md-tool pipeline split long.md 4 = format-newlines -o long_clean.md
```

## Development shortcut

For local development without installing the package, the compatibility script mirrors the CLI:

```powershell
python split_markdown.py split path\to\file.md 3
python split_markdown.py format-newlines path\to\file.md
python split_markdown.py combine file1.md file2.md -o combined.md
```

## Man Page

Render the man page directly in your terminal by running `md-tool man` (or use `md-tool <command> --help` for command-specific details). The canonical man page content is reproduced below for reference:

```text
MD-TOOL(1)                    User Commands                    MD-TOOL(1)

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
    split <input> <parts>
        Requires a file path outside pipeline mode.
        Accepts -o/--output inside pipeline mode to also write part files.

    combine [inputs...] [-l FILELIST] [-o OUTPUT]
        Merge explicit inputs or paths listed in FILELIST.

    format-newlines <input> [-o OUTPUT]
        Normalise spacing in-place or write to OUTPUT.

    translate-md <input> --target LANG [options]
        Translate Markdown paragraphs concurrently. Respects all delay options.

    pipeline STAGE[=STAGE...]
        Chain commands. Stage-level -o writes that stage’s result; pipeline-level
        -o/--output writes the final artifact. Use --no-output to suppress rendering.

OPTIONS
    -o, --output
        Stage-level: write the stage result to the specified file.
        Pipeline-level: write the final pipeline artifact to the specified file.

    --no-output (pipeline)
        Suppress final rendering when no pipeline-level output file is requested.

    --help
        Display help for md-tool or the chosen sub-command.

EXAMPLES
    md-tool split notes.md 4
    md-tool combine intro.md chapter1.md chapter2.md -o full.md
    md-tool pipeline translate-md draft.md --target es = format-newlines -o draft_es.md

AUTHOR
    md-tool contributors.

REPORTING BUGS
    Open issues or pull requests in the project repository.
```
