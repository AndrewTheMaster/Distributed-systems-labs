package engine

import (
	"fmt"
	"math/rand"
	"sort"
)

func NodeIDs(n int) []string {
	out := make([]string, n)
	for i := 0; i < n; i++ {
		out[i] = fmt.Sprintf("n%03d", i)
	}
	return out
}

func NodeID(i int) string { return fmt.Sprintf("n%03d", i) }

// Topology builds a symmetric adjacency list. Supported names: random, ring,
// full. random starts from a ring (so it is always connected) and then adds
// random edges until every node has at least the requested degree.
func Topology(name string, n, degree int, rng *rand.Rand) map[string][]string {
	ids := NodeIDs(n)
	switch name {
	case "full":
		return fullGraph(ids)
	case "ring":
		return ringGraph(ids, degree)
	default:
		return randomGraph(ids, degree, rng)
	}
}

func newAdj(ids []string) map[string]map[string]struct{} {
	adj := make(map[string]map[string]struct{}, len(ids))
	for _, id := range ids {
		adj[id] = make(map[string]struct{})
	}
	return adj
}

func addEdge(adj map[string]map[string]struct{}, a, b string) {
	if a == b {
		return
	}
	adj[a][b] = struct{}{}
	adj[b][a] = struct{}{}
}

// toList converts adjacency sets to sorted slices. Sorting matters: map
// iteration order in Go is random, and neighbour order decides which peers
// a seeded RNG selects, so without sorting runs are not reproducible.
func toList(ids []string, adj map[string]map[string]struct{}) map[string][]string {
	out := make(map[string][]string, len(ids))
	for _, id := range ids {
		peers := make([]string, 0, len(adj[id]))
		for peer := range adj[id] {
			peers = append(peers, peer)
		}
		sort.Strings(peers)
		out[id] = peers
	}
	return out
}

func randomGraph(ids []string, degree int, rng *rand.Rand) map[string][]string {
	if degree < 2 {
		degree = 2
	}
	if degree > len(ids)-1 {
		degree = len(ids) - 1
	}
	adj := newAdj(ids)
	for i := range ids {
		addEdge(adj, ids[i], ids[(i+1)%len(ids)])
	}
	for _, id := range ids {
		attempts := 0
		for len(adj[id]) < degree && attempts < len(ids)*8 {
			attempts++
			peer := ids[rng.Intn(len(ids))]
			addEdge(adj, id, peer)
		}
	}
	return toList(ids, adj)
}

func ringGraph(ids []string, degree int) map[string][]string {
	if degree < 2 {
		degree = 2
	}
	if degree > len(ids)-1 {
		degree = len(ids) - 1
	}
	adj := newAdj(ids)
	half := degree / 2
	for i := range ids {
		for d := 1; d <= half; d++ {
			addEdge(adj, ids[i], ids[(i+d)%len(ids)])
			addEdge(adj, ids[i], ids[(i-d+len(ids))%len(ids)])
		}
	}
	return toList(ids, adj)
}

func fullGraph(ids []string) map[string][]string {
	adj := newAdj(ids)
	for i := range ids {
		for j := i + 1; j < len(ids); j++ {
			addEdge(adj, ids[i], ids[j])
		}
	}
	return toList(ids, adj)
}

// PickGroup returns a random subset that does not contain origin.
func PickGroup(ids []string, origin string, fraction float64, rng *rand.Rand) []string {
	candidates := make([]string, 0, len(ids))
	for _, id := range ids {
		if id != origin {
			candidates = append(candidates, id)
		}
	}
	k := int(float64(len(ids))*fraction + 0.5)
	if k < 1 {
		k = 1
	}
	if k > len(candidates) {
		k = len(candidates)
	}
	rng.Shuffle(len(candidates), func(i, j int) { candidates[i], candidates[j] = candidates[j], candidates[i] })
	return append([]string(nil), candidates[:k]...)
}

// PickFailed returns a random subset of nodes that does not contain origin.
func PickFailed(ids []string, origin string, fraction float64, rng *rand.Rand) []string {
	candidates := make([]string, 0, len(ids))
	for _, id := range ids {
		if id != origin {
			candidates = append(candidates, id)
		}
	}
	k := int(float64(len(ids))*fraction + 0.5)
	if k < 0 {
		k = 0
	}
	if k > len(candidates) {
		k = len(candidates)
	}
	rng.Shuffle(len(candidates), func(i, j int) { candidates[i], candidates[j] = candidates[j], candidates[i] })
	return append([]string(nil), candidates[:k]...)
}

func PickOne(ids []string, exclude string, rng *rand.Rand) string {
	if len(ids) <= 1 {
		return ""
	}
	for {
		id := ids[rng.Intn(len(ids))]
		if id != exclude {
			return id
		}
	}
}

func SetOf(items []string) map[string]bool {
	out := make(map[string]bool, len(items))
	for _, item := range items {
		out[item] = true
	}
	return out
}
