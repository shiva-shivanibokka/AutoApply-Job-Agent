"""
scraper.py
Job discovery from multiple sources:

  1. Adzuna API          — free, structured JSON, 50+ countries
  2. Greenhouse boards   — boards.greenhouse.io/{company}/jobs
  3. Lever boards        — jobs.lever.co/{company}
  4. Ashby boards        — jobs.ashbyhq.com/{company}

Company lists are NOT hardcoded. They come from:

  A. Simplify's live JSON repos (1000+ companies, updated daily by the community)
       - SimplifyJobs/New-Grad-Positions  (full-time roles)
       - SimplifyJobs/Summer2026-Internships (broader company coverage)
     Cached to disk for 24 hours so the app does NOT re-fetch on every run.

  B. A curated fallback list of 200+ AI/ML/tech companies built in.
     Used if GitHub is unreachable, and always merged in to ensure coverage
     of frontier AI companies that may not appear in the Simplify lists.

  C. User-supplied custom slugs entered in the UI.
"""

import hashlib
import json
import logging
import re
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup  # type: ignore[import-untyped]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

log = logging.getLogger("hireview.scraper")


def _get(url: str, *, timeout: int = 12, **kw):
    """
    GET with a timeout that LOGS failures instead of swallowing them silently.
    Returns the Response, or None on any network error.

    ponytail: no retry — the parallel fan-out + per-source deadline already
    absorb single flaky boards. Add a urllib3 Retry adapter here if transient
    5xx/connection errors start measurably thinning results.
    """
    try:
        return requests.get(url, headers=HEADERS, timeout=timeout, **kw)
    except Exception as e:
        log.warning("fetch failed [%s]: %s", e.__class__.__name__, url)
        return None


# Disk cache path — persists across app restarts
CACHE_FILE = Path(__file__).parent / "data" / "company_cache.json"
CACHE_TTL_HOURS = 24

# Always merged on top of Simplify data as a gap-filler.
# Covers every major AI/ML, cloud, infra, fintech, and high-growth tech company.
# Organised by ATS platform (Greenhouse / Lever / Ashby).

FALLBACK_GREENHOUSE = [
    "anthropic",
    "openai",
    "cohere",
    "adept",
    "characterai",
    "inflectionai",
    "imbue",
    "alephalpha",
    "xai",
    "mosaicml",
    "mistral-ai",
    "ai21labs",
    "tii",
    "technion",
    "codeium",
    "tabnine",
    "sourcegraph",
    "replit",
    "githubnext",
    "sweep-ai",
    "factory-ai",
    "cosine-ai",
    "scale-ai",
    "huggingface",
    "together-ai",
    "anyscale",
    "modular",
    "lightning-ai",
    "replicate",
    "baseten",
    "weights-biases",
    "determined-ai",
    "nomic",
    "trychroma",
    "activeloop",
    "zenml",
    "bentoml",
    "seldon",
    "truefoundry",
    "pinecone",
    "weaviate",
    "qdrant",
    "milvusio",
    "chroma",
    "arize-ai",
    "whylabs",
    "fiddler-ai",
    "aporia",
    "truera",
    "superwise",
    "gantry",
    "arthur-ai",
    "censius",
    "tecton",
    "feast-dev",
    "hopsworks",
    "databricks",
    "snowflake",
    "dbt-labs",
    "fivetran",
    "airbyte",
    "starburst",
    "dremio",
    "imply",
    "clickhouse",
    "motherduck",
    "rockset",
    "materialize",
    "timeplus",
    "greatexpectations",
    "monte-carlo-data",
    "datafold",
    "anomalo",
    "soda-data",
    "lightup-data",
    "labelbox",
    "scale-ai",
    "snorkel-ai",
    "humanloop",
    "argilla-io",
    "diffgram",
    "encord",
    "dataloop",
    "hashicorp",
    "pulumi",
    "teleport",
    "tailscale",
    "cloudflare",
    "fastly",
    "render",
    "railway",
    "fly-io",
    "coherence",
    "nitric",
    "shuttle",
    "porter-dev",
    "honeycomb-io",
    "lightstep",
    "incident-io",
    "firehydrant",
    "rootly",
    "grafana",
    "chronosphere",
    "last9",
    "figma",
    "notion",
    "linear",
    "vercel",
    "netlify",
    "retool",
    "airtable",
    "webflow",
    "coda",
    "zapier",
    "make",
    "n8n",
    "workato",
    "tray-io",
    "postman",
    "readme",
    "stoplight",
    "bump-sh",
    "algolia",
    "elastic",
    "typesense",
    "meilisearch",
    "launchdarkly",
    "statsig",
    "eppo",
    "split-io",
    "optimizely",
    "flagsmith",
    "growthbook",
    "snyk",
    "lacework",
    "orca-security",
    "wiz",
    "cyera",
    "deepfence",
    "semgrep",
    "aikido-security",
    "socket-dev",
    "nightfall",
    "skyflow",
    "evervault",
    "stripe",
    "plaid",
    "brex",
    "ramp",
    "mercury",
    "moderntreasury",
    "lithic",
    "column",
    "increase",
    "bond",
    "unit",
    "synctera",
    "treasury-prime",
    "alpaca",
    "polygon-io",
    "tradier",
    "lattice",
    "rippling",
    "deel",
    "gusto",
    "workos",
    "merge-api",
    "finch-api",
    "pave",
    "comprehensive-io",
    "commure",
    "ro",
    "cerebral",
    "hims",
    "novu",
    "tempus",
    "freenome",
    "recursion",
    "insitro",
    "bighat-biosciences",
    "absci",
    "inceptive",
    "profluent",
    "zoox",
    "waymo",
    "aurora",
    "motional",
    "gatik",
    "nuro",
    "kodiak-robotics",
    "argo-ai",
    "boston-dynamics",
    "figure-ai",
    "climateai",
    "watershed",
    "patch",
    "south-pole",
    "arcadia",
    "swell-energy",
    "anza",
    "banyan-infrastructure",
    "shopify",
    "faire",
    "flexport",
    "stord",
    "convictional",
    "notion",
    "coda",
    "craft",
    "taskade",
    "fibery",
    "height-app",
    "plane-so",
    "shortcut",
    "amplitude",
    "mixpanel",
    "heap",
    "fullstory",
    "logrocket",
    "posthog",
    "june-so",
    "koala",
    "clearbit",
    "twilio",
    "sendgrid",
    "postmark",
    "courier",
    "assembly-ai",
    "deepgram",
    "rev-ai",
    "speechmatics",
    "duolingo",
    "quizlet",
    "khan-academy",
    "brilliant",
    "coursera",
    "outschool",
    "synthesis",
    "harvey",
    "clio",
    "ironclad",
    "lexion",
    "spellbook",
    "luminance",
    "contractpodai",
]

