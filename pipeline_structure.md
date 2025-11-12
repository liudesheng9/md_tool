## Pipeline Call Chains

This project supports two entry paths into the same pipeline engine: the CLI (argument driven) path and the JSON payload path used by `ToolManager`. Both ultimately produce a `PipelineDefinition` and execute it with `run_pipeline`.

### 1. CLI Argument Path

```
user command
  └── md_tools.cli.build_parser()
        └── PipelineCommand (md_tools/pipeline/command.py)
              └── build_pipeline_definition()
                    └── run_pipeline()
```

1. The CLI parser (built in `md_tools/cli.py`) collects all registered tools plus the `pipeline` subcommand.
2. `PipelineCommand` enforces the global options (`--input`, `--output`, stage tokens after `=`) and forwards the raw stage tokens to `build_pipeline_definition` along with the input path.
3. `build_pipeline_definition` replays the same tool parsers to create `PipelineStage` objects. Each stage carries its tokens, parsed args, callable `pipeline_func`, `pipeline_caps`, and any output paths resolved through the tool’s `PipelineOutputSpec`.
4. `run_pipeline` iterates the definition: it validates input cardinality via `pipeline_caps`, invokes each stage’s `pipeline_func`, and propagates the resulting `MarkdownArtifact` downstream. Any `PipelineStageError` bubbles back to the CLI for printing.

### 2. JSON Payload Path (ToolManager)

```
PipelinePayload dataclasses (mirroring JSON schema)
  └── ToolManager.run_payloads()
        └── ToolManager.build_definition_from_payload()
              └── build_pipeline_definition()
                    └── run_pipeline()
```

1. Each `PipelinePayload` mirrors the CLI schema: it contains an `input` path and a list of `StagePayload` records like `{"stage_name": "split", "args": ["5", "-o", "out.md"]}`. This matches the output from `build_parser` (command name plus the exact CLI arguments).
2. `ToolManager.run_payloads` converts the payloads into `PipelineDefinition` objects by calling `build_pipeline_definition_from_payload`, which flattens each stage entry into the CLI token list (`= stage args...`) and feeds it into `build_pipeline_definition` with the declared input path.
3. The resulting definitions are executed in order via the same `run_pipeline` routine used by the CLI path, so stage parsing, capability enforcement, and output tracking behave identically.

### Shared Components

- **PipelineStageRunner & stage modules**: Individual tools implement `run_pipeline` helpers (e.g., `md_tools/pipeline/format_newlines/__init__.py`) that rely on `PipelineStageRunner` for reading upstream artifacts, validating inputs, and writing outputs.
- **PipelineOutputSpec**: Tools advertise the files they write (e.g., split parts, translate debug JSON). Those specs are resolved during definition building so both call chains know which artifacts to expect.

In short, whether stages originate from CLI arguments or JSON payloads, they funnel through `build_pipeline_definition` → `run_pipeline`, ensuring consistent validation, execution, and error handling.
