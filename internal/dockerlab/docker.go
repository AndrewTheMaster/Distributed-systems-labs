package dockerlab

import (
	"bytes"
	"encoding/csv"
	"encoding/json"
	"fmt"
	"io"
	"math/rand"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/AndrewTheMaster/Distributed-systems-labs/internal/agent"
	"github.com/AndrewTheMaster/Distributed-systems-labs/internal/engine"
)

type Options struct {
	ProjectDir    string
	Image         string
	Network       string
	Prefix        string
	Nodes         int
	BasePort      int
	Build         bool
	Keep          bool
	Reuse         bool
	Fresh         bool
	Out           string
	Algorithms    []string
	Losses        []float64
	Fails         []float64
	Seeds         []int64
	Topology      string
	Degree        int
	GroupFraction float64
	Fanout        int
	GossipMs      int
	MaxRounds     int
	RumorBudget   int
	MaxMS         int
	StartDelayMS  int
	PollMS        int
	CrashFraction float64
	CrashAtMS     int
}

func (o *Options) normalize() {
	if o.ProjectDir == "" {
		o.ProjectDir = "."
	}
	if o.Image == "" {
		o.Image = "ds-lab-node:latest"
	}
	if o.Network == "" {
		o.Network = "dslab-net"
	}
	if o.Prefix == "" {
		o.Prefix = "dslab"
	}
	if o.Nodes < 2 {
		o.Nodes = 110
	}
	if o.BasePort == 0 {
		o.BasePort = 18000
	}
	if o.Out == "" {
		o.Out = "results/docker_main.csv"
	}
	if len(o.Algorithms) == 0 {
		for _, a := range engine.AllAlgorithms() {
			o.Algorithms = append(o.Algorithms, string(a))
		}
	}
	if len(o.Losses) == 0 {
		o.Losses = []float64{0, 0.2, 0.4}
	}
	if len(o.Fails) == 0 {
		o.Fails = []float64{0, 0.2}
	}
	if len(o.Seeds) == 0 {
		o.Seeds = []int64{1}
	}
	if o.Topology == "" {
		o.Topology = "random"
	}
	if o.Degree <= 0 {
		o.Degree = 6
	}
	if o.GroupFraction <= 0 || o.GroupFraction >= 1 {
		o.GroupFraction = 0.3
	}
	if o.Fanout <= 0 {
		o.Fanout = 3
	}
	if o.GossipMs <= 0 {
		o.GossipMs = 100
	}
	if o.MaxRounds <= 0 {
		o.MaxRounds = 60
	}
	if o.RumorBudget <= 0 {
		o.RumorBudget = 15
	}
	if o.MaxMS <= 0 {
		o.MaxMS = 8000
	}
	if o.StartDelayMS <= 0 {
		o.StartDelayMS = 1200
	}
	if o.PollMS <= 0 {
		o.PollMS = 75
	}
	if o.CrashFraction < 0 {
		o.CrashFraction = 0
	}
}

func Run(opts Options) error {
	opts.normalize()
	if _, err := exec.LookPath("docker"); err != nil {
		return fmt.Errorf("docker CLI not found: %w", err)
	}
	if _, err := dockerOutput("version", "--format", "{{.Server.Version}}"); err != nil {
		return fmt.Errorf("docker daemon is not available: %w", err)
	}
	names := namesFor(opts)
	var ips []string
	startAll := func() error {
		runID := fmt.Sprintf("%d", time.Now().UnixNano())
		var err error
		names, err = startContainers(opts, runID)
		if err != nil {
			return err
		}
		if err := waitHealthy(opts); err != nil {
			return err
		}
		ips, err = containerIPs(names)
		if err != nil {
			return fmt.Errorf("container IP discovery: %w", err)
		}
		return nil
	}
	if !opts.Reuse {
		if opts.Build {
			fmt.Printf("building image %s\n", opts.Image)
			if out, err := dockerOutput("build", "-t", opts.Image, opts.ProjectDir); err != nil {
				return fmt.Errorf("docker build: %w\n%s", err, out)
			}
		}
		if err := ensureNetwork(opts.Network); err != nil {
			return err
		}
		if err := startAll(); err != nil {
			cleanup(names)
			return err
		}
		if !opts.Keep {
			defer cleanup(names)
			defer dockerIgnore("network", "rm", opts.Network)
		}
	}
	if opts.Reuse {
		fmt.Printf("reusing running containers\n")
		if err := waitHealthy(opts); err != nil {
			return err
		}
		var err error
		ips, err = containerIPs(names)
		if err != nil {
			return fmt.Errorf("container IP discovery: %w", err)
		}
	}
	if err := os.MkdirAll(filepath.Dir(opts.Out), 0o755); err != nil {
		return err
	}
	f, err := os.Create(opts.Out)
	if err != nil {
		return err
	}
	defer f.Close()
	w := csv.NewWriter(f)
	defer w.Flush()
	if err := writeHeader(w); err != nil {
		return err
	}

	ports := make([]int, opts.Nodes)
	for i := range ports {
		ports[i] = opts.BasePort + i
	}

	total := len(opts.Algorithms) * len(opts.Losses) * len(opts.Fails) * len(opts.Seeds)
	done := 0
	for _, alg := range opts.Algorithms {
		for _, loss := range opts.Losses {
			for _, fail := range opts.Fails {
				for _, seed := range opts.Seeds {
					done++
					expID := fmt.Sprintf("docker-%s-l%.2f-f%.2f-s%d", alg, loss, fail, seed)
					fmt.Printf("[%d/%d] %s nodes=%d\n", done, total, expID, opts.Nodes)
					if opts.Fresh && !opts.Reuse {
						if err := startAll(); err != nil {
							return fmt.Errorf("%s: restart: %w", expID, err)
						}
					}
					res, err := runOne(opts, engine.ParseAlgorithm(alg), loss, fail, seed, ports, ips, expID)
					if err != nil {
						return fmt.Errorf("%s: %w", expID, err)
					}
					if err := writeRow(w, res); err != nil {
						return err
					}
					w.Flush()
					fmt.Printf("    coverage=%.3f p95=%.0fms sent=%d dropped=%d\n",
						res.CoverageIntended, res.DisseminationMS95, res.MessagesSent, res.Dropped)
				}
			}
		}
	}
	return nil
}

