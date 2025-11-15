from __future__ import annotations

from typing import List

from md_tools.paragraphs import collect_paragraphs_with_metadata


def _non_blank(metadata: List[dict]) -> List[dict]:
    return [entry for entry in metadata if entry["type"] != "blank"]


def test_collect_paragraphs_identifies_varied_structures() -> None:
    markdown = "\n".join(
        [
            "Intro paragraph",
            "",
            "| Name | Age |",
            "| ---- | --- |",
            "| Ada  |  36 |",
            "",
            "$$",
            "E = mc^2",
            "$$",
            "",
            "<div>",
            "HTML block content",
            "</div>",
            "",
            "```python",
            "print('hi')",
            "",
            "```",
            "",
            "![diagram](diagram.png)",
            "[diagram]: https://example.com/diagram.png",
            "",
            "[ref-id]: https://example.com/reference",
            "",
            "<hr />",
            "",
            "$$x = y$$",
            "",
            "Closing text",
            "",
        ]
    )

    _paragraphs, metadata = collect_paragraphs_with_metadata(markdown, newline="\n")
    entries = _non_blank(metadata)
    assert [entry["type"] for entry in entries] == [
        "text",
        "table",
        "equation",
        "html",
        "code_fence",
        "image_block",
        "reference",
        "html_single",
        "equation_single",
        "text",
    ]

    table_entry = next(entry for entry in entries if entry["type"] == "table")
    assert table_entry["lines"] == [
        "| Name | Age |",
        "| ---- | --- |",
        "| Ada  |  36 |",
    ]
    assert (table_entry["line_start"], table_entry["line_end"]) == (2, 4)

    equation_entry = next(entry for entry in entries if entry["type"] == "equation")
    assert equation_entry["lines"] == ["$$", "E = mc^2", "$$"]
    assert (equation_entry["line_start"], equation_entry["line_end"]) == (6, 8)

    image_entry = next(entry for entry in entries if entry["type"] == "image_block")
    assert image_entry["lines"] == [
        "![diagram](diagram.png)",
        "[diagram]: https://example.com/diagram.png",
    ]
    assert (image_entry["line_start"], image_entry["line_end"]) == (19, 20)

    html_single_entry = next(entry for entry in entries if entry["type"] == "html_single")
    assert html_single_entry["lines"] == ["<hr />"]
    assert (html_single_entry["line_start"], html_single_entry["line_end"]) == (24, 24)

    equation_single_entry = next(entry for entry in entries if entry["type"] == "equation_single")
    assert equation_single_entry["lines"] == ["$$x = y$$"]
    assert (equation_single_entry["line_start"], equation_single_entry["line_end"]) == (26, 26)

    fence_entry = next(entry for entry in entries if entry["type"] == "code_fence")
    assert fence_entry["lines"] == [
        "```python",
        "print('hi')",
        "",
        "```",
    ]
    assert (fence_entry["line_start"], fence_entry["line_end"]) == (14, 17)

    html_entry = next(entry for entry in entries if entry["type"] == "html")
    assert (html_entry["line_start"], html_entry["line_end"]) == (10, 12)


def test_collect_paragraphs_flushes_trailing_structures() -> None:
    markdown = "\n".join(
        [
            "| Header |",
            "| ------ |",
            "| Cell   |",
            "<section>",
            "Unclosed HTML block",
        ]
    )

    _paragraphs, metadata = collect_paragraphs_with_metadata(markdown, newline="\n")
    entries = _non_blank(metadata)

    assert [entry["type"] for entry in entries] == ["table", "html"]

    html_entry = entries[-1]
    assert html_entry["lines"] == ["<section>", "Unclosed HTML block"]
    assert (html_entry["line_start"], html_entry["line_end"]) == (3, 4)

    table_entry = entries[0]
    assert (table_entry["line_start"], table_entry["line_end"]) == (0, 2)
