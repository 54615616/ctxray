"use strict";

const vscode = require("vscode");
const cp = require("child_process");
const path = require("path");
const fs = require("fs");

/** @type {vscode.StatusBarItem | undefined} */
let statusBarItem;
/** @type {vscode.OutputChannel | undefined} */
let outputChannel;
/** @type {cp.ChildProcess | undefined} */
let studioProcess;

/**
 * Fast, deterministic BPE token estimator calibrated to o200k_base / Claude 4.
 * Mirrors ctxray.TokenEstimator so the status bar updates with zero latency.
 * @param {string} text
 * @returns {number}
 */
function estimateTokens(text) {
  if (!text) return 0;
  if (text.length > 60000) {
    const words = text.trim().split(/\s+/).length;
    let symbols = 0;
    for (let i = 0; i < text.length; i++) {
      if ("{}[]().,:;+-*/=<>!&|".includes(text[i])) symbols++;
    }
    return Math.max(1, Math.floor(words * 1.15 + symbols * 0.45));
  }
  const chunks =
    text.match(/[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\b)|\d+|[\u4e00-\u9fff]|[^\w\s]|\s+/g) || [];
  let tokens = 0;
  for (const ch of chunks) {
    if (/^\s+$/.test(ch)) {
      tokens += Math.max(0, Math.floor(ch.length / 4));
    } else if (ch.length > 10) {
      tokens += Math.ceil(ch.length / 4.2);
    } else {
      tokens += 1;
    }
  }
  return Math.max(1, Math.floor(tokens * 0.88));
}

/**
 * Resolve workspace root directory.
 * @returns {string | undefined}
 */
function getWorkspaceRoot() {
  const folders = vscode.workspace.workspaceFolders;
  if (folders && folders.length > 0) {
    return folders[0].uri.fsPath;
  }
  const activeEditor = vscode.window.activeTextEditor;
  if (activeEditor && activeEditor.document.uri.scheme === "file") {
    return path.dirname(activeEditor.document.uri.fsPath);
  }
  return undefined;
}

/**
 * Read ctxray user configuration settings.
 */
function getConfig() {
  const cfg = vscode.workspace.getConfiguration("ctxray");
  return {
    defaultBudget: cfg.get("defaultBudget", "32k"),
    format: cfg.get("format", "xml"),
    pythonPath: cfg.get("pythonPath", "python"),
    studioPort: cfg.get("studioPort", 8420),
  };
}

/**
 * Execute a ctxray CLI command using either global ctxray or local ctxray.py.
 * @param {string[]} args
 * @param {string} cwd
 * @returns {Promise<{ stdout: string, stderr: string }>}
 */
function runCtxRayCli(args, cwd) {
  const { pythonPath } = getConfig();
  const localScriptCandidates = [
    path.join(cwd, "ctxray.py"),
    path.resolve(__dirname, "..", "ctxray.py"),
  ];
  const localScript = localScriptCandidates.find((p) => fs.existsSync(p));

  return new Promise((resolve, reject) => {
    const execOptions = {
      cwd,
      maxBuffer: 25 * 1024 * 1024,
      env: { ...process.env, PYTHONIOENCODING: "utf-8" },
    };

    const tryPythonFallback = () => {
      const cmdArgs = localScript ? [localScript, ...args] : ["-m", "ctxray.cli", ...args];
      cp.execFile(pythonPath, cmdArgs, execOptions, (err, stdout, stderr) => {
        if (err) {
          reject(new Error(stderr || err.message));
          return;
        }
        resolve({ stdout, stderr });
      });
    };

    if (localScript) {
      tryPythonFallback();
      return;
    }

    cp.execFile("ctxray", args, execOptions, (err, stdout, stderr) => {
      if (err) {
        tryPythonFallback();
        return;
      }
      resolve({ stdout, stderr });
    });
  });
}

/**
 * Update the live Status Bar item when active editor or selection changes.
 */
