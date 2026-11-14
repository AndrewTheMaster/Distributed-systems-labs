package main

import (
	"encoding/csv"
	"flag"
	"fmt"
	"os"
	"os/exec"
	"reflect"
	"strconv"
	"strings"

	"github.com/AndrewTheMaster/Distributed-systems-labs/internal/dockerlab"
	"github.com/AndrewTheMaster/Distributed-systems-labs/internal/engine"
	"github.com/AndrewTheMaster/Distributed-systems-labs/internal/sim"
)

func main() {
	if len(os.Args) < 2 {
		usage()
		os.Exit(2)
	}
	switch os.Args[1] {
	case "sim":
		runSim(os.Args[2:])
	case "docker":
		runDocker(os.Args[2:])
	case "clean":
		cleanDocker()
	default:
		usage()
		os.Exit(2)
	}
}

func usage() {
	fmt.Fprintf(os.Stderr, `distributed-systems lab

Usage:
  lab sim      run in-memory experiments and write CSV
  lab docker   run experiments on real Docker containers
  lab clean    remove ds-lab containers and network

Run "lab sim -h" or "lab docker -h" for flags.
`)
}

func runSim(args []string) {
	fs := flag.NewFlagSet("sim", flag.ExitOnError)
	nodes := fs.Int("nodes", 120, "number of logical nodes")
	nodeList := fs.String("node-list", "", "comma-separated node counts (overrides -nodes)")
	topology := fs.String("topology", "random", "topology: random|ring|full")
	topologyList := fs.String("topologies", "", "comma-separated topologies (overrides -topology)")
	degree := fs.Int("degree", 6, "target graph degree")
	losses := fs.String("losses", "0,0.1,0.2,0.3,0.5", "comma-separated packet loss probabilities")
	fails := fs.String("fails", "0,0.1,0.2,0.3", "comma-separated failed-node fractions")
	algorithms := fs.String("algorithms", "", "comma-separated algorithms; empty = all")
	seeds := fs.Int("seeds", 5, "number of seeds (1..N)")
	seedList := fs.String("seed-list", "", "comma-separated seeds (overrides -seeds)")
	groupFrac := fs.Float64("group-frac", 0.3, "multicast group fraction")
	fanout := fs.Int("fanout", 3, "gossip fanout")
	latency := fs.Int("latency-ms", 5, "one-hop latency")
	jitter := fs.Int("jitter-ms", 5, "extra one-hop latency jitter")
	gossipMs := fs.Int("gossip-ms", 100, "gossip interval")
	maxRounds := fs.Int("max-rounds", 60, "maximum periodic rounds")
	rumorBudget := fs.Int("rumor-budget", 15, "rumor mongering budget")
	maxMS := fs.Int("max-ms", 8000, "experiment timeout")
	tickMS := fs.Int("tick-ms", 10, "simulation tick")
	failAtMS := fs.Int("fail-at-ms", 0, "crash nodes at this time (0 = fail at start)")
	out := fs.String("out", "results/sim_main.csv", "CSV output")
	timelineOut := fs.String("timeline-out", "", "optional timeline CSV output")
	timelineAlgos := fs.String("timeline-algos", "broadcast,gossip_push,anti_entropy", "algorithms for timeline CSV")
	timelineLoss := fs.Float64("timeline-loss", 0.2, "loss for timeline CSV")
	timelineFail := fs.Float64("timeline-fail", 0.1, "failure fraction for timeline CSV")
	_ = fs.Parse(args)

	algList := engine.AllAlgorithms()
	if *algorithms != "" {
		algList = algList[:0]
		for _, a := range split(*algorithms) {
			algList = append(algList, engine.ParseAlgorithm(a))
		}
	}
	lossList := parseFloats(*losses)
	failList := parseFloats(*fails)
	seedValues := parseSeeds(*seeds, *seedList)
	topoList := []string{*topology}
	if *topologyList != "" {
		topoList = split(*topologyList)
	}
	nodeValues := []int{*nodes}
	if *nodeList != "" {
		nodeValues = parseInts(*nodeList)
	}
	timelineSet := map[string]bool{}
	for _, a := range split(*timelineAlgos) {
		timelineSet[string(engine.ParseAlgorithm(a))] = true
	}

	f, err := os.Create(*out)
	if err != nil {
		fatal(err)
	}
	defer f.Close()
	w := csv.NewWriter(f)
	defer w.Flush()
	writeHeader(w)

	var tl *csv.Writer
	if *timelineOut != "" {
		if err := os.MkdirAll(dirOf(*timelineOut), 0o755); err != nil {
			fatal(err)
		}
		tf, err := os.Create(*timelineOut)
		if err != nil {
			fatal(err)
		}
		defer tf.Close()
		tl = csv.NewWriter(tf)
		defer tl.Flush()
		_ = tl.Write([]string{"algorithm", "seed", "loss", "fail_fraction", "time_ms", "coverage"})
	}

	total := len(algList) * len(lossList) * len(failList) * len(seedValues) * len(topoList) * len(nodeValues)
	done := 0
	for _, n := range nodeValues {
		for _, topo := range topoList {
			for _, alg := range algList {
				for _, loss := range lossList {
					for _, fail := range failList {
						for _, seed := range seedValues {
							done++
							expID := fmt.Sprintf("sim-%s-%s-n%d-l%.2f-f%.2f-s%d", topo, alg, n, loss, fail, seed)
							fmt.Printf("[%d/%d] %s\n", done, total, expID)
							outcome := sim.Run(sim.Spec{
								ExperimentID:     expID,
								Algorithm:        alg,
								Nodes:            n,
								Topology:         topo,
								Degree:           *degree,
								Loss:             loss,
								FailFraction:     fail,
								FailAtMS:         *failAtMS,
								Seed:             seed,
								GroupFraction:    *groupFrac,
								Fanout:           *fanout,
								LatencyMS:        *latency,
								JitterMS:         *jitter,
								GossipIntervalMS: *gossipMs,
								MaxRounds:        *maxRounds,
								RumorBudget:      *rumorBudget,
								MaxMS:            *maxMS,
								TickMS:           *tickMS,
							})
							if err := writeRow(w, outcome.Result); err != nil {
								fatal(err)
							}
							w.Flush()
							if tl != nil && timelineSet[string(alg)] && topo == "random" && n == 120 &&
								loss == *timelineLoss && fail == *timelineFail && seed == seedValues[0] {
								for _, p := range outcome.Timeline {
									_ = tl.Write([]string{
										string(alg),
										strconv.FormatInt(seed, 10),
										strconv.FormatFloat(loss, 'f', 2, 64),
										strconv.FormatFloat(fail, 'f', 2, 64),
										strconv.Itoa(p.TimeMS),
										strconv.FormatFloat(p.Coverage, 'f', 4, 64),
									})
								}
							}
						}
					}
				}
			}
		}
	}
	fmt.Printf("wrote %s\n", *out)
}

