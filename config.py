# symbol -> GitHub language name (used in search queries)
LANGUAGES = {
    # Core / original 12
    "PY":  "Python",
    "JS":  "JavaScript",
    "TS":  "TypeScript",
    "RS":  "Rust",
    "GO":  "Go",
    "JV":  "Java",
    "CPP": "C++",
    "CS":  "C#",
    "PHP": "PHP",
    "KT":  "Kotlin",
    "SW":  "Swift",
    "RB":  "Ruby",
    # Expansion set
    "LU":  "Lua",          # game scripting, embedded systems
    "DA":  "Dart",         # Flutter / cross-platform mobile
    "ZG":  "Zig",          # emerging systems language, WASM target
    "EX":  "Elixir",       # distributed / real-time backend
    "SC":  "Scala",        # big-data pipelines (Spark, Kafka)
    "HS":  "Haskell",      # functional, academic but influential
    "JL":  "Julia",        # scientific computing, numerical methods
    "SL":  "Solidity",     # EVM smart contract language
    "SH":  "Shell",        # automation / DevOps infrastructure
    "PL":  "Perl",         # legacy sysadmin, text processing
}

LANGUAGE_META = {
    # -- original set --
    "PY":  {"color": "#3572A5", "category": "AI & Data",       "tag": "Scripting",   "desc": "Dominant language for machine learning, data engineering, and scientific computing.", "pkg": "PyPI",         "pkg_stats": "550k packages"},
    "JS":  {"color": "#f1e05a", "category": "Web & Cloud",     "tag": "Frontend",    "desc": "Universal browser language, runtime via Node.js across client and server.",           "pkg": "npm",          "pkg_stats": "2.4M packages"},
    "TS":  {"color": "#3178c6", "category": "Web & Cloud",     "tag": "Fullstack",   "desc": "Statically-typed JavaScript superset adopted by most large frontend codebases.",      "pkg": "npm",          "pkg_stats": "2.4M packages"},
    "RS":  {"color": "#dea584", "category": "Systems & Web3",  "tag": "High-Perf",   "desc": "Memory-safe systems language with no garbage collector. Fastest adoption in infra.",  "pkg": "crates.io",    "pkg_stats": "150k crates"},
    "GO":  {"color": "#00ADD8", "category": "Cloud & Infra",   "tag": "Services",    "desc": "Compiled, garbage-collected language behind Kubernetes, Docker, and Terraform.",      "pkg": "pkg.go.dev",   "pkg_stats": "Go Modules"},
    "JV":  {"color": "#b07219", "category": "Enterprise",      "tag": "Backend",     "desc": "JVM language powering global banking, Android runtime, and enterprise middleware.",   "pkg": "Maven Central","pkg_stats": "12M artifacts"},
    "CPP": {"color": "#f34b7d", "category": "Systems & Games", "tag": "Native",      "desc": "Zero-overhead compiled language in game engines, browsers, and embedded firmware.",  "pkg": "Conan/vcpkg",  "pkg_stats": "C++ Registry"},
    "CS":  {"color": "#178600", "category": "Enterprise",      "tag": ".NET/Unity",  "desc": "Microsoft-ecosystem language for Azure services, Unity games, and Windows software.","pkg": "NuGet",        "pkg_stats": "420k packages"},
    "PHP": {"color": "#4F5D95", "category": "Web Legacy",      "tag": "Server Web",  "desc": "Server-side scripting language running WordPress, Drupal, and legacy CMSs.",         "pkg": "Packagist",    "pkg_stats": "380k packages"},
    "KT":  {"color": "#A97BFF", "category": "Mobile & JVM",   "tag": "Android",     "desc": "JetBrains-designed language, official first-class Android development language.",     "pkg": "Maven Central","pkg_stats": "Kotlin Multiplatform"},
    "SW":  {"color": "#F05138", "category": "Mobile & Apple",  "tag": "iOS/macOS",   "desc": "Apple-designed compiled language replacing Objective-C across all Apple platforms.",  "pkg": "SwiftPM",      "pkg_stats": "Swift Packages"},
    "RB":  {"color": "#701516", "category": "Web & Scripting", "tag": "Rails",       "desc": "Dynamic scripting language powering Ruby on Rails and rapid-prototype SaaS apps.",   "pkg": "RubyGems",     "pkg_stats": "170k gems"},
    # -- expansion set --
    "LU":  {"color": "#000080", "category": "Embedded & Games","tag": "Scripting",   "desc": "Lightweight embeddable scripting language used in game engines and IoT firmware.",   "pkg": "LuaRocks",     "pkg_stats": "4k rocks"},
    "DA":  {"color": "#00B4AB", "category": "Mobile & Web",    "tag": "Flutter",     "desc": "Google-backed language for Flutter cross-platform apps on mobile, desktop, and web.", "pkg": "pub.dev",      "pkg_stats": "38k packages"},
    "ZG":  {"color": "#F7A41D", "category": "Systems",         "tag": "Emerging",    "desc": "New systems language targeting WebAssembly and embedded without a runtime.",         "pkg": "ziglang.org",  "pkg_stats": "Growing"},
    "EX":  {"color": "#6E4A7E", "category": "Backend & Infra", "tag": "Distributed", "desc": "Erlang-VM language designed for fault-tolerant distributed real-time systems.",      "pkg": "Hex.pm",       "pkg_stats": "16k packages"},
    "SC":  {"color": "#c22d40", "category": "Big Data & JVM",  "tag": "Analytics",   "desc": "Functional-OO hybrid language powering Apache Spark and Kafka stream processing.",   "pkg": "Maven Central","pkg_stats": "Scala ecosystem"},
    "HS":  {"color": "#5e5086", "category": "Academic & FP",   "tag": "Functional",  "desc": "Pure functional language with strong static typing, influential in PL theory.",      "pkg": "Hackage",      "pkg_stats": "16k packages"},
    "JL":  {"color": "#9558B2", "category": "Scientific",      "tag": "Numerical",   "desc": "High-performance language for numerical computing and scientific simulation.",        "pkg": "pkg.julialang.org","pkg_stats": "10k packages"},
    "SL":  {"color": "#A0A0A0", "category": "Web3 & Crypto",   "tag": "Smart Contracts","desc": "EVM-compiled contract language deployed on Ethereum and all EVM-compatible chains.","pkg": "npm/hardhat",  "pkg_stats": "EVM ecosystem"},
    "SH":  {"color": "#89e051", "category": "DevOps & Infra",  "tag": "Automation",  "desc": "POSIX shell scripting for CI/CD pipelines, server automation, and sysadmin tooling.","pkg": "N/A",          "pkg_stats": "Ubiquitous"},
    "PL":  {"color": "#0298c3", "category": "Legacy & Ops",    "tag": "Text/Sys",    "desc": "Text-processing language behind many legacy sysadmin, bioinformatics, and CPAN tools.","pkg": "CPAN",        "pkg_stats": "200k modules"},
}

# Index formula parameters
START_CASH        = 0.0   # ledger starts at zero, no fake money
WINDOW            = 7     # days in the moving average smoother
CAP_MULT          = 2.0   # daily count clipped to 2x trailing median (anti-spam burst)
CAP_LOOKBACK      = 14    # days of history used to compute that median

# DEK reward token parameters
DEK_PER_TRADE_BPS  = 10   # basis points of trade value awarded as DEK (0.10%)
DEK_PER_ORACLE_DAY = 50   # DEK awarded to an oracle node per validated daily submission
DEK_MAX_SUPPLY     = 20_502_006  # strict hard cap
TARGET_BLOCK_TIME_SEC = 86_400  # 24 hours per daily epoch block
DIFFICULTY_LOOKBACK_BLOCKS = 14 # difficulty retargets every 14 blocks based on active oracle count

# Solvency and Anti-Whale Liquidity Controls
MAX_ASSET_OPEN_INTEREST      = 250_000.0  # aggregate exposure cap per language index
MAX_USER_OPEN_INTEREST_RATIO = 0.15       # maximum 15% of open interest held by one user
MIN_ORDER_VALUE              = 1.0        # minimum 1.0 USDT order size
