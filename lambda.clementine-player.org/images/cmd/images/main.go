// Command images serves artist images for Clementine's artist info pane.
//
// GET /?artist=NAME returns a JSON array of the best-matching artist's
// images, each {"url", "width", "height", "attributions"}. Clients read
// url/width/height and ignore other fields, so this shape must stay a bare
// array: Clementine releases that predate "attributions" call
// QJsonDocument::array() on it.
//
// Attribution entries: "source" is a stable ID, "name" a display name that
// clients show when they don't recognise the ID, "url" a link for the
// credit, and optional "text" is wording a source requires shown verbatim.
package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"
)

const deezerSearchURL = "https://api.deezer.com/search/artist"

type attribution struct {
	Source string `json:"source"`
	Name   string `json:"name"`
	URL    string `json:"url,omitempty"`
	Text   string `json:"text,omitempty"`
}

type image struct {
	URL          string        `json:"url"`
	Width        int           `json:"width"`
	Height       int           `json:"height"`
	Attributions []attribution `json:"attributions"`
}

type deezerArtist struct {
	Name          string `json:"name"`
	Link          string `json:"link"`
	PictureSmall  string `json:"picture_small"`
	PictureMedium string `json:"picture_medium"`
	PictureBig    string `json:"picture_big"`
	PictureXL     string `json:"picture_xl"`
}

type deezerSearch struct {
	Data  []deezerArtist `json:"data"`
	Error *struct {
		Type    string `json:"type"`
		Message string `json:"message"`
		Code    int    `json:"code"`
	} `json:"error"`
}

var errNotFound = fmt.Errorf("not found")

type server struct {
	searchURL string
	client    *http.Client
}

func (s *server) lookup(artist string) ([]image, error) {
	resp, err := s.client.Get(s.searchURL + "?" + url.Values{"q": {artist}, "limit": {"1"}}.Encode())
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("deezer: HTTP %d", resp.StatusCode)
	}
	var result deezerSearch
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("deezer: %v", err)
	}
	// Deezer reports errors, including quota exhaustion, as HTTP 200.
	if result.Error != nil {
		return nil, fmt.Errorf("deezer: %s (%d): %s", result.Error.Type, result.Error.Code, result.Error.Message)
	}
	if len(result.Data) == 0 {
		return nil, errNotFound
	}

	a := result.Data[0]
	// Artists without a photo get a generic placeholder, identifiable by an
	// empty image hash in the URL (.../images/artist//1000x1000-...).
	if a.PictureXL == "" || strings.Contains(a.PictureXL, "/images/artist//") {
		return nil, errNotFound
	}
	credit := []attribution{{Source: "deezer", Name: "Deezer", URL: a.Link}}
	var images []image
	for _, p := range []struct {
		url  string
		size int
	}{
		{a.PictureSmall, 56},
		{a.PictureMedium, 250},
		{a.PictureBig, 500},
		{a.PictureXL, 1000},
	} {
		if p.url != "" {
			images = append(images, image{URL: p.url, Width: p.size, Height: p.size, Attributions: credit})
		}
	}
	return images, nil
}

func (s *server) ServeHTTP(rw http.ResponseWriter, r *http.Request) {
	artist := r.URL.Query().Get("artist")
	if artist == "" {
		http.Error(rw, "missing artist", http.StatusBadRequest)
		return
	}
	images, err := s.lookup(artist)
	if err == errNotFound {
		http.Error(rw, fmt.Sprintf("%s not found", artist), http.StatusNotFound)
		return
	}
	if err != nil {
		log.Printf("lookup %q: %v", artist, err)
		http.Error(rw, fmt.Sprintf("oops: %v", err), http.StatusBadGateway)
		return
	}
	rw.Header().Set("Content-Type", "application/json; charset=utf-8")
	if err := json.NewEncoder(rw).Encode(images); err != nil {
		log.Printf("writing response: %v", err)
	}
}

func main() {
	s := &server{searchURL: deezerSearchURL, client: &http.Client{Timeout: 10 * time.Second}}
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}
	log.Printf("Listening on :%s", port)
	log.Fatal(http.ListenAndServe(":"+port, s))
}
