package agent

import (
	"encoding/json"
	"fmt"
	"log"
	"net"
	"net/http"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/AndrewTheMaster/Distributed-systems-labs/internal/engine"
)

type Agent struct {
	eng *engine.Engine
	udp *net.UDPConn

	mu    sync.RWMutex
	addrs map[string]string
	cache map[string]*net.UDPAddr
}

func env(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func RunFromEnv() error {
	id := env("NODE_ID", "n000")
	dataAddr := env("DATA_ADDR", ":9000")
	controlAddr := env("CONTROL_ADDR", ":8080")
	seed := int64(1)
	if s := os.Getenv("GOSSIP_SEED"); s != "" {
		fmt.Sscanf(s, "%d", &seed)
	}

	conn, err := net.ListenUDP("udp", mustResolve(dataAddr))
	if err != nil {
		return fmt.Errorf("udp listen %s: %w", dataAddr, err)
	}
	defer conn.Close()
	_ = conn.SetReadBuffer(4 * 1024 * 1024)

	a := &Agent{
		udp:   conn,
		addrs: make(map[string]string),
		cache: make(map[string]*net.UDPAddr),
	}
	cfg := engine.Config{
		NodeID:           id,
		Algorithm:        engine.Broadcast,
		AllNodes:         map[string]string{},
		Fanout:           3,
		GossipIntervalMS: 100,
		MaxRounds:        60,
		RumorBudget:      15,
		TTL:              64,
		Seed:             seed,
	}
	a.eng = engine.New(cfg, a.sendPacket, func() int64 { return time.Now().UnixMilli() })

	enableRecvErr(conn)
	go a.readLoop()
	go a.tickLoop()

	mux := http.NewServeMux()
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, map[string]interface{}{"ok": true, "id": id})
	})
	mux.HandleFunc("/state", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, a.eng.Snapshot())
	})
	mux.HandleFunc("/config", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "POST required", http.StatusMethodNotAllowed)
			return
		}
		var cfg engine.Config
		if err := json.NewDecoder(r.Body).Decode(&cfg); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		if cfg.NodeID == "" {
			cfg.NodeID = id
		}
		a.setConfig(cfg)
		writeJSON(w, map[string]interface{}{"ok": true})
	})
	mux.HandleFunc("/start", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "POST required", http.StatusMethodNotAllowed)
			return
		}
		var req engine.StartRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		if req.StartedAt == 0 {
			req.StartedAt = time.Now().UnixMilli()
		}
		a.eng.Start(req)
		writeJSON(w, map[string]interface{}{"ok": true})
	})
	mux.HandleFunc("/reset", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "POST required", http.StatusMethodNotAllowed)
			return
		}
		a.eng.Reset()
		writeJSON(w, map[string]interface{}{"ok": true})
	})
	mux.HandleFunc("/fail", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "POST required", http.StatusMethodNotAllowed)
			return
		}
		var body struct {
			Failed bool `json:"failed"`
		}
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		a.eng.SetFailed(body.Failed)
		writeJSON(w, map[string]interface{}{"ok": true, "failed": body.Failed})
	})

	mux.HandleFunc("/kernel", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, readKernelUDP())
	})

	srv := &http.Server{
		Addr:              controlAddr,
		Handler:           mux,
		ReadHeaderTimeout: 5 * time.Second,
	}
	log.Printf("node %s data=%s control=%s", id, dataAddr, controlAddr)
	return srv.ListenAndServe()
}

func (a *Agent) setConfig(cfg engine.Config) {
	a.mu.Lock()
	a.addrs = make(map[string]string, len(cfg.AllNodes))
	for k, v := range cfg.AllNodes {
		a.addrs[k] = v
	}
	a.cache = make(map[string]*net.UDPAddr)
	a.mu.Unlock()
	a.eng.SetConfig(cfg)
}

func (a *Agent) sendPacket(to string, p engine.Packet) error {
	a.mu.RLock()
	addr := a.addrs[to]
	cached := a.cache[to]
	a.mu.RUnlock()
	if addr == "" {
		return fmt.Errorf("unknown peer %q", to)
	}
	ua := cached
	if ua == nil {
		var err error
		ua, err = net.ResolveUDPAddr("udp", addr)
		if err != nil {
			return err
		}
		a.mu.Lock()
		a.cache[to] = ua
		a.mu.Unlock()
	}
	b, err := json.Marshal(p)
	if err != nil {
		return err
	}
	_, err = a.udp.WriteToUDP(b, ua)
	return err
}

func (a *Agent) readLoop() {
	buf := make([]byte, 64*1024)
	for {
		n, _, err := a.udp.ReadFromUDP(buf)
		if err != nil {
			return
		}
		var p engine.Packet
		if err := json.Unmarshal(buf[:n], &p); err != nil {
			continue
		}
		a.eng.Handle(p)
	}
}

func (a *Agent) tickLoop() {
	ticker := time.NewTicker(10 * time.Millisecond)
	defer ticker.Stop()
	for now := range ticker.C {
		a.eng.Tick(now.UnixMilli())
	}
}

func writeJSON(w http.ResponseWriter, v interface{}) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(v)
}

func mustResolve(addr string) *net.UDPAddr {
	ua, err := net.ResolveUDPAddr("udp", addr)
	if err != nil {
		panic(err)
	}
	return ua
}

// KernelUDP holds UDP counters of the container kernel (see /proc/net/snmp).
type KernelUDP struct {
	OutDatagrams int64 `json:"out_datagrams"`
	InDatagrams  int64 `json:"in_datagrams"`
	SndbufErrors int64 `json:"sndbuf_errors"`
	RcvbufErrors int64 `json:"rcvbuf_errors"`
	InErrors     int64 `json:"in_errors"`
}

// readKernelUDP parses /proc/net/snmp; it returns zeros where procfs is absent.
func readKernelUDP() KernelUDP {
	var out KernelUDP
	data, err := os.ReadFile("/proc/net/snmp")
	if err != nil {
		return out
	}
	var header []string
	for _, line := range strings.Split(string(data), "\n") {
		fields := strings.Fields(line)
		if len(fields) == 0 || fields[0] != "Udp:" {
			continue
		}
		if header == nil {
			header = fields[1:]
			continue
		}
		values := fields[1:]
		for i, name := range header {
			if i >= len(values) {
				break
			}
			v, _ := strconv.ParseInt(values[i], 10, 64)
			switch name {
			case "OutDatagrams":
				out.OutDatagrams = v
			case "InDatagrams":
				out.InDatagrams = v
			case "SndbufErrors":
				out.SndbufErrors = v
			case "RcvbufErrors":
				out.RcvbufErrors = v
			case "InErrors":
				out.InErrors = v
			}
		}
		break
	}
	return out
}
