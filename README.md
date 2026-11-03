# LangIndex

LangIndex is an open developer adoption index and deterministic market protocol. It measures programming language utilization across public version control systems and software package registries, computing a continuous normalized index for each asset.

## System Architecture

The protocol consists of four distinct decoupled layers:

1. Data Collector (`collector.py`):
   Queries public endpoints across GitHub, PyPI, npm, and crates.io.
   Filters repository counts using non-fork parameters (`fork:false`) and pulls representative daily package download metrics.
   Stores timestamped integers into SQLite under WAL mode.

2. Deterministic Index Engine (`index_engine.py`):
   Processes raw observations through a 5-stage transformation pipeline:
   - Median burst suppression: Truncates daily counts exceeding 2.0x of the trailing 14-day median.
   - Sybil discount: Applies an initial 0.85 scaling factor against unverified single-node telemetry.
   - 7-day smoothing: Computes a rolling 7-day simple moving average to eliminate weekday versus weekend commit variance.
   - Relative share calculation: Evaluates each language share as a fraction of total ecosystem activity across all tracked assets.
   - Base-100 normalization: Re-indexes each language against its share on day one of observation.

3. Execution and Ledger Core (`trading.py`, `db.py`):
   Maintains user accounts identified by 160-bit hex keypairs.
   Manages spot balance accounting, position valuation, weighted average cost basis, and DEK protocol incentive emissions (0.10% basis points per executed order volume).

4. HTTP Transport and Interface (`api.py`, `static/index.html`):
   FastAPI service exposing REST endpoints for market depth, asset statistics, ledger verification, and the genesis manifest.
   Trading terminal UI rendered with IBM Plex typography, native Canvas chart pipelines, and an ecosystem distribution bar.

## Mathematical Formulation

Let $C_{i,t}$ denote the raw activity observation for language $i$ on day $t$.

1. Median clipping:
   $$C'_{i,t} = \min\left(C_{i,t}, 2.0 \cdot \text{median}(C_{i, t-14 \dots t-1})\right)$$

2. Sybil discount:
   $$\tilde{C}_{i,t} = 0.85 \cdot C'_{i,t}$$

3. Seven-day rolling average:
   $$A_{i,t} = \frac{1}{7} \sum_{k=0}^{6} \tilde{C}_{i, t-k}$$

4. Relative ecosystem proportion:
   $$S_{i,t} = \frac{A_{i,t}}{\sum_{j} A_{j,t}}$$

5. Index price quotation:
   $$P_{i,t} = 100.0 \cdot \frac{S_{i,t}}{S_{i,0}}$$

User trade orders do not shift $P_{i,t}$. The quotation reflects code production and distribution metrics rather than capital inflow.

## Tracked Assets

| Symbol | Language | Category | Primary Registry Source |
| :--- | :--- | :--- | :--- |
| PY | Python | AI and Data | PyPI |
| JS | JavaScript | Web and Cloud | npm |
| TS | TypeScript | Web and Cloud | npm |
| RS | Rust | Systems and Web3 | crates.io |
| GO | Go | Cloud and Infra | pkg.go.dev |
| JV | Java | Enterprise | Maven Central |
| CPP | C++ | Systems and Games | Conan / vcpkg |
| CS | C# | Enterprise and Games | NuGet |
| PHP | PHP | Web Legacy | Packagist |
| KT | Kotlin | Mobile and JVM | Maven Central |
| SW | Swift | Mobile and Apple | SwiftPM |
| RB | Ruby | Web and Scripting | RubyGems |
| LU | Lua | Embedded and Games | LuaRocks |
| DA | Dart | Mobile and Client | pub.dev |
| ZG | Zig | Systems and WebAssembly | ziglang.org |
| EX | Elixir | Distributed Backend | Hex.pm |
| SC | Scala | Big Data Pipelines | Maven Central |
| HS | Haskell | Functional Theory | Hackage |
| JL | Julia | Scientific Computing | pkg.julialang.org |
| SL | Solidity | EVM Smart Contracts | npm / hardhat |
| SH | Shell | DevOps and System Admin | POSIX standard |
| PL | Perl | System Automation | CPAN |

## Genesis Verification

The genesis block is mathematically anchored to SHA-256 state:

- Protocol: LangIndex Protocol - Developer Adoption Index
- Genesis Hash: `87be4735c1f0c9f85c5e2822b893c097dfa9690ccd4bfa95374036b537090def`
- Signer Public Key: `0x7a892bF584C8bEb8f682057F7392aA7b25F18dE0`

Verification via standard utilities:
```bash
curl -s http://localhost:8000/api/genesis | jq .
```

## Running the Protocol

### Requirements
- Python 3.10+
- SQLite 3.35+

### Installation
```bash
git clone https://github.com/NaelVask/langindex.git
cd langindex
pip install -r requirements.txt
```

### Ingestion and Index Calculation
```bash
# Optional: Set GITHUB_TOKEN for 30 req/min rate limit instead of default 10 req/min
export GITHUB_TOKEN="ghp_your_token_here"

# Collect telemetry for the preceding 7 days
python collector.py 7

# Rebuild index series
python index_engine.py
```

### Start Local Node
```bash
uvicorn api:app --host 127.0.0.1 --port 8000
```
Terminal interface available at `http://127.0.0.1:8000`.

### Tor Hidden Service Deployment
To serve without dependency on public DNS or commercial hosting providers:

Add to `torrc`:
```text
HiddenServiceDir /var/lib/tor/langindex_service/
HiddenServicePort 80 127.0.0.1:8000
```

Start the Tor daemon and read the generated `.onion` hostname:
```bash
cat /var/lib/tor/langindex_service/hostname
```

## Support Protocol Development & On-Chain Liquidity
Langdex is an autonomous, open-source protocol built with zero venture capital, no pre-mine, and no token sale.

To support autonomous smart contract deployment and initial decentralized liquidity pool pairing (Uniswap / Aerodrome on Ethereum L2) to make DEK swappable on-chain for BTC and ETH:

- **Bitcoin Donation Address (Native SegWit):**
  `bc1qtpfpmm2f3eghnhp8ke854gsql045tqxza708e2`

All contributions are directed exclusively toward bootstrapping cross-chain liquidity pools and sustained oracle node infrastructure.

## License
MIT License. Author: Nael Vask.
