package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"

	"github.com/kelseyhightower/envconfig"
	"github.com/zmb3/spotify"
	"golang.org/x/oauth2/clientcredentials"
)

type config struct {
	SPOTIFY_CLIENT_ID     string `required:"true"`
	SPOTIFY_CLIENT_SECRET string `required:"true"`
}

func Int(i int) *int {
	return &i
}

func main() {
	var c config
	if err := envconfig.Process("", &c); err != nil {
		log.Fatal(err)
	}
	auth := clientcredentials.Config{
		ClientID:     c.SPOTIFY_CLIENT_ID,
		ClientSecret: c.SPOTIFY_CLIENT_SECRET,
		TokenURL:     spotify.TokenURL,
	}
	ctx := context.Background()
	client := spotify.NewClient(auth.Client(ctx))

	http.HandleFunc("/", func(rw http.ResponseWriter, r *http.Request) {
		artist := r.URL.Query().Get("artist")
		searchResp, err := client.SearchOpt(artist, spotify.SearchTypeArtist, &spotify.Options{
			Limit: Int(1),
		})
		if err != nil {
			http.Error(rw, fmt.Sprintf("oops: %v", err), http.StatusInternalServerError)
			return
		}

		if len(searchResp.Artists.Artists) == 0 {
			http.Error(rw, fmt.Sprintf("%s not found", artist), http.StatusNotFound)
			return
		}

		a := searchResp.Artists.Artists[0]
		d, err := json.Marshal(a.Images)
		if err != nil {
			http.Error(rw, fmt.Sprintf("oops: %v", err), http.StatusInternalServerError)
			return
		}
		if _, err := rw.Write(d); err != nil {
			http.Error(rw, fmt.Sprintf("oops: %v", err), http.StatusInternalServerError)
			return
		}
	})

	log.Println("Listening...")
	if err := http.ListenAndServe(":8080", nil); err != nil {
		log.Fatal(err)
	}
}
