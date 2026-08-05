use anyhow::{Context, Result, anyhow, bail};
use serde::Serialize;
use serde_json::{Value, json};
use std::collections::BTreeSet;
use std::env;
use std::fs;
use std::io::{self, BufRead, Write};
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::SystemTime;

const MCP_PROTOCOL_VERSION: &str = "2025-11-25";

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "snake_case")]
enum Severity {
    Error,
    Warning,
    Info,
}

#[derive(Debug, Clone, Serialize)]
struct Diagnostic {
    code: &'static str,
    severity: Severity,
    message: String,
    resolution: String,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "snake_case")]
enum ActionSafety {
    ReadOnly,
    MutatesProject,
    InstallsSoftware,
}

#[derive(Debug, Clone, Serialize)]
struct RecommendedAction {
    id: &'static str,
    title: String,
    command: Option<String>,
    rationale: String,
    safety: ActionSafety,
}

#[derive(Debug, Clone, Serialize)]
struct CliState {
    available: bool,
    version: Option<String>,
    error: Option<String>,
}

#[derive(Debug, Clone, Default, Serialize)]
struct PackageState {
    manifest_path: Option<String>,
    lock_path: Option<String>,
    modules_path: Option<String>,
    org: Option<String>,
    name: Option<String>,
    version: Option<String>,
    direct_dependency_count: usize,
    manifest_valid: bool,
    lock_valid: bool,
}

#[derive(Debug, Clone, Serialize)]
struct Summary {
    errors: usize,
    warnings: usize,
    info: usize,
}

#[derive(Debug, Clone, Serialize)]
struct ProjectReport {
    root: String,
    cli: CliState,
    package: PackageState,
    summary: Summary,
    diagnostics: Vec<Diagnostic>,
    recommended_actions: Vec<RecommendedAction>,
}

fn main() -> Result<()> {
    let mut args = env::args().skip(1);
    match args.next().as_deref() {
        None | Some("mcp") => serve_mcp(),
        Some("inspect") | Some("doctor") => run_inspect(args.collect()),
        Some("--version") | Some("-V") => {
            println!("zed-air {}", env!("CARGO_PKG_VERSION"));
            Ok(())
        }
        Some("help") | Some("--help") | Some("-h") => {
            print_help();
            Ok(())
        }
        Some(other) => bail!("unknown command `{other}`; run `zed-air help`"),
    }
}

fn print_help() {
    println!(
        "zed-air {version}\n\nUSAGE:\n  zed-air mcp\n  zed-air inspect [--root PATH] [--json]\n  zed-air doctor [--root PATH] [--json]\n\nThe MCP server is read-only. Recommended commands are returned to the Air agent,\nbut project-changing commands are never executed by zed-air.",
        version = env!("CARGO_PKG_VERSION")
    );
}

fn run_inspect(args: Vec<String>) -> Result<()> {
    let mut root = env::current_dir().context("resolve current directory")?;
    let mut json_output = false;
    let mut iter = args.into_iter();
    while let Some(arg) = iter.next() {
        match arg.as_str() {
            "--root" => {
                root = PathBuf::from(iter.next().ok_or_else(|| anyhow!("--root requires a path"))?);
            }
            "--json" => json_output = true,
            other => bail!("unknown inspect argument `{other}`"),
        }
    }

    let report = inspect_project(&root)?;
    if json_output {
        println!("{}", serde_json::to_string_pretty(&report)?);
    } else {
        println!("{}", render_report(&report));
    }
    Ok(())
}

