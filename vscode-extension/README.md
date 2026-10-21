# ctxray for VS Code, Cursor & Windsurf (`ctxray-vscode`)

**Visual Context Compiler, Dependency PageRank & AST Skeletonizer inside your IDE.**

`ctxray-vscode` brings real-time token telemetry, one-click cache-pinned context compilation, AST signature folding, and blast-radius analysis directly into **VS Code**, **Cursor**, and **Windsurf**.

---

## Features

- **Live Status Bar Token Telemetry (`$(pulse) ctxray: Ready`)**:
  Automatically estimates raw vs. AST-skeletonized BPE tokens (`o200k_base` / Claude 4 calibrated) as you switch files or highlight code selections.
- **Compile Repository to Clipboard (`ctxray.compileRepo`)**:
  Runs Dependency PageRank across your workspace, allocates `FULL` / `SKELETON` / `SUMMARY` tiers within your exact token budget (`16k`, `32k`, `64k`, `128k`), redacts secrets via `SecretGuard`, and copies the cache-pinned `<ctxray_bundle>` directly to your clipboard.
- **AST-Skeletonize Current File (`ctxray.skeletonizeCurrentFile`)**:
  Folds function/method implementation bodies into compact `[ctxray: folded N lines]` markers while preserving imports, types, class hierarchies, signatures, and docstrings — opening a side-by-side preview and copying to clipboard.
- **Dependency Blast Radius Inspector (`ctxray.showBlastRadius`)**:
  Computes direct and transitive downstream dependents, PageRank centrality, and risk classification (`LOW` / `MODERATE` / `CRITICAL`) for any file from the editor or file explorer context menu.
- **Live Visual X-Ray Studio (`ctxray.openStudio`)**:
  Launches the local zero-dependency `ctxray studio` HTTP server (`http://127.0.0.1:8420`) with interactive Dependency Force Graph, Token Treemap, and Budget Simulator connected to your live workspace.
- **One-Click Agent Rules (`ctxray.initRules`)**:
  Scaffolds `AGENTS.md`, `CLAUDE.md`, and `.cursor/rules/ctxray.mdc` into your project root.

---

## Installation (VS Code / Cursor / Windsurf)

### Option 1: Install from Local Extension Folder (Development / Monorepo)

```bash
# Symlink or copy into your IDE extensions folder:
# VS Code:
cp -r ./vscode-extension ~/.vscode/extensions/ctxray-vscode-1.0.0

# Cursor:
cp -r ./vscode-extension ~/.cursor/extensions/ctxray-vscode-1.0.0

# Windsurf:
cp -r ./vscode-extension ~/.windsurf/extensions/ctxray-vscode-1.0.0
```

### Option 2: Package as `.vsix`

```bash
cd vscode-extension
npx @vscode/vsce package
code --install-extension ctxray-vscode-1.0.0.vsix
# Or in Cursor / Windsurf:
cursor --install-extension ctxray-vscode-1.0.0.vsix
```

---

## Commands & Default Keybindings

| Command | Title | Shortcut (Win/Linux) | Shortcut (macOS) |
| :--- | :--- | :--- | :--- |
| `ctxray.compileRepo` | Compile Repository Context Bundle to Clipboard | `Ctrl+Shift+X C` | `Cmd+Shift+X C` |
| `ctxray.skeletonizeCurrentFile` | AST-Skeletonize Current File | `Ctrl+Shift+X S` | `Cmd+Shift+X S` |
| `ctxray.showBlastRadius` | Analyze File Dependency Blast Radius | `Ctrl+Shift+X B` | `Cmd+Shift+X B` |
| `ctxray.openStudio` | Launch Live Visual X-Ray Studio | `Ctrl+Shift+X O` | `Cmd+Shift+X O` |
| `ctxray.initRules` | Initialize AGENTS.md / CLAUDE.md / Cursor Rules | Command Palette | Command Palette |

---

## Extension Settings

Configure `ctxray` in your `settings.json`:

```json
{
  "ctxray.defaultBudget": "32k",
  "ctxray.format": "xml",
  "ctxray.pythonPath": "python",
  "ctxray.studioPort": 8420
}
```

---

## License

MIT © ctxray contributors
