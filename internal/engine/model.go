package engine

// Algorithm identifies a dissemination strategy.
type Algorithm string

const (
	Unicast     Algorithm = "unicast"
	Multicast   Algorithm = "multicast"
	Broadcast   Algorithm = "broadcast"
	GossipPush  Algorithm = "gossip_push"
	GossipPull  Algorithm = "gossip_pull"
	Rumor       Algorithm = "rumor_mongering"
	AntiEntropy Algorithm = "anti_entropy"
)

func AllAlgorithms() []Algorithm {
	return []Algorithm{
		Unicast,
		Multicast,
		Broadcast,
		GossipPush,
		GossipPull,
		Rumor,
		AntiEntropy,
	}
}

func ParseAlgorithm(s string) Algorithm {
	switch Algorithm(s) {
	case Unicast, Multicast, Broadcast, GossipPush, GossipPull, Rumor, AntiEntropy:
		return Algorithm(s)
	default:
		return Broadcast
	}
}

// PacketType is the kind of a wire message.
type PacketType string

const (
	PacketData   PacketType = "data"
	PacketPull   PacketType = "pull"
	PacketDigest PacketType = "digest"
	PacketStale  PacketType = "stale"
)

// Packet is one application-level message (JSON on the wire).
type Packet struct {
	Type         PacketType `json:"type"`
	ExperimentID string     `json:"experiment_id"`
	MessageID    string     `json:"message_id"`
	Origin       string     `json:"origin"`
	Sender       string     `json:"sender"`
	Target       string     `json:"target,omitempty"`
	Algorithm    Algorithm  `json:"algorithm"`
	Hop          int        `json:"hop,omitempty"`
	TTL          int        `json:"ttl,omitempty"`
	Has          bool       `json:"has,omitempty"`
	CreatedAt    int64      `json:"created_at,omitempty"`
	Payload      string     `json:"payload,omitempty"`
}

// Config is sent to every node before an experiment.
type Config struct {
	NodeID           string            `json:"node_id"`
	Algorithm        Algorithm         `json:"algorithm"`
	AllNodes         map[string]string `json:"all_nodes"`
	Neighbors        []string          `json:"neighbors"`
	Group            []string          `json:"group"`
	Loss             float64           `json:"loss"`
	LatencyMS        int               `json:"latency_ms"`
	JitterMS         int               `json:"jitter_ms"`
	Fanout           int               `json:"fanout"`
	GossipIntervalMS int               `json:"gossip_interval_ms"`
	MaxRounds        int               `json:"max_rounds"`
	RumorBudget      int               `json:"rumor_budget"`
	TTL              int               `json:"ttl"`
	UnicastTarget    string            `json:"unicast_target"`
	Seed             int64             `json:"seed"`
}

// Stats are per-experiment counters.
type Stats struct {
	Attempted  int64 `json:"attempted"`
	Sent       int64 `json:"sent"`
	Received   int64 `json:"received"`
	Dropped    int64 `json:"dropped"`
	Duplicates int64 `json:"duplicates"`
	Forwarded  int64 `json:"forwarded"`
	SendErrors int64 `json:"send_errors"`
	Ignored    int64 `json:"ignored"`
	Datagrams  int64 `json:"datagrams"`
}

// State is returned by GET /state.
type State struct {
	NodeID       string   `json:"node_id"`
	ExperimentID string   `json:"experiment_id"`
	MessageID    string   `json:"message_id"`
	Informed     bool     `json:"informed"`
	FirstSeen    int64    `json:"first_seen"`
	StartedAt    int64    `json:"started_at"`
	Failed       bool     `json:"failed"`
	Stats        Stats    `json:"stats"`
	Algorithm    string   `json:"algorithm"`
	NeighborN    int      `json:"neighbor_n"`
	GroupN       int      `json:"group_n"`
	Neighbors    []string `json:"neighbors"`
	Group        []string `json:"group"`
	Loss         float64  `json:"loss"`
}

// StartRequest arms a node for an experiment.
type StartRequest struct {
	ExperimentID string `json:"experiment_id"`
	MessageID    string `json:"message_id"`
	Origin       string `json:"origin"`
	StartedAt    int64  `json:"started_at"`
	Payload      string `json:"payload"`
}

// Result is one CSV row; times are milliseconds from the start.
type Result struct {
	Mode               string  `csv:"mode"`
	ExperimentID       string  `csv:"experiment_id"`
	Algorithm          string  `csv:"algorithm"`
	Nodes              int     `csv:"nodes"`
	Topology           string  `csv:"topology"`
	Degree             int     `csv:"degree"`
	Loss               float64 `csv:"loss"`
	FailFraction       float64 `csv:"fail_fraction"`
	FailAtMS           int     `csv:"fail_at_ms"`
	Seed               int64   `csv:"seed"`
	GroupSize          int     `csv:"group_size"`
	AliveNodes         int     `csv:"alive_nodes"`
	Intended           int     `csv:"intended"`
	InformedIntended   int     `csv:"informed_intended"`
	CoverageIntended   float64 `csv:"coverage_intended"`
	CoverageTotal      float64 `csv:"coverage_total"`
	DisseminationMS50  float64 `csv:"dissemination_ms_50"`
	DisseminationMS90  float64 `csv:"dissemination_ms_90"`
	DisseminationMS95  float64 `csv:"dissemination_ms_95"`
	DisseminationMS99  float64 `csv:"dissemination_ms_99"`
	DisseminationMS100 float64 `csv:"dissemination_ms_100"`
	MessagesSent       int64   `csv:"messages_sent"`
	MessagesReceived   int64   `csv:"messages_received"`
	Duplicates         int64   `csv:"duplicates"`
	Dropped            int64   `csv:"dropped"`
	SendErrors         int64   `csv:"send_errors"`
	KernelOut          int64   `csv:"kernel_out"`
	KernelIn           int64   `csv:"kernel_in"`
	KernelSndbufErr    int64   `csv:"kernel_sndbuf_errors"`
	KernelRcvbufErr    int64   `csv:"kernel_rcvbuf_errors"`
	Ignored            int64   `csv:"ignored"`
	Datagrams          int64   `csv:"datagrams"`
	ElapsedMS          float64 `csv:"elapsed_ms"`
	Converged          bool    `csv:"converged"`
	TimedOut           bool    `csv:"timed_out"`
}
