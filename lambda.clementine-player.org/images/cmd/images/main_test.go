package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"testing"
)

const radiohead = `{"data":[{"name":"Radiohead","link":"https://www.deezer.com/artist/399",
  "picture_small":"https://cdn/images/artist/abc/56x56.jpg",
  "picture_medium":"https://cdn/images/artist/abc/250x250.jpg",
  "picture_big":"https://cdn/images/artist/abc/500x500.jpg",
  "picture_xl":"https://cdn/images/artist/abc/1000x1000.jpg"}]}`

func serve(t *testing.T, deezerBody string, artist string) *httptest.ResponseRecorder {
	t.Helper()
	deezer := httptest.NewServer(http.HandlerFunc(func(rw http.ResponseWriter, r *http.Request) {
		if got := r.URL.Query().Get("q"); got != artist {
			t.Errorf("deezer queried for %q, want %q", got, artist)
		}
		rw.Write([]byte(deezerBody))
	}))
	defer deezer.Close()
	s := &server{searchURL: deezer.URL, client: deezer.Client()}
	rec := httptest.NewRecorder()
	s.ServeHTTP(rec, httptest.NewRequest("GET", "/?"+url.Values{"artist": {artist}}.Encode(), nil))
	return rec
}

func TestReturnsAllSizesWithAttribution(t *testing.T) {
	rec := serve(t, radiohead, "Radiohead")
	if rec.Code != http.StatusOK {
		t.Fatalf("status %d: %s", rec.Code, rec.Body)
	}
	// Decode the way current Clementine releases do: a bare array of objects
	// with url/width/height.
	var images []image
	if err := json.Unmarshal(rec.Body.Bytes(), &images); err != nil {
		t.Fatalf("response isn't a JSON array of images: %v: %s", err, rec.Body)
	}
	if len(images) != 4 {
		t.Fatalf("got %d images, want 4", len(images))
	}
	largest := images[len(images)-1]
	if largest.Width != 1000 || largest.Height != 1000 || largest.URL != "https://cdn/images/artist/abc/1000x1000.jpg" {
		t.Errorf("largest image = %+v", largest)
	}
	for _, img := range images {
		want := attribution{Source: "deezer", Name: "Deezer", URL: "https://www.deezer.com/artist/399"}
		if len(img.Attributions) != 1 || img.Attributions[0] != want {
			t.Errorf("attributions = %+v, want [%+v]", img.Attributions, want)
		}
	}
}

func TestPlaceholderPictureIsNotFound(t *testing.T) {
	body := `{"data":[{"name":"Some Choir","link":"https://www.deezer.com/artist/1",
	  "picture_xl":"https://cdn/images/artist//1000x1000-000000-80-0-0.jpg"}]}`
	if rec := serve(t, body, "Some Choir"); rec.Code != http.StatusNotFound {
		t.Errorf("status %d, want 404", rec.Code)
	}
}

func TestNoResultsIsNotFound(t *testing.T) {
	if rec := serve(t, `{"data":[],"total":0}`, "Nobody"); rec.Code != http.StatusNotFound {
		t.Errorf("status %d, want 404", rec.Code)
	}
}

func TestDeezerErrorIsBadGateway(t *testing.T) {
	// Deezer reports errors such as quota exhaustion with HTTP 200.
	body := `{"error":{"type":"Exception","message":"Quota limit exceeded","code":4}}`
	if rec := serve(t, body, "Radiohead"); rec.Code != http.StatusBadGateway {
		t.Errorf("status %d, want 502", rec.Code)
	}
}

func TestMissingArtistIsBadRequest(t *testing.T) {
	s := &server{searchURL: "http://unused.invalid", client: http.DefaultClient}
	rec := httptest.NewRecorder()
	s.ServeHTTP(rec, httptest.NewRequest("GET", "/", nil))
	if rec.Code != http.StatusBadRequest {
		t.Errorf("status %d, want 400", rec.Code)
	}
}

func TestBestMatchPrefersMostPopularExactName(t *testing.T) {
	artists := []deezerArtist{
		{Name: "Muse", Fans: 38, Link: "obscure"},
		{Name: "Muse", Fans: 11037, Link: "other"},
		{Name: "muse", Fans: 5043564, Link: "the band"},
		{Name: "M.U.S.E.", Fans: 9999999, Link: "not an exact match"},
	}
	if got := bestMatch("Muse", artists).Link; got != "the band" {
		t.Errorf("bestMatch = %q, want the band", got)
	}
}

func TestBestMatchFallsBackToTopResult(t *testing.T) {
	artists := []deezerArtist{
		{Name: "Beyoncé", Fans: 100, Link: "top"},
		{Name: "Beyonce Tribute", Fans: 5, Link: "other"},
	}
	if got := bestMatch("beyonce", artists).Link; got != "top" {
		t.Errorf("bestMatch = %q, want Deezer's top result", got)
	}
}
