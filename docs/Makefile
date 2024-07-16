# Minimal makefile for Sphinx documentation
# shellcheck disable=all

# You can set these variables from the command line, and also
# from the environment for the first two.
SPHINXOPTS    ?=
SPHINXBUILD   ?= sphinx-build
SOURCEDIR     = ./source
BUILDDIR      = ./_build

# Put it first so that "make" without argument is like "make help".
help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

.PHONY: help Makefile

# Catch-all target: route all unknown targets to Sphinx using the new
# "make mode" option.  $(O) is meant as a shortcut for $(SPHINXOPTS).
%: Makefile
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

## —— All 🎵 ———————————————————————————————————————————————————————————————
.PHONY: all
all: clean

## —— Clean Sphinx 🧹🐳💩 ———————————————————————————————————————————————————————————————
.PHONY: clean-sphinx
clean-sphinx:
	@echo "=> Cleaning sphinx..."

## —— Clean 🧹 ———————————————————————————————————————————————————————————————
.PHONY: clean
clean: clean-sphinx

## —— Doc 📜 —————————————————————————————————————————————————————————————————
.PHONY: doc
doc: ## Documentation
	@echo "=> Doc..."
	sphinx-build ./source _build --color -W -bhtml

## —— Tests 🧪 —————————————————————————————————————————————————————————————————
.PHONY: test
test:
	@echo "=> Testing sphinx..."
