package builds

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"strings"

	"cloud.google.com/go/storage"
	"github.com/golang/glog"
	"google.golang.org/api/iterator"
)

func Serve(w http.ResponseWriter, r *http.Request) {
	ctx := context.Background()

	client, err := storage.NewClient(ctx)
	if err != nil {
		glog.Errorf("%v", err)
		return
	}

	bucket := client.Bucket("builds.clementine-player.org")
	prefix := strings.TrimPrefix(r.URL.Path, "/")
	if prefix != "" {
		reader, err := bucket.Object(prefix).NewReader(ctx)
		if err != nil {
			if err != storage.ErrObjectNotExist {
				glog.Errorf("%v", err)
				return
			}
		} else {
			if _, err := io.Copy(w, reader); err != nil {
				glog.Errorf("%v", err)
			}
			return
		}
	}

	fmt.Fprintln(w, "<!doctype html>")
	fmt.Fprintln(w, "<head><meta name=\"google\" content=\"notranslate\"></head>")
	fmt.Fprintln(w, "<body>")
	it := bucket.Objects(ctx, &storage.Query{
		Delimiter: "/",
		Prefix:    prefix,
		Versions:  false,
	})
	for {
		attrs, err := it.Next()
		if err == iterator.Done {
			break
		}
		if err != nil {
			glog.Errorf("%v", err)
			continue
		}
		// Synthetic directory.
		if attrs.Prefix != "" {
			fmt.Fprintf(w, "<div><a href=\"/%s\">%s</a></div>", attrs.Prefix, attrs.Prefix)
		} else {
			fmt.Fprintf(w, "<div><a href=\"%s\">%s</a></div>", attrs.MediaLink, strings.TrimPrefix(attrs.Name, prefix))
		}
	}
	fmt.Fprintln(w, "</body>")
}