func runOne(opts Options, alg engine.Algorithm, loss, fail float64, seed int64, ports []int, ips []string, expID string) (engine.Result, error) {
	rng := rand.New(rand.NewSource(seed))
	ids := engine.NodeIDs(opts.Nodes)
	origin := ids[0]
	adj := engine.Topology(opts.Topology, opts.Nodes, opts.Degree, rng)
	group := engine.PickGroup(ids, origin, opts.GroupFraction, rng)
	failedStart := engine.PickFailed(ids, origin, fail, rng)
	if opts.CrashAtMS > 0 {
		failedStart = nil
	}
	failedSet := engine.SetOf(failedStart)
	var crash []string
	crashSet := map[string]bool{}
	if opts.CrashAtMS > 0 {
		crash = engine.PickFailed(ids, origin, opts.CrashFraction, rng)
		crashSet = engine.SetOf(crash)
	}
	unicastTarget := ""
	for tries := 0; tries < 1000; tries++ {
		candidate := engine.PickOne(ids, origin, rng)
		if candidate != "" && !failedSet[candidate] && !crashSet[candidate] {
			unicastTarget = candidate
			break
		}
	}
	allNodes := make(map[string]string, opts.Nodes)
	for i := 0; i < opts.Nodes; i++ {
		if i < len(ips) && ips[i] != "" {
			allNodes[engine.NodeID(i)] = ips[i] + ":9000"
		} else {
			allNodes[engine.NodeID(i)] = fmt.Sprintf("node-%03d:9000", i)
		}
	}

	if err := parallel(opts.Nodes, func(i int) error {
		return post(ports[i], "/reset", nil)
	}); err != nil {
		return engine.Result{}, err
	}
	if err := parallel(opts.Nodes, func(i int) error {
		id := engine.NodeID(i)
		cfg := engine.Config{
			NodeID:           id,
			Algorithm:        alg,
			AllNodes:         allNodes,
			Neighbors:        adj[id],
			Group:            group,
			Loss:             loss,
			Fanout:           opts.Fanout,
			GossipIntervalMS: opts.GossipMs,
			MaxRounds:        opts.MaxRounds,
			RumorBudget:      opts.RumorBudget,
			TTL:              64,
			UnicastTarget:    unicastTarget,
			Seed:             seed*100003 + int64(i+1),
		}
		return post(ports[i], "/config", cfg)
	}); err != nil {
		return engine.Result{}, err
	}
	for _, id := range failedStart {
		if err := post(ports[indexOf(id)], "/fail", map[string]bool{"failed": true}); err != nil {
			return engine.Result{}, err
		}
	}

	kernelBefore, err := kernelTotals(ports)
	if err != nil {
		return engine.Result{}, err
	}
	startedAt := time.Now().UnixMilli() + int64(opts.StartDelayMS)
	msgID := "m-" + expID
	startReq := engine.StartRequest{
		ExperimentID: expID,
		MessageID:    msgID,
		Origin:       origin,
		StartedAt:    startedAt,
		Payload:      "dissemination-payload-" + expID,
	}
	if err := parallel(opts.Nodes, func(i int) error {
		return post(ports[i], "/start", startReq)
	}); err != nil {
		return engine.Result{}, err
	}

	intended := intendedIDs(alg, ids, origin, group, failedSet, unicastTarget)
	deadline := startedAt + int64(opts.MaxMS)
	crashDone := false
	for time.Now().UnixMilli() <= deadline {
		now := time.Now().UnixMilli()
		if opts.CrashAtMS > 0 && !crashDone && now >= startedAt+int64(opts.CrashAtMS) {
			for _, id := range crash {
				_ = post(ports[indexOf(id)], "/fail", map[string]bool{"failed": true})
			}
			crashDone = true
		}
		states, err := collectStates(ports)
		if err != nil {
			return engine.Result{}, err
		}
		if allInformed(states, intended) {
			break
		}
		time.Sleep(time.Duration(opts.PollMS) * time.Millisecond)
	}
	states, err := collectStates(ports)
	if err != nil {
		return engine.Result{}, err
	}
	kernelAfter, err := kernelTotals(ports)
	if err != nil {
		return engine.Result{}, err
	}
	alive := len(ids) - len(failedStart)
	groupSize := 0
	if alg == engine.Multicast {
		groupSize = len(group)
	}
	res := engine.ComputeResult(engine.ResultInput{
		Mode:         "docker",
		ExperimentID: expID,
		Algorithm:    alg,
		Nodes:        opts.Nodes,
		Topology:     opts.Topology,
		Degree:       opts.Degree,
		Loss:         loss,
		FailFraction: fail,
		FailAtMS:     opts.CrashAtMS,
		Seed:         seed,
		GroupSize:    groupSize,
		AliveNodes:   alive,
		Intended:     intended,
		Origin:       origin,
		IDs:          ids,
		States:       states,
		StartedAt:    startedAt,
	})
	res.KernelOut = kernelAfter.OutDatagrams - kernelBefore.OutDatagrams
	res.KernelIn = kernelAfter.InDatagrams - kernelBefore.InDatagrams
	res.KernelSndbufErr = kernelAfter.SndbufErrors - kernelBefore.SndbufErrors
	res.KernelRcvbufErr = kernelAfter.RcvbufErrors - kernelBefore.RcvbufErrors
	return res, nil
}

