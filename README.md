# MD Tools

Utility commands for splitting Markdown documents into balanced parts and
normalising paragraph spacing.

## Installation

```powershell
cd D:\md_parse
py -m pip install .
```

## Usage

Split a Markdown file into roughly equal-sized parts (by paragraph):

```powershell
md-tool split path\to\file.md 3
```

The command above creates files such as `file_part_1.md`, `file_part_2.md`, and
`file_part_3.md` alongside the original document when the request is valid,
balancing paragraph groups to keep the resulting files roughly equal in size.

Normalise paragraph spacing so that single newline separators are expanded to
two newline characters (while longer runs are left untouched):

```powershell
md-tool format-newlines path\to\file.md
```

Combine multiple Markdown files, inserting a single newline between each source:

```powershell
md-tool combine file1.md file2.md -o combined.md

# or read the list from a text file (one path per line)
md-tool combine --file-list files.txt -o combined.md
```

### Pipelines

Commands can now be chained without writing intermediate files by using the
`pipeline` sub-command. Separate stages with the equals character (`=`).

```powershell
md-tool pipeline translate-md input.md --target fr = format-newlines --output translated.md
```

In the example above, the translated Markdown is passed directly to the
`format-newlines` stage, which writes the final document to `translated.md`. You
can also collect the last stage output via the pipeline itself using the
`-o/--output` flag, for example:

```powershell
md-tool pipeline translate-md input.md --target fr = format-newlines -o final.md
```

If no pipeline-level output is specified, the result is rendered to standard
output (unless `--no-output` is given).

For development without installation, run the compatibility script directly:
