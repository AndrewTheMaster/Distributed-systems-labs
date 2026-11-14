package engine

import (
	"math/rand"
	"sync"
	"time"
)

// SendFunc delivers one already-serialized application packet to a peer.
// A non-nil error is counted as a send error and usually means the peer address
// could not be resolved or the UDP socket rejected the datagram.
type SendFunc func(to string, p Packet) error

// Engine is the transport-independent dissemination state machine. The same
// code is used by the in-memory simulator and by the Docker UDP agent.
type Engine struct {
	mu   sync.Mutex
	cfg  Config
	rng  *rand.Rand
	send SendFunc
	now  func() int64

	active    bool
	initiated bool
	failed    bool
	expID     string
	msgID     string
	origin    string
	payload   string
	startedAt int64

	informed  bool
	firstSeen int64
	stats     Stats

	rounds       int
	budget       int
	lastPeriodic int64
}

func New(cfg Config, send SendFunc, now func() int64) *Engine {
	if now == nil {
		now = func() int64 { return time.Now().UnixMilli() }
	}
	seed := cfg.Seed
	if seed == 0 {
		seed = time.Now().UnixNano()
	}
	return &Engine{
		cfg:  cloneConfig(cfg),
		rng:  rand.New(rand.NewSource(seed)),
		send: send,
		now:  now,
	}
}

func cloneConfig(c Config) Config {
	out := c
	out.AllNodes = make(map[string]string, len(c.AllNodes))
	for k, v := range c.AllNodes {
		out.AllNodes[k] = v
	}
	out.Neighbors = append([]string(nil), c.Neighbors...)
	out.Group = append([]string(nil), c.Group...)
	return out
}

func (e *Engine) SetConfig(c Config) {
	e.mu.Lock()
	defer e.mu.Unlock()
	e.cfg = cloneConfig(c)
	seed := c.Seed
	if seed == 0 {
		seed = time.Now().UnixNano()
	}
	e.rng = rand.New(rand.NewSource(seed))
}

func (e *Engine) Config() Config {
	e.mu.Lock()
	defer e.mu.Unlock()
	return cloneConfig(e.cfg)
}

func (e *Engine) Reset() {
	e.mu.Lock()
	defer e.mu.Unlock()
	e.active = false
	e.initiated = false
	e.failed = false
	e.expID = ""
	e.msgID = ""
	e.origin = ""
	e.payload = ""
	e.startedAt = 0
	e.informed = false
	e.firstSeen = 0
	e.stats = Stats{}
	e.rounds = 0
	e.budget = 0
	e.lastPeriodic = 0
}

func (e *Engine) SetFailed(failed bool) {
	e.mu.Lock()
	defer e.mu.Unlock()
	e.failed = failed
}

func (e *Engine) Failed() bool {
	e.mu.Lock()
	defer e.mu.Unlock()
	return e.failed
}

// Start arms the local state machine. It must be called on every node. Only
// the node whose ID equals req.Origin starts the actual dissemination.
func (e *Engine) Start(req StartRequest) {
	e.mu.Lock()
	defer e.mu.Unlock()
	e.active = true
	e.initiated = false
	e.expID = req.ExperimentID
	e.msgID = req.MessageID
	e.origin = req.Origin
	e.payload = req.Payload
	e.startedAt = req.StartedAt
	e.rounds = 0
	e.budget = 0
	e.lastPeriodic = 0
	if e.cfg.NodeID != req.Origin {
		return
	}
	e.informed = true
	e.firstSeen = req.StartedAt
}

