package sim

import (
	"container/heap"
	"fmt"
	"math/rand"

	"github.com/AndrewTheMaster/Distributed-systems-labs/internal/engine"
)

type Spec struct {
	ExperimentID     string
	Algorithm        engine.Algorithm
	Nodes            int
	Topology         string
	Degree           int
	Loss             float64
	FailFraction     float64
	FailAtMS         int
	Seed             int64
	GroupFraction    float64
	Fanout           int
	LatencyMS        int
	JitterMS         int
	GossipIntervalMS int
	MaxRounds        int
	RumorBudget      int
	MaxMS            int
	TickMS           int
}

func (s *Spec) Normalize() {
	if s.Nodes < 2 {
		s.Nodes = 2
	}
	if s.Topology == "" {
		s.Topology = "random"
	}
	if s.Degree <= 0 {
		s.Degree = 6
	}
	if s.GroupFraction <= 0 || s.GroupFraction >= 1 {
		s.GroupFraction = 0.3
	}
	if s.Fanout <= 0 {
		s.Fanout = 3
	}
	if s.LatencyMS < 0 {
		s.LatencyMS = 0
	}
	if s.JitterMS < 0 {
		s.JitterMS = 0
	}
	if s.GossipIntervalMS <= 0 {
		s.GossipIntervalMS = 100
	}
	if s.MaxRounds <= 0 {
		s.MaxRounds = 60
	}
	if s.RumorBudget <= 0 {
		s.RumorBudget = 15
	}
	if s.MaxMS <= 0 {
		s.MaxMS = 8000
	}
	if s.TickMS <= 0 {
		s.TickMS = 10
	}
	if s.FailFraction < 0 {
		s.FailFraction = 0
	}
	if s.FailFraction > 1 {
		s.FailFraction = 1
	}
}

type Outcome struct {
	Result   engine.Result
	Timeline []engine.TimelinePoint
}

type event struct {
	at     int64
	to     string
	packet engine.Packet
}

type eventQueue []*event

func (q eventQueue) Len() int            { return len(q) }
func (q eventQueue) Less(i, j int) bool  { return q[i].at < q[j].at }
func (q eventQueue) Swap(i, j int)       { q[i], q[j] = q[j], q[i] }
func (q *eventQueue) Push(x interface{}) { *q = append(*q, x.(*event)) }
func (q *eventQueue) Pop() interface{} {
	old := *q
	n := len(old)
	item := old[n-1]
	old[n-1] = nil
	*q = old[:n-1]
	return item
}

