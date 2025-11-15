### Format Newlines Tool (`md_tools/format_newlines`)

`format-newlines` normalises paragraph spacing in Markdown files so that every paragraph boundary is separated by at least two newline characters while preserving intentional multi-line gaps and structural blocks (code fences, tables, HTML, etc.). The tool can be run directly via `md-tool format-newlines <input> -o <output>` or as part of a pipeline stage.

#### How the logic works

1. **Paragraph detection**  
   The tool uses `collect_paragraphs_with_metadata` from `md_tools/paragraphs.py` to walk the document and emit a metadata stream describing each chunk (`text`, `blank`, `code_fence`, `table`, `html`, etc.) with its original content and line numbers.

2. **Blank tracking**  
   As the metadata is processed, consecutive `blank` entries are counted (`pending_blank_lines`). These represent the number of empty lines between structural blocks.

3. **Separator rules**  
   - When blank lines exist between two blocks, the formatter preserves them, ensuring there are *at least* two newline characters. (A single blank line is expanded to two; longer runs are left untouched.)
   - When two consecutive `text` paragraphs are adjacent with no blank lines (i.e., separated only by a single `\n`), the formatter inserts two newline characters to create the expected blank paragraph separator.
   - Transitions between non-text structures (e.g., text → code fence, code fence → text, table → text) receive a single newline unless explicit blank lines were present in the source.

4. **Output assembly**  
   The tool accumulates each block’s content plus the computed separators into `result_parts`, then writes the joined string to the requested `--output` path. Newline style (`\n`, `\r\n`, etc.) matches the input and is preserved for all inserted separators.

This approach ensures human-readable paragraph spacing without disturbing code blocks, tables, or intentional multi-line spacing inside those structures.