func (e *Engine) initiateLocked() {
	switch e.cfg.Algorithm {
	case Unicast:
		if e.cfg.UnicastTarget != "" && e.cfg.UnicastTarget != e.cfg.NodeID {
			e.sendDataLocked(e.cfg.UnicastTarget)
		}
	case Multicast:
		for _, id := range e.cfg.Group {
			if id != e.cfg.NodeID {
				e.sendDataLocked(id)
			}
		}
	case Broadcast:
		for _, id := range e.cfg.Neighbors {
			if id != e.cfg.NodeID {
				e.sendDataLocked(id)
			}
		}
		e.stats.Forwarded++
	case GossipPush:
		e.lastPeriodic = e.now()
		e.pushLocked(e.now())
	case Rumor:
		e.budget = e.cfg.RumorBudget
		e.lastPeriodic = e.now()
		e.pushLocked(e.now())
	case GossipPull, AntiEntropy:
		// Uninformed nodes pull/digest from Tick; the origin will also
		// participate in anti-entropy and answer pulls.
	}
}

func (e *Engine) Handle(p Packet) {
	e.mu.Lock()
	defer e.mu.Unlock()
	e.stats.Datagrams++
	if e.failed {
		return
	}
	if !e.active || p.ExperimentID != e.expID || e.now() < e.startedAt {
		// Packet arrived before this node was armed for the experiment
		// (or from another experiment). It is discarded, but counted so that
		// the cause of missing deliveries can be measured.
		e.stats.Ignored++
		return
	}
	e.stats.Received++
	switch p.Type {
	case PacketData:
		e.onDataLocked(p)
	case PacketPull:
		e.onPullLocked(p)
	case PacketDigest:
		e.onDigestLocked(p)
	case PacketStale:
		e.onStaleLocked(p)
	}
}

func (e *Engine) onDataLocked(p Packet) {
	if e.informed {
		e.stats.Duplicates++
		if e.cfg.Algorithm == Rumor && p.Sender != "" {
			e.sendPacketLocked(p.Sender, Packet{Type: PacketStale})
		}
		return
	}
	e.informed = true
	e.firstSeen = e.now()
	switch e.cfg.Algorithm {
	case Broadcast:
		e.stats.Forwarded++
		for _, id := range e.cfg.Neighbors {
			if id != e.cfg.NodeID && id != p.Sender {
				e.sendDataLocked(id)
			}
		}
	case GossipPush:
		e.rounds = 0
		e.lastPeriodic = e.now()
		e.pushLocked(e.now())
	case Rumor:
		e.rounds = 0
		e.budget = e.cfg.RumorBudget
		e.lastPeriodic = e.now()
		e.pushLocked(e.now())
	case Multicast, GossipPull, AntiEntropy, Unicast:
		// No proactive forwarding.
	}
}

func (e *Engine) onPullLocked(p Packet) {
	if e.informed {
		e.sendDataLocked(p.Sender)
	}
}

func (e *Engine) onDigestLocked(p Packet) {
	if p.Has && !e.informed {
		e.sendPacketLocked(p.Sender, Packet{Type: PacketPull})
		e.stats.Forwarded++
		return
	}
	if !p.Has && e.informed {
		e.sendDataLocked(p.Sender)
		e.stats.Forwarded++
	}
}

func (e *Engine) onStaleLocked(_ Packet) {
	if e.cfg.Algorithm != Rumor {
		return
	}
	if e.budget > 0 {
		e.budget--
	}
}

