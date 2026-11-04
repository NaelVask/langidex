"""Component 1: Multi-source data ingestion and authentic Git object verification.

Sources live:
  - GitHub Search API   -> repos pushed per language per day (fork:false)
  - PyPI Stats API      -> daily package downloads for top Python packages
  - npm Stats API       -> daily package downloads for top JS/TS packages
  - crates.io API       -> recent download counts for top Rust crates
  - Codeberg Gitea API  -> independent European open-source Git repo search
  - GitLab Public API   -> active projects per language
  - GitHub Git Trees    -> authentic commit SHA-1 and tree SHA-1 object extraction
"""
import os, sys, time, datetime as dt, requests, hmac, hashlib
import urllib.request, json
from config import LANGUAGES
from db import conn, init

# -- helpers ----------------------------------------------------------------

def get_token():
    t = os.environ.get("GITHUB_TOKEN")
    if not t and os.path.exists(".env"):
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("GITHUB_TOKEN="):
                    t = line.split("=", 1)[1].strip().strip('"').strip("'")
    return t

def safe_get(url, params=None, headers=None, timeout=20, label=""):
    """HTTP GET with retry logic for transient network failures."""
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=timeout)
            if r.status_code == 429:
                time.sleep(10)
                continue
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt == 2:
                print(f"  [warn] {label} failed after 3 attempts: {e}")
                return None
            time.sleep(4)

# -- GitHub source -----------------------------------------------------------

def count_github_repos(lang, day, token=None, max_retries=4):
    url = "https://api.github.com/search/repositories"
    q = f"language:{lang} pushed:{day} fork:false"
    params = {"q": q, "per_page": 1}
    headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "Langdex/1.0"}
    if token:
        headers["Authorization"] = f"token {token}"
    backoff = 3
    for attempt in range(max_retries):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=15)
            if r.status_code == 200:
                return r.json().get("total_count", 0)
            elif r.status_code == 403:
                reset = int(r.headers.get("X-RateLimit-Reset", time.time() + 60))
                wait = max(int(reset - time.time()) + 1, 5)
                time.sleep(min(wait, 60))
            elif r.status_code == 422:
                return None
            else:
                time.sleep(backoff)
                backoff *= 2
        except Exception:
            time.sleep(backoff)
            backoff *= 2
    return None

# -- PyPI source (Python) ---------------------------------------------------

PYPI_TOP_PACKAGES = [
    "requests", "boto3", "urllib3", "setuptools", "certifi",
    "idna", "charset-normalizer", "typing-extensions", "pip", "packaging"
]

def get_pypi_downloads(day):
    total = 0
    headers = {"User-Agent": "Langdex/1.0"}
    for pkg in PYPI_TOP_PACKAGES:
        url = f"https://api.pepy.tech/api/v2/projects/{pkg}"
        data = safe_get(url, headers=headers, label=f"PyPI-{pkg}")
        if data and "downloads" in data:
            day_downloads = data["downloads"].get(day, {})
            if isinstance(day_downloads, dict):
                total += sum(day_downloads.values())
            elif isinstance(day_downloads, int):
                total += day_downloads
        time.sleep(0.1)
    if total == 0:
        for pkg in PYPI_TOP_PACKAGES[:4]:
            url = f"https://pypistats.org/api/packages/{pkg}/recent"
            d = safe_get(url, headers=headers, label=f"pypistats-{pkg}")
            if d and "data" in d:
                total += d["data"].get("last_day", 0)
            time.sleep(0.1)
    return total

# -- npm source (JavaScript / TypeScript) -----------------------------------

NPM_TOP_PACKAGES = [
    "lodash", "chalk", "request", "express", "react",
    "commander", "moment", "axios", "tslib", "debug"
]

def get_npm_downloads(day):
    total = 0
    headers = {"User-Agent": "Langdex/1.0"}
    for pkg in NPM_TOP_PACKAGES:
        url = f"https://api.npmjs.org/downloads/point/{day}/{pkg}"
        d = safe_get(url, headers=headers, label=f"npm-{pkg}")
        if d and "downloads" in d:
            total += d["downloads"]
        time.sleep(0.05)
    return total

# -- crates.io source (Rust) ------------------------------------------------

CRATES_TOP = ["syn", "quote", "proc-macro2", "rand", "serde", "tokio", "cfg-if", "libc"]

def get_crates_downloads():
    total = 0
    headers = {"User-Agent": "Langdex-Indexer (contact@langdex.protocol)"}
    for crate in CRATES_TOP:
        url = f"https://crates.io/api/v1/crates/{crate}"
        d = safe_get(url, headers=headers, label=f"crates-{crate}")
        if d and "crate" in d:
            total += d["crate"].get("recent_downloads", 0) // 90
        time.sleep(0.1)
    return total

# -- Codeberg source (Gitea API - Independent European Git Forge) -----------

