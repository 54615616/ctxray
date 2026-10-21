<#
.SYNOPSIS
    1-Click GitHub Publisher for CtxRay (Windows PowerShell)
.DESCRIPTION
    Initializes Git (if needed), creates or links a GitHub repository, pushes the 'main' branch,
    sets discoverability topics (ai, llm, mcp, context-engineering, ast, developer-tools,
    claude-code, cursor, codex), and enables GitHub Pages for the live Interactive Studio demo.
.EXAMPLE
    .\publish_to_github.ps1
.EXAMPLE
    .\publish_to_github.ps1 -RepoName "ctxray" -Visibility "public"
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$RepoName = "ctxray",

    [Parameter(Mandatory = $false)]
    [ValidateSet("public", "private", "internal")]
    [string]$Visibility = "public",

    [Parameter(Mandatory = $false)]
    [string]$RemoteUrl = "",

    [Parameter(Mandatory = $false)]
    [string]$Branch = "main",

    [Parameter(Mandatory = $false)]
    [string]$CommitMessage = "feat: initial release of CtxRay — AI Context Window X-Ray, AST Skeletonizer & Smart Packer",

    [Parameter(Mandatory = $false)]
    [string]$Description = "CtxRay: Zero-dependency AI Context Window X-Ray, AST Skeletonizer, Token Heatmap Studio & MCP Server for Claude Code, Cursor & Codex",

    [Parameter(Mandatory = $false)]
    [switch]$SkipPages
)

$ErrorActionPreference = "Stop"

$Topics = @(
    "ai",
    "llm",
    "mcp",
    "context-engineering",
    "ast",
    "developer-tools",
    "claude-code",
    "cursor",
    "codex"
)

function Write-Step([string]$Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Write-Ok([string]$Message) {
    Write-Host " [OK] $Message" -ForegroundColor Green
}

function Write-Warn([string]$Message) {
    Write-Host " [!] $Message" -ForegroundColor Yellow
}

# Ensure we run from the script's directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ScriptDir

Write-Host "================================================================" -ForegroundColor Magenta
Write-Host "  CtxRay :: 1-Click GitHub Repository & Pages Publisher (PS1)   " -ForegroundColor Magenta
Write-Host "================================================================" -ForegroundColor Magenta

# 1. Verify git is installed
Write-Step "Checking Git installation..."
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "Git is not installed or not on PATH. Install Git from https://git-scm.com/ and retry."
}
Write-Ok "Git found: $(git --version)"

# 2. Initialize Git repository & commit if needed
Write-Step "Preparing local Git repository on branch '$Branch'..."
if (-not (Test-Path -LiteralPath (Join-Path $ScriptDir ".git"))) {
    git init -b $Branch | Out-Null
    Write-Ok "Initialized new Git repository on branch '$Branch'."
} else {
    git checkout -B $Branch | Out-Null
    Write-Ok "Checked out branch '$Branch'."
}

git add -A
$Status = git status --porcelain
if ($Status) {
    git commit -m $CommitMessage | Out-Null
    Write-Ok "Committed workspace changes: '$CommitMessage'"
} else {
    $HasHead = $false
    try {
        git rev-parse --verify HEAD *> $null
        if ($LASTEXITCODE -eq 0) { $HasHead = $true }
    } catch {}
    if (-not $HasHead) {
        git commit --allow-empty -m $CommitMessage | Out-Null
        Write-Ok "Created initial commit."
    } else {
        Write-Ok "Working tree clean; HEAD commit is ready."
    }
}

# 3. Check GitHub CLI (gh) or Remote URL
Write-Step "Checking GitHub CLI ('gh') and remote configuration..."
$HasGh = $false
$GhAuthed = $false
if (Get-Command gh -ErrorAction SilentlyContinue) {
    $HasGh = $true
    try {
        gh auth status *> $null
        if ($LASTEXITCODE -eq 0) { $GhAuthed = $true }
    } catch {}
}

$ExistingOrigin = ""
try {
    $ExistingOrigin = (git remote get-url origin 2>$null).Trim()
} catch {}

if ($RemoteUrl) {
    if ($ExistingOrigin) {
        git remote set-url origin $RemoteUrl
        Write-Ok "Updated 'origin' remote to $RemoteUrl"
    } else {
        git remote add origin $RemoteUrl
        Write-Ok "Added 'origin' remote: $RemoteUrl"
    }
    $ExistingOrigin = $RemoteUrl
}

if (-not $ExistingOrigin) {
    if ($HasGh -and $GhAuthed) {
        Write-Step "Creating GitHub repository '$RepoName' ($Visibility) via GitHub CLI..."
        gh repo create $RepoName "--$Visibility" --source=. --remote=origin --description $Description --push
        $ExistingOrigin = (git remote get-url origin 2>$null).Trim()
        Write-Ok "Created and pushed repository to $ExistingOrigin"
    } else {
        Write-Warn "GitHub CLI ('gh') is not authenticated and no 'origin' remote is configured."
        $InputUrl = Read-Host "Enter your target GitHub repository URL (e.g., https://github.com/54615616/ctxray.git)"
        if ([string]::IsNullOrWhiteSpace($InputUrl)) {
            throw "No remote URL provided. Authenticate with 'gh auth login' or pass -RemoteUrl <url>."
        }
        git remote add origin $InputUrl.Trim()
        $ExistingOrigin = $InputUrl.Trim()
        Write-Ok "Configured 'origin' remote: $ExistingOrigin"
    }
}

# 4. Push branch to origin
Write-Step "Pushing '$Branch' to origin..."
git push -u origin $Branch
Write-Ok "Branch '$Branch' pushed to $ExistingOrigin"

# 5. Configure Repository Topics & GitHub Pages when gh is authenticated
if ($HasGh -and $GhAuthed) {
    Write-Step "Setting GitHub repository topics for discoverability..."
    $TopicArgs = @("repo", "edit", "--description", $Description)
    foreach ($t in $Topics) {
        $TopicArgs += @("--add-topic", $t)
    }
    try {
        & gh @TopicArgs
        Write-Ok "Applied topics: $($Topics -join ', ')"
    } catch {
        Write-Warn "Could not set topics automatically via 'gh repo edit': $_"
    }

    if (-not $SkipPages) {
        Write-Step "Enabling GitHub Pages (GitHub Actions workflow build_type)..."
        try {
            $RepoSlug = (gh repo view --json nameWithOwner -q ".nameWithOwner").Trim()
            if ($RepoSlug) {
                gh api --method POST "repos/$RepoSlug/pages" -f "build_type=workflow" *> $null
                if ($LASTEXITCODE -ne 0) {
                    gh api --method PUT "repos/$RepoSlug/pages" -f "build_type=workflow" *> $null
                }
                Write-Ok "GitHub Pages enabled for $RepoSlug (workflow deployment via .github/workflows/pages.yml)."
                gh workflow run pages.yml *> $null
                Write-Ok "Triggered 'Deploy CtxRay Studio to GitHub Pages' workflow."
            }
        } catch {
            Write-Warn "GitHub Pages may already be enabled or requires manual toggle in Settings -> Pages."
        }
    }
} else {
    Write-Warn "Tip: Run 'gh auth login' to automatically set repo topics ($($Topics -join ', ')) and enable GitHub Pages."
}

Write-Host "`n================================================================" -ForegroundColor Green
Write-Host "  CtxRay Published Successfully!                                " -ForegroundColor Green
Write-Host "  Remote : $ExistingOrigin" -ForegroundColor Green
Write-Host "  Topics : $($Topics -join ', ')" -ForegroundColor Green
Write-Host "================================================================`n" -ForegroundColor Green
