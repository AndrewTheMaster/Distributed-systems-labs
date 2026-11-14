package sim

import (
	"testing"

	"github.com/AndrewTheMaster/Distributed-systems-labs/internal/engine"
)

func run(alg engine.Algorithm, nodes int, loss, fail float64, seed int64, maxMS int) engine.Result {
	return Run(Spec{
		Algorithm:     alg,
		Nodes:         nodes,
		Topology:      "random",
		Degree:        6,
		Loss:          loss,
		FailFraction:  fail,
		Seed:          seed,
		GroupFraction: 0.3,
		Fanout:        3,
		LatencyMS:     2,
		JitterMS:      2,
		MaxRounds:     60,
		RumorBudget:   15,
		MaxMS:         maxMS,
		TickMS:        5,
	})
}

func TestBroadcastConverges(t *testing.T) {
	out := run(engine.Broadcast, 120, 0, 0, 1, 3000)
	if !out.Converged {
		t.Fatalf("broadcast did not converge: coverage=%f p95=%f", out.CoverageIntended, out.DisseminationMS95)
	}
	if out.DisseminationMS95 <= 0 {
		t.Fatalf("broadcast p95 = %f", out.DisseminationMS95)
	}
}

func TestUnicastDeliversToSingleTarget(t *testing.T) {
	out := run(engine.Unicast, 120, 0, 0, 1, 1000)
	if out.Intended != 1 || out.CoverageIntended != 1 {
		t.Fatalf("unicast intended=%d coverage=%f", out.Intended, out.CoverageIntended)
	}
}

func TestMulticastDeliversToGroup(t *testing.T) {
	out := run(engine.Multicast, 120, 0, 0, 1, 1000)
	if out.Intended == 0 || out.CoverageIntended != 1 {
		t.Fatalf("multicast intended=%d coverage=%f", out.Intended, out.CoverageIntended)
	}
}

func TestGossipResilientToLossAndFailures(t *testing.T) {
	for _, alg := range []engine.Algorithm{engine.GossipPush, engine.GossipPull, engine.AntiEntropy} {
		t.Run(string(alg), func(t *testing.T) {
			for _, seed := range []int64{1, 2, 3} {
				out := run(alg, 120, 0.3, 0.2, seed, 8000)
				if out.CoverageIntended < 0.99 {
					t.Fatalf("seed %d: coverage=%f p95=%f sent=%d",
						seed, out.CoverageIntended, out.DisseminationMS95, out.MessagesSent)
				}
			}
		})
	}
}

func TestRumorConverges(t *testing.T) {
	out := run(engine.Rumor, 120, 0.2, 0.1, 1, 8000)
	if out.CoverageIntended < 0.99 {
		t.Fatalf("rumor coverage=%f", out.CoverageIntended)
	}
}

func TestTotalLossPreventsDissemination(t *testing.T) {
	out := run(engine.GossipPush, 120, 1.0, 0, 1, 1000)
	if out.InformedIntended != 0 {
		t.Fatalf("informed %d nodes under total loss", out.InformedIntended)
	}
	if out.CoverageIntended != 0 {
		t.Fatalf("coverage = %f under total loss", out.CoverageIntended)
	}
}