// Run executes one complete in-memory experiment.
func Run(spec Spec) Outcome {
	spec.Normalize()
	rng := rand.New(rand.NewSource(spec.Seed))
	ids := engine.NodeIDs(spec.Nodes)
	origin := ids[0]
	adj := engine.Topology(spec.Topology, spec.Nodes, spec.Degree, rng)
	group := engine.PickGroup(ids, origin, spec.GroupFraction, rng)
	failedAtStart := engine.PickFailed(ids, origin, spec.FailFraction, rng)
	if spec.FailAtMS > 0 {
		// Crash experiment: nodes are healthy at t=0 and fail later.
		failedAtStart = nil
	}
	failedAtStartSet := engine.SetOf(failedAtStart)

	aliveAtStart := make([]string, 0, len(ids))
	for _, id := range ids {
		if !failedAtStartSet[id] && id != origin {
			aliveAtStart = append(aliveAtStart, id)
		}
	}

	var failedLater []string
	if spec.FailAtMS > 0 {
		failedLater = engine.PickFailed(ids, origin, spec.FailFraction, rng)
	}
	failedLaterSet := engine.SetOf(failedLater)

	unicastTarget := ""
	for tries := 0; tries < 1000; tries++ {
		candidate := engine.PickOne(ids, origin, rng)
		if candidate != "" && !failedAtStartSet[candidate] && !failedLaterSet[candidate] {
			unicastTarget = candidate
			break
		}
	}

	var now int64
	var q eventQueue
	heap.Init(&q)
	nowFn := func() int64 { return now }
	sendFn := func(to string, p engine.Packet) error {
		delay := int64(spec.LatencyMS)
		if spec.JitterMS > 0 {
			delay += int64(rng.Intn(spec.JitterMS + 1))
		}
		heap.Push(&q, &event{at: now + delay, to: to, packet: p})
		return nil
	}

	nodes := make(map[string]*engine.Engine, len(ids))
	for i, id := range ids {
		cfg := engine.Config{
			NodeID:           id,
			Algorithm:        spec.Algorithm,
			Neighbors:        adj[id],
			Group:            group,
			Loss:             spec.Loss,
			LatencyMS:        spec.LatencyMS,
			JitterMS:         spec.JitterMS,
			Fanout:           spec.Fanout,
			GossipIntervalMS: spec.GossipIntervalMS,
			MaxRounds:        spec.MaxRounds,
			RumorBudget:      spec.RumorBudget,
			TTL:              64,
			UnicastTarget:    unicastTarget,
			Seed:             spec.Seed*100003 + int64(i+1),
		}
		nodes[id] = engine.New(cfg, sendFn, nowFn)
	}

	for _, id := range failedAtStart {
		nodes[id].SetFailed(true)
	}

	startedAt := int64(0)
	expID := spec.ExperimentID
	if expID == "" {
		expID = fmt.Sprintf("sim-%s-l%.2f-f%.2f-s%d", spec.Algorithm, spec.Loss, spec.FailFraction, spec.Seed)
	}
	msgID := "m-" + expID
	req := engine.StartRequest{
		ExperimentID: expID,
		MessageID:    msgID,
		Origin:       origin,
		StartedAt:    startedAt,
		Payload:      "dissemination-payload-" + expID,
	}
	for _, id := range ids {
		nodes[id].Start(req)
	}

	crashed := false
	tick := int64(spec.TickMS)
	maxMS := int64(spec.MaxMS)
	for now = 0; now <= maxMS; now += tick {
		for q.Len() > 0 && q[0].at <= now {
			ev := heap.Pop(&q).(*event)
			if n := nodes[ev.to]; n != nil {
				n.Handle(ev.packet)
			}
		}
		if spec.FailAtMS > 0 && !crashed && now >= int64(spec.FailAtMS) {
			for _, id := range failedLater {
				nodes[id].SetFailed(true)
			}
			crashed = true
		}
		for _, id := range ids {
			nodes[id].Tick(now)
		}
		if spec.Algorithm == engine.Broadcast || spec.Algorithm == engine.Unicast || spec.Algorithm == engine.Multicast {
			if q.Len() == 0 && now > 0 {
				break
			}
		}
		if (spec.FailAtMS == 0 || now >= int64(spec.FailAtMS)) &&
			allInformed(nodes, intendedIDs(spec.Algorithm, ids, origin, group, failedAtStartSet, unicastTarget)) {
			break
		}
	}

	states := make(map[string]engine.State, len(ids))
	for _, id := range ids {
		states[id] = nodes[id].Snapshot()
	}
	intended := intendedIDs(spec.Algorithm, ids, origin, group, failedAtStartSet, unicastTarget)
	groupSize := 0
	if spec.Algorithm == engine.Multicast {
		groupSize = len(group)
	}
	result := engine.ComputeResult(engine.ResultInput{
		Mode:         "sim",
		ExperimentID: expID,
		Algorithm:    spec.Algorithm,
		Nodes:        len(ids),
		Topology:     spec.Topology,
		Degree:       spec.Degree,
		Loss:         spec.Loss,
		FailFraction: spec.FailFraction,
		FailAtMS:     spec.FailAtMS,
		Seed:         spec.Seed,
		GroupSize:    groupSize,
		AliveNodes:   len(aliveAtStart) + 1,
		Intended:     intended,
		Origin:       origin,
		IDs:          ids,
		States:       states,
		StartedAt:    startedAt,
	})
	timeline := engine.BuildTimeline(intended, states, startedAt, spec.MaxMS)
	return Outcome{Result: result, Timeline: timeline}
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

func allInformed(nodes map[string]*engine.Engine, intended []string) bool {
	for _, id := range intended {
		if n := nodes[id]; n == nil || !n.Informed() {
			return false
		}
	}
	return true
}
