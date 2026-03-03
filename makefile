SHELL := /bin/bash

PACKAGE_SLUG=beenative
PYTHON_VERSION := $(shell cat .python-version)
PYTHON_SHORT_VERSION := $(shell echo $(PYTHON_VERSION) | grep -o '[0-9].[0-9]*')

# Detect OS
# We check if apt-get exists and if the OS-release file contains "debian" or "ubuntu"
IS_DEBIAN := $(shell command -v apt-get >/dev/null 2>&1 && grep -E 'debian|ubuntu' /etc/os-release >/dev/null 2>&1 && echo yes || echo no)
# Detect OS
UNAME_S := $(shell uname -s)


ifeq ($(USE_SYSTEM_PYTHON), true)
	PYTHON_PACKAGE_PATH:=$(shell python -c "import sys; print(sys.path[-1])")
	PYTHON_ENV :=
	PYTHON := python
	PYTHON_VENV :=
	UV := uv
else
	PYTHON_PACKAGE_PATH:=.venv/lib/python$(PYTHON_SHORT_VERSION)/site-packages
	PYTHON_ENV :=  . .venv/bin/activate &&
	PYTHON := . .venv/bin/activate && python
	PYTHON_VENV := .venv
	UV := uv
endif

# Used to confirm that uv has run at least once
PACKAGE_CHECK:=$(PYTHON_PACKAGE_PATH)/build
PYTHON_DEPS := $(PACKAGE_CHECK)


.PHONY: all
all: $(PACKAGE_CHECK)

.PHONY: install
install: install-deps sync-python

.PHONY: sync-python
sync-python:
	@echo "--- Syncing Python dependencies ---"
	VIRTUAL_ENV=$(PYTHON_VENV) uv sync

.PHONY: install-deps
install-deps:
ifeq ($(UNAME_S),Linux)
    @echo "--- Linux detected. Installing apt dependencies ---"
    ifeq ($(IS_DEBIAN),yes)
		@echo "--- Debian-based Linux detected. Installing system dependencies ---"
		sudo apt update --allow-releaseinfo-change
		sudo apt-get install -y --no-install-recommends \
			clang ninja-build libgtk-3-dev libasound2-dev libmpv-dev mpv \
			libcairo2-dev libffi-dev libjpeg-dev \
			libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev libgstreamer-plugins-bad1.0-dev \
			gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly \
			gstreamer1.0-libav gstreamer1.0-tools gstreamer1.0-x gstreamer1.0-alsa gstreamer1.0-gl gstreamer1.0-gtk3 \
			gstreamer1.0-qt5 gstreamer1.0-pulseaudio pkg-config libsecret-1-0 libsecret-1-dev
		sudo apt-get clean
	else
		@echo "--- Skipping system dependencies: Not a Debian-based Linux system ---"
	endif
endif
ifeq ($(UNAME_S),Darwin)
    @echo "--- macOS detected. Installing Homebrew dependencies ---"
    brew install libjpeg libtiff little-cms2 openjpeg webp
endif

.venv:
	$(UV) venv --python $(PYTHON_VERSION)

.PHONY: uv
uv:
	@command -v uv >/dev/null 2>&1 || { echo >&2 "uv is not installed. Installing via pip..."; pip install uv; }

.PHONY: sync
sync: $(PYTHON_VENV) uv.lock
	$(UV) sync --group dev

$(PACKAGE_CHECK): $(PYTHON_VENV) uv.lock
	$(UV) sync --group dev

uv.lock: pyproject.toml
	$(UV) lock

.PHONY: pre-commit
pre-commit:
	pre-commit install

#
# Formatting
#
.PHONY: chores
chores: ruff_fixes black_fixes dapperdata_fixes tomlsort_fixes document_schema

.PHONY: ruff_fixes
ruff_fixes:
	$(UV) run ruff check . --fix

.PHONY: black_fixes
black_fixes:
	$(UV) run ruff format .

.PHONY: dapperdata_fixes
dapperdata_fixes:
	$(UV) run python -m dapperdata.cli pretty . --no-dry-run

.PHONY: tomlsort_fixes
tomlsort_fixes:
	$(PYTHON_ENV) tombi format $$(find . -not -path "./.venv/*" -name "*.toml")

#
# Testing
#
.PHONY: tests
tests: install pytest ruff_check black_check mypy_check dapperdata_check tomlsort_check paracelsus_check

.PHONY: pytest
pytest:
	$(UV) run pytest --cov=./${PACKAGE_SLUG} --cov-report=term-missing tests

.PHONY: pytest_loud
pytest_loud:
	$(UV) run pytest --log-cli-level=DEBUG -log_cli=true --cov=./${PACKAGE_SLUG} --cov-report=term-missing tests

.PHONY: ruff_check
ruff_check:
	$(UV) run ruff check

.PHONY: black_check
black_check:
	$(UV) run ruff format . --check

.PHONY: mypy_check
mypy_check:
	$(UV) run mypy ${PACKAGE_SLUG}

.PHONY: dapperdata_check
dapperdata_check:
	$(UV) run python -m dapperdata.cli pretty .

.PHONY: tomlsort_check
tomlsort_check:
	$(UV) run tombi lint $$(find . -not -path "./.venv/*" -name "*.toml")
	$(UV) run tombi format $$(find . -not -path "./.venv/*" -name "*.toml") --check



#
# Dependencies
#

.PHONY: lock
lock:
	$(UV) lock --upgrade

.PHONY: lock-check
lock-check:
	$(UV) lock --check


#
# Packaging
#

.PHONY: build
build: $(PACKAGE_CHECK)
	$(UV) run python -m build

#
# Database
#

.PHONY: document_schema
document_schema:
	$(UV) run python -m paracelsus.cli inject docs/dev/database.md $(PACKAGE_SLUG).models.base:Base --import-module "$(PACKAGE_SLUG).models:*"

.PHONY: paracelsus_check
paracelsus_check:
	$(UV) run python -m paracelsus.cli inject docs/dev/database.md $(PACKAGE_SLUG).models.base:Base --import-module "$(PACKAGE_SLUG).models:*" --check

.PHONY: check_ungenerated_migrations
check_ungenerated_migrations:
	$(UV) run alembic -c ./beenative/assets/alembic.ini check
