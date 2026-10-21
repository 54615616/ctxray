#!/usr/bin/env bash
# ==============================================================================
# CtxRay :: 1-Click GitHub Repository & Pages Publisher (POSIX / Bash)
# ==============================================================================
# Initializes Git (if needed), checks 'gh' CLI or remote URL, pushes 'main' to
# GitHub, sets discoverability topics (ai, llm, mcp, context-engineering, ast,
# developer-tools, claude-code, cursor, codex), and enables GitHub Pages for
# the interactive CtxRay Web Studio.
#
# Usage:
#   ./publish_to_github.sh
#   ./publish_to_github.sh --repo ctxray --visibility public
#   ./publish_to_github.sh --remote https://github.com/username/ctxray.git
# ==============================================================================

set -euo pipefail

REPO_NAME="ctxray"
VISIBILITY="public"
REMOTE_URL=""
BRANCH="main"
COMMIT_MSG="feat: initial release of CtxRay — AI Context Window X-Ray, AST Skeletonizer & Smart Packer"
DESCRIPTION="CtxRay: Zero-dependency AI Context Window X-Ray, AST Skeletonizer, Token Heatmap Studio & MCP Server for Claude Code, Cursor & Codex"
SKIP_PAGES=0

TOPICS=(
  "ai"
  "llm"
  "mcp"
  "context-engineering"
  "ast"
  "developer-tools"
  "claude-code"
  "cursor"
  "codex"
)

while [ "$#" -gt 0 ]; do
  case "$1" in
    --repo|-n)
      REPO_NAME="$2"
      shift 2
      ;;
    --visibility|-v)
      VISIBILITY="$2"
      shift 2
      ;;
    --remote|-r)
      REMOTE_URL="$2"
      shift 2
      ;;
    --branch|-b)
      BRANCH="$2"
      shift 2
      ;;
    --message|-m)
      COMMIT_MSG="$2"
      shift 2
      ;;
    --skip-pages)
      SKIP_PAGES=1
      shift 1
      ;;
    --help|-h)
      echo "Usage: ./publish_to_github.sh [--repo <name>] [--visibility public|private] [--remote <url>] [--branch main] [--skip-pages]"
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

step() { printf "\n\033[1;36m==> %s\033[0m\n" "$1"; }
ok()   { printf "\033[1;32m [OK] %s\033[0m\n" "$1"; }
warn() { printf "\033[1;33m [!] %s\033[0m\n" "$1"; }

echo "================================================================"
echo "  CtxRay :: 1-Click GitHub Repository & Pages Publisher (SH)    "
echo "================================================================"

# 1. Verify git is installed
step "Checking Git installation..."
if ! command -v git >/dev/null 2>&1; then
  echo "Error: git is not installed or not on PATH." >&2
  exit 1
fi
ok "Git found: $(git --version)"

# 2. Initialize Git repository & commit if needed
step "Preparing local Git repository on branch '${BRANCH}'..."
if [ ! -d ".git" ]; then
  git init -b "${BRANCH}" >/dev/null 2>&1 || { git init >/dev/null && git checkout -B "${BRANCH}" >/dev/null; }
  ok "Initialized new Git repository on branch '${BRANCH}'."
else
  git checkout -B "${BRANCH}" >/dev/null
  ok "Checked out branch '${BRANCH}'."
fi

git add -A
if [ -n "$(git status --porcelain)" ]; then
  git commit -m "${COMMIT_MSG}" >/dev/null
  ok "Committed workspace changes: '${COMMIT_MSG}'"
elif ! git rev-parse --verify HEAD >/dev/null 2>&1; then
  git commit --allow-empty -m "${COMMIT_MSG}" >/dev/null
  ok "Created initial commit."
else
  ok "Working tree clean; HEAD commit is ready."
fi

# 3. Check GitHub CLI (gh) or Remote URL
step "Checking GitHub CLI ('gh') and remote configuration..."
HAS_GH=0
GH_AUTHED=0
if command -v gh >/dev/null 2>&1; then
  HAS_GH=1
  if gh auth status >/dev/null 2>&1; then
    GH_AUTHED=1
  fi
