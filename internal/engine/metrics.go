package engine

import (
	"math"
	"sort"
)

type ResultInput struct {
	Mode         string
	ExperimentID string
	Algorithm    Algorithm
	Nodes        int
	Topology     string
	Degree       int
	Loss         float64
	FailFraction float64
	FailAtMS     int
	Seed         int64
	GroupSize    int
	AliveNodes   int
	Intended     []string
	Origin       string
	IDs          []string
	States       map[string]State
	StartedAt    int64
}

func ComputeResult(in ResultInput) Result {
	informedIntended := 0
	times := make([]int64, 0, len(in.Intended))
	var sent, received, duplicates, dropped, sendErrors, ignored, datagrams int64
	latest := in.StartedAt
	for _, id := range in.IDs {
		st := in.States[id]
		sent += st.Stats.Sent
		received += st.Stats.Received
		duplicates += st.Stats.Duplicates
		dropped += st.Stats.Dropped
		sendErrors += st.Stats.SendErrors
		ignored += st.Stats.Ignored
		datagrams += st.Stats.Datagrams
		if st.Informed && st.FirstSeen > latest {
			latest = st.FirstSeen
		}
	}
	for _, id := range in.Intended {
		st := in.States[id]
		if st.Informed {
			informedIntended++
			times = append(times, st.FirstSeen)
		}
	}
	sort.Slice(times, func(i, j int) bool { return times[i] < times[j] })

	coverageIntended := 0.0
	if len(in.Intended) > 0 {
		coverageIntended = float64(informedIntended) / float64(len(in.Intended))
	}
	informedAll := 0
	for _, id := range in.IDs {
		if id != in.Origin && in.States[id].Informed {
			informedAll++
		}
	}
	coverageTotal := 0.0
	if len(in.IDs) > 1 {
		coverageTotal = float64(informedAll) / float64(len(in.IDs)-1)
	}
	elapsed := float64(latest - in.StartedAt)
	if elapsed < 0 {
		elapsed = 0
	}
	return Result{
		Mode:               in.Mode,
		ExperimentID:       in.ExperimentID,
		Algorithm:          string(in.Algorithm),
		Nodes:              in.Nodes,
		Topology:           in.Topology,
		Degree:             in.Degree,
		Loss:               in.Loss,
		FailFraction:       in.FailFraction,
		FailAtMS:           in.FailAtMS,
		Seed:               in.Seed,
		GroupSize:          in.GroupSize,
		AliveNodes:         in.AliveNodes,
		Intended:           len(in.Intended),
		InformedIntended:   informedIntended,
		CoverageIntended:   coverageIntended,
		CoverageTotal:      coverageTotal,
		DisseminationMS50:  thresholdTime(times, len(in.Intended), 0.50, in.StartedAt),
		DisseminationMS90:  thresholdTime(times, len(in.Intended), 0.90, in.StartedAt),
		DisseminationMS95:  thresholdTime(times, len(in.Intended), 0.95, in.StartedAt),
		DisseminationMS99:  thresholdTime(times, len(in.Intended), 0.99, in.StartedAt),
		DisseminationMS100: thresholdTime(times, len(in.Intended), 1.00, in.StartedAt),
		MessagesSent:       sent,
		MessagesReceived:   received,
		Duplicates:         duplicates,
		Dropped:            dropped,
		SendErrors:         sendErrors,
		Ignored:            ignored,
		Datagrams:          datagrams,
		ElapsedMS:          elapsed,
		Converged:          coverageIntended >= 0.999,
		TimedOut:           coverageIntended < 0.999,
	}
}

func thresholdTime(times []int64, intended int, q float64, startedAt int64) float64 {
	if intended <= 0 {
		return 0
	}
	target := int(math.Ceil(q * float64(intended)))
	if target < 1 {
		target = 1
	}
	if len(times) < target {
		return -1
	}
	return float64(times[target-1] - startedAt)
}

type TimelinePoint struct {
	TimeMS   int     `json:"time_ms"`
	Coverage float64 `json:"coverage"`
}

func BuildTimeline(intended []string, states map[string]State, startedAt int64, maxMS int) []TimelinePoint {
	if len(intended) == 0 {
		return nil
	}
	times := make([]int64, 0, len(intended))
	for _, id := range intended {
		if st := states[id]; st.Informed {
			times = append(times, st.FirstSeen-startedAt)
		}
	}
	sort.Slice(times, func(i, j int) bool { return times[i] < times[j] })
	step := 50
	if maxMS < step {
		step = 10
	}
	out := make([]TimelinePoint, 0, maxMS/step+1)
	idx := 0
	for t := 0; t <= maxMS; t += step {
		for idx < len(times) && times[idx] <= int64(t) {
			idx++
		}
		out = append(out, TimelinePoint{TimeMS: t, Coverage: float64(idx) / float64(len(intended))})
	}
	return out
}