CODEBERG_LANG_MAP = {
    "PY": "Python", "RS": "Rust", "GO": "Go", "JS": "JavaScript", "TS": "TypeScript",
    "CPP": "C++", "CS": "C#", "JV": "Java", "PHP": "PHP", "KT": "Kotlin",
    "SW": "Swift", "RB": "Ruby", "SL": "Solidity", "ZG": "Zig", "EX": "Elixir",
    "DA": "Dart", "LU": "Lua", "SC": "Scala", "HS": "Haskell", "JL": "Julia",
    "SH": "Shell", "PL": "Perl"
}

def get_codeberg_repos(sym: str) -> int:
    lang_name = CODEBERG_LANG_MAP.get(sym)
    if not lang_name:
        return 0
    url = "https://codeberg.org/api/v1/repos/search"
    params = {"lang": lang_name, "limit": 1}
    headers = {"Accept": "application/json", "User-Agent": "Langdex-Oracle/1.0"}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=10)
        if r.status_code == 200:
            total_header = r.headers.get("x-total-count") or r.headers.get("X-Total-Count")
            if total_header and total_header.isdigit():
                return int(total_header)
            data = r.json()
            if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
                return len(data["data"])
    except Exception:
        pass
    return 0

# -- GitLab source (Public REST API) ----------------------------------------

def get_gitlab_activity(sym: str) -> int:
    lang_name = CODEBERG_LANG_MAP.get(sym)
    if not lang_name:
        return 0
    url = "https://gitlab.com/api/v4/projects"
    params = {"with_programming_language": lang_name, "per_page": 20, "order_by": "last_activity_at"}
    headers = {"User-Agent": "Langdex-Oracle/1.0"}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list):
                return len(data)
    except Exception:
        pass
    return 0

# -- Composite weights -------------------------------------------------------

WEIGHTS = {
    "PY": {"gh": 0.65, "pkg": 0.35, "scale": 0.0001},
    "JS": {"gh": 0.65, "pkg": 0.35, "scale": 0.00005},
    "TS": {"gh": 0.65, "pkg": 0.35, "scale": 0.0001},
    "RS": {"gh": 0.70, "pkg": 0.30, "scale": 0.001},
}

def compute_composite(sym, gh_count, day):
    cb_count = get_codeberg_repos(sym)
    gl_count = get_gitlab_activity(sym)
    extra_forge_count = cb_count + gl_count

    if sym not in WEIGHTS:
        return gh_count + extra_forge_count

    cfg = WEIGHTS[sym]
    pkg_count = 0
    if sym == "PY":
        pkg_count = get_pypi_downloads(day)
    elif sym in ("JS", "TS"):
        pkg_count = get_npm_downloads(day)
    elif sym == "RS":
        pkg_count = get_crates_downloads()

    if pkg_count == 0:
        return gh_count + extra_forge_count

    scaled_pkg = int(pkg_count * cfg["scale"])
    composite = int(gh_count * cfg["gh"] + scaled_pkg * cfg["pkg"]) + extra_forge_count
    return max(composite, gh_count)

# -- Main collector loop -----------------------------------------------------

def collect(day):
    token = get_token()
    print(f"[*] Starting ingestion for epoch: {day}")

    for sym, lang in LANGUAGES.items():
        gh = count_github_repos(lang, day, token=token)
        if gh is None:
            continue
        with conn() as c:
            c.execute(
                "INSERT INTO raw_counts(day, symbol, count, source) VALUES (?, ?, ?, 'github') "
                "ON CONFLICT(day, symbol, source) DO UPDATE SET count=excluded.count",
                (day, sym, gh)
            )

        composite = compute_composite(sym, gh, day)
        with conn() as c:
            c.execute(
                "INSERT INTO raw_counts(day, symbol, count, source) VALUES (?, ?, ?, 'composite') "
                "ON CONFLICT(day, symbol, source) DO UPDATE SET count=excluded.count",
                (day, sym, composite)
            )

# -- Authentic Git Object Verification & Merkle Sharding ---------------------

REPRESENTATIVE_REPOS = {
    "PY": ["python/cpython", "psf/requests", "pallets/flask", "pydantic/pydantic", "encode/httpx"],
    "RS": ["rust-lang/rust", "tokio-rs/tokio", "serde-rs/serde", "hyperium/hyper", "BurntSushi/ripgrep"],
    "GO": ["golang/go", "kubernetes/kubernetes", "moby/moby", "gin-gonic/gin", "prometheus/prometheus"],
    "JS": ["facebook/react", "nodejs/node", "expressjs/express", "lodash/lodash", "axios/axios"],
    "TS": ["microsoft/typescript", "angular/angular", "nestjs/nest", "denoland/deno"],
    "CPP": ["llvm/llvm-project", "electron/electron", "opencv/opencv"],
    "CS": ["dotnet/runtime", "dotnet/aspnetcore", "jellyfin/jellyfin"],
    "JV": ["spring-projects/spring-boot", "elastic/elasticsearch", "apache/kafka"],
    "PHP": ["laravel/laravel", "symfony/symfony"],
    "KT": ["JetBrains/kotlin", "square/okhttp"],
    "SW": ["apple/swift", "Alamofire/Alamofire"],
    "RB": ["rails/rails", "jekyll/jekyll"],
    "SL": ["ethereum/solidity", "OpenZeppelin/openzeppelin-contracts"]
}

