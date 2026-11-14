package agent

import (
	"net"

	"syscall"
)

// enableRecvErr makes the kernel report local send failures (ENOBUFS when the
// egress queue is full) to the application instead of silently dropping the
// datagram and returning success.
func enableRecvErr(conn *net.UDPConn) {
	raw, err := conn.SyscallConn()
	if err != nil {
		return
	}
	_ = raw.Control(func(fd uintptr) {
		_ = syscall.SetsockoptInt(int(fd), syscall.IPPROTO_IP, syscall.IP_RECVERR, 1)
	})
}