func runDocker(args []string) {
	fs := flag.NewFlagSet("docker", flag.ExitOnError)
	nodes := fs.Int("nodes", 110, "number of containers")
	image := fs.String("image", "ds-lab-node:latest", "Docker image")
	network := fs.String("network", "dslab-net", "Docker network")
	prefix := fs.String("prefix", "dslab", "container name prefix")
	basePort := fs.Int("base-port", 18000, "first published control port")
	build := fs.Bool("build", false, "build the image before starting")
	keep := fs.Bool("keep", false, "keep containers after the run")
	reuse := fs.Bool("reuse", false, "reuse already running healthy containers")
	fresh := fs.Bool("fresh", false, "recreate containers before every experiment")
	topology := fs.String("topology", "random", "topology: random|ring|full")
	degree := fs.Int("degree", 6, "target graph degree")
	losses := fs.String("losses", "0,0.2,0.4", "comma-separated packet loss probabilities")
	fails := fs.String("fails", "0,0.2", "comma-separated failed-node fractions")
	algorithms := fs.String("algorithms", "", "comma-separated algorithms; empty = all")
	seeds := fs.Int("seeds", 1, "number of seeds (1..N)")
	seedList := fs.String("seed-list", "", "comma-separated seeds")
	groupFrac := fs.Float64("group-frac", 0.3, "multicast group fraction")
	fanout := fs.Int("fanout", 3, "gossip fanout")
	gossipMs := fs.Int("gossip-ms", 100, "gossip interval")
	maxRounds := fs.Int("max-rounds", 60, "maximum periodic rounds")
	rumorBudget := fs.Int("rumor-budget", 15, "rumor mongering budget")
	maxMS := fs.Int("max-ms", 8000, "experiment timeout")
	startDelay := fs.Int("start-delay-ms", 1200, "delay used to arm all nodes")
	pollMS := fs.Int("poll-ms", 75, "state polling interval")
	crashFraction := fs.Float64("crash-fraction", 0, "fraction of nodes crashed during run")
	crashAtMS := fs.Int("crash-at-ms", 0, "crash time (0 = disabled)")
	projectDir := fs.String("project-dir", ".", "project directory for docker build")
	out := fs.String("out", "results/docker_main.csv", "CSV output")
	_ = fs.Parse(args)

	algList := engine.AllAlgorithms()
	if *algorithms != "" {
		algList = algList[:0]
		for _, a := range split(*algorithms) {
			algList = append(algList, engine.ParseAlgorithm(a))
		}
	}
	err := dockerlab.Run(dockerlab.Options{
		ProjectDir:    *projectDir,
		Image:         *image,
		Network:       *network,
		Prefix:        *prefix,
		Nodes:         *nodes,
		BasePort:      *basePort,
		Build:         *build,
		Keep:          *keep,
		Reuse:         *reuse,
		Fresh:         *fresh,
		Out:           *out,
		Algorithms:    algorithmsToStrings(algList),
		Losses:        parseFloats(*losses),
		Fails:         parseFloats(*fails),
		Seeds:         parseSeeds(*seeds, *seedList),
		Topology:      *topology,
		Degree:        *degree,
		GroupFraction: *groupFrac,
		Fanout:        *fanout,
		GossipMs:      *gossipMs,
		MaxRounds:     *maxRounds,
		RumorBudget:   *rumorBudget,
		MaxMS:         *maxMS,
		StartDelayMS:  *startDelay,
		PollMS:        *pollMS,
		CrashFraction: *crashFraction,
		CrashAtMS:     *crashAtMS,
	})
	if err != nil {
		fatal(err)
	}
	fmt.Printf("wrote %s\n", *out)
}

