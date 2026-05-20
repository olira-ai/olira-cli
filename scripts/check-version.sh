#!/usr/bin/env bash

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🔍 Checking version consistency and changelog entry...${NC}"
echo "========================================================="

# Function to extract version from pyproject.toml
get_pyproject_version() {
    grep -E '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/' || echo ""
}

# Function to extract version from __init__.py (src layout)
get_init_version() {
    grep -E '^__version__ = ' src/olira_cli/__init__.py | sed 's/__version__ = "\(.*\)"/\1/' || echo ""
}

# Function to extract version from CHANGELOG.md
get_changelog_version() {
    # Try to find version in changelog - look for common formats:
    # ## [1.2.3] or ## 1.2.3 or ### [1.2.3] or ### 1.2.3
    if [ -f CHANGELOG.md ]; then
        grep -E '^## \[?[0-9]+\.[0-9]+\.[0-9]+' CHANGELOG.md | head -1 | sed -E 's/^## \[?([0-9]+\.[0-9]+\.[0-9]+(-[^]]+)?)\]?.*/\1/' || echo ""
    else
        echo ""
    fi
}

# Get versions
PYPROJECT_VERSION=$(get_pyproject_version)
INIT_VERSION=$(get_init_version)
CHANGELOG_VERSION=$(get_changelog_version)

echo ""
echo -e "${BLUE}📋 Found versions:${NC}"
echo "  - pyproject.toml: ${PYPROJECT_VERSION:-<not found>}"
echo "  - src/olira_cli/__init__.py: ${INIT_VERSION:-<not found>}"
echo "  - CHANGELOG.md: ${CHANGELOG_VERSION:-<not found>}"

# Check if versions were found
if [ -z "$PYPROJECT_VERSION" ]; then
    echo -e "${RED}❌ ERROR: Could not find version in pyproject.toml${NC}"
    exit 1
fi

if [ -z "$INIT_VERSION" ]; then
    echo -e "${RED}❌ ERROR: Could not find version in src/olira_cli/__init__.py${NC}"
    exit 1
fi

if [ -z "$CHANGELOG_VERSION" ]; then
    echo -e "${RED}❌ ERROR: Could not find version entry in CHANGELOG.md${NC}"
    echo -e "${RED}   Please add a changelog entry with format: '## [version]' or '## version'${NC}"
    exit 1
fi

# Check version consistency
echo ""
echo -e "${BLUE}🔍 Checking version consistency...${NC}"

if [ "$PYPROJECT_VERSION" != "$INIT_VERSION" ]; then
    echo -e "${RED}❌ ERROR: Version mismatch!${NC}"
    echo -e "${RED}   pyproject.toml: $PYPROJECT_VERSION${NC}"
    echo -e "${RED}   __init__.py: $INIT_VERSION${NC}"
    exit 1
fi

# Check if changelog version matches (allow for pre-release versions)
PYPROJECT_BASE=$(echo "$PYPROJECT_VERSION" | sed 's/-.*//')
CHANGELOG_BASE=$(echo "$CHANGELOG_VERSION" | sed 's/-.*//')

if [ "$PYPROJECT_BASE" != "$CHANGELOG_BASE" ]; then
    echo -e "${YELLOW}⚠️  WARNING: Changelog version ($CHANGELOG_VERSION) doesn't match project version ($PYPROJECT_VERSION)${NC}"
    echo -e "${YELLOW}   Base versions: $CHANGELOG_BASE vs $PYPROJECT_BASE${NC}"
fi

# Check if version has changed from base branch (if in CI or git is available)
if [ "${CI:-false}" = "true" ] && [ -n "${GITHUB_BASE_REF:-}" ]; then
    echo ""
    echo -e "${BLUE}🔍 Checking if version changed from base branch ($GITHUB_BASE_REF)...${NC}"

    BASE_VERSION=$(git show "origin/${GITHUB_BASE_REF}:pyproject.toml" 2>/dev/null | grep -E '^version = ' | sed 's/version = "\(.*\)"/\1/' || echo "")
    if [ -z "$BASE_VERSION" ]; then
        BASE_VERSION=$(git show "origin/${GITHUB_BASE_REF}:packages/olira-cli/pyproject.toml" 2>/dev/null | grep -E '^version = ' | sed 's/version = "\(.*\)"/\1/' || echo "")
    fi

    if [ -z "$BASE_VERSION" ]; then
        echo -e "${YELLOW}⚠️  Could not determine base branch version, skipping change check${NC}"
    elif [ "$PYPROJECT_VERSION" = "$BASE_VERSION" ]; then
        echo -e "${RED}❌ ERROR: Version has not been changed!${NC}"
        echo -e "${RED}   Current version: $PYPROJECT_VERSION${NC}"
        echo -e "${RED}   Base branch version: $BASE_VERSION${NC}"
        echo -e "${RED}   Please update the version in pyproject.toml, __init__.py, and add a CHANGELOG.md entry${NC}"
        exit 1
    else
        echo -e "${GREEN}✅ Version has been changed from $BASE_VERSION to $PYPROJECT_VERSION${NC}"
    fi
elif command -v git &> /dev/null && git rev-parse --git-dir &> /dev/null; then
    BASE_BRANCH=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@' || echo "main")
    BASE_VERSION=$(git show "origin/${BASE_BRANCH}:pyproject.toml" 2>/dev/null | grep -E '^version = ' | sed 's/version = "\(.*\)"/\1/' || echo "")
    if [ -z "$BASE_VERSION" ]; then
        BASE_VERSION=$(git show "origin/${BASE_BRANCH}:packages/olira-cli/pyproject.toml" 2>/dev/null | grep -E '^version = ' | sed 's/version = "\(.*\)"/\1/' || echo "")
    fi

    if [ -n "$BASE_VERSION" ] && [ "$PYPROJECT_VERSION" = "$BASE_VERSION" ]; then
        echo ""
        echo -e "${YELLOW}⚠️  WARNING: Version matches base branch ($BASE_BRANCH) version: $BASE_VERSION${NC}"
        echo -e "${YELLOW}   Consider updating the version if this is a new release${NC}"
    elif [ -n "$BASE_VERSION" ]; then
        echo ""
        echo -e "${GREEN}✅ Version changed from $BASE_VERSION to $PYPROJECT_VERSION${NC}"
    fi
fi

# Final summary
echo ""
echo -e "${GREEN}✅ Version check passed!${NC}"
echo -e "${GREEN}   All versions are consistent: $PYPROJECT_VERSION${NC}"
if [ -n "$CHANGELOG_VERSION" ]; then
    echo -e "${GREEN}   Changelog entry found: $CHANGELOG_VERSION${NC}"
fi