func kernelTotals(ports []int) (agent.KernelUDP, error) {
	var mu sync.Mutex
	var total agent.KernelUDP
	err := parallel(len(ports), func(i int) error {
		resp, err := client.Get(fmt.Sprintf("http://127.0.0.1:%d/kernel", ports[i]))
		if err != nil {
			return err
		}
		defer resp.Body.Close()
		var k agent.KernelUDP
		if err := json.NewDecoder(resp.Body).Decode(&k); err != nil {
			return err
		}
		mu.Lock()
		total.OutDatagrams += k.OutDatagrams
		total.InDatagrams += k.InDatagrams
		total.SndbufErrors += k.SndbufErrors
		total.RcvbufErrors += k.RcvbufErrors
		total.InErrors += k.InErrors
		mu.Unlock()
		return nil
	})
	return total, err
}

func intendedIDs(alg engine.Algorithm, ids []string, origin string, group []string, failed map[string]bool, unicastTarget string) []string {
	switch alg {
	case engine.Unicast:
		if unicastTarget == "" {
			return nil
		}
		return []string{unicastTarget}
	case engine.Multicast:
		out := make([]string, 0, len(group))
		for _, id := range group {
			if id != origin && !failed[id] {
				out = append(out, id)
			}
		}
		return out
	default:
		out := make([]string, 0, len(ids))
		for _, id := range ids {
			if id != origin && !failed[id] {
				out = append(out, id)
			}
		}
		return out
	}
}

func allInformed(states map[string]engine.State, intended []string) bool {
	for _, id := range intended {
		if !states[id].Informed {
			return false
		}
	}
	return true
}

func indexOf(id string) int {
	n, _ := strconv.Atoi(strings.TrimPrefix(id, "n"))
	return n
}

func collectStates(ports []int) (map[string]engine.State, error) {
	out := make(map[string]engine.State, len(ports))
	var mu sync.Mutex
	if err := parallel(len(ports), func(i int) error {
		st, err := getState(ports[i])
		if err != nil {
			return err
		}
		mu.Lock()
		out[st.NodeID] = st
		mu.Unlock()
		return nil
	}); err != nil {
		return nil, err
	}
	return out, nil
}

var client = &http.Client{Timeout: 4 * time.Second}

func post(port int, path string, body interface{}) error {
	var r io.Reader
	if body != nil {
		b, err := json.Marshal(body)
		if err != nil {
			return err
		}
		r = bytes.NewReader(b)
	}
	req, err := http.NewRequest(http.MethodPost, fmt.Sprintf("http://127.0.0.1:%d%s", port, path), r)
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode/100 != 2 {
		b, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("%s: %s: %s", path, resp.Status, string(b))
	}
	return nil
}

