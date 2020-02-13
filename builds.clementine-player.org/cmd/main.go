package main

import (
	"flag"
	"net/http"

	builds "github.com/clementine-player/Website/builds.clementine-player.org"
	"github.com/golang/glog"
)

func main() {
	flag.Parse()
	http.HandleFunc("/", builds.Serve)
	glog.Infof("Serving...")
	glog.Fatal(http.ListenAndServe(":8080", nil))
}