FALLBACK_LEVER = [
    "netflix",
    "lyft",
    "reddit",
    "dropbox",
    "pinterest",
    "etsy",
    "wayfair",
    "robinhood",
    "coinbase",
    "twitch",
    "box",
    "zendesk",
    "surveymonkey",
    "hootsuite",
    "clarifai",
    "roboflow",
    "landing-ai",
    "v7labs",
    "scale",
    "labelbox",
    "snorkel-ai",
    "comet-ml",
    "neptune-ai",
    "valohai",
    "lightdash",
    "metabase",
    "mode-analytics",
    "preset",
    "sigma-computing",
    "omni-analytics",
    "cube-dev",
    "census-data",
    "hightouch",
    "polytomic",
    "cockroachdb",
    "planetscale",
    "neon",
    "turso",
    "grafana",
    "datadog",
    "elastic",
    "confluent",
    "temporal",
    "inngest",
    "trigger-dev",
    "doppler",
    "infisical",
    "vault-by-hashicorp",
    "ngrok",
    "hookdeck",
    "svix",
    "mintlify",
    "gitbook",
    "archbee",
    "drata",
    "vanta",
    "secureframe",
    "tugboat-logic",
    "anecdotes",
    "hyperproof",
    "affirm",
    "marqeta",
    "chime",
    "current",
    "kraken",
    "gemini",
    "bitgo",
    "chainalysis",
    "alchemy",
    "quicknode",
    "moralis",
    "outreach",
    "salesloft",
    "gong-io",
    "chorus",
    "clari",
    "people-ai",
    "dooly",
    "grain",
    "apollo-io",
    "instantly",
    "smartlead",
    "greenhouse",
    "lever",
    "ashby",
    "workable",
    "bamboohr",
    "15five",
    "leapsome",
    "culture-amp",
    "miro",
    "loom",
    "pitch",
    "mmhmm",
    "read-ai",
    "otter-ai",
    "fireflies-ai",
    "health-gorilla",
    "redox",
    "zus-health",
    "canvas-medical",
    "elation-health",
    "opendoor",
    "offerpad",
    "knock",
    "orchard",
    "doorstead",
    "atlas",
    "lessen",
    "project44",
    "fourkites",
    "visible-scm",
    "turvo",
    "loadsmart",
    "transfix",
]

