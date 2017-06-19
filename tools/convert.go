package main

import (
  "crypto/rsa"
  "crypto/x509"
  "encoding/pem"
  "flag"
  "io/ioutil"
  "log"
)

const (
  PKCS8_HEADER = "PRIVATE KEY"
  PKCS1_HEADER = "RSA PRIVATE KEY"
)

var cert = flag.String("cert", "", "Path to PKCS8 PEM encoded private key")
var output = flag.String("out", "rsa.pem", "Path to output PKCS1 RSA private key")

func main() {
  flag.Parse()
  data, err := ioutil.ReadFile(*cert)
  if err != nil {
    log.Fatal(err)
  }

  block, _ := pem.Decode(data)
  if block == nil || block.Type != PKCS8_HEADER {
    log.Fatal("Failed to decode private key block")
  }

  key, err := x509.ParsePKCS8PrivateKey(block.Bytes)
  if err != nil {
    log.Fatal("Failed to decode private key")
  }

  rsaKey, ok := key.(*rsa.PrivateKey)
  if !ok {
    log.Fatal("Failed to extract RSA key")
  }

  pkcs1 := x509.MarshalPKCS1PrivateKey(rsaKey)

  pemBlock := &pem.Block{
    Type: PKCS1_HEADER,
    Bytes: pkcs1,
  }

  err = ioutil.WriteFile("rsa.pem", pem.EncodeToMemory(pemBlock), 0600)
  if err != nil {
    log.Fatal("Failed to write key")
  }
}