fn inspect_project(start: &Path) -> Result<ProjectReport> {
    let start = fs::canonicalize(start)
        .with_context(|| format!("project path does not exist: {}", start.display()))?;
    let root = discover_root(&start);
    let manifest_path = root.join(".zpkg.toml");
    let lock_path = root.join(".zpkg.lock");
    let modules_path = root.join("zed_modules");
    let cli = inspect_cli();
    let mut package = PackageState::default();
    let mut diagnostics = Vec::new();

    if !cli.available {
        diagnostics.push(diag(
            "ZED001",
            Severity::Error,
            "The `zed` CLI is not available on PATH.",
            "Install zed-cli, restart Air so its environment sees the updated PATH, and inspect again.",
        ));
    }

    let manifest_value = if manifest_path.exists() {
        package.manifest_path = Some(path_text(&manifest_path));
        match parse_toml(&manifest_path) {
            Ok(value) => {
                package.manifest_valid = true;
                package.org = nested_string(&value, &["package", "org"]);
                package.name = nested_string(&value, &["package", "name"]);
                package.version = nested_string(&value, &["package", "version"]);
                package.direct_dependency_count = value
                    .get("dependencies")
                    .and_then(toml::Value::as_table)
                    .map(|table| table.len())
                    .unwrap_or(0);
                Some(value)
            }
            Err(error) => {
                diagnostics.push(diag(
                    "ZED005",
                    Severity::Error,
                    format!("The Zed manifest is invalid TOML: {error}"),
                    "Fix `.zpkg.toml`; do not regenerate the lockfile until the manifest parses cleanly.",
                ));
                None
            }
        }
    } else {
        diagnostics.push(diag(
            "ZED002",
            Severity::Warning,
            "No `.zpkg.toml` manifest was found for this workspace.",
            "Run `zed init` for an authored package, or `zed install <org>/<name>@<requirement>` to adopt Zed while adding a dependency.",
        ));
        None
    };

    let lock_value = if lock_path.exists() {
        package.lock_path = Some(path_text(&lock_path));
        match parse_toml(&lock_path) {
            Ok(value) => {
                package.lock_valid = true;
                Some(value)
            }
            Err(error) => {
                diagnostics.push(diag(
                    "ZED006",
                    Severity::Error,
                    format!("The Zed lockfile is invalid TOML: {error}"),
                    "Restore the lockfile from version control or resolve from a valid manifest with `zed install`.",
                ));
                None
            }
        }
    } else {
        if manifest_path.exists() {
            diagnostics.push(diag(
                "ZED003",
                Severity::Warning,
                "The project has a manifest but no `.zpkg.lock`.",
                "Run `zed install` to resolve dependencies and create the lockfile.",
            ));
        }
        None
    };

    if lock_path.exists() && !manifest_path.exists() {
        diagnostics.push(diag(
            "ZED004",
            Severity::Warning,
            "A lockfile exists without a manifest, so direct dependency intent cannot be reconstructed.",
            "Restore `.zpkg.toml` when possible. For an intentional lock-only restore use `zed install --frozen --do-not-write-new-manifest`.",
        ));
    }

    if modules_path.exists() {
        package.modules_path = Some(path_text(&modules_path));
    } else if manifest_value.is_some() && lock_value.is_some() {
        diagnostics.push(diag(
            "ZED007",
            Severity::Warning,
            "The manifest and lockfile exist, but `zed_modules/` is not materialized.",
            "Run `zed install --frozen` to restore the exact locked packages.",
        ));
    }

    if manifest_value.is_some()
        && lock_value.is_some()
        && is_newer(&manifest_path, &lock_path).unwrap_or(false)
    {
        diagnostics.push(diag(
            "ZED008",
            Severity::Info,
            "The manifest is newer than the lockfile; dependency intent may have changed since the last resolution.",
            "Run `zed install` and review the lockfile diff.",
        ));
    }

    if package.manifest_valid
        && package.org.is_none()
        && package.name.is_none()
        && package.version.is_none()
    {
        diagnostics.push(diag(
            "ZED009",
            Severity::Warning,
            "The manifest parses, but `[package]` identity fields are missing.",
            "Set `package.org`, `package.name`, and `package.version` before publishing.",
        ));
    }

    if diagnostics.is_empty() {
        diagnostics.push(diag(
            "ZED000",
            Severity::Info,
            "No obvious Zed package-state problems were detected.",
            "Use `zed install --frozen` in CI and `zed store status` when investigating local cache behavior.",
        ));
    }

    let recommended_actions = actions_for(&diagnostics);
    let summary = summarize(&diagnostics);

    Ok(ProjectReport {
        root: path_text(&root),
        cli,
        package,
        summary,
        diagnostics,
        recommended_actions,
    })
}

fn discover_root(start: &Path) -> PathBuf {
    let mut current = if start.is_file() {
        start.parent().unwrap_or(start).to_path_buf()
    } else {
        start.to_path_buf()
    };
    let fallback = current.clone();
    loop {
        if current.join(".zpkg.toml").exists() || current.join(".zpkg.lock").exists() {
            return current;
        }
        if !current.pop() {
            return fallback;
        }
    }
}

fn inspect_cli() -> CliState {
    match Command::new("zed").arg("--version").output() {
        Ok(output) if output.status.success() => CliState {
            available: true,
            version: Some(String::from_utf8_lossy(&output.stdout).trim().to_string()),
            error: None,
        },
        Ok(output) => CliState {
            available: false,
            version: None,
            error: Some(String::from_utf8_lossy(&output.stderr).trim().to_string()),
        },
        Err(error) => CliState {
            available: false,
            version: None,
            error: Some(error.to_string()),
        },
    }
}

