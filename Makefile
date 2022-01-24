#!/bin/bash
#
# Copyright (c) 2020 Dell Inc., or its subsidiaries. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0

export BUILDER=docker
export REGISTRY=tssgery
export IMAGENAME=pmm-dizquetv
export IMAGETAG=latest


# Help target, prints usefule information
help:
	@echo
	@echo "The following targets are commonly used:"
	@echo
	@echo "docker           - Builds the gateway containiner image"
	@echo "push             - Pushes the built container to a target registry"
	@echo

# -- general targets
# Generates the docker container
docker:
	$(BUILDER) build -t $(REGISTRY)/$(IMAGENAME):$(IMAGETAG) .
	@echo "Built $(REGISTRY)/$(IMAGENAME):$(IMAGETAG) "

# Pushes container to the repository
push:	docker
ifeq ($(REGISTRY),)
	@echo "No push necessary, local image"
else
	$(BUILDER) push  $(REGISTRY)/$(IMAGENAME):$(IMAGETAG)
	@echo "Pushed  $(REGISTRY)/$(IMAGENAME):$(IMAGETAG)"
endif

## --

