# Configuring gcloud

```
gcloud config set project clementine-web
```

# Deploying

```
gcloud app deploy
```

## Adding a new language

1. Edit `Makefile` and add the new language code to `LANGUAGES`.
1. Edit `data.py` and add the [endonym](https://www.omniglot.com/language/names.htm) for the language.
1. Edit `data.py` and add the language code to `LANGUAGES`
1. `make`
1. Deploy