fn parse_toml(path: &Path) -> std::result::Result<toml::Value, String> {
    let text = fs::read_to_string(path).map_err(|error| error.to_string())?;
    toml::from_str(&text).map_err(|error| error.to_string())
}

fn nested_string(value: &toml::Value, keys: &[&str]) -> Option<String> {
    let mut current = value;
    for key in keys {
        current = current.get(*key)?;
    }
    current.as_str().map(ToOwned::to_owned)
}

fn is_newer(left: &Path, right: &Path) -> Result<bool> {
    let left_modified = fs::metadata(left)?.modified().unwrap_or(SystemTime::UNIX_EPOCH);
    let right_modified = fs::metadata(right)?.modified().unwrap_or(SystemTime::UNIX_EPOCH);
    Ok(left_modified > right_modified)
}

fn diag(
    code: &'static str,
    severity: Severity,
    message: impl Into<String>,
    resolution: impl Into<String>,
) -> Diagnostic {
    Diagnostic {
        code,
        severity,
        message: message.into(),
        resolution: resolution.into(),
    }
}

fn summarize(diagnostics: &[Diagnostic]) -> Summary {
    let mut summary = Summary {
        errors: 0,
        warnings: 0,
        info: 0,
    };
    for diagnostic in diagnostics {
        match diagnostic.severity {
            Severity::Error => summary.errors += 1,
            Severity::Warning => summary.warnings += 1,
            Severity::Info => summary.info += 1,
        }
    }
    summary
}

fn actions_for(diagnostics: &[Diagnostic]) -> Vec<RecommendedAction> {
    let codes: BTreeSet<_> = diagnostics.iter().map(|diagnostic| diagnostic.code).collect();
    let mut actions = Vec::new();

    if codes.contains("ZED001") {
        actions.push(action(
            "install-zed-cli",
            "Install the Zed CLI",
            Some("curl -fsSL https://zpkg.tech/install.sh | bash"),
            "Air cannot ask zed-cli for authoritative package operations until the executable is available.",
            ActionSafety::InstallsSoftware,
        ));
    }
    if codes.contains("ZED002") {
        actions.push(action(
            "initialize-zed-package",
            "Initialize a Zed manifest",
            Some("zed init"),
            "Creates the package manifest that records package identity and dependency intent.",
            ActionSafety::MutatesProject,
        ));
    }
    if codes.contains("ZED003") || codes.contains("ZED008") {
        actions.push(action(
            "resolve-dependencies",
            "Resolve Zed dependencies",
            Some("zed install"),
            "Reconciles the manifest with the lockfile and materialized dependency tree.",
            ActionSafety::MutatesProject,
        ));
    }
    if codes.contains("ZED004") {
        actions.push(action(
            "restore-lock-only",
            "Restore an intentional lock-only workspace",
            Some("zed install --frozen --do-not-write-new-manifest"),
            "Uses exact locked artifacts without inventing direct-dependency intent.",
            ActionSafety::MutatesProject,
        ));
    }
    if codes.contains("ZED007") {
        actions.push(action(
            "materialize-locked-packages",
            "Materialize exact locked packages",
            Some("zed install --frozen"),
            "Restores `zed_modules/` without changing selected versions.",
            ActionSafety::MutatesProject,
        ));
    }
    if codes.contains("ZED005") || codes.contains("ZED006") || codes.contains("ZED009") {
        actions.push(action(
            "repair-metadata",
            "Repair package metadata",
            None,
            "The manifest or lockfile needs human review before an automated package command is safe.",
            ActionSafety::ReadOnly,
        ));
    }

    actions.push(action(
        "inspect-store",
        "Inspect the local Zed store",
        Some("zed store status"),
        "Provides read-only cache and store context useful during package troubleshooting.",
        ActionSafety::ReadOnly,
    ));
    actions
}

fn action(
    id: &'static str,
    title: impl Into<String>,
    command: Option<&str>,
    rationale: impl Into<String>,
    safety: ActionSafety,
) -> RecommendedAction {
    RecommendedAction {
        id,
        title: title.into(),
        command: command.map(ToOwned::to_owned),
        rationale: rationale.into(),
        safety,
    }
}