function updateStatusBar() {
  if (!statusBarItem) return;
  const editor = vscode.window.activeTextEditor;
  if (!editor || editor.document.uri.scheme !== "file") {
    statusBarItem.text = "$(pulse) ctxray: Ready";
    statusBarItem.tooltip = "ctxray Visual Context Compiler — Click to compile repository context";
    statusBarItem.show();
    return;
  }

  const doc = editor.document;
  const fullText = doc.getText();
  const rawTokens = estimateTokens(fullText);
  const estSkeletonTokens = Math.max(1, Math.round(rawTokens * 0.28));
  const fileName = path.basename(doc.uri.fsPath);

  const selection = editor.selection;
  if (selection && !selection.isEmpty) {
    const selTokens = estimateTokens(doc.getText(selection));
    statusBarItem.text = "$(pulse) ctxray: " + selTokens.toLocaleString() + " sel / " + rawTokens.toLocaleString() + " tok";
  } else {
    statusBarItem.text = "$(pulse) ctxray: " + rawTokens.toLocaleString() + " tok (~" + estSkeletonTokens.toLocaleString() + " skel)";
  }

  statusBarItem.tooltip = new vscode.MarkdownString(
    [
      "**ctxray Live Token X-Ray** — `" + fileName + "`",
      "- **Raw File Tokens**: " + rawTokens.toLocaleString() + " tok",
      "- **Est. AST Skeleton**: ~" + estSkeletonTokens.toLocaleString() + " tok (-72%)",
      "",
      "Click to compile repository bundle to clipboard, or run **ctxray: Launch Live Visual X-Ray Studio**.",
    ].join("\n")
  );
  statusBarItem.show();
}

/**
 * Command: ctxray.compileRepo
 * Compiles the workspace within the target token budget and copies the bundle to IDE clipboard.
 */
async function handleCompileRepo() {
  const root = getWorkspaceRoot();
  if (!root) {
    vscode.window.showWarningMessage("ctxray: Open a workspace folder first to compile repository context.");
    return;
  }

  const cfg = getConfig();
  const budgetInput = await vscode.window.showInputBox({
    title: "ctxray: Target Token Budget",
    prompt: "Enter token budget for PageRank context allocation (e.g. 16k, 32k, 64k, 128k)",
    value: cfg.defaultBudget,
  });
  if (!budgetInput) return;

  await vscode.window.withProgress(
    {
      location: vscode.ProgressLocation.Notification,
      title: "ctxray: Compiling repository within " + budgetInput + " token budget...",
      cancellable: false,
    },
    async () => {
      try {
        const { stdout, stderr } = await runCtxRayCli(
          ["scan", root, "--budget", budgetInput, "--format", cfg.format],
          root
        );
        await vscode.env.clipboard.writeText(stdout);

        const compiledTokens = estimateTokens(stdout);
        outputChannel.appendLine("[compileRepo] Compiled " + root + " (budget=" + budgetInput + ", format=" + cfg.format + ", ~" + compiledTokens + " tokens)");
        if (stderr) outputChannel.appendLine(stderr.trim());

        const action = await vscode.window.showInformationMessage(
          "ctxray: Copied compiled " + cfg.format.toUpperCase() + " bundle (~" + compiledTokens.toLocaleString() + " tokens) to clipboard!",
          "Open Preview",
          "Launch Studio"
        );
        if (action === "Open Preview") {
          const doc = await vscode.workspace.openTextDocument({
            content: stdout,
            language: cfg.format === "md" ? "markdown" : cfg.format === "json" ? "json" : "xml",
          });
          await vscode.window.showTextDocument(doc, { preview: true });
        } else if (action === "Launch Studio") {
          await handleOpenStudio();
        }
      } catch (err) {
        outputChannel.appendLine("[compileRepo Error] " + err.message);
        vscode.window.showErrorMessage("ctxray compile failed: " + err.message);
      }
    }
  );
}

/**
 * Command: ctxray.skeletonizeCurrentFile
 * Extracts AST signatures & docstrings from the active editor and opens side-by-side preview + copies to clipboard.
 */
