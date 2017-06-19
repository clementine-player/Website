package main

import (
  "crypto/x509"
  "encoding/pem"
  "flag"
  "fmt"
  "io/ioutil"
  "log"
  "strings"
  "time"

  "github.com/clementine-player/Website/tools"
  "golang.org/x/net/context"
  "golang.org/x/oauth2/google"
  "google.golang.org/api/appengine/v1beta"
)

var project = flag.String("project", "clementine-data", "Google Cloud project id")
var fullchain = flag.String("fullchain", "", "Path to PEM encoded full certificate chain")
var key = flag.String("key", "", "Path to PEM encoded private key")

func extractBlocks(data []byte) (ret []*pem.Block) {
  block, rest := pem.Decode(data)
  ret = append(ret, block)
  if rest != nil && len(rest) > 0 {
    ret = append(ret, extractBlocks(rest)...)
  }
  return ret
}

func extractExpiry(chain []byte) (time.Time, error) {
  blocks := extractBlocks(chain)
  for _, block := range blocks {
    certs, err := x509.ParseCertificates(block.Bytes)
    if err != nil {
      return time.Unix(0, 0), fmt.Errorf("Failed to parse certificates")
    }

    for _, cert := range certs {
      for _, name := range cert.DNSNames {
        if strings.Contains(name, "clementine-player.org") {
          return cert.NotAfter, nil
        }
      }
    }
  }
  return time.Unix(0, 0), fmt.Errorf("Could not find clementine-player.org certificate")
}

func mapDomainToCertificate(apps *appengine.APIService, project string, domain string, certId string) error {
  mappingRequest := apps.Apps.DomainMappings.Patch(project, domain, &appengine.DomainMapping{
    SslSettings: &appengine.SslSettings{
      CertificateId: certId,
    },
  })
  mappingRequest.UpdateMask("sslSettings.certificateId")
  mappingResponse, err := mappingRequest.Do()
  if err != nil {
    return fmt.Errorf("Failed to map certificate %s for domain %s: %v", certId, domain, err)
  }
  log.Println(mappingResponse)
  return nil
}

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

  rsaKey, err := convert.PKCS8ToPKCS1(privateKey)
  if err != nil {
    log.Fatal("Failed to convert key to RSA PRIVATE KEY")
  }

  expiry, err := extractExpiry(publicKey)
  if err != nil {
    log.Fatal("Failed to extract expiry time: ", err)
  }

  cert := &appengine.AuthorizedCertificate{
    CertificateRawData: &appengine.CertificateRawData{
      PublicCertificate: fmt.Sprintf("%s", publicKey),
      PrivateKey:        fmt.Sprintf("%s", rsaKey),
    },
    DisplayName: fmt.Sprintf("clementine-%02d-%d", expiry.Month(), expiry.Year()),
  }

  req := apps.Apps.AuthorizedCertificates.Create(*project, cert)
  resp, err := req.Do()
  if err != nil {
    log.Fatal("Uploading certificate failed: ", err)
  }

  certId := resp.Id
  if err = mapDomainToCertificate(apps, "clementine-data", "data.clementine-player.org", certId); err != nil {
    log.Print(err)
  }
  if err = mapDomainToCertificate(apps, "clementine-web", "clementine-player.org", certId); err != nil {
    log.Print(err)
  }
  if err = mapDomainToCertificate(apps, "clementine-web", "www.clementine-player.org", certId); err != nil {
    log.Print(err)
  }
}
