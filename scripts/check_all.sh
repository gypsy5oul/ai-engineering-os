#!/usr/bin/env bash
# Everything CI runs, in the order CI runs it. Fails fast on the first problem,
# because a broken manifest makes every later result meaningless.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

step() { printf '\n\033[1m== %s\033[0m\n' "$1"; }

step "Plugin structure and cross-document consistency"
python3 scripts/validate_plugin.py

step "Schemas, policies and the shipped project template"
python3 scripts/validate_schemas.py
python3 scripts/validate_project_config.py templates/project/project.yaml

step "Stage contracts: definition-of-done grammar and model routing"
python3 scripts/check_dod.py --grammar
python3 scripts/resolve_model.py --all > /dev/null && echo "model routing resolves for every stage"

step "Department execution cycles"
python3 scripts/check_cycle.py

step "Notification routing"
python3 scripts/route_event.py --table > /dev/null && echo "routing table resolves for every event"

step "Documentation links"
python3 scripts/check_links.py

step "Secret scan"
python3 scripts/secret_scan.py .

step "Tests"
python3 -m unittest discover -s tests -q

step "End-to-end SDLC simulation"
python3 scripts/simulate_sdlc.py --all | tail -3

step "Deterministic evaluations"
python3 scripts/run_evaluations.py

step "Claude Code structural validation"
if command -v claude >/dev/null 2>&1; then
  # This repository is both a plugin and a marketplace. With marketplace.json
  # present, `claude plugin validate .` validates the *marketplace* manifest and
  # never looks at plugin.json. Validate the plugin from a copy without it.
  claude plugin validate .
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  cp -r .claude-plugin agents skills hooks policies schemas sdlc evaluations templates scripts "$tmp"/
  rm -f "$tmp/.claude-plugin/marketplace.json"
  claude plugin validate "$tmp"
else
  echo "claude CLI not found; skipped. Run 'claude plugin validate .' before proposing a change."
fi

printf '\n\033[1mAll checks passed.\033[0m\n'
