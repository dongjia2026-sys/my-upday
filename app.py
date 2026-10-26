<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AssetHorizon - 资产底仓与微信提醒看板</title>
    <style>
        :root {
            --bg-color: #0f172a;
            --card-bg: #1e293b;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --accent: #38bdf8;
            --accent-hover: #0ea5e9;
            --success: #22c55e;
            --danger: #ef4444;
            --border: #334155;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-main);
            margin: 0;
            padding: 20px;
            box-sizing: border-box;
        }
        .container {
            max-width: 1000px;
            margin: 0 auto;
        }
        .card {
            background-color: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 24px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
        }
        h2, h3 {
            margin-top: 0;
            color: var(--accent);
        }
        .form-group {
            margin-bottom: 16px;
        }
        label {
            display: block;
            margin-bottom: 6px;
            font-weight: 500;
            color: var(--text-muted);
        }
        input, select {
            width: 100%;
            padding: 10px 14px;
            background-color: #0f172a;
            border: 1px solid var(--border);
            border-radius: 6px;
            color: var(--text-main);
            font-size: 14px;
            box-sizing: border-box;
        }
        input:focus {
            outline: none;
            border-color: var(--accent);
        }
        .btn {
            background-color: var(--accent);
            color: #0f172a;
            border: none;
            padding: 10px 18px;
            border-radius: 6px;
            font-weight: 600;
            cursor: pointer;
            transition: background-color 0.2s;
        }
        .btn:hover {
            background-color: var(--accent-hover);
        }
        .btn-danger {
            background-color: var(--danger);
            color: white;
        }
        .btn-danger:hover {
            background-color: #dc2626;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 16px;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid var(--border);
            font-size: 14px;
        }
        th {
            color: var(--text-muted);
            font-weight: 600;
        }
        .console-box {
            background-color: #0b0f19;
            border: 1px solid var(--border);
            border-radius: 6px;
            padding: 12px;
            font-family: monospace;
            font-size: 13px;
            color: #34d399;
            min-height: 50px;
            max-height: 150px;
            overflow-y: auto;
            margin-top: 12px;
            white-space: pre-wrap;
        }
        .grid-2 {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 16px;
        }
        @media (max-width: 768px) {
            .grid-2 { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>

<div class="container">
    
    <!-- 模块一：个股底仓与终极目标校准看板 -->
    <div class="card">
        <h2>📊 真实底仓与终极目标校准看板</h2>
        <p style="color: var(--text-muted); font-size: 14px;">管理您的每一支个股持仓、成本价以及长期终极目标股数。</p>
        
        <div id="stockForm" style="background: rgba(255,255,255,0.02); padding: 16px; border-radius: 8px; border: 1px solid var(--border); margin-bottom: 16px;">
            <h3 style="font-size: 16px; margin-bottom: 12px;">➕ 添加 / 修改个股持仓</h3>
            <div class="grid-2">
                <div class="form-group">
                    <label>股票名称 / 股票代码 (如 TSLA)</label>
                    <input type="text" id="stockName" placeholder="例如: 特斯拉 (TSLA)">
                </div>
                <div class="form-group">
                    <label>当前持有股数</label>
                    <input type="number" id="currentShares" placeholder="例如: 10">
                </div>
            </div>
            <div class="grid-2">
                <div class="form-group">
                    <label>当前成本价 (USD / RMB)</label>
                    <input type="number" step="0.01" id="currentCost" placeholder="例如: 120.00">
                </div>
                <div class="form-group">
                    <label>终极目标持有总股数</label>
                    <input type="number" id="targetShares" placeholder="例如: 100">
                </div>
            </div>
            <button class="btn" onclick="saveStock()">💾 保存底仓到数据库</button>
        </div>

        <h3>📋 当前持仓明细列表</h3>
        <div style="overflow-x: auto;">
            <table>
                <thead>
                    <tr>
                        <th>股票名称/代码</th>
                        <th>当前持股</th>
                        <th>成本价</th>
                        <th>当前市值/投入</th>
                        <th>终极目标股数</th>
                        <th>目标达成率</th>
                        <th>操作</th>
                    </tr>
                </thead>
                <tbody id="stockTableBody">
                    <!-- 动态加载 -->
                </tbody>
            </table>
        </div>
    </div>

    <!-- 模块二：Server酱微信弹窗配置与网页端自检 -->
    <div class="card">
        <h2>🔔 微信弹窗配置 (Server酱 API Key)</h2>
        <p style="color: var(--text-muted); font-size: 14px;">配置您的 Server酱 SendKey，系统会自动持久化存储。点击测试后，网页端将直接进行 API 自检并返回回执结果。</p>
        
        <div class="form-group">
            <label>Server酱 SendKey (支持本地自动持久化记忆)</label>
            <input type="text" id="sendKeyInput" placeholder="请输入您的 Server酱 SendKey (例如 sctp... 或 SCU...)">
        </div>

        <div style="display: flex; gap: 12px; flex-wrap: wrap;">
            <button class="btn" onclick="saveServerKey()">💾 保存配置到本地</button>
            <button class="btn" style="background-color: #10b981; color: white;" onclick="testServerChanPush()">🚀 运行网页端自检并发送测试</button>
        </div>

        <div class="form-group" style="margin-top: 16px;">
            <label>💻 网页端自检控制台 (API 回执结果)</label>
            <div id="consoleOutput" class="console-box">等待测试... 键入 Key 后点击上方按钮进行网页端主动自检。</div>
        </div>
    </div>

</div>

<script>
    // --- 1. 带强容错保护的个股底仓管理逻辑 ---
    let stocks = [];
    try {
        const savedStocks = localStorage.getItem('portfolio_stocks');
        stocks = savedStocks ? JSON.parse(savedStocks) : null;
        if (!Array.isArray(stocks)) {
            throw new Error('Not an array');
        }
    } catch (e) {
        // 如果本地数据损坏，启用默认安全数据并重置
        stocks = [
            { name: '特斯拉 (TSLA)', shares: 10, cost: 120, target: 100 },
            { name: 'SpaceX', shares: 30, cost: 140, target: 150 },
            { name: '英伟达 (NVDA)', shares: 15, cost: 110, target: 80 }
        ];
        localStorage.setItem('portfolio_stocks', JSON.stringify(stocks));
    }

    function renderStocks() {
        const tbody = document.getElementById('stockTableBody');
        if (!tbody) return;
        tbody.innerHTML = '';
        if (stocks.length === 0) {
            tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-muted);">暂无持仓数据，请在上方向添加。</td></tr>`;
            return;
        }
        stocks.forEach((s, index) => {
            const shares = Number(s.shares) || 0;
            const cost = Number(s.cost) || 0;
            const target = Number(s.target) || 1;
            const invested = (shares * cost).toFixed(2);
            const rate = target > 0 ? ((shares / target) * 100).toFixed(1) : 0;
            
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><strong>${s.name || '未命名'}</strong></td>
                <td>${shares} 股</td>
                <td>$${cost}</td>
                <td>$${invested}</td>
                <td>${target} 股</td>
                <td><span style="color: ${rate >= 100 ? 'var(--success)' : 'var(--accent)'}; font-weight: 600;">${rate}%</span></td>
                <td>
                    <button class="btn btn-danger" style="padding: 4px 8px; font-size: 12px;" onclick="deleteStock(${index})">删除</button>
                </td>
            `;
            tbody.appendChild(tr);
        });
        try {
            localStorage.setItem('portfolio_stocks', JSON.stringify(stocks));
        } catch (err) {
            console.error('Storage save failed', err);
        }
    }

    function saveStock() {
        const nameEl = document.getElementById('stockName');
        const sharesEl = document.getElementById('currentShares');
        const costEl = document.getElementById('currentCost');
        const targetEl = document.getElementById('targetShares');

        if (!nameEl || !sharesEl || !costEl || !targetEl) return;

        const name = nameEl.value.trim();
        const shares = parseFloat(sharesEl.value);
        const cost = parseFloat(costEl.value);
        const target = parseFloat(targetEl.value);

        if (!name || isNaN(shares) || isNaN(cost) || isNaN(target)) {
            alert('请完整填写所有股票信息字段！');
            return;
        }

        stocks.push({ name, shares, cost, target });
        renderStocks();

        nameEl.value = '';
        sharesEl.value = '';
        costEl.value = '';
        targetEl.value = '';
    }

    function deleteStock(index) {
        if (index >= 0 && index < stocks.length) {
            stocks.splice(index, 1);
            renderStocks();
        }
    }

    // --- 2. Server酱持久化与网页端主动自检逻辑 ---
    window.addEventListener('DOMContentLoaded', () => {
        renderStocks();

        try {
            const savedKey = localStorage.getItem('serverchan_key');
            const keyInput = document.getElementById('sendKeyInput');
            if (savedKey && keyInput) {
                keyInput.value = savedKey;
            }
        } catch (e) {
            console.error('Failed to load serverchan_key', e);
        }
    });

    function saveServerKey() {
        const keyInput = document.getElementById('sendKeyInput');
        if (!keyInput) return;
        const key = keyInput.value.trim();
        if (!key) {
            alert('请输入有效的 Server酱 SendKey！');
            return;
        }
        try {
            localStorage.setItem('serverchan_key', key);
            alert('✅ Server酱配置已成功持久化保存到本地浏览器缓存！');
        } catch (e) {
            alert('❌ 保存失败：浏览器存储受限。');
        }
    }

    async function testServerChanPush() {
        const keyInput = document.getElementById('sendKeyInput');
        const consoleBox = document.getElementById('consoleOutput');
        if (!keyInput || !consoleBox) return;

        const key = keyInput.value.trim();

        if (!key) {
            consoleBox.style.color = 'var(--danger)';
            consoleBox.textContent = '❌ 错误：SendKey 不能为空！请先输入您的 Server酱 Key。';
            return;
        }

        try {
            localStorage.setItem('serverchan_key', key);
        } catch (e) {}

        consoleBox.style.color = 'var(--accent)';
        consoleBox.textContent = '⏳ 正在向 Server酱 官方 API 发送测试请求 (Self-Test)...';

        const title = encodeURIComponent('【网页端自检】资产管理系统测试弹窗');
        const desp = encodeURIComponent('如果您在手机微信上看到了这条消息，说明网页端自检与 Server酱 API 通信链路完全跑通！');
        const url = `https://sctapi.ftqq.com/${key}.send?title=${title}&desp=${desp}`;

        try {
            const response = await fetch(url, { method: 'GET' });
            const data = await response.json();

            if (response.ok && (data.code === 0 || data.errno === 0 || data.pushid)) {
                consoleBox.style.color = 'var(--success)';
                consoleBox.textContent = `✅ 网页端自检成功！API 响应正常。\n服务器返回详情: ${JSON.stringify(data, null, 2)}\n\n👉 请检查您的手机微信，弹窗消息已发送！`;
            } else {
                consoleBox.style.color = 'var(--danger)';
                consoleBox.textContent = `❌ API 返回异常（发送失败）：\n${JSON.stringify(data, null, 2)}\n\n👉 可能原因：SendKey 错误、已过期或当日配额已满。`;
            }
        } catch (error) {
            consoleBox.style.color = 'var(--danger)';
            consoleBox.textContent = `❌ 网络请求失败（Network Error / CORS）：\n${error.message}\n\n👉 可能原因：网络中断、浏览器跨域限制或 API 地址错误。`;
        }
    }
</script>

</body>
</html>
