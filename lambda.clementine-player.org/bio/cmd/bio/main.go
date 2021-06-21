package main

import (
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/url"

	"github.com/kelseyhightower/envconfig"
)

type config struct {
	KG_API_KEY string `required:"true"`
}

type kgResponse struct {
	ItemListElement []struct {
		Result struct {
			DetailedDescription struct {
				URL         string `json:"url"`
				ArticleBody string `json:"articleBody"`
				License     string `json:"license"`
			} `json:"detailedDescription"`
		} `json:"result"`
	} `json:"itemListElement"`
}

const kgURL = "https://kgsearch.googleapis.com/v1/entities:search"

func main() {
	var c config
	if err := envconfig.Process("", &c); err != nil {
		log.Fatal(err)
	}

	http.HandleFunc("/", func(rw http.ResponseWriter, r *http.Request) {
		rawQuery := r.URL.Query()

		u, _ := url.Parse(kgURL)
		q := u.Query()
		q.Set("query", rawQuery.Get("artist"))
		q.Set("limit", "1")
		q.Set("types", "Person,MusicGroup")
		q.Set("key", c.KG_API_KEY)
		q.Set("languages", rawQuery.Get("lang"))
		u.RawQuery = q.Encode()

		resp, err := http.Get(u.String())
		if err != nil {
			http.Error(rw, fmt.Sprintf("oops: %v", err), http.StatusInternalServerError)
			return
		}

		d, err := io.ReadAll(resp.Body)
		if err != nil {
			http.Error(rw, fmt.Sprintf("oops: %v", err), http.StatusInternalServerError)
			return
		}

		if resp.StatusCode != 200 {
			http.Error(rw, fmt.Sprintf("oops: %v %s", resp.Status, d), http.StatusInternalServerError)
			return
		}

		var kgResp kgResponse
		if err := json.Unmarshal(d, &kgResp); err != nil {
			http.Error(rw, fmt.Sprintf("oops: %v", err), http.StatusInternalServerError)
			return
		}

		if len(kgResp.ItemListElement) == 0 {
			http.Error(rw, fmt.Sprintf("not found: %s", rawQuery.Get("artist")), http.StatusNotFound)
			return
		}

		out, err := json.Marshal(kgResp.ItemListElement[0].Result.DetailedDescription)
		if err != nil {
			http.Error(rw, fmt.Sprintf("oops: %v", err), http.StatusInternalServerError)
			return
		}

		if _, err := rw.Write(out); err != nil {
			http.Error(rw, fmt.Sprintf("oops: %v", err), http.StatusInternalServerError)
			return
		}
	})

	log.Print("Listening...")
	if err := http.ListenAndServe(":8080", nil); err != nil {
		log.Fatal(err)
	}
}
