package engine

import (
	"math/rand"
	"testing"
)

func TestTopologiesConnected(t *testing.T) {
	for _, name := range []string{"random", "ring", "full"} {
		t.Run(name, func(t *testing.T) {
			ids := NodeIDs(100)
			adj := Topology(name, 100, 6, rand.New(rand.NewSource(7)))
			seen := map[string]bool{ids[0]: true}
			queue := []string{ids[0]}
			for len(queue) > 0 {
				cur := queue[0]
				queue = queue[1:]
				for _, peer := range adj[cur] {
					if !seen[peer] {
						seen[peer] = true
						queue = append(queue, peer)
					}
				}
			}
			if len(seen) != len(ids) {
				t.Fatalf("graph is not connected: reached %d of %d", len(seen), len(ids))
			}
			for _, id := range ids {
				if len(adj[id]) < 2 {
					t.Fatalf("%s has degree %d", id, len(adj[id]))
				}
			}
		})
	}
}

func TestPickGroupAndFailuresExcludeOrigin(t *testing.T) {
	ids := NodeIDs(50)
	rng := rand.New(rand.NewSource(3))
	group := PickGroup(ids, ids[0], 0.3, rng)
	if len(group) != 15 {
		t.Fatalf("group size = %d, want 15", len(group))
	}
	for _, id := range group {
		if id == ids[0] {
			t.Fatal("group contains origin")
		}
	}
	failed := PickFailed(ids, ids[0], 0.2, rng)
	for _, id := range failed {
		if id == ids[0] {
			t.Fatal("failed set contains origin")
		}
	}
}