async function handleSkeletonizeCurrentFile() {
  const editor = vscode.window.activeTextEditor;
  if (!editor || editor.document.uri.scheme !== "file") {
    vscode.window.showWarningMessage("ctxray: Open a source file to AST-skeletonize.");
    return;
  }

  const filePath = editor.document.uri.fsPath;
  const root = getWorkspaceRoot() || path.dirname(filePath);

  try {
    const { stdout } = await runCtxRayCli(["skeleton", filePath], root);
    await vscode.env.clipboard.writeText(stdout);

    const rawTok = estimateTokens(editor.document.getText());
    const skelTok = estimateTokens(stdout);
    const savedPct = Math.max(0, Math.round((1 - skelTok / Math.max(1, rawTok)) * 100));

    const doc = await vscode.workspace.openTextDocument({
      content: stdout,
      language: editor.document.languageId,
    });
    await vscode.window.showTextDocument(doc, {
      viewColumn: vscode.ViewColumn.Beside,
      preview: true,
    });

    vscode.window.showInformationMessage(
      "ctxray Skeleton: " + rawTok.toLocaleString() + " -> " + skelTok.toLocaleString() + " tokens (-" + savedPct + "%) copied to clipboard!"
    );
  } catch (err) {
    outputChannel.appendLine("[skeletonizeCurrentFile Error] " + err.message);
    vscode.window.showErrorMessage("ctxray skeletonize failed: " + err.message);
  }
}

/**
 * Command: ctxray.showBlastRadius
 * Computes upstream/downstream dependency blast radius for the active or selected file.
 * @param {vscode.Uri | undefined} resourceUri
 */
async function handleShowBlastRadius(resourceUri) {
  const root = getWorkspaceRoot();
  if (!root) {
    vscode.window.showWarningMessage("ctxray: Open a repository folder first.");
    return;
  }

  let targetPath = resourceUri ? resourceUri.fsPath : undefined;
  if (!targetPath && vscode.window.activeTextEditor) {
    targetPath = vscode.window.activeTextEditor.document.uri.fsPath;
  }

  let relTarget = targetPath ? path.relative(root, targetPath).replace(/\\/g, "/") : "";
  if (!relTarget || relTarget.startsWith("..")) {
    relTarget = await vscode.window.showInputBox({
      title: "ctxray: Blast Radius Target",
      prompt: "Enter relative file path or module name to inspect",
      placeHolder: "ctxray/engine.py",
    });
  }
  if (!relTarget) return;

  try {
    const { stdout } = await runCtxRayCli(["blast", relTarget, "--path", root], root);
    const report = JSON.parse(stdout);

    outputChannel.clear();
    outputChannel.appendLine("======================================================================");
    outputChannel.appendLine(" CTXRAY BLAST RADIUS REPORT: " + (report.target || relTarget));
    outputChannel.appendLine("======================================================================");
    outputChannel.appendLine(" Risk Level          : " + (report.risk_level || "UNKNOWN"));
    outputChannel.appendLine(" Dependency PageRank : " + (report.pagerank ?? "N/A"));
    outputChannel.appendLine(" Transitive Impact   : " + (report.transitive_impact_count ?? 0) + " downstream files");
    outputChannel.appendLine(" Direct Dependents   : " + ((report.direct_dependents || []).join(", ") || "None"));
    outputChannel.appendLine(" Direct Imports      : " + ((report.direct_dependencies || []).join(", ") || "None"));
    outputChannel.appendLine("----------------------------------------------------------------------");
    outputChannel.appendLine(JSON.stringify(report, null, 2));
    outputChannel.show(true);

    vscode.window.showInformationMessage(
      "ctxray Blast Radius [" + (report.risk_level || "OK") + "]: " + (report.target || relTarget) + " (PR=" + (report.pagerank ?? 0) + ", Impact=" + (report.transitive_impact_count ?? 0) + " files)"
    );
  } catch (err) {
    outputChannel.appendLine("[showBlastRadius Error] " + err.message);
    vscode.window.showErrorMessage("ctxray blast radius failed: " + err.message);
  }
}

/**
 * Command: ctxray.openStudio
 * Starts the local zero-dependency ctxray Live Visual X-Ray Studio server and opens it in browser.
 */
