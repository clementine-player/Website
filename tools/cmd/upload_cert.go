package main

import (
  "flag"
  "fmt"
  "io/ioutil"
  "log"

  "golang.org/x/net/context"
  "golang.org/x/oauth2/google"
  "google.golang.org/api/appengine/v1beta"
)

var project = flag.String("project", "clementine-data", "Google Cloud project id")
var fullchain = flag.String("fullchain", "", "Path to PEM encoded full certificate chain")
var key = flag.String("key", "", "Path to PEM encoded private key")

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

  publicKey, err := ioutil.ReadFile(*fullchain)
  if err != nil {
    log.Fatal("Failed to read certificate chain: ", err)
  }

  privateKey, err := ioutil.ReadFile(*key)
  if err != nil {
    log.Fatal("Failed to read private key: ", err)
  }

  cert := &appengine.AuthorizedCertificate{
    CertificateRawData: &appengine.CertificateRawData{
      PublicCertificate: fmt.Sprintf("%s", publicKey),
      PrivateKey:        fmt.Sprintf("%s", privateKey),
    },
    DisplayName: "foobar",
  }

  req := apps.Apps.AuthorizedCertificates.Create(*project, cert)
  resp, err := req.Do()
  if err != nil {
    log.Fatal("Uploading certificate failed: ", err)
  }
  log.Println(resp)
}
