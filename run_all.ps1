# Re-run the whole reproduction on Windows (PowerShell), from this folder.
# The 2026-10-19 run used Python 3.14.7 and the package versions in env\requirements-lock.txt.
#
#   python -m venv ..\.venv
#   ..\.venv\Scripts\python.exe -m pip install -r env\requirements-lock.txt
#   git clone https://github.com/yumoxu/stocknet-dataset ..\_downloads\stocknet   # commit 330708b5
#   powershell -ExecutionPolicy Bypass -File run_all.ps1 [-SkipDownload]
#
# -X utf8 is a precaution on a Traditional-Chinese Windows (default code page cp950): several scripts
# open or write files without an encoding argument.  With the current StockNet files (pure ASCII)
# and outputs it changes nothing; -I would ignore the PYTHONUTF8 environment variable, hence the flag.
param([switch]$SkipDownload, [string]$Py = "..\.venv\Scripts\python.exe", [string]$StockNet = "..\_downloads\stocknet")
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
New-Item -ItemType Directory -Force results, logs | Out-Null

function Run($name, [string[]]$argv) {
    Write-Host "== $name"
    # redirect through cmd: the log keeps Python's UTF-8 bytes (PowerShell 5.1 would write UTF-16 and
    # turn Python warnings on stderr into PowerShell errors)
    $line = (@($Py) + $argv | ForEach-Object { '"' + $_ + '"' }) -join " "
    cmd /s /c " $line > `"logs\$name.log`" 2>&1 "
    if ($LASTEXITCODE -ne 0) { throw "$name failed, see logs\$name.log" }
}

# base cases BC1-BC5 (no network except the StockNet clone)
Run bc1 @("-I", "-X", "utf8", "code\scripts\bc1_power_effective_n.py", "results")
Run bc2 @("-I", "-X", "utf8", "code\scripts\bc2_synthetic_leakage.py", "results")
Run bc3 @("-I", "-X", "utf8", "code\scripts\bc3_stocknet_real.py", $StockNet, "results")
Run bc5 @("-I", "-X", "utf8", "code\scripts\bc5_stocknet_volatility.py", $StockNet, "results")

# starter steps 1-5 (BC6 in Python)
if (-not $SkipDownload) {
    # FinMind: about 181 requests; the free limit without a token is 300 per hour
    Run step1_prices @("-X", "utf8", "code\starter\step1_prices.py", "--universe", "both", "--start", "2024-06-01",
                       "--end", "2026-10-16", "--out", "data\prices", "--yahoo-check")
    Run fetch_taiex @("-X", "utf8", "code\fetch_taiex.py", "--out", "data\prices")
    # about 45 minutes at 1 request per second; resumes if interrupted
    Run step2_crawl @("-X", "utf8", "code\starter\step2_cnyes_crawl.py", "--start", "2024-09-30", "--end", "2026-09-30",
                      "--out", "data\news_cnyes.jsonl")
}
Run step3_selftest @("-X", "utf8", "code\starter\step3_align.py", "--selftest")
Run step3_align @("-X", "utf8", "code\starter\step3_align.py", "--news", "data\news_cnyes.jsonl",
                  "--calendar", "data\prices\tw_trading_dates.csv", "--out", "data\news_buckets.csv")
Run news_stats @("-X", "utf8", "code\news_stats.py", "data\news_cnyes.jsonl", "data\prices\tw_trading_dates.csv", "results\news_stats.json")
foreach ($u in "mid", "mega") {
    Run "step4_$u" @("-X", "utf8", "code\starter\step4_baseline_models.py", "--prices", "data\prices",
                     "--news", "data\news_cnyes.jsonl", "--universe", $u, "--walkforward", "--out", "results\step4_$u.json")
    Run "step4_supplement_$u" @("-X", "utf8", "code\step4_supplement.py", "--prices", "data\prices",
                                "--news", "data\news_cnyes.jsonl", "--universe", $u,
                                "--taiex", "data\prices\taiex_finmind.csv", "data\prices\taiex_yahoo.csv",
                                "--out", "results\step4_supplement_$u.json")
}
# naive and HAR baselines on the same rows and test period as step 4
foreach ($u in "mid", "mega") {
    Run "baselines_$u" @("-X", "utf8", "code\baselines.py", "--prices", "data\prices", "--news", "data\news_cnyes.jsonl",
                         "--universe", $u, "--out", "results\baselines_$u.json")
}
# step 5 needs the gated google/embeddinggemma-300m (accept the licence on Hugging Face first);
# --dry-run uses random vectors and only tests the pipeline
Run step5_dryrun @("-X", "utf8", "code\starter\step5_embed.py", "--news", "data\news_cnyes.jsonl",
                   "--calendar", "data\prices\tw_trading_dates.csv", "--dim", "64", "--dry-run",
                   "--out", "data\emb_overnight_DRYRUN_random.npz")
Run step4_mid_emb_dryrun @("-X", "utf8", "code\starter\step4_baseline_models.py", "--prices", "data\prices",
                           "--news", "data\news_cnyes.jsonl", "--universe", "mid", "--emb", "data\emb_overnight_DRYRUN_random.npz",
                           "--pca", "8", "16", "32", "64", "--reps", "200", "--out", "results\step4_mid_emb_DRYRUN_random.json")
Run check_section32 @("-X", "utf8", "code\check_section32.py", "data\prices", "results\check_section32.json")

# number-by-number comparison with the original results\*.json
Run compare @("-X", "utf8", "code\compare_results.py", "original_results", "results", "results\compare_bc1_bc2_bc3_bc5.csv",
              "bc1_power_effective_n.json", "bc2_synthetic_leakage.json", "bc3_stocknet_real.json", "bc5_stocknet_volatility.json")
Run bc6_table @("-X", "utf8", "code\bc6_comparison.py", "original_results\bc6_taiwan.json", "results", "results\bc6_vs_step4.csv")
Write-Host "done"