async function handleOpenStudio() {
  const root = getWorkspaceRoot();
  if (!root) {
    vscode.window.showWarningMessage("ctxray: Open a workspace folder to launch Live X-Ray Studio.");
    return;
  }

  const cfg = getConfig();
  const localScriptCandidates = [
    path.join(root, "ctxray.py"),
    path.resolve(__dirname, "..", "ctxray.py"),
  ];
  const localScript = localScriptCandidates.find((p) => fs.existsSync(p));

  if (studioProcess && !studioProcess.killed) {
    const url = "http://127.0.0.1:" + cfg.studioPort;
    await vscode.env.openExternal(vscode.Uri.parse(url));
    return;
  }

  const args = localScript
    ? [localScript, "-m", "ctxray.server", root, "--port", String(cfg.studioPort), "--no-open"]
    : ["-m", "ctxray.server", root, "--port", String(cfg.studioPort), "--no-open"];

  studioProcess = cp.spawn(cfg.pythonPath, ["-m", "ctxray.server", root, "--port", String(cfg.studioPort), "--no-open"], {
    cwd: localScript ? path.dirname(localScript) : root,
    env: { ...process.env, PYTHONIOENCODING: "utf-8" },
  });

  let opened = false;
  studioProcess.stdout.on("data", (chunk) => {
    const text = chunk.toString();
    outputChannel.append(text);
    const match = text.match(/http:\/\/127\.0\.0\.1:\d+/);
    if (match && !opened) {
      opened = true;
      vscode.env.openExternal(vscode.Uri.parse(match[0]));
      vscode.window.showInformationMessage("ctxray Live X-Ray Studio running at " + match[0]);
    }
  });

  studioProcess.stderr.on("data", (chunk) => {
    outputChannel.append(chunk.toString());
  });

  setTimeout(() => {
    if (!opened) {
      opened = true;
      const fallbackUrl = "http://127.0.0.1:" + cfg.studioPort;
      vscode.env.openExternal(vscode.Uri.parse(fallbackUrl));
    }
  }, 1200);
}

/**
 * Command: ctxray.initRules
 * Scaffolds AGENTS.md, CLAUDE.md, and .cursor/rules/ctxray.mdc into the current workspace.
 */
async function handleInitRules() {
  const root = getWorkspaceRoot();
  if (!root) {
    vscode.window.showWarningMessage("ctxray: Open a workspace folder to initialize AI agent rules.");
    return;
  }

  try {
    await runCtxRayCli(["init", root], root);
    vscode.window.showInformationMessage(
      "ctxray: Initialized AGENTS.md, CLAUDE.md, and Cursor rules in workspace!"
    );
  } catch (_cliErr) {
    const agentsMdPath = path.join(root, "AGENTS.md");
    if (!fs.existsSync(agentsMdPath)) {
      fs.writeFileSync(
        agentsMdPath,
        [
          "# AGENTS.md — ctxray Context Engineering Protocol",
          "",
          "Before broad multi-file exploration, run:",
          "```bash",
          "ctxray rank . --budget 32k",
          "ctxray blast <target_file>",
          "```",
          "",
          "- Inspect high-PageRank architectural hubs (`FULL` tier) first.",
          "- Use `ctxray skeleton <file>` to read structural signatures of large modules at 70%+ fewer tokens.",
          "",
        ].join("\n"),
        "utf8"
      );
    }
    vscode.window.showInformationMessage("ctxray: Initialized AGENTS.md in workspace root!");
  }
}

/**
 * @param {vscode.ExtensionContext} context
 */
function activate(context) {
  outputChannel = vscode.window.createOutputChannel("ctxray");
  statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
  statusBarItem.command = "ctxray.compileRepo";
  statusBarItem.text = "$(pulse) ctxray: Ready";
  statusBarItem.show();

  context.subscriptions.push(
    outputChannel,
    statusBarItem,
    vscode.commands.registerCommand("ctxray.compileRepo", handleCompileRepo),
    vscode.commands.registerCommand("ctxray.skeletonizeCurrentFile", handleSkeletonizeCurrentFile),
    vscode.commands.registerCommand("ctxray.showBlastRadius", handleShowBlastRadius),
    vscode.commands.registerCommand("ctxray.openStudio", handleOpenStudio),
    vscode.commands.registerCommand("ctxray.initRules", handleInitRules),
    vscode.window.onDidChangeActiveTextEditor(updateStatusBar),
    vscode.window.onDidChangeTextEditorSelection(updateStatusBar),
    vscode.workspace.onDidChangeTextDocument(() => updateStatusBar())
  );

  updateStatusBar();
}

function deactivate() {
  if (studioProcess && !studioProcess.killed) {
    studioProcess.kill();
  }
}

module.exports = {
  activate,
  deactivate,
  estimateTokens,
};
