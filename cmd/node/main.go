package main

import (
	"log"

	"github.com/AndrewTheMaster/Distributed-systems-labs/internal/agent"
)

func main() {
	if err := agent.RunFromEnv(); err != nil {
		log.Fatal(err)
	}
}
