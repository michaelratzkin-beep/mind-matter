# MIND / MATTER

A free, self-updating research aggregator for:

- consciousness and philosophy of mind
- quantum foundations and quantum physics
- neuroscience of consciousness
- serious cross-domain work connecting these fields

The site is static and can be hosted free on GitHub Pages. A scheduled GitHub Action refreshes the index every day from OpenAlex, arXiv, and Europe PMC, generates a concise briefing, writes an RSS feed, and redeploys the site.

## Deploy in about five minutes

1. Create a new **public** GitHub repository.
2. Upload every file and folder in this package to the repository root.
3. Open **Settings → Pages** and set **Source** to **GitHub Actions**.
4. Open the **Actions** tab and run **Update research and deploy Pages** once.
5. The deployment will produce a free URL such as `https://YOURNAME.github.io/REPOSITORY/`.

## Recommended: add the free OpenAlex key

OpenAlex now uses API keys. The updater can make a limited number of anonymous requests, but a free key is more reliable.

1. Create a free key in your OpenAlex account settings.
2. In GitHub, open **Settings → Secrets and variables → Actions**.
3. Add a repository secret named `OPENALEX_API_KEY`.
4. Optionally add a repository variable named `SITE_URL` with the final Pages URL. This makes links in the generated RSS feed point to the right site.

No key is needed for arXiv or Europe PMC.

## What “signal score” means

The score is a transparent reading-priority heuristic based on recency, citation activity, evidence-language indicators, open-access availability, abstract availability, and cross-domain relevance. It is **not** a truth score, peer review, or a claim that a paper is a breakthrough.

## Customize the topics

Edit `DOMAIN_QUERIES` and `KEYWORDS` in `scripts/update.py`. The current configuration emphasizes:

- phenomenology, qualia, panpsychism, higher-order theories, illusionism, artificial consciousness
- quantum foundations, decoherence, measurement, entanglement, quantum gravity and information
- neural correlates, anesthesia, wakefulness, disorders of consciousness, GNW and IIT

## Local preview

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/update.py
python -m http.server 8000
```

Then open `http://localhost:8000`.

## Notes

- arXiv entries are preprints and are clearly labeled.
- Some metadata services lag behind publishers.
- Automated summaries are extractive and based on source abstracts, not full-paper evaluation.
- GitHub scheduled workflows may run several minutes later than the nominal cron time.

## License

MIT. Research metadata remains subject to each source's terms and the original publications' licenses.
