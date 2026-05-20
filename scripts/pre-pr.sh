#!/usr/bin/env bash

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}Running pre-PR validation for olira-cli...${NC}"
echo "================================================"

echo ""
echo -e "${BLUE}Step 0: Install dependencies...${NC}"
bash scripts/uv.sh sync --frozen --extra dev

echo ""
echo -e "${BLUE}Step 1: Version consistency...${NC}"
bash scripts/check-version.sh

echo ""
echo -e "${BLUE}Step 2: Lint...${NC}"
bash scripts/lint.sh

echo ""
echo -e "${BLUE}Step 3: Tests...${NC}"
bash scripts/test.sh

echo ""
echo -e "${GREEN}All pre-PR checks passed.${NC}"
