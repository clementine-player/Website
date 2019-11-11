package main

import (
	"flag"
	"net/http"

	"github.com/golang/glog"
	builds "github.com/clementine-player/Website/builds.clementine-player.org"
)

func main() {
	flag.Parse()
	http.HandleFunc("/", builds.Serve)
	glog.Infof("Serving...")
	glog.Fatal(http.ListenAndServe(":8080", nil))
}
