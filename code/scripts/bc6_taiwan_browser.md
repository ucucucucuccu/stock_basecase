# BC6：台股真實資料 base case（在瀏覽器裡執行）

雲端環境連不到鉅亨網和 Yahoo，所以 BC6 是在使用者電腦上的瀏覽器分頁裡執行的。
步驟和程式碼都在 `bc6_taiwan_browser.js`（共 9 段）。

1. 用瀏覽器打開 `https://api.cnyes.com/media/api/v1/newslist/category/tw_stock?limit=1`。
   （同一個網域下才能呼叫鉅亨網的新聞 API 和 `ws.api.cnyes.com` 的線圖 API。）
2. 開發者工具 → Console，貼上第 1 段。最後一行 `crawl(days('2024-09-30','2026-09-30'), 700)` 會開始爬新聞，
   等 `window.__cr.running` 變成 `false`。BC6 實測：34.5 分鐘、2,017 次請求、321 MB、0 次錯誤。
3. 貼上第 2 段，執行 `await fetchPrices()`（股價和美股）；再貼第 3–8 段。
4. 依序執行 `__build()`、`__models()`、`__wf({within:true})`、`__subset()`、`__extra()`，
   用 `JSON.stringify(...)` 把每個結果存下來。這些就是 `results/bc6_taiwan.json` 裡的數字。
5. 中覆蓋組 40 檔：照第 9 段的說明，把 `window.__U` 換成 `results/bc6_taiwan.json` 裡的名單，
   補上這些股票的除權息與分割日期，再重跑第 4 步。

注意：
- 爬蟲每次請求間隔 0.7 秒。不要調得更快，也不要同時開好幾個分頁一起跑。
- 新聞原文只留在瀏覽器記憶體裡；這個 base case 只輸出統計量。關掉分頁資料就沒了。
- 檔案裡的除權息與分割日期（`__EX`、`__SPL`）只有權值股 20 檔，是 2026-10-19 從 Yahoo 的 events 取得的。
  中覆蓋組的日期要另外取得（Yahoo events，或 FinMind 的 `TaiwanStockDividendResult`、`TaiwanStockSplitPrice`）。
- 正式版請用 `starter/` 的 Python 程式：股價改用 FinMind，美股改用 yfinance（鉅亨網的美股個股有缺日）。