func (e *Engine) Tick(now int64) {
	e.mu.Lock()
	defer e.mu.Unlock()
	if e.failed || !e.active {
		return
	}
	if now < e.startedAt {
		return
	}
	if !e.initiated {
		e.initiated = true
		if e.cfg.NodeID == e.origin {
			e.initiateLocked()
		}
	}
	interval := int64(e.cfg.GossipIntervalMS)
	if interval <= 0 {
		interval = 100
	}
	if now-e.lastPeriodic < interval {
		return
	}
	switch e.cfg.Algorithm {
	case GossipPush:
		if e.informed && e.rounds < e.cfg.MaxRounds {
			e.pushLocked(now)
		}
	case Rumor:
		if e.informed && e.rounds < e.cfg.MaxRounds && e.budget > 0 {
			e.pushLocked(now)
			e.budget--
		}
	case GossipPull:
		if !e.informed && e.rounds < e.cfg.MaxRounds {
			peers := e.randomPeersLocked(e.cfg.Fanout)
			for _, id := range peers {
				e.sendPacketLocked(id, Packet{Type: PacketPull})
			}
			e.rounds++
			e.lastPeriodic = now
			e.stats.Forwarded++
		}
	case AntiEntropy:
		if e.rounds < e.cfg.MaxRounds {
			peers := e.randomPeersLocked(e.cfg.Fanout)
			for _, id := range peers {
				e.sendPacketLocked(id, Packet{Type: PacketDigest, Has: e.informed})
			}
			e.rounds++
			e.lastPeriodic = now
			e.stats.Forwarded++
		}
	}
}

func (e *Engine) pushLocked(now int64) {
	peers := e.randomPeersLocked(e.cfg.Fanout)
	for _, id := range peers {
		e.sendDataLocked(id)
	}
	e.rounds++
	e.lastPeriodic = now
	e.stats.Forwarded++
}

func (e *Engine) randomPeersLocked(n int) []string {
	if len(e.cfg.Neighbors) == 0 {
		return nil
	}
	if n <= 0 {
		n = 1
	}
	if n >= len(e.cfg.Neighbors) {
		out := make([]string, len(e.cfg.Neighbors))
		copy(out, e.cfg.Neighbors)
		e.rng.Shuffle(len(out), func(i, j int) { out[i], out[j] = out[j], out[i] })
		return out
	}
	perm := e.rng.Perm(len(e.cfg.Neighbors))
	out := make([]string, 0, n)
	for _, idx := range perm[:n] {
		out = append(out, e.cfg.Neighbors[idx])
	}
	return out
}

func (e *Engine) sendDataLocked(to string) {
	e.sendPacketLocked(to, Packet{Type: PacketData, Target: to})
}

func (e *Engine) sendPacketLocked(to string, p Packet) {
	if to == "" || to == e.cfg.NodeID {
		return
	}
	e.stats.Attempted++
	if e.cfg.Loss > 0 && e.rng.Float64() < e.cfg.Loss {
		e.stats.Dropped++
		return
	}
	p.ExperimentID = e.expID
	p.MessageID = e.msgID
	p.Origin = e.origin
	p.Sender = e.cfg.NodeID
	p.Algorithm = e.cfg.Algorithm
	p.CreatedAt = e.now()
	p.Payload = e.payload
	if p.TTL == 0 {
		p.TTL = e.cfg.TTL
	}
	e.stats.Sent++
	if e.send != nil {
		if err := e.send(to, p); err != nil {
			e.stats.SendErrors++
		}
	}
}

func (e *Engine) Snapshot() State {
	e.mu.Lock()
	defer e.mu.Unlock()
	return State{
		NodeID:       e.cfg.NodeID,
		ExperimentID: e.expID,
		MessageID:    e.msgID,
		Informed:     e.informed,
		FirstSeen:    e.firstSeen,
		StartedAt:    e.startedAt,
		Failed:       e.failed,
		Stats:        e.stats,
		Algorithm:    string(e.cfg.Algorithm),
		NeighborN:    len(e.cfg.Neighbors),
		GroupN:       len(e.cfg.Group),
		Neighbors:    append([]string(nil), e.cfg.Neighbors...),
		Group:        append([]string(nil), e.cfg.Group...),
		Loss:         e.cfg.Loss,
	}
}

func (e *Engine) Informed() bool {
	e.mu.Lock()
	defer e.mu.Unlock()
	return e.informed
}

// CountSendError is used by transports that report asynchronous write
// failures, so that they are visible in the experiment statistics.
func (e *Engine) CountSendError() {
	e.mu.Lock()
	defer e.mu.Unlock()
	e.stats.SendErrors++
}