fn render_report(report: &ProjectReport) -> String {
    let mut out = format!(
        "Zed package status for {}\nerrors: {}, warnings: {}, info: {}\n",
        report.root, report.summary.errors, report.summary.warnings, report.summary.info
    );
    for diagnostic in &report.diagnostics {
        out.push_str(&format!(
            "\n[{:?}] {}: {}\n  Resolution: {}\n",
            diagnostic.severity, diagnostic.code, diagnostic.message, diagnostic.resolution
        ));
    }
    out.push_str("\nRecommended actions:\n");
    for action in &report.recommended_actions {
        out.push_str(&format!("- {}", action.title));
        if let Some(command) = &action.command {
            out.push_str(&format!(": `{command}`"));
        }
        out.push('\n');
    }
    out
}

fn path_text(path: &Path) -> String {
    path.to_string_lossy().into_owned()
}

fn serve_mcp() -> Result<()> {
    let stdin = io::stdin();
    let mut stdout = io::BufWriter::new(io::stdout().lock());

    for line in stdin.lock().lines() {
        let line = line.context("read MCP request")?;
        if line.trim().is_empty() {
            continue;
        }
        match serde_json::from_str::<Value>(&line) {
            Ok(request) => {
                if let Some(response) = handle_mcp(request) {
                    serde_json::to_writer(&mut stdout, &response)?;
                    stdout.write_all(b"\n")?;
                    stdout.flush()?;
                }
            }
            Err(error) => {
                let response = rpc_error(Value::Null, -32700, format!("parse error: {error}"));
                serde_json::to_writer(&mut stdout, &response)?;
                stdout.write_all(b"\n")?;
                stdout.flush()?;
            }
        }
    }
    Ok(())
}

fn handle_mcp(request: Value) -> Option<Value> {
    let id = request.get("id").cloned();
    let method = request.get("method").and_then(Value::as_str).unwrap_or_default();
    let params = request.get("params").cloned().unwrap_or_else(|| json!({}));

    let Some(id) = id else {
        return None;
    };

    let result = match method {
        "initialize" => Ok(json!({
            "protocolVersion": negotiated_protocol(&params),
            "capabilities": { "tools": { "listChanged": false } },
            "serverInfo": {
                "name": "zed-jetbrains-air",
                "version": env!("CARGO_PKG_VERSION"),
                "description": "Read-only Zed package diagnostics and recommended resolutions for JetBrains Air"
            }
        })),
        "server/discover" => Ok(json!({
            "protocolVersions": [MCP_PROTOCOL_VERSION],
            "capabilities": { "tools": {} },
            "serverInfo": { "name": "zed-jetbrains-air", "version": env!("CARGO_PKG_VERSION") }
        })),
        "ping" => Ok(json!({})),
        "tools/list" => Ok(json!({ "tools": tool_definitions() })),
        "tools/call" => call_tool(&params),
        _ => Err((-32601, format!("method not found: {method}"))),
    };

    Some(match result {
        Ok(result) => json!({ "jsonrpc": "2.0", "id": id, "result": result }),
        Err((code, message)) => rpc_error(id, code, message),
    })
}

fn negotiated_protocol(params: &Value) -> String {
    params
        .get("protocolVersion")
        .and_then(Value::as_str)
        .filter(|version| *version == MCP_PROTOCOL_VERSION)
        .unwrap_or(MCP_PROTOCOL_VERSION)
        .to_string()
}

fn tool_definitions() -> Vec<Value> {
    vec![
        json!({
            "name": "zed_project_status",
            "description": "Inspect real Zed package state without changing the project.",
            "inputSchema": root_schema()
        }),
        json!({
            "name": "zed_recommended_actions",
            "description": "Return prioritized commands and human fixes for detected Zed package problems. Commands are recommendations only and are never executed by this tool.",
            "inputSchema": root_schema()
        }),
        json!({
            "name": "zed_explain_diagnostic",
            "description": "Explain a stable Zed Air diagnostic code and its safe resolution.",
            "inputSchema": {
                "type": "object",
                "properties": { "code": { "type": "string", "description": "Diagnostic code such as ZED003" } },
                "required": ["code"],
                "additionalProperties": false
            }
        }),
    ]
}

fn root_schema() -> Value {
    json!({
        "type": "object",
        "properties": {
            "root": {
                "type": "string",
                "description": "Workspace path to inspect. Defaults to the MCP server process working directory."
            }
        },
        "additionalProperties": false
    })
}

