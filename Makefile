SHELL := /bin/bash
GO ?= go
PY ?= python3

.PHONY: build test vet fmt sim sim-main sim-topology sim-scale sim-crash \
	docker-build docker figures report all full clean

build:
	mkdir -p bin
	$(GO) build -trimpath -o bin/node ./cmd/node
	$(GO) build -trimpath -o bin/lab ./cmd/lab

test:
	$(GO) test ./...

vet:
	$(GO) vet ./...

fmt:
	gofmt -w cmd internal

sim: sim-main sim-topology sim-scale sim-crash

sim-main:
	$(GO) run ./cmd/lab sim -nodes 120 -topology random -degree 6 \
		-losses 0,0.1,0.2,0.3,0.5 -fails 0,0.1,0.2,0.3 -seeds 5 \
		-out results/sim_main.csv -timeline-out results/timeline.csv

sim-topology:
	$(GO) run ./cmd/lab sim -nodes 120 -topologies random,ring,full \
		-algorithms broadcast,gossip_push,gossip_pull,anti_entropy \
		-losses 0.1 -fails 0.1 -seeds 3 -out results/sim_topology.csv

sim-scale:
	$(GO) run ./cmd/lab sim -node-list 50,100,200,400 \
		-algorithms broadcast,gossip_push,anti_entropy \
		-losses 0.1 -fails 0.1 -seeds 3 -out results/sim_scale.csv

sim-crash:
	$(GO) run ./cmd/lab sim -nodes 120 \
		-algorithms broadcast,gossip_push,gossip_pull,anti_entropy \
		-losses 0.2 -fails 0.2 -fail-at-ms 500 -seeds 3 -out results/sim_crash.csv

docker-build:
	docker build -t ds-lab-node:latest .

docker:
	$(GO) run ./cmd/lab docker -nodes 110 -build -fresh \
		-algorithms unicast,multicast,broadcast,gossip_push,gossip_pull,rumor_mongering,anti_entropy \
		-losses 0,0.2,0.4 -fails 0,0.2 -seeds 2 -max-ms 8000 \
		-out results/docker_main.csv

figures:
	$(PY) scripts/analyze.py

report: figures
	$(PY) scripts/build_report.py

all: test sim figures report

full: test sim docker figures report

clean:
	rm -rf bin
	$(GO) run ./cmd/lab clean
