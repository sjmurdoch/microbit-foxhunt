# Micro:bit Fox Hunt -- build, test and flash.
#
# There is nothing to compile: MicroPython runs source directly. "Building"
# here means checking the code parses and passes its tests before it goes near
# a board.
#
# Flashing goes through flash.py rather than `ufs` directly -- see the comment
# at the top of that file for why a plain `ufs put` is not safe on these boards.

PY     ?= uv run python
PYTEST ?= uv run pytest

DEVICE_SRC := fox.py hound.py hound_logic.py radio_config.py
HOST_SRC   := flash.py calibrate.py integration_check.py test_hound.py test_flash.py

# Single-board targets accept PORT=; it is only required when two boards are
# attached, since flash.py autodetects a lone board.
PORT_ARG := $(if $(PORT),--port $(PORT),)

.DEFAULT_GOAL := help
.PHONY: help build test check devices flash flash-fox flash-hound calibrate integration clean

help: ## Show this help
	@echo "Micro:bit Fox Hunt"
	@echo
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-16s %s\n", $$1, $$2}'
	@echo
	@echo "Flashing two boards (run 'make devices' first):"
	@echo "  make flash FOX_PORT=/dev/cu.usbmodemAAAA HOUND_PORT=/dev/cu.usbmodemBBBB"
	@echo "  make flash-hound PORT=/dev/cu.usbmodemBBBB"

build: check ## Alias for check (MicroPython needs no compile step)

check: ## Parse every source file, then run the tests
	$(PY) -m compileall -q $(DEVICE_SRC) $(HOST_SRC)
	$(PYTEST)

test: ## Run the unit tests
	$(PYTEST)

devices: ## List attached micro:bits, with firmware version
	$(PY) flash.py list

flash-fox: check ## Flash the fox (PORT= if two boards attached)
	$(PY) flash.py fox $(PORT_ARG)

flash-hound: check ## Flash the hound, both files (PORT= if two boards attached)
	$(PY) flash.py hound $(PORT_ARG)

flash: check ## Flash both boards; needs FOX_PORT and HOUND_PORT
	@if [ -z "$(FOX_PORT)" ] || [ -z "$(HOUND_PORT)" ]; then \
	  echo "Two boards cannot be told apart automatically."; \
	  echo "Run 'make devices', then:"; \
	  echo "  make flash FOX_PORT=<port> HOUND_PORT=<port>"; \
	  exit 1; \
	fi
	$(PY) flash.py fox --port $(FOX_PORT)
	$(PY) flash.py hound --port $(HOUND_PORT)

calibrate: ## Field-calibrate MIN_RSSI/MAX_RSSI (run outdoors, see AGENTS.md)
	$(PY) calibrate.py $(PORT_ARG)

integration: ## Radio round-trip check across two attached boards
	$(PY) integration_check.py

clean: ## Remove caches and scratch files
	rm -rf __pycache__ .pytest_cache .flash_verify.tmp
	find . -name '*.pyc' -not -path './.venv/*' -delete