def resolve_repo_git_objects(repo_name: str) -> tuple[str, str]:
    """Authentically resolves real Git commit SHA and tree SHA directly from the repository.
    Returns: (commit_sha, tree_sha)
    """
    token = get_token()
    headers = {"User-Agent": "Langdex/1.0", "Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"

    url = f"https://api.github.com/repos/{repo_name}/commits/HEAD"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            commit_sha = data.get("sha")
            tree_sha = data.get("commit", {}).get("tree", {}).get("sha")
            if commit_sha and tree_sha:
                return commit_sha, tree_sha
    except Exception:
        pass

    raise ConnectionError(f"Could not reach remote git objects for {repo_name}. Mining requires live network access.")

def compute_node_shard(node_address: str, prev_block_hash: str, candidate_repo_list: list, shard_size: int = 10) -> list:
    """Deterministic Sharded Sampling:
    Assigns a deterministic shard of candidate repositories to node_address seeded by prev_block_hash."""
    if not candidate_repo_list:
        return []
    total = len(candidate_repo_list)
    shard_size = min(shard_size, total)

    seed_bytes = hashlib.sha256(f"{node_address}:{prev_block_hash}".encode()).digest()
    seed_int = int.from_bytes(seed_bytes, "big")

    selected = []
    step = max(1, total // shard_size)
    for i in range(shard_size):
        idx = (seed_int + (i * step) + (i * 37)) % total
        selected.append(candidate_repo_list[idx])
    return selected

def compute_potop_proof(miner_private_key_hex: str, repo_records: list, epoch_day: str) -> dict:
    """Builds HMAC Merkle root across verified repository commit trees.
    The HMAC is keyed to the miner's Ed25519 private key, proving possession of the private key."""
    leaf_hashes = []
    key_bytes = hashlib.sha256(miner_private_key_hex.encode()).digest()

    for r in repo_records:
        commit_hash = r.get("commit_hash", "")
        tree_hash = r.get("tree_hash", "")
        repo_name = r.get("repo_name", "")
        msg = f"{repo_name}:{commit_hash}:{tree_hash}:{epoch_day}".encode()
        leaf_hmac = hmac.new(key_bytes, msg, hashlib.sha256).hexdigest()
        leaf_hashes.append(leaf_hmac)

    # Balanced binary Merkle tree
    current_level = sorted(leaf_hashes) if leaf_hashes else ["0" * 64]
    while len(current_level) > 1:
        next_level = []
        for i in range(0, len(current_level), 2):
            left = current_level[i]
            right = current_level[i + 1] if i + 1 < len(current_level) else left
            combined = hashlib.sha256(f"{left}{right}".encode()).hexdigest()
            next_level.append(combined)
        current_level = next_level

    return {
        "merkle_root": current_level[0],
        "leaf_count": len(leaf_hashes),
        "epoch_day": epoch_day
    }

def verify_and_record_proofs(node_pubkey: str, miner_privkey: str, epoch_day: str, prev_block_hash: str = "87be4735c1f0c9f85c5e2822b893c097dfa9690ccd4bfa95374036b537090def") -> int:
    """Verifies assigned repository shard and commits Proof of Tree Object Possession records to the ledger."""
    all_candidates = []
    for sym, repos in REPRESENTATIVE_REPOS.items():
        for r in repos:
            all_candidates.append({"symbol": sym, "repo_name": r})

    shard = compute_node_shard(node_pubkey, prev_block_hash, all_candidates, shard_size=10)
    verified_records = []

    for item in shard:
        sym = item["symbol"]
        repo_name = item["repo_name"]
        commit_sha, tree_sha = resolve_repo_git_objects(repo_name)
        verified_records.append({
            "symbol": sym,
            "repo_name": repo_name,
            "commit_hash": commit_sha,
            "tree_hash": tree_sha
        })

    potop_proof = compute_potop_proof(miner_privkey, verified_records, epoch_day)
    merkle_root = potop_proof["merkle_root"]

    with conn() as c:
        for r in verified_records:
            c.execute("""
                INSERT INTO verified_proofs(epoch_day, symbol, repo_name, commit_hash, tree_hash, verifier_node, merkle_root)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (epoch_day, r["symbol"], r["repo_name"], r["commit_hash"], r["tree_hash"], node_pubkey, merkle_root))

    return len(verified_records)

if __name__ == "__main__":
    init()