FALLBACK_ASHBY = [
    "mistral",
    "perplexity",
    "harvey",
    "cognition",
    "cursor",
    "magic",
    "factory",
    "cosine",
    "sweep",
    "devin-ai",
    "aide",
    "cline",
    "continue-dev",
    "aider-chat",
    "plandex",
    "mentat",
    "codeium",
    "tabnine",
    "sourcegraph",
    "githubnext",
    "pieces-app",
    "bloop",
    "greptile",
    "codestory",
    "e2b",
    "daytona",
    "gitpod",
    "coder",
    "luma-ai",
    "runway",
    "pika-labs",
    "stability-ai",
    "midjourney",
    "ideogram",
    "adobe-firefly",
    "elevenlabs",
    "playht",
    "resemble-ai",
    "cartesia",
    "suno",
    "udio",
    "soundraw",
    "photoroom",
    "clipdrop",
    "pixelcut",
    "jasper-ai",
    "writer-com",
    "copy-ai",
    "glean",
    "guru",
    "tettra",
    "notion-ai",
    "modal-labs",
    "baseten",
    "fireworks-ai",
    "deepinfra",
    "groq",
    "cerebras",
    "sambanova",
    "d-matrix",
    "tenstorrent",
    "graphcore",
    "lambda-labs",
    "coreweave",
    "vast-ai",
    "together-ai",
    "lepton-ai",
    "mystic",
    "langchain",
    "llamaindex",
    "brainlid",
    "langfuse",
    "helicone",
    "traceloop",
    "promptlayer",
    "pezzo-ai",
    "agentops",
    "braintrust-data",
    "log10-io",
    "patronus-ai",
    "physical-intelligence",
    "covariant",
    "1x-technologies",
    "apptronik",
    "agility-robotics",
    "figure-ai",
    "arc-motors",
    "marble",
    "machina-labs",
    "viam-robotics",
    "formant",
    "formant-io",
    "inceptive",
    "profluent",
    "openfold",
    "isomorphic-labs",
    "exscientia",
    "menten-ai",
    "enveda",
    "peptone",
    "charm-therapeutics",
    "perplexity",
    "you-com",
    "metaphor-systems",
    "exa-ai",
    "kagi",
    "phind",
    "linear",
    "raycast",
    "superhuman",
    "clerk",
    "supabase",
    "neon",
    "resend",
    "loops",
    "trigger-dev",
    "inngest",
    "zuplo",
    "unkey",
    "stytch",
    "hanko",
    "langsmith",
    "weaviate",
    "qdrant",
    "milvus",
    "turbopuffer",
    "lancedb",
    "vespa-engine",
    "ashby",
    "gem",
    "dover",
    "teamable",
    "karat",
    "interviewing-io",
    "pramp",
    "arc-dev",
    "lemon-io",
    "toptal",
    "moonpay",
    "privy",
    "dynamic-xyz",
    "particle-network",
    "turnkey",
    "bereal",
    "artifact-news",
    "read-cv",
    "cosmos-fm",
    "farcaster",
    "lens-protocol",
]

# Both repos are maintained by the community and updated daily.
# New-Grad has full-time roles. Summer2026 has broader company coverage.

SIMPLIFY_URLS = [
    "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/.github/scripts/listings.json",
    "https://raw.githubusercontent.com/SimplifyJobs/Summer2026-Internships/dev/.github/scripts/listings.json",
]

_cache_lock = threading.Lock()


def _load_disk_cache() -> dict | None:
    try:
        if not CACHE_FILE.exists():
            return None
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        fetched_at = datetime.fromisoformat(
            data.get("fetched_at", "2000-01-01T00:00:00+00:00")
        )
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - fetched_at > timedelta(hours=CACHE_TTL_HOURS):
            return None
        return data
    except Exception:
        return None