func cleanDocker() {
	cmd := exec.Command("docker", "ps", "-aq", "--filter", "label=ds-lab=node")
	out, err := cmd.Output()
	if err == nil {
		ids := strings.Fields(string(out))
		if len(ids) > 0 {
			args := append([]string{"rm", "-f"}, ids...)
			_ = exec.Command("docker", args...).Run()
			fmt.Printf("removed %d containers\n", len(ids))
		}
	}
	_ = exec.Command("docker", "network", "rm", "dslab-net").Run()
}

func writeHeader(w *csv.Writer) {
	t := reflect.TypeOf(engine.Result{})
	header := make([]string, 0, t.NumField())
	for i := 0; i < t.NumField(); i++ {
		header = append(header, t.Field(i).Tag.Get("csv"))
	}
	_ = w.Write(header)
}

func writeRow(w *csv.Writer, r engine.Result) error {
	v := reflect.ValueOf(r)
	t := v.Type()
	row := make([]string, 0, t.NumField())
	for i := 0; i < t.NumField(); i++ {
		row = append(row, fmt.Sprint(v.Field(i).Interface()))
	}
	return w.Write(row)
}

func split(s string) []string {
	if strings.TrimSpace(s) == "" {
		return nil
	}
	parts := strings.Split(s, ",")
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		p = strings.TrimSpace(p)
		if p != "" {
			out = append(out, p)
		}
	}
	return out
}

func parseFloats(s string) []float64 {
	var out []float64
	for _, p := range split(s) {
		v, err := strconv.ParseFloat(p, 64)
		if err != nil {
			fatal(fmt.Errorf("bad float %q: %w", p, err))
		}
		out = append(out, v)
	}
	return out
}

func parseInts(s string) []int {
	var out []int
	for _, p := range split(s) {
		v, err := strconv.Atoi(p)
		if err != nil {
			fatal(fmt.Errorf("bad int %q: %w", p, err))
		}
		out = append(out, v)
	}
	return out
}

func parseSeeds(count int, list string) []int64 {
	if list != "" {
		var out []int64
		for _, p := range split(list) {
			v, err := strconv.ParseInt(p, 10, 64)
			if err != nil {
				fatal(fmt.Errorf("bad seed %q: %w", p, err))
			}
			out = append(out, v)
		}
		return out
	}
	out := make([]int64, 0, count)
	for i := 1; i <= count; i++ {
		out = append(out, int64(i))
	}
	return out
}

func algorithmsToStrings(algs []engine.Algorithm) []string {
	out := make([]string, len(algs))
	for i, a := range algs {
		out[i] = string(a)
	}
	return out
}

func dirOf(path string) string {
	i := strings.LastIndex(path, "/")
	if i <= 0 {
		return "."
	}
	return path[:i]
}

func fatal(err error) {
	fmt.Fprintln(os.Stderr, "error:", err)
	os.Exit(1)
}
