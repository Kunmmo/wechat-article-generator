#!/bin/bash

# Platform Setup Script for WeChat Article Generator
# Usage: ./scripts/setup_platform.sh [platform]
# Platforms: cursor, claude, copilot, windsurf, aider, all

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Ensure agents directory exists with AGENT.md files
setup_agents() {
    log_info "Setting up unified agents directory..."
    
    mkdir -p "$PROJECT_ROOT/agents"
    
    # Copy from .cursor/skills if they exist and agents don't
    if [ -d "$PROJECT_ROOT/.cursor/skills" ]; then
        for skill_dir in "$PROJECT_ROOT/.cursor/skills"/*/; do
            if [ -d "$skill_dir" ]; then
                skill_name=$(basename "$skill_dir")
                agent_dir="$PROJECT_ROOT/agents/$skill_name"
                mkdir -p "$agent_dir"
                
                # Copy SKILL.md as AGENT.md if doesn't exist
                if [ -f "$skill_dir/SKILL.md" ] && [ ! -f "$agent_dir/AGENT.md" ]; then
                    cp "$skill_dir/SKILL.md" "$agent_dir/AGENT.md"
                    log_info "  Created agents/$skill_name/AGENT.md"
                fi
            fi
        done
    fi
    
    log_success "Agents directory configured"
}

# Setup Cursor (Skills already exist, ensure rules also exist)
setup_cursor() {
    log_info "Setting up Cursor configuration..."
    
    mkdir -p "$PROJECT_ROOT/.cursor/rules"
    
    # Create rules file if not exists
    if [ ! -f "$PROJECT_ROOT/.cursor/rules/wechat-article-generator.mdc" ]; then
        cat > "$PROJECT_ROOT/.cursor/rules/wechat-article-generator.mdc" << 'EOF'
---
description: 微信公众号文章生成器规则
alwaysApply: true
---

# WeChat Article Generator

使用 `.cursor/skills/` 中的智能体生成公众号文章。
主工作流: `.cursor/skills/triagent-workflow/SKILL.md`
EOF
        log_info "  Created .cursor/rules/wechat-article-generator.mdc"
    fi
    
    # Sync skills from agents if needed
    if [ -d "$PROJECT_ROOT/agents" ]; then
        for agent_dir in "$PROJECT_ROOT/agents"/*/; do
            if [ -d "$agent_dir" ]; then
                agent_name=$(basename "$agent_dir")
                skill_dir="$PROJECT_ROOT/.cursor/skills/$agent_name"
                mkdir -p "$skill_dir"
                
                if [ -f "$agent_dir/AGENT.md" ] && [ ! -f "$skill_dir/SKILL.md" ]; then
                    cp "$agent_dir/AGENT.md" "$skill_dir/SKILL.md"
                    log_info "  Synced to .cursor/skills/$agent_name/SKILL.md"
                fi
            fi
        done
    fi
    
    log_success "Cursor configuration complete"
}

# Setup Claude Code
setup_claude() {
    log_info "Setting up Claude Code configuration..."
    
    if [ ! -f "$PROJECT_ROOT/CLAUDE.md" ]; then
        cat > "$PROJECT_ROOT/CLAUDE.md" << 'EOF'
# WeChat Article Generator - Claude Code Instructions

Multi-agent article generation system. See `AGENTS.md` for overview and `agents/` for agent definitions.

## Quick Start
- Article generation: Read `agents/triagent-workflow/AGENT.md`
- Individual agents in `agents/*/AGENT.md`

## Key Directories
- `agents/` - Agent definitions
- `scripts/` - Python utilities
- `outputs/articles/` - Generated HTML
EOF
        log_info "  Created CLAUDE.md"
    fi
    
    log_success "Claude Code configuration complete"
}

# Setup GitHub Copilot
setup_copilot() {
    log_info "Setting up GitHub Copilot configuration..."
    
    mkdir -p "$PROJECT_ROOT/.github"
    
    if [ ! -f "$PROJECT_ROOT/.github/copilot-instructions.md" ]; then
        cat > "$PROJECT_ROOT/.github/copilot-instructions.md" << 'EOF'
# GitHub Copilot Instructions

Multi-agent WeChat article generator. Agents defined in `agents/*/AGENT.md`.
Main workflow: `agents/triagent-workflow/AGENT.md`
EOF
        log_info "  Created .github/copilot-instructions.md"
    fi
    
    log_success "GitHub Copilot configuration complete"
}

# Setup Windsurf
setup_windsurf() {
    log_info "Setting up Windsurf configuration..."
    
    if [ ! -f "$PROJECT_ROOT/.windsurfrules" ]; then
        cat > "$PROJECT_ROOT/.windsurfrules" << 'EOF'
# Windsurf Rules

多智能体公众号文章生成系统。
智能体定义: agents/*/AGENT.md
主工作流: agents/triagent-workflow/AGENT.md
EOF
        log_info "  Created .windsurfrules"
    fi
    
    log_success "Windsurf configuration complete"
}

# Setup Aider
setup_aider() {
    log_info "Setting up Aider configuration..."
    
    if [ ! -f "$PROJECT_ROOT/.aider.conf.yml" ]; then
        cat > "$PROJECT_ROOT/.aider.conf.yml" << 'EOF'
read:
  - AGENTS.md
  - agents/triagent-workflow/AGENT.md
EOF
        log_info "  Created .aider.conf.yml"
    fi
    
    log_success "Aider configuration complete"
}

# Show help
show_help() {
    echo "Platform Setup Script for WeChat Article Generator"
    echo ""
    echo "Usage: $0 [platform]"
    echo ""
    echo "Platforms:"
    echo "  cursor    - Setup Cursor IDE (skills + rules)"
    echo "  claude    - Setup Claude Code (CLAUDE.md)"
    echo "  copilot   - Setup GitHub Copilot (.github/copilot-instructions.md)"
    echo "  windsurf  - Setup Windsurf/Codeium (.windsurfrules)"
    echo "  aider     - Setup Aider (.aider.conf.yml)"
    echo "  all       - Setup all platforms"
    echo ""
    echo "Examples:"
    echo "  $0 cursor"
    echo "  $0 all"
}

# Main
main() {
    cd "$PROJECT_ROOT"
    
    case "${1:-}" in
        cursor)
            setup_agents
            setup_cursor
            ;;
        claude)
            setup_agents
            setup_claude
            ;;
        copilot)
            setup_agents
            setup_copilot
            ;;
        windsurf)
            setup_agents
            setup_windsurf
            ;;
        aider)
            setup_agents
            setup_aider
            ;;
        all)
            setup_agents
            setup_cursor
            setup_claude
            setup_copilot
            setup_windsurf
            setup_aider
            echo ""
            log_success "All platforms configured!"
            ;;
        --help|-h|"")
            show_help
            ;;
        *)
            echo "Unknown platform: $1"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

main "$@"
