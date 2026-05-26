PYTHON ?= python3

.PHONY: test stage-image

test:
PYTHONPATH=. $(PYTHON) -m unittest discover -s tests -v

stage-image:
./scripts/build-image-layout.sh out/stage
