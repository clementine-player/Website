package main

import (
	"flag"
	"log"

	"golang.org/x/net/context"
	"golang.org/x/oauth2/google"
	"google.golang.org/api/appengine/v1beta"
)

var project = flag.String("project", "clementine-data", "Google Cloud project id")

func main() {
	flag.Parse()

	ctx := context.Background()

	c, err := google.DefaultClient(ctx, appengine.CloudPlatformScope)
	if err != nil {
		log.Fatal(err)
	}

	apps, err := appengine.New(c)
	if err != nil {
		log.Fatal(err)
	}

	req := apps.Apps.AuthorizedCertificates.List(*project)
	if err := req.Pages(ctx, func(page *appengine.ListAuthorizedCertificatesResponse) error {
		for _, cert := range page.Certificates {
			log.Printf("%s: %v\n", cert.DisplayName, cert.ExpireTime)
		}
		return nil
	}); err != nil {
		log.Fatal(err)
	}
}