fn call_tool(params: &Value) -> std::result::Result<Value, (i64, String)> {
    let name = params
        .get("name")
        .and_then(Value::as_str)
        .ok_or_else(|| (-32602, "tools/call requires `name`".to_string()))?;
    let arguments = params.get("arguments").cloned().unwrap_or_else(|| json!({}));

    match name {
        "zed_project_status" => {
            let report = inspect_from_arguments(&arguments)?;
            tool_success(render_report(&report), serde_json::to_value(report).map_err(internal_error)?)
        }
        "zed_recommended_actions" => {
            let report = inspect_from_arguments(&arguments)?;
            let text = report
                .recommended_actions
                .iter()
                .map(|action| match &action.command {
                    Some(command) => format!("{}: `{}` — {}", action.title, command, action.rationale),
                    None => format!("{} — {}", action.title, action.rationale),
                })
                .collect::<Vec<_>>()
                .join("\n");
            tool_success(
                text,
                json!({
                    "root": report.root,
                    "summary": report.summary,
                    "recommended_actions": report.recommended_actions
                }),
            )
        }
        "zed_explain_diagnostic" => {
            let code = arguments
                .get("code")
                .and_then(Value::as_str)
                .ok_or_else(|| (-32602, "zed_explain_diagnostic requires `code`".to_string()))?;
            let explanation = explain_code(code);
            tool_success(explanation.clone(), json!({ "code": code, "explanation": explanation }))
        }
        _ => Err((-32602, format!("unknown tool `{name}`"))),
    }
}

fn inspect_from_arguments(arguments: &Value) -> std::result::Result<ProjectReport, (i64, String)> {
    let root = arguments
        .get("root")
        .and_then(Value::as_str)
        .map(PathBuf::from)
        .or_else(|| env::current_dir().ok())
        .ok_or_else(|| (-32603, "cannot determine workspace root".to_string()))?;
    inspect_project(&root).map_err(|error| (-32603, error.to_string()))
}

fn tool_success(text: String, structured: Value) -> std::result::Result<Value, (i64, String)> {
    Ok(json!({
        "content": [{ "type": "text", "text": text }],
        "structuredContent": structured,
        "isError": false
    }))
}

fn explain_code(code: &str) -> String {
    match code.to_ascii_uppercase().as_str() {
        "ZED000" => "No obvious package-state problem was detected. Continue to use frozen installs in CI.".into(),
        "ZED001" => "The zed CLI is missing from PATH. Install it and restart Air so the MCP subprocess receives the new environment.".into(),
        "ZED002" => "No .zpkg.toml exists. Initialize an authored package or adopt Zed through a dependency-bearing install.".into(),
        "ZED003" => "A manifest exists without a lockfile. Run zed install to resolve and record exact artifacts.".into(),
        "ZED004" => "A lockfile exists without a manifest. Restore the manifest when possible; otherwise use the explicit frozen lock-only workflow.".into(),
        "ZED005" => "The manifest is invalid TOML and must be repaired before dependency resolution is safe.".into(),
        "ZED006" => "The lockfile is invalid TOML. Restore it from version control or regenerate it from a valid manifest.".into(),
        "ZED007" => "Locked packages are not materialized. Run zed install --frozen to restore exact versions.".into(),
        "ZED008" => "The manifest is newer than the lockfile. Re-resolve and review the resulting lockfile diff.".into(),
        "ZED009" => "The package identity is incomplete. Add org, name, and version before publishing.".into(),
        _ => format!("Unknown diagnostic code `{code}`. Run zed_project_status to obtain current supported codes."),
    }
}

fn internal_error(error: serde_json::Error) -> (i64, String) {
    (-32603, error.to_string())
}

fn rpc_error(id: Value, code: i64, message: String) -> Value {
    json!({
        "jsonrpc": "2.0",
        "id": id,
        "error": { "code": code, "message": message }
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs::File;
    use std::io::Write as _;

    #[test]
    fn reports_missing_lock_and_modules() {
        let directory = tempfile::tempdir().unwrap();
        let mut manifest = File::create(directory.path().join(".zpkg.toml")).unwrap();
        writeln!(
            manifest,
            "[package]\norg = \"acme\"\nname = \"demo\"\nversion = \"0.1.0\"\n\n[dependencies]\nfoo = \"^1\""
        )
        .unwrap();

        let report = inspect_project(directory.path()).unwrap();
        assert_eq!(report.package.direct_dependency_count, 1);
        assert!(report.diagnostics.iter().any(|item| item.code == "ZED003"));
    }

    #[test]
    fn explains_known_code() {
        assert!(explain_code("zed007").contains("--frozen"));
    }

    #[test]
    fn mcp_lists_tools() {
        let response = handle_mcp(json!({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {}
        }))
        .unwrap();
        assert_eq!(response["result"]["tools"].as_array().unwrap().len(), 3);
    }
}