fi

EXISTING_ORIGIN="$(git remote get-url origin 2>/dev/null || true)"

if [ -n "${REMOTE_URL}" ]; then
  if [ -n "${EXISTING_ORIGIN}" ]; then
    git remote set-url origin "${REMOTE_URL}"
    ok "Updated 'origin' remote to ${REMOTE_URL}"
  else
    git remote add origin "${REMOTE_URL}"
    ok "Added 'origin' remote: ${REMOTE_URL}"
  fi
  EXISTING_ORIGIN="${REMOTE_URL}"
fi

if [ -z "${EXISTING_ORIGIN}" ]; then
  if [ "${HAS_GH}" -eq 1 ] && [ "${GH_AUTHED}" -eq 1 ]; then
    step "Creating GitHub repository '${REPO_NAME}' (${VISIBILITY}) via GitHub CLI..."
    gh repo create "${REPO_NAME}" "--${VISIBILITY}" --source=. --remote=origin --description "${DESCRIPTION}" --push
    EXISTING_ORIGIN="$(git remote get-url origin 2>/dev/null || true)"
    ok "Created and pushed repository to ${EXISTING_ORIGIN}"
  else
    warn "GitHub CLI ('gh') is not authenticated and no 'origin' remote is configured."
    printf "Enter your target GitHub repository URL (e.g., https://github.com/username/ctxray.git): "
    read -r INPUT_URL
    if [ -z "${INPUT_URL}" ]; then
      echo "Error: No remote URL provided. Run 'gh auth login' or pass --remote <url>." >&2
      exit 1
    fi
    git remote add origin "${INPUT_URL}"
    EXISTING_ORIGIN="${INPUT_URL}"
    ok "Configured 'origin' remote: ${EXISTING_ORIGIN}"
  fi
fi

# 4. Push branch to origin
step "Pushing '${BRANCH}' to origin..."
git push -u origin "${BRANCH}"
ok "Branch '${BRANCH}' pushed to ${EXISTING_ORIGIN}"

# 5. Configure Repository Topics & GitHub Pages when gh is authenticated
if [ "${HAS_GH}" -eq 1 ] && [ "${GH_AUTHED}" -eq 1 ]; then
  step "Setting GitHub repository topics for discoverability..."
  TOPIC_ARGS=(repo edit --description "${DESCRIPTION}")
  for t in "${TOPICS[@]}"; do
    TOPIC_ARGS+=(--add-topic "$t")
  done
  if gh "${TOPIC_ARGS[@]}" >/dev/null 2>&1; then
    ok "Applied topics: ${TOPICS[*]}"
  else
    warn "Could not set topics automatically via 'gh repo edit'."
  fi

  if [ "${SKIP_PAGES}" -eq 0 ]; then
    step "Enabling GitHub Pages (GitHub Actions workflow build_type)..."
    REPO_SLUG="$(gh repo view --json nameWithOwner -q '.nameWithOwner' 2>/dev/null || true)"
    if [ -n "${REPO_SLUG}" ]; then
      gh api --method POST "repos/${REPO_SLUG}/pages" -f "build_type=workflow" >/dev/null 2>&1 \
        || gh api --method PUT "repos/${REPO_SLUG}/pages" -f "build_type=workflow" >/dev/null 2>&1 \
        || true
      ok "GitHub Pages configured for ${REPO_SLUG} (workflow deployment via .github/workflows/pages.yml)."
      gh workflow run pages.yml >/dev/null 2>&1 || true
    fi
  fi
else
  warn "Tip: Run 'gh auth login' to automatically set repo topics (${TOPICS[*]}) and enable GitHub Pages."
fi

echo ""
echo "================================================================"
echo "  CtxRay Published Successfully!"
echo "  Remote : ${EXISTING_ORIGIN}"
echo "  Topics : ${TOPICS[*]}"
echo "================================================================"
