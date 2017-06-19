package main

import (
  "flag"
  "io/ioutil"
  "log"

  "github.com/clementine-player/Website/tools"
)

var cert = flag.String("cert", "", "Path to PKCS8 PEM encoded private key")
var output = flag.String("out", "rsa.pem", "Path to output PKCS1 RSA private key")

func main() {
  flag.Parse()
  data, err := ioutil.ReadFile(*cert)
  if err != nil {
    log.Fatal(err)
  }

  rsa, err := convert.PKCS8ToPKCS1(data)
  if err != nil {
    log.Fatal("Failed to convert key: ", err)
  }

  err = ioutil.WriteFile(*output, rsa, 0600)
  if err != nil {
    log.Fatal("Failed to write key: ", err)
  }
}
