# Make sure the requests library exists first with:
# pip install requests -t .

zips: fetch_bio.zip fetch_images.zip

fetch_bio.zip: fetch_bio.py requests
	zip -r $@ $^

fetch_images.zip: fetch_images.py requests
	zip -r $@ $^