def _save_disk_cache(companies: dict, name_map: dict):
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(
            json.dumps(
                {
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "companies": companies,
                    "name_map": name_map,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception as e:
        # Not fatal — the caller has the data in memory either way. But a cache
        # that silently never writes means every run re-fetches Simplify's
        # listings, which looks like nothing at all from the outside.
        log.warning("company cache write failed [%s]: %s", e.__class__.__name__, CACHE_FILE)


_INVALID_SLUGS = {"embed", "job_board", "jobs", "postings", "api", "apply"}


def _fetch_simplify_companies() -> dict:
    """
    Fetch Greenhouse/Lever/Ashby slugs from Simplify's live JSON.
    Returns {"greenhouse": [...], "lever": [...], "ashby": [...]}

    Cache strategy:
      1. Check disk cache (fresh for 24h, survives app restarts)
      2. If stale/missing, fetch from GitHub
      3. Save result to disk for next run
    """
    with _cache_lock:
        cached = _load_disk_cache()
        if cached:
            return cached.get("companies", {})

        result: dict = {"greenhouse": [], "lever": [], "ashby": []}
        # name_map: company display name → {"platform": ..., "slug": ...}
        name_map: dict = {}

        for url in SIMPLIFY_URLS:
            try:
                resp = _get(url, timeout=25)
                if resp is None or resp.status_code != 200:
                    continue
                listings = resp.json()
                if not isinstance(listings, list):
                    continue

                for item in listings:
                    link = str(item.get("url", "") or item.get("link", "") or "")
                    company_name = str(item.get("company_name", "") or "").strip()
                    if not link:
                        continue

                    gh = re.search(r"boards\.greenhouse\.io/([^/?#\s]+)", link)
                    if gh:
                        slug = gh.group(1).lower().split("?")[0]
                        if (
                            slug
                            and slug not in _INVALID_SLUGS
                            and slug not in result["greenhouse"]
                        ):
                            result["greenhouse"].append(slug)
                            if company_name:
                                name_map[company_name] = {
                                    "platform": "greenhouse",
                                    "slug": slug,
                                }
                        continue

                    lv = re.search(r"jobs\.lever\.co/([^/?#\s]+)", link)
                    if lv:
                        slug = lv.group(1).lower().split("?")[0]
                        if (
                            slug
                            and slug not in _INVALID_SLUGS
                            and slug not in result["lever"]
                        ):
                            result["lever"].append(slug)
                            if company_name:
                                name_map[company_name] = {
                                    "platform": "lever",
                                    "slug": slug,
                                }
                        continue

                    ab = re.search(r"jobs\.ashbyhq\.com/([^/?#\s]+)", link)
                    if ab:
                        slug = ab.group(1).lower().split("?")[0]
                        if (
                            slug
                            and slug not in _INVALID_SLUGS
                            and slug not in result["ashby"]
                        ):
                            result["ashby"].append(slug)
                            if company_name:
                                name_map[company_name] = {
                                    "platform": "ashby",
                                    "slug": slug,
                                }
                        continue

            except Exception as e:
                # Losing a Simplify source drops ~1,000 companies and quietly
                # degrades every later search to the curated fallback list.
                # Identical results, far fewer of them, and no signal anywhere —
                # so this gets logged loudly even though it is recoverable.
                log.warning(
                    "simplify source unusable, falling back for it [%s]: %s",
                    e.__class__.__name__,
                    url,
                )
                continue

        if any(result.values()):
            _save_disk_cache(result, name_map)
        else:
            log.warning(
                "no companies from any Simplify source; using the curated fallback only"
            )

        return result


def get_company_name_map() -> dict:
    """
    Return a dict mapping company display name → {platform, slug}.
    Built from the Simplify JSON + fallback lists.
    Used for company autocomplete and targeted company search.
    """
    with _cache_lock:
        cached = _load_disk_cache()
        if cached and cached.get("name_map"):
            return cached["name_map"]

    # Cache miss or no name_map yet — trigger a fresh fetch which will populate it
    _fetch_simplify_companies()
    with _cache_lock:
        cached = _load_disk_cache()
        if cached and cached.get("name_map"):
            return cached["name_map"]

    # Final fallback: build from slug lists only (no display names)
    name_map: dict = {}
    for slug in FALLBACK_GREENHOUSE:
        name = slug.replace("-", " ").replace("_", " ").title()
        name_map[name] = {"platform": "greenhouse", "slug": slug}
    for slug in FALLBACK_LEVER:
        name = slug.replace("-", " ").replace("_", " ").title()
        name_map[name] = {"platform": "lever", "slug": slug}
    for slug in FALLBACK_ASHBY:
        name = slug.replace("-", " ").replace("_", " ").title()
        name_map[name] = {"platform": "ashby", "slug": slug}
    return name_map


def get_company_lists(
    custom_greenhouse: "list | None" = None,
    custom_lever: "list | None" = None,
    custom_ashby: "list | None" = None,
) -> dict:
    """
    Build final company lists by merging:
      1. Simplify live JSON (1000+ companies, disk-cached 24h)
      2. Curated fallback (200+ AI/ML companies — always present)
      3. User-supplied custom slugs from the UI
    """
    simplify = _fetch_simplify_companies()

    def merge(simplify_list: list, fallback: list, custom: list | None) -> list:
        seen: set = set()
        combined: list = []
        for slug in list(simplify_list) + list(fallback) + list(custom or []):
            slug = slug.strip().lower()
            if slug and slug not in seen:
                seen.add(slug)
                combined.append(slug)
        return combined

    gh = merge(simplify.get("greenhouse", []), FALLBACK_GREENHOUSE, custom_greenhouse)
    lv = merge(simplify.get("lever", []), FALLBACK_LEVER, custom_lever)
    ab = merge(simplify.get("ashby", []), FALLBACK_ASHBY, custom_ashby)

    # Remove cross-list duplicates: if a slug appears in multiple ATS sources,
    # keep it only in the first list it appears in (Greenhouse > Lever > Ashby)
    lv = [s for s in lv if s not in set(gh)]
    ab = [s for s in ab if s not in set(gh) and s not in set(lv)]

    return {"greenhouse": gh, "lever": lv, "ashby": ab}


def _job_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:16]


def _make_job(
    title: str,
    company: str,
    location: str,
    url: str,
    description: str = "",
    job_type: str = "",  # full-time | part-time | contract | internship
    workplace: str = "",  # remote | hybrid | onsite
    source: str = "",
    required_skills: list | None = None,
    keywords: list | None = None,
    posted_at: str = "",
) -> dict:
    return {
        "id": _job_id(url),
        "title": title.strip(),
        "company": company.strip(),
        "location": location.strip(),
        "url": url.strip(),
        "description": description.strip(),
        "job_type": job_type,
        "workplace": workplace,
        "source": source,
        "required_skills": required_skills or [],
        "keywords": keywords or [],
        "match_score": 0.0,
        "scraped_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "posted_at": posted_at,
        "status": "new",
    }


def _normalise_workplace(raw: str) -> str:
    """Normalise various workplace strings to: remote | hybrid | onsite"""
    v = raw.lower().strip()
    if any(
        x in v for x in ["remote", "distributed", "work from home", "wfh", "anywhere"]
    ):
        return "remote"
    if "hybrid" in v:
        return "hybrid"
    if any(
        x in v
        for x in ["onsite", "on-site", "on site", "in office", "in-office", "office"]
    ):
        return "onsite"
    return ""


def _normalise_job_type(raw: str) -> str:
    """Normalise various job type strings to: full-time | part-time | contract | internship"""
    v = raw.lower().strip()
    if any(x in v for x in ["intern", "internship", "placement", "co-op", "coop"]):
        return "internship"
    if any(x in v for x in ["part", "part-time", "parttime"]):
        return "part-time"
    if any(
        x in v for x in ["contract", "freelance", "consultant", "temp", "temporary"]
    ):
        return "contract"
    if any(x in v for x in ["full", "full-time", "fulltime", "permanent"]):
        return "full-time"
    return ""


def search_adzuna(
    keywords: str,
    location: str = "",
    results_per_page: int = 50,
    app_id: str = "",
    app_key: str = "",
) -> list:
    if not app_id or not app_key:
        return []

    country = "us"
    loc = location.lower()
    if any(
        x in loc for x in ["uk", "london", "england", "europe", "germany", "france"]
    ):
        country = "gb"  # Adzuna UK as closest proxy for Europe
    elif any(x in loc for x in ["india", "bangalore", "mumbai", "delhi"]):
        country = "in"
    elif any(x in loc for x in ["canada", "toronto", "vancouver"]):
        country = "ca"
    elif any(x in loc for x in ["australia", "sydney", "melbourne"]):
        country = "au"
    # "remote" and "United States" both stay as "us"

    base = (
        f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
        f"?app_id={app_id}&app_key={app_key}"
        f"&results_per_page={results_per_page}"
        f"&what={quote(keywords)}"
        f"&content-type=application/json&sort_by=relevance"
    )
    if location and country == "us":
        base += f"&where={quote(location)}"

    resp = _get(base, timeout=15)
    if resp is None:
        return []
    try:
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.warning("adzuna response parse failed [%s]", e.__class__.__name__)
        return []

    return [
        _make_job(
            title=r.get("title", ""),
            company=(r.get("company") or {}).get("display_name", ""),
            location=(r.get("location") or {}).get("display_name", ""),
            url=r.get("redirect_url", ""),
            description=r.get("description", ""),
            job_type=_normalise_job_type(r.get("contract_time", "")),
            source="adzuna",
        )
        for r in data.get("results", [])
        if r.get("redirect_url")
    ]


def _scrape_greenhouse(company_slug: str, keywords: list) -> list:
    """
    Uses the Greenhouse boards JSON API which returns first_published date.
    Falls back to HTML scraping if the API returns a non-200.
    """
    api_url = f"https://boards-api.greenhouse.io/v1/boards/{company_slug}/jobs"
    resp = _get(api_url)
    if resp is not None and resp.status_code == 200:
        try:
            return _parse_greenhouse_json(resp.json(), company_slug, keywords)
        except Exception as e:
            log.warning("greenhouse json parse failed for %s [%s]", company_slug, e.__class__.__name__)

    # HTML fallback
    html_url = f"https://boards.greenhouse.io/{company_slug}/jobs"
    resp = _get(html_url)
    if resp is None or resp.status_code != 200:
        return []
    return _parse_greenhouse_html(resp.text, company_slug, keywords)


def _parse_greenhouse_json(data: dict, company_slug: str, keywords: list) -> list:
    jobs = []
    kw_lower = [k.lower() for k in keywords]
    for j in data.get("jobs", []):
        title = str(j.get("title") or "")
        if kw_lower and not any(kw in title.lower() for kw in kw_lower):
            continue
        job_url = str(j.get("absolute_url") or "")
        location = str((j.get("location") or {}).get("name") or "")
        company = str(
            j.get("company_name")
            or company_slug.replace("-", " ").replace("_", " ").title()
        )
        posted = str(j.get("first_published") or "")
        # Extract workplace from metadata (Greenhouse stores it there)
        workplace = ""
        for m in j.get("metadata") or []:
            if str(m.get("name") or "").lower() == "location type":
                workplace = _normalise_workplace(str(m.get("value") or ""))
                break
        # Infer remote from location string if metadata didn't have it
        if not workplace:
            workplace = _normalise_workplace(location)
        if not job_url:
            continue
        jobs.append(
            _make_job(
                title=title,
                company=company,
                location=location,
                url=job_url,
                source="greenhouse",
                posted_at=posted,
                workplace=workplace,
            )
        )
    return jobs


def _parse_greenhouse_html(html: str, company_slug: str, keywords: list) -> list:
    soup = BeautifulSoup(html, "html.parser")
    jobs = []
    kw_lower = [k.lower() for k in keywords]
    company_name = company_slug.replace("-", " ").replace("_", " ").title()
    for opening in soup.find_all("div", class_="opening"):
        a_tag = opening.find("a")
        if not a_tag:
            continue
        title = a_tag.get_text(strip=True)
        href = str(a_tag.get("href") or "")
        job_url = (
            href if href.startswith("http") else f"https://boards.greenhouse.io{href}"
        )
        loc_tag = opening.find("span", attrs={"class": "location"})
        location = loc_tag.get_text(strip=True) if loc_tag else ""
        if kw_lower and not any(kw in title.lower() for kw in kw_lower):
            continue
        if not job_url or job_url == "https://boards.greenhouse.io":
            continue
        jobs.append(
            _make_job(
                title=title,
                company=company_name,
                location=location,
                url=job_url,
                source="greenhouse",
            )
        )
    return jobs


def _scrape_lever(company_slug: str, keywords: list) -> list:
    """
    Uses the Lever public JSON API which returns createdAt (Unix ms timestamp).
    Falls back to HTML scraping if the API returns a non-200.
    """
    api_url = f"https://api.lever.co/v0/postings/{company_slug}?mode=json&limit=250"
    resp = _get(api_url)
    if resp is not None and resp.status_code == 200:
        try:
            return _parse_lever_json(resp.json(), company_slug, keywords)
        except Exception as e:
            log.warning("lever json parse failed for %s [%s]", company_slug, e.__class__.__name__)

    # HTML fallback
    html_url = f"https://jobs.lever.co/{company_slug}"
    resp = _get(html_url)
    if resp is None or resp.status_code != 200:
        return []
    return _parse_lever_html(resp.text, company_slug, keywords)


def _parse_lever_json(postings: list, company_slug: str, keywords: list) -> list:
    jobs = []
    kw_lower = [k.lower() for k in keywords]
    for p in postings:
        title = str(p.get("text") or "")
        if kw_lower and not any(kw in title.lower() for kw in kw_lower):
            continue
        _lever_id = p.get("id", "")
        job_url = str(
            p.get("hostedUrl")
            or (
                f"https://jobs.lever.co/{company_slug}/{_lever_id}" if _lever_id else ""
            )
        )
        cats = p.get("categories") or {}
        location = str(cats.get("location") or "")
        company = str(
            p.get("company") or company_slug.replace("-", " ").replace("_", " ").title()
        )
        # createdAt is Unix ms timestamp
        created_ms = p.get("createdAt")
        posted_at = ""
        if created_ms:
            try:
                posted_at = datetime.fromtimestamp(
                    int(float(created_ms)) / 1000, tz=timezone.utc
                ).strftime("%Y-%m-%dT%H:%M:%SZ")
            except Exception:  # noqa: S110 - one unparseable timestamp, per job; logging would be noise
                pass
        # Lever provides workplaceType and categories.commitment
        workplace = _normalise_workplace(str(p.get("workplaceType") or ""))
        if not workplace:
            workplace = _normalise_workplace(location)
        job_type = _normalise_job_type(str(cats.get("commitment") or ""))
        if not job_url:
            continue
        jobs.append(
            _make_job(
                title=title,
                company=company,
                location=location,
                url=job_url,
                source="lever",
                posted_at=posted_at,
                workplace=workplace,
                job_type=job_type,
            )
        )
    return jobs


def _parse_lever_html(html: str, company_slug: str, keywords: list) -> list:
    soup = BeautifulSoup(html, "html.parser")
    jobs = []
    kw_lower = [k.lower() for k in keywords]
    company_name = company_slug.replace("-", " ").replace("_", " ").title()
    for posting in soup.find_all("div", class_="posting"):
        h5 = posting.find("h5")
        if not h5:
            continue
        title = h5.get_text(strip=True)
        a_tag = posting.find("a", class_="posting-btn-submit") or posting.find("a")
        if not a_tag:
            continue
        href = str(a_tag.get("href") or "")
        job_url = href if href.startswith("http") else f"https://jobs.lever.co{href}"
        loc_tag = posting.find("span", class_="location")
        location = loc_tag.get_text(strip=True) if loc_tag else ""
        if kw_lower and not any(kw in title.lower() for kw in kw_lower):
            continue
        if not job_url:
            continue
        jobs.append(
            _make_job(
                title=title,
                company=company_name,
                location=location,
                url=job_url,
                source="lever",
            )
        )
    return jobs


def _scrape_ashby(company_slug: str, keywords: list) -> list:
    api_url = f"https://api.ashbyhq.com/posting-api/job-board/{company_slug}"
    resp = _get(api_url)
    if resp is None or resp.status_code != 200:
        return []
    try:
        data = resp.json()
    except Exception as e:
        log.warning("ashby json parse failed for %s [%s]", company_slug, e.__class__.__name__)
        return []

    jobs = []
    kw_lower = [k.lower() for k in keywords]
    company_name = company_slug.replace("-", " ").replace("_", " ").title()

    # The API returns either "jobs" or "jobPostings" depending on the endpoint
    postings = data.get("jobs") or data.get("jobPostings") or []

    for posting in postings:
        title = str(posting.get("title") or "")
        posting_id = str(posting.get("id") or "")
        _raw_url = posting.get("jobUrl") or posting.get("applyUrl") or ""
        job_url = (
            str(_raw_url)
            if _raw_url
            else f"https://jobs.ashbyhq.com/{company_slug}/{posting_id}"
        )

        is_remote = bool(posting.get("isRemote"))
        location = str(
            posting.get("locationName")
            or posting.get("location")
            or ("Remote" if is_remote else "")
        )
        workplace = (
            "remote"
            if is_remote
            else _normalise_workplace(str(posting.get("workplaceType") or location))
        )
        job_type = _normalise_job_type(str(posting.get("employmentType") or ""))
        posted_at = str(posting.get("publishedAt") or "")

        desc_html = str(posting.get("descriptionHtml") or "")
        desc = (
            BeautifulSoup(desc_html, "html.parser").get_text(separator="\n")
            if desc_html
            else ""
        )

        if kw_lower and not any(kw in title.lower() for kw in kw_lower):
            continue
        if not job_url:
            continue

        jobs.append(
            _make_job(
                title=title,
                company=company_name,
                location=location,
                url=job_url,
                description=desc[:3000],
                source="ashby",
                workplace=workplace,
                job_type=job_type,
                posted_at=posted_at,
            )
        )
    return jobs


# Per-source wall-clock budget. Search across all 3 sources must finish
# well within the 115s Next.js route handler timeout.
_SOURCE_TIMEOUT = 30  # seconds per source (Greenhouse / Lever / Ashby each get 30s)
_MAX_WORKERS = 50  # concurrent threads — higher = faster fan-out


def _scrape_parallel(
    slugs: list,
    keywords: list,
    scrape_fn,
    max_workers: int = _MAX_WORKERS,
    deadline_seconds: int = _SOURCE_TIMEOUT,
) -> list:
    """
    Scrape company slugs in parallel with a hard wall-clock deadline.
    Any futures still running when the deadline is reached are cancelled
    so the overall search never blocks longer than deadline_seconds.
    """
    results: list = []
    deadline = time.monotonic() + deadline_seconds

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(scrape_fn, slug, keywords): slug for slug in slugs}
        remaining = set(futures.keys())

        while remaining:
            time_left = deadline - time.monotonic()
            if time_left <= 0:
                # Cancel whatever is still pending — already-running threads
                # finish naturally but we stop waiting for them
                for f in remaining:
                    f.cancel()
                break

            done, remaining = wait(
                remaining, timeout=min(time_left, 2), return_when=FIRST_COMPLETED
            )
            for future in done:
                try:
                    results.extend(future.result())
                except Exception as e:
                    log.warning(
                        "scrape task failed for %s [%s]",
                        futures.get(future, "?"),
                        e.__class__.__name__,
                    )

    return results


def is_job_live(url: str):
    """
    Check whether a job posting is still open.
    Returns False if the posting is gone (404/410), True if it still resolves,
    and None if the check itself failed (network error) — callers should NOT
    close a job on None, only on an explicit False.
    """
    if not url:
        return None
    resp = _get(url, timeout=15)
    if resp is None:
        return None
    if resp.status_code in (404, 410):
        return False
    return True


def fetch_job_description(url: str) -> str:
    """Fetch and clean the full job description text from a job posting URL."""
    NOISE_TAGS = {
        "script",
        "style",
        "noscript",
        "header",
        "footer",
        "nav",
        "aside",
        "form",
        "svg",
        "img",
        "button",
        "iframe",
    }
    resp = _get(url, timeout=20)
    if resp is None:
        return ""
    try:
        resp.raise_for_status()
    except Exception:
        log.warning("description fetch got non-200 for %s", url)
        return ""

    soup = BeautifulSoup(resp.text, "html.parser")

    # Platform-specific selectors tried in priority order BEFORE any DOM removal
    # so that nested containers aren't accidentally destroyed
    CSS_SELECTORS = [
        # Lever
        "div.content",
        "div.posting-content",
        "div.posting-description",
        # Greenhouse
        "div#content",
        "div#jobDescriptionText",
        # Ashby
        "div.ashby-job-posting-brief-description",
        # Generic
        "div.job-description",
        "div.jobDescription",
        "div[class*='description']",
        "article",
        "main",
        "section",
    ]

    text = ""
    for sel in CSS_SELECTORS:
        try:
            el = soup.select_one(sel)
        except Exception:  # noqa: S112 - selectors are a fixed list; a bad one just falls through
            continue
        if el:
            candidate = el.get_text(separator="\n", strip=True)
            if len(candidate) > 200:
                text = candidate
                break

    # Fallback: remove noise then find the largest div
    if len(text) < 200:
        try:
            for tag in list(soup.find_all(list(NOISE_TAGS))):
                tag.decompose()
            all_divs = soup.find_all("div")
            if all_divs:
                best = max(all_divs, key=lambda t: len(t.get_text()))
                candidate = best.get_text(separator="\n", strip=True)
                if len(candidate) > len(text):
                    text = candidate
        except Exception:  # noqa: S110 - best-effort fallback; caller checks the result length
            pass

    if len(text) < 200:
        try:
            body = soup.find("body")
            if body:
                text = body.get_text(separator="\n", strip=True)
        except Exception:  # noqa: S110 - last-resort fallback; an empty result is a handled 422
            pass

    text = re.sub(r"\n{3,}", "\n\n", text)
    return "\n".join(ln.strip() for ln in text.splitlines() if ln.strip())[:12000]


def search_jobs(
    keywords: str,
    location: str = "",
    adzuna_app_id: str = "",
    adzuna_app_key: str = "",
    use_greenhouse: bool = True,
    use_lever: bool = True,
    use_ashby: bool = True,
    custom_greenhouse: list | None = None,
    custom_lever: list | None = None,
    custom_ashby: list | None = None,
    target_companies: list | None = None,
) -> list:
    """
    Run all enabled scrapers and return deduplicated, normalised job list.

    If target_companies is provided (list of {platform, slug} dicts), only those
    specific companies are scraped — the full fan-out is skipped. This makes
    company-specific searches complete in 2–5 seconds instead of 20–30.
    """
    kw_list = [k.strip() for k in re.split(r"[,;|]", keywords) if k.strip()]

    all_jobs: list = []

    if target_companies:
        # Every field here is caller-supplied JSON, so read it defensively:
        # a dict without "slug" used to raise KeyError and surface as a 500.
        def _slugs(platform: str) -> list:
            return [
                slug
                for c in target_companies
                if isinstance(c, dict) and c.get("platform") == platform
                for slug in [str(c.get("slug", "")).strip()]
                if slug
            ]

        gh_slugs = _slugs("greenhouse")
        lv_slugs = _slugs("lever")
        ab_slugs = _slugs("ashby")

        if gh_slugs:
            all_jobs.extend(_scrape_parallel(gh_slugs, kw_list, _scrape_greenhouse))
        if lv_slugs:
            all_jobs.extend(_scrape_parallel(lv_slugs, kw_list, _scrape_lever))
        if ab_slugs:
            all_jobs.extend(_scrape_parallel(ab_slugs, kw_list, _scrape_ashby))
    else:
        companies = get_company_lists(custom_greenhouse, custom_lever, custom_ashby)

        if adzuna_app_id and adzuna_app_key:
            all_jobs.extend(
                search_adzuna(keywords, location, 50, adzuna_app_id, adzuna_app_key)
            )

        if use_greenhouse and companies["greenhouse"]:
            all_jobs.extend(
                _scrape_parallel(companies["greenhouse"], kw_list, _scrape_greenhouse)
            )

        if use_lever and companies["lever"]:
            all_jobs.extend(
                _scrape_parallel(companies["lever"], kw_list, _scrape_lever)
            )

        if use_ashby and companies["ashby"]:
            all_jobs.extend(
                _scrape_parallel(companies["ashby"], kw_list, _scrape_ashby)
            )

    # Deduplicate by URL
    seen: set = set()
    unique: list = []
    for job in all_jobs:
        url = job.get("url", "")
        if url and url not in seen:
            seen.add(url)
            unique.append(job)

    # Location filter — applied after scraping since ATS boards don't support location params
    if location:
        unique = _filter_by_location(unique, location)

    return unique


def _filter_by_location(jobs: list, location: str) -> list:
    """
    Filter jobs by location string. Case-insensitive substring match against
    job.location. Special handling for common location values from the UI.
    Remote jobs are always included when location is 'Remote', and also
    included alongside any other location since remote workers can be anywhere.
    """
    loc = location.strip().lower()

    # Mapping from UI values to keywords to match in job.location
    LOC_KEYWORDS: dict[str, list[str]] = {
        "united states": [
            ", us",
            "usa",
            "united states",
            "u.s.",
            "america",
            "new york",
            "san francisco",
            "seattle",
            "austin",
            "chicago",
            "boston",
            "los angeles",
            "denver",
            "atlanta",
            "miami",
            "remote",
        ],
        "europe": [
            "europe",
            "uk",
            "london",
            "berlin",
            "paris",
            "amsterdam",
            "dublin",
            "madrid",
            "lisbon",
            "stockholm",
            "copenhagen",
            "zurich",
            "remote",
        ],
        "india": [
            "india",
            "bangalore",
            "bengaluru",
            "mumbai",
            "delhi",
            "hyderabad",
            "pune",
            "chennai",
            "remote",
        ],
        "remote": [
            "remote",
            "anywhere",
            "distributed",
            "work from home",
            "wfh",
            "worldwide",
            "global",
        ],
    }

    keywords = LOC_KEYWORDS.get(loc)

    if not keywords:
        # Fallback: treat the raw location string as a keyword
        keywords = [loc, "remote"]

    result = []
    for job in jobs:
        job_loc = (job.get("location") or "").lower()
        # Empty location = unknown, include it rather than drop it
        if not job_loc:
            result.append(job)
            continue
        if any(kw in job_loc for kw in keywords):
            result.append(job)

    return result
