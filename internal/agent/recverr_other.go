//go:build !linux

package agent

import "net"

func enableRecvErr(_ *net.UDPConn) {}
