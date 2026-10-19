# Pre-market news and Taiwan stock volatility — base cases

預測學習（Predictive Learning from Data，115-1）期中專題的 base case 與程式。

**問題：** 每個交易日 08:45（開盤前），用前一交易日 13:30 以後的盤前新聞，能不能在股價歷史和美股夜間行情之外，多預測一點台股當天的波動（對數真實振幅）？增量出現在哪些日子、哪些股票？漲跌方向用同一套流程預測，只當對照組。

## 目前結果（2026-10-19 組內重現）

| | 權值股組（20 檔） | 中覆蓋組（40 檔） |
|---|---|---|
| 最好的簡單基準（EWMA）within R² | 0.232 | 0.204 |
| M0：HAR | 0.277 | 0.265 |
| M1：HAR＋大盤＋美股夜間（新聞模型要贏過的基準） | 0.306 | 0.287 |
| 加新聞篇數（M2 − M1） | −0.0006 | +0.0001 |
| 財報／營收新聞日：加兩個關鍵字旗標（M1e − M1） | +0.019（不顯著） | **+0.078（0.021–0.130）** |
| 方向準確率／多數類別 | 51.1%／52.2% | 55.0%／55.4% |

測試期 2025-10 到 2026-09（236 個交易日），walk-forward 每月重估；括號是以交易日重抽的 95% 信賴區間。R² 的基準是各股測試期自己的平均，是最嚴格的算法，解讀見 `docs/analysis_report.md` 5.6 節。完整設定見 [EXPERIMENTS.md](EXPERIMENTS.md)。

## 目錄

| 路徑 | 內容 |
|---|---|
| `EXPERIMENTS.md` | BC1–BC6 與 baseline 的實驗設定和結果 |
| `code/scripts/` | BC1、BC2、BC3、BC5（Python）與 BC6 瀏覽器版（JavaScript） |
| `code/starter/` | step1 股價、step2 新聞爬取、step3 時段對齊、step4 模型、step5 embedding |
| `code/*.py` | 重現與補充分析：`baselines.py`、`step4_supplement.py`、`bc6_comparison.py`、`compare_results.py`、`news_stats.py`、`check_section32.py`、`fetch_taiex.py` |
| `results/` | 2026-10-19 組內重現的輸出 |
| `original_results/` | 第一次在雲端與瀏覽器跑出的結果（比對用） |
| `logs/` | 重現時每一步的終端機輸出 |
| `docs/analysis_report.md` | 開工前分析報告（第二版，含重現結果） |
| `docs/reproduction_2026-10-19.md` | 組內重現報告：遇到的問題與處理 |
| `run_all.ps1` | Windows 一鍵重跑 |
| `env/requirements-lock.txt` | 重現時的套件版本（Python 3.14） |

## 重跑

```powershell
python -m venv ..\.venv
..\.venv\Scripts\python.exe -m pip install -r env\requirements-lock.txt
git clone https://github.com/yumoxu/stocknet-dataset ..\_downloads\stocknet
powershell -ExecutionPolicy Bypass -File run_all.ps1
```

- 第一次跑會下載股價（FinMind，約 180 次請求）和新聞（鉅亨網，約 45 分鐘）。同一小時內重跑 FinMind 會超過未註冊的上限，請先免費註冊並設定環境變數 `FINMIND_TOKEN`。
- step5 的預設模型 `google/embeddinggemma-300m` 在 Hugging Face 要先登入並同意 Gemma 授權。

## 資料政策

- **不放資料：** `data/`（股價、新聞原文、embedding）不進 repo，用程式重新下載。
- **新聞原文只限組內使用：** 財經新聞受著作權保護（著作權法第 9 條只排除單純傳達事實的報導）。報告只放統計結果和改寫過的例子。
- `results/`、`original_results/` 只有統計量，沒有新聞原文。
- 只做課堂研究，不做真錢交易，也不提供投資建議。