func getState(port int) (engine.State, error) {
	var st engine.State
	resp, err := client.Get(fmt.Sprintf("http://127.0.0.1:%d/state", port))
	if err != nil {
		return st, err
	}
	defer resp.Body.Close()
	if resp.StatusCode/100 != 2 {
		return st, fmt.Errorf("state: %s", resp.Status)
	}
	err = json.NewDecoder(resp.Body).Decode(&st)
	return st, err
}

func parallel(n int, fn func(i int) error) error {
	var wg sync.WaitGroup
	errs := make(chan error, n)
	for i := 0; i < n; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			if err := fn(i); err != nil {
				errs <- err
			}
		}(i)
	}
	wg.Wait()
	close(errs)
	for err := range errs {
		if err != nil {
			return err
		}
	}
	return nil
}

func ensureNetwork(name string) error {
	if out, err := dockerOutput("network", "inspect", name); err == nil {
		_ = out
		return nil
	}
	if out, err := dockerOutput("network", "create", name); err != nil {
		return fmt.Errorf("network create: %w\n%s", err, out)
	}
	return nil
}

func namesFor(opts Options) []string {
	names := make([]string, opts.Nodes)
	for i := range names {
		names[i] = fmt.Sprintf("%s-node-%03d", opts.Prefix, i)
	}
	return names
}

func startContainers(opts Options, runID string) ([]string, error) {
	names := make([]string, 0, opts.Nodes)
	for i := 0; i < opts.Nodes; i++ {
		name := fmt.Sprintf("%s-node-%03d", opts.Prefix, i)
		host := fmt.Sprintf("node-%03d", i)
		port := opts.BasePort + i
		dockerIgnore("rm", "-f", name)
		args := []string{
			"run", "-d",
			"--name", name,
			"--network", opts.Network,
			"--hostname", host,
			"-p", fmt.Sprintf("127.0.0.1:%d:8080", port),
			"--label", "ds-lab=node",
			"--label", "ds-lab-run=" + runID,
			"-e", "NODE_ID=" + engine.NodeID(i),
			"-e", "DATA_ADDR=:9000",
			"-e", "CONTROL_ADDR=:8080",
			"-e", "GOSSIP_SEED=" + strconv.FormatInt(int64(i+1), 10),
			opts.Image,
		}
		if out, err := dockerOutput(args...); err != nil {
			return names, fmt.Errorf("start %s: %w\n%s", name, err, out)
		}
		names = append(names, name)
		if i%20 == 19 {
			fmt.Printf("  started %d/%d containers\n", i+1, opts.Nodes)
		}
	}
	return names, nil
}

func containerIPs(names []string) ([]string, error) {
	ips := make([]string, len(names))
	err := parallel(len(names), func(i int) error {
		out, err := dockerOutput("inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}", names[i])
		if err != nil {
			return err
		}
		ips[i] = strings.TrimSpace(out)
		if ips[i] == "" {
			return fmt.Errorf("empty IP for %s", names[i])
		}
		return nil
	})
	return ips, err
}

func waitHealthy(opts Options) error {
	deadline := time.Now().Add(4 * time.Minute)
	for {
		ok := true
		for i := 0; i < opts.Nodes; i++ {
			port := opts.BasePort + i
			if !healthy(port) {
				ok = false
				break
			}
		}
		if ok {
			return nil
		}
		if time.Now().After(deadline) {
			return fmt.Errorf("containers did not become healthy in time")
		}
		time.Sleep(500 * time.Millisecond)
	}
}

func healthy(port int) bool {
	resp, err := client.Get(fmt.Sprintf("http://127.0.0.1:%d/health", port))
	if err != nil {
		return false
	}
	defer resp.Body.Close()
	return resp.StatusCode == http.StatusOK
}

func cleanup(names []string) {
	var wg sync.WaitGroup
	for _, name := range names {
		wg.Add(1)
		go func(name string) {
			defer wg.Done()
			dockerIgnore("rm", "-f", name)
		}(name)
	}
	wg.Wait()
}

func dockerOutput(args ...string) (string, error) {
	cmd := exec.Command("docker", args...)
	var buf bytes.Buffer
	cmd.Stdout = &buf
	cmd.Stderr = &buf
	err := cmd.Run()
	return buf.String(), err
}

func dockerIgnore(args ...string) {
	_, _ = dockerOutput(args...)
}

func writeHeader(w *csv.Writer) error {
	t := reflect.TypeOf(engine.Result{})
	header := make([]string, 0, t.NumField())
	for i := 0; i < t.NumField(); i++ {
		header = append(header, t.Field(i).Tag.Get("csv"))
	}
	return w.Write(header)
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
